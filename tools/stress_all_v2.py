#!/usr/bin/env python3
"""Adaptive AXM Monolith activate-all stress controller.

Extends the v0.1 stress controller with an evidence-producing pressure governor:

- full-stack stress remains an explicit ON/OFF mode;
- at >= 98% physical RAM used, record the pressure event BEFORE shedding anything;
- ask the open browser stress surface to shed browser runtimes first because that path is
  cheap and reversible;
- if pressure remains above the target after a short grace period, stop stress-spawned
  application runtimes newest-first, one at a time;
- stop shedding when physical RAM used is <= 90%;
- record every shed decision, what was stopped, why, and before/after memory observations;
- retain a deeper last-resort cutoff so the machine still has a recovery path if adaptive
  shedding cannot react quickly enough.

The RAM percentages are whole-system physical-RAM pressure. They are not claims about the
memory owned exclusively by AXM; unrelated applications can contribute to the measured load.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import stress_all as base

PRESSURE_TRIGGER = 0.98
PRESSURE_TARGET = 0.90
BROWSER_GRACE_SECONDS = 2.0
LAST_RESORT_AVAILABLE_RATIO = 0.005
LAST_RESORT_AVAILABLE_BYTES = 128 * 1024 * 1024
SHED_HISTORY_FILE = "SHED_HISTORY.json"


def utilization(memory: dict[str, int | None]) -> float | None:
    total = memory.get("total_bytes")
    used = memory.get("used_bytes")
    if isinstance(total, int) and total > 0 and isinstance(used, int):
        return used / total
    return None


class StressController(base.StressController):
    """v0.2 stress controller with adaptive pressure shedding."""

    def __init__(self, snapshot: Path):
        super().__init__(snapshot)
        self.pressure_state = "normal"
        self.pressure_cycle = 0
        self.pressure_triggered_at: str | None = None
        self.pressure_trigger_monotonic: float | None = None
        self.pressure_trigger_memory: dict[str, int | None] | None = None
        self.browser_shed_requested = False
        self.browser_shed_count = 0
        self.shed_history: list[dict[str, Any]] = []
        self.last_stabilized_at: str | None = None

    def _reset_adaptive_state_locked(self) -> None:
        self.pressure_state = "normal"
        self.pressure_cycle = 0
        self.pressure_triggered_at = None
        self.pressure_trigger_monotonic = None
        self.pressure_trigger_memory = None
        self.browser_shed_requested = False
        self.browser_shed_count = 0
        self.shed_history = []
        self.last_stabilized_at = None

    def start(self) -> dict[str, Any]:
        with self.lock:
            if not self.active:
                self._reset_adaptive_state_locked()
        return super().start()

    def _begin_shedding_locked(self, memory: dict[str, int | None]) -> None:
        self.pressure_cycle += 1
        self.pressure_state = "shedding"
        self.pressure_triggered_at = base.utc_now()
        self.pressure_trigger_monotonic = time.monotonic()
        self.pressure_trigger_memory = dict(memory)
        self.browser_shed_requested = True
        self._event(
            "pressure_trigger",
            cycle=self.pressure_cycle,
            reason="physical RAM reached adaptive stress trigger",
            trigger_percent=PRESSURE_TRIGGER * 100,
            target_percent=PRESSURE_TARGET * 100,
            memory=memory,
            planned_shedding_order=[
                "browser surfaces: newest loaded first",
                "stress-spawned application runtimes: newest started first",
            ],
        )

    def _mark_stabilized_locked(self, memory: dict[str, int | None]) -> None:
        self.pressure_state = "stabilized"
        self.browser_shed_requested = False
        self.last_stabilized_at = base.utc_now()
        self._event(
            "pressure_stabilized",
            cycle=self.pressure_cycle,
            reason="physical RAM returned to or below adaptive target",
            target_percent=PRESSURE_TARGET * 100,
            memory=memory,
            shed_count=len(self.shed_history),
        )

    def _alive_runtime_for_shedding_locked(self) -> dict[str, Any] | None:
        for record in reversed(self.processes):
            proc = record.get("process")
            if not proc or proc.poll() is not None:
                continue
            if record.get("adaptive_shed"):
                continue
            return record
        return None

    def _shed_one_runtime_locked(self, memory_before: dict[str, int | None]) -> bool:
        record = self._alive_runtime_for_shedding_locked()
        if record is None:
            return False

        reason = (
            f"RAM pressure remained above {PRESSURE_TARGET * 100:.0f}% after crossing "
            f"{PRESSURE_TRIGGER * 100:.0f}%; adaptive stress shedding"
        )
        order = len(self.shed_history) + 1
        decision = {
            "order": order,
            "cycle": self.pressure_cycle,
            "kind": "runtime",
            "module": record.get("module"),
            "pid": record.get("pid"),
            "declared_command": record.get("declared_command"),
            "reason": reason,
            "memory_before": memory_before,
            "decided_at_utc": base.utc_now(),
        }

        # Evidence is written BEFORE termination so a failed/abrupt kill still has a reason record.
        self._event("shed_decision", **decision)
        record["adaptive_shed"] = True
        record["adaptive_shed_reason"] = reason
        record["adaptive_shed_order"] = order
        record["adaptive_shed_at_utc"] = decision["decided_at_utc"]

        self._kill_tree(record)
        handle = record.get("log_handle")
        if handle:
            try:
                handle.close()
            except OSError:
                pass
        proc = record.get("process")
        record["returncode"] = proc.poll() if proc else None
        record["process"] = None
        record["log_handle"] = None

        # Give the OS a brief opportunity to reclaim pages before the result sample.
        time.sleep(0.12)
        memory_after = base.system_memory()
        result = {
            **decision,
            "completed_at_utc": base.utc_now(),
            "memory_after": memory_after,
            "utilization_after_percent": (
                round(utilization(memory_after) * 100, 3)
                if utilization(memory_after) is not None
                else None
            ),
        }
        self.shed_history.append(result)
        self._event("shed_runtime", **result)
        return True

    def report_browser_shed(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        with self.lock:
            memory = base.system_memory()
            reason = (
                f"browser surface unloaded because RAM pressure crossed "
                f"{PRESSURE_TRIGGER * 100:.0f}% and target is {PRESSURE_TARGET * 100:.0f}%"
            )
            self.browser_shed_count += 1
            record = {
                "order": len(self.shed_history) + 1,
                "cycle": self.pressure_cycle,
                "kind": "browser-surface",
                "surface": payload.get("surface"),
                "module": payload.get("module"),
                "route": payload.get("route"),
                "reason": reason,
                "completed_at_utc": base.utc_now(),
                "memory_after": memory,
                "utilization_after_percent": (
                    round(utilization(memory) * 100, 3)
                    if utilization(memory) is not None
                    else None
                ),
            }
            self.shed_history.append(record)
            self._event("shed_browser_surface", **record)
            ratio = utilization(memory)
            if self.active and self.pressure_state == "shedding" and ratio is not None and ratio <= PRESSURE_TARGET:
                self._mark_stabilized_locked(memory)
            self._write_state_locked(memory)
            return self.status()

    def _monitor(self) -> None:
        while not self.stop_event.wait(0.5):
            with self.lock:
                if not self.active:
                    return

                memory = base.system_memory()
                used = memory.get("used_bytes")
                if isinstance(used, int):
                    if self.peak_used_bytes is None or used > self.peak_used_bytes:
                        self.peak_used_bytes = used

                total = memory.get("total_bytes")
                available = memory.get("available_bytes")
                ratio = utilization(memory)

                # Deeper last-resort protection. The normal policy should have started shedding
                # much earlier at 98%, but keep a smaller hard floor if pressure rises too fast.
                if isinstance(total, int) and isinstance(available, int):
                    last_resort_floor = max(
                        LAST_RESORT_AVAILABLE_BYTES,
                        int(total * LAST_RESORT_AVAILABLE_RATIO),
                    )
                    if available < last_resort_floor:
                        self.auto_stop_reason = (
                            "adaptive shedding could not preserve last-resort RAM reserve "
                            f"({last_resort_floor} bytes available threshold)"
                        )
                        self._event(
                            "last_resort_stop",
                            reason=self.auto_stop_reason,
                            memory=memory,
                            prior_shedding=self.shed_history,
                        )
                        self._stop_locked(from_monitor=True)
                        return

                if ratio is not None:
                    if ratio >= PRESSURE_TRIGGER and self.pressure_state != "shedding":
                        self._begin_shedding_locked(memory)

                    if self.pressure_state == "shedding":
                        if ratio <= PRESSURE_TARGET:
                            self._mark_stabilized_locked(memory)
                        else:
                            elapsed = (
                                time.monotonic() - self.pressure_trigger_monotonic
                                if self.pressure_trigger_monotonic is not None
                                else BROWSER_GRACE_SECONDS
                            )
                            # Give the browser pool first chance to unload cheap/reversible surfaces.
                            # If it cannot lower pressure quickly enough, shed one runtime per sample.
                            if elapsed >= BROWSER_GRACE_SECONDS:
                                self._shed_one_runtime_locked(memory)
                                memory = base.system_memory()
                                ratio = utilization(memory)
                                if ratio is not None and ratio <= PRESSURE_TARGET:
                                    self._mark_stabilized_locked(memory)

                self._write_state_locked(memory)

    def _public_processes(self) -> list[dict[str, Any]]:
        processes = super()._public_processes()
        for public, record in zip(processes, self.processes):
            public.update({
                "adaptive_shed": bool(record.get("adaptive_shed", False)),
                "adaptive_shed_reason": record.get("adaptive_shed_reason"),
                "adaptive_shed_order": record.get("adaptive_shed_order"),
                "adaptive_shed_at_utc": record.get("adaptive_shed_at_utc"),
            })
        return processes

    def _state_payload(self, current: dict[str, int | None]) -> dict[str, Any]:
        payload = super()._state_payload(current)
        ratio = utilization(current)
        payload.update({
            "schema_version": "0.2-adaptive-pressure",
            "pressure_state": self.pressure_state,
            "pressure_cycle": self.pressure_cycle,
            "pressure_triggered_at_utc": self.pressure_triggered_at,
            "last_stabilized_at_utc": self.last_stabilized_at,
            "current_utilization_percent": round(ratio * 100, 3) if ratio is not None else None,
            "pressure_policy": {
                "trigger_used_percent": PRESSURE_TRIGGER * 100,
                "target_used_percent": PRESSURE_TARGET * 100,
                "browser_grace_seconds": BROWSER_GRACE_SECONDS,
                "shedding_order": [
                    "browser surfaces newest-first",
                    "stress-spawned runtimes newest-first",
                ],
                "last_resort_available_percent": LAST_RESORT_AVAILABLE_RATIO * 100,
                "last_resort_available_bytes": LAST_RESORT_AVAILABLE_BYTES,
            },
            "browser_shed_requested": self.browser_shed_requested,
            "browser_shed_count": self.browser_shed_count,
            "shed_count": len(self.shed_history),
            "last_shed": self.shed_history[-1] if self.shed_history else None,
            "shed_history": self.shed_history,
            "truth_boundary": (
                "RAM pressure is whole-system physical-memory use. At >=98% used, adaptive stress mode "
                "records the trigger then sheds stress-loaded browser surfaces/runtimes until <=90% used. "
                "Other OS/application memory changes can contribute to both the trigger and recovery."
            ),
        })
        return payload

    def _write_state_locked(self, current: dict[str, int | None]) -> None:
        super()._write_state_locked(current)
        base.write_json(
            self.root / SHED_HISTORY_FILE,
            {
                "schema_version": "0.1",
                "trigger_used_percent": PRESSURE_TRIGGER * 100,
                "target_used_percent": PRESSURE_TARGET * 100,
                "pressure_cycle": self.pressure_cycle,
                "pressure_state": self.pressure_state,
                "history": self.shed_history,
                "truth_boundary": "Every entry records stress shedding evidence; RAM observations are whole-system measurements.",
            },
        )


def _patch_stress_html(html: str) -> str:
    """Add adaptive-shedding UI/behavior to the v0.1 stress page."""
    html = html.replace(
        '<div class="card"><div class="big" id="browser">0</div><div class="muted">browser surfaces active</div></div></div>',
        '<div class="card"><div class="big" id="browser">0</div><div class="muted">browser surfaces active</div></div>'
        '<div class="card"><div class="big" id="shed">0</div><div class="muted">items adaptively shed</div></div>'
        '<div class="card"><div class="big" id="pressure">normal</div><div class="muted">pressure governor</div></div></div>',
    )
    html = html.replace(
        'An emergency reserve auto-stops spawned runtimes if available RAM falls below 256 MiB or 2% of physical RAM.',
        'At 98% physical RAM used, the governor first records the pressure event, then sheds browser surfaces and stress-spawned runtimes until RAM returns to 90% used or lower. Every shed item and reason is recorded. A deeper last-resort cutoff remains only if recovery cannot happen fast enough.',
    )
    html = html.replace(
        "f.src=s.route;pool.appendChild(f)",
        "f.src=s.route;f.dataset.surface=s.id||'';f.dataset.module=s.module||'';f.dataset.route=s.route||'';pool.appendChild(f)",
    )
    html = html.replace(
        "const $=id=>document.getElementById(id),pool=$('pool');let active=false,surfaces=[];",
        "const $=id=>document.getElementById(id),pool=$('pool');let active=false,surfaces=[],browserShedBusy=false;",
    )
    adaptive_js = r'''async function adaptiveBrowserShed(s){if(browserShedBusy||!pool.lastElementChild)return;browserShedBusy=true;try{const f=pool.lastElementChild;const info={surface:f.dataset.surface||null,module:f.dataset.module||null,route:f.dataset.route||null};f.remove();$('browser').textContent=String(pool.children.length);await fetch('/api/stress/browser-shed',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(info)})}catch(e){console.warn('browser shed report failed',e)}finally{browserShedBusy=false}}'''
    html = html.replace("async function status(){", adaptive_js + "async function status(){", 1)
    html = html.replace(
        "if(!active&&pool.children.length)browserOff();if(s.auto_stop_reason)",
        "$('shed').textContent=String(s.shed_count??0);$('pressure').textContent=String(s.pressure_state||'normal');if(s.browser_shed_requested&&active&&pool.children.length)adaptiveBrowserShed(s);if(!active&&pool.children.length)browserOff();if(s.auto_stop_reason)",
    )
    html = html.replace(
        '<p><a href="OPEN_ME.html">← Capability Lab</a></p>',
        '<div class="card"><b>Adaptive shedding log</b><div class="muted">The complete machine-readable record is <code>evidence/stress-all/SHED_HISTORY.json</code> and <code>EVENTS.jsonl</code>. The page shows the latest shed item through the live counters above.</div></div><p><a href="OPEN_ME.html">← Capability Lab</a></p>',
    )
    return html


def install_stress_controls(snapshot: Path) -> dict[str, Any]:
    result = base.install_stress_controls(snapshot)
    path = snapshot.resolve() / "STRESS_ALL.html"
    path.write_text(_patch_stress_html(path.read_text(encoding="utf-8")), encoding="utf-8")
    return {
        **result,
        "adaptive_pressure": {
            "trigger_used_percent": PRESSURE_TRIGGER * 100,
            "target_used_percent": PRESSURE_TARGET * 100,
            "browser_first": True,
            "shed_history": "evidence/stress-all/SHED_HISTORY.json",
            "events": "evidence/stress-all/EVENTS.jsonl",
        },
    }
