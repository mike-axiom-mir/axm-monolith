#!/usr/bin/env python3
"""AXM Monolith activate-all stress controller.

Purpose: deliberately wake every structurally runnable application entrypoint in one
materialized snapshot, keep them alive together where their runtimes allow it, and measure
whole-machine RAM pressure relative to the pre-test baseline.

This is NOT the normal AXM launch mode. It is an explicit stress mode with an OFF switch.
It never runs discovered test/build/check/lint commands, never reaches outside the pinned
snapshot for source, and records what it attempted and observed beside that snapshot.

Browser surfaces are activated by STRESS_ALL.html as same-origin sandboxed iframes. This
module owns non-browser runtimes and process-tree shutdown.
"""

from __future__ import annotations

import csv
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any

STATE_DIR = Path("evidence/stress-all")
STATE_FILE = "STRESS_STATE.json"
EVENTS_FILE = "EVENTS.jsonl"
MAX_STARTS = 512
ALLOWED_NPM_SCRIPTS = {"start", "dev", "serve", "preview"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _linux_memory() -> dict[str, int] | None:
    path = Path("/proc/meminfo")
    if not path.exists():
        return None
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        m = re.search(r"(\d+)", rest)
        if m:
            values[key] = int(m.group(1)) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    return {"total_bytes": total, "available_bytes": available, "used_bytes": total - available}


def _windows_memory() -> dict[str, int] | None:
    if not sys.platform.startswith("win"):
        return None

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    total = int(status.ullTotalPhys)
    available = int(status.ullAvailPhys)
    return {"total_bytes": total, "available_bytes": available, "used_bytes": total - available}


def _mac_memory() -> dict[str, int] | None:
    if sys.platform != "darwin":
        return None
    try:
        total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
        output = subprocess.check_output(["vm_stat"], text=True)
        page_match = re.search(r"page size of (\d+) bytes", output)
        page_size = int(page_match.group(1)) if page_match else 4096
        pages: dict[str, int] = {}
        for line in output.splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            m = re.search(r"(\d+)", raw)
            if m:
                pages[key.strip()] = int(m.group(1))
        available_pages = sum(
            pages.get(name, 0)
            for name in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable")
        )
        available = min(total, available_pages * page_size)
        return {"total_bytes": total, "available_bytes": available, "used_bytes": total - available}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def system_memory() -> dict[str, int | None]:
    data = _linux_memory() or _windows_memory() or _mac_memory()
    if data:
        return data
    return {"total_bytes": None, "available_bytes": None, "used_bytes": None}


def runnable_plan(snapshot: Path) -> dict[str, Any]:
    """Build an explicit stress plan from analyzed application entrypoints.

    The plan intentionally excludes test/build/check/lint commands. It executes only command
    forms that can be reconstructed without a shell from the inspector's structured fields.
    """
    analysis_path = snapshot / "STACK_ANALYSIS.json"
    if not analysis_path.exists():
        raise ValueError(f"missing {analysis_path}")
    analysis = read_json(analysis_path)
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for module in analysis.get("modules", []):
        if not isinstance(module, dict):
            continue
        name = str(module.get("module") or "").strip()
        if not name:
            continue
        module_root = snapshot / "modules" / name
        for entry in module.get("entrypoints", []):
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("kind") or "").strip()
            path = str(entry.get("path") or "").replace("\\", "/").lstrip("/")
            command = str(entry.get("command") or "").strip()
            reason: str | None = None
            argv: list[str] | None = None

            if kind == "browser" or path.lower().endswith((".html", ".htm")):
                skipped.append({"module": name, "kind": kind, "command": command, "reason": "browser surface is activated by STRESS_ALL.html"})
                continue
            if kind == "python" and path:
                target = module_root / path
                if target.is_file():
                    argv = [sys.executable, str(target)]
                else:
                    reason = "python entrypoint file missing"
            elif kind == "node" and path:
                node = shutil.which("node")
                target = module_root / path
                if not node:
                    reason = "node runtime unavailable"
                elif not target.is_file():
                    reason = "node entrypoint file missing"
                else:
                    argv = [node, str(target)]
            elif kind == "npm-script":
                match = re.fullmatch(r"npm\s+run\s+([A-Za-z0-9:_-]+)", command)
                script = match.group(1) if match else ""
                npm = shutil.which("npm") or shutil.which("npm.cmd")
                if script not in ALLOWED_NPM_SCRIPTS:
                    reason = "npm script is not an application run script allowed in stress mode"
                elif not npm:
                    reason = "npm runtime unavailable"
                else:
                    argv = [npm, "run", script]
            elif kind == "python-script":
                reason = "packaged console-script entrypoint is not executed until an install/runtime adapter proves it"
            else:
                reason = "entrypoint kind has no shell-free stress adapter"

            if argv:
                key = (name, "\0".join(argv))
                if key not in seen:
                    seen.add(key)
                    candidates.append({
                        "module": name,
                        "repository": module.get("repository"),
                        "kind": kind,
                        "cwd": str(module_root),
                        "argv": argv,
                        "declared_command": command,
                        "evidence": entry.get("evidence"),
                    })
            else:
                skipped.append({"module": name, "kind": kind, "command": command, "reason": reason or "not runnable"})

    if len(candidates) > MAX_STARTS:
        skipped.extend({**item, "reason": "beyond MAX_STARTS stress cap"} for item in candidates[MAX_STARTS:])
        candidates = candidates[:MAX_STARTS]

    return {
        "schema_version": "0.1",
        "generated_at_utc": utc_now(),
        "runnable_count": len(candidates),
        "runnable": candidates,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "truth_boundary": "application entrypoints only; discovered tests/build/check/lint commands are not executed by activate-all stress mode",
    }


class StressController:
    def __init__(self, snapshot: Path):
        self.snapshot = snapshot.resolve()
        self.root = self.snapshot / STATE_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs = self.root / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.processes: list[dict[str, Any]] = []
        self.active = False
        self.started_at: str | None = None
        self.stopped_at: str | None = None
        self.baseline = system_memory()
        self.peak_used_bytes: int | None = self.baseline.get("used_bytes")  # type: ignore[assignment]
        self.auto_stop_reason: str | None = None
        self.monitor_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.plan: dict[str, Any] | None = None

    def _event(self, event: str, **data: Any) -> None:
        payload = {"at_utc": utc_now(), "event": event, **data}
        with (self.root / EVENTS_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _start_process(self, item: dict[str, Any], index: int) -> dict[str, Any]:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(item["module"]))[:80] or f"module-{index}"
        log_path = self.logs / f"{index:03d}_{safe}.log"
        log_handle = log_path.open("ab", buffering=0)
        kwargs: dict[str, Any] = {
            "cwd": item["cwd"],
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
            "env": {
                **os.environ,
                "AXM_STRESS_ALL": "1",
                "AXM_MONOLITH_SNAPSHOT": str(self.snapshot),
            },
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(item["argv"], **kwargs)
            return {**item, "pid": proc.pid, "process": proc, "log": str(log_path.relative_to(self.snapshot)), "started": True, "error": None, "log_handle": log_handle}
        except Exception as exc:
            log_handle.close()
            return {**item, "pid": None, "process": None, "log": str(log_path.relative_to(self.snapshot)), "started": False, "error": str(exc), "log_handle": None}

    def _kill_tree(self, record: dict[str, Any]) -> None:
        proc = record.get("process")
        pid = record.get("pid")
        if not proc or not pid:
            return
        if proc.poll() is not None:
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                try:
                    proc.wait(timeout=2.5)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except Exception:
                pass

    def _monitor(self) -> None:
        while not self.stop_event.wait(0.5):
            with self.lock:
                if not self.active:
                    return
                mem = system_memory()
                used = mem.get("used_bytes")
                if isinstance(used, int):
                    if self.peak_used_bytes is None or used > self.peak_used_bytes:
                        self.peak_used_bytes = used
                total = mem.get("total_bytes")
                available = mem.get("available_bytes")
                if isinstance(total, int) and isinstance(available, int):
                    emergency_floor = max(256 * 1024 * 1024, int(total * 0.02))
                    if available < emergency_floor:
                        self.auto_stop_reason = f"available RAM dropped below emergency reserve ({emergency_floor} bytes)"
                        self._event("automatic_stop", reason=self.auto_stop_reason, memory=mem)
                        # Avoid joining our own monitor thread.
                        self._stop_locked(from_monitor=True)
                        return
                self._write_state_locked(mem)

    def start(self) -> dict[str, Any]:
        with self.lock:
            if self.active:
                return self.status()
            self.plan = runnable_plan(self.snapshot)
            self.baseline = system_memory()
            baseline_used = self.baseline.get("used_bytes")
            self.peak_used_bytes = baseline_used if isinstance(baseline_used, int) else None
            self.started_at = utc_now()
            self.stopped_at = None
            self.auto_stop_reason = None
            self.stop_event.clear()
            self.processes = []
            self.active = True
            self._event("stress_on", runnable_count=self.plan["runnable_count"], baseline=self.baseline)
            for index, item in enumerate(self.plan["runnable"], start=1):
                record = self._start_process(item, index)
                self.processes.append(record)
                self._event("process_start", module=item["module"], pid=record.get("pid"), started=record.get("started"), error=record.get("error"), argv=item["argv"])
                time.sleep(0.03)
            self.monitor_thread = threading.Thread(target=self._monitor, name="axm-stress-all-monitor", daemon=True)
            self.monitor_thread.start()
            self._write_state_locked(system_memory())
            return self.status()

    def _stop_locked(self, from_monitor: bool = False) -> None:
        if not self.active and not self.processes:
            return
        self.active = False
        self.stop_event.set()
        for record in reversed(self.processes):
            self._kill_tree(record)
            handle = record.get("log_handle")
            if handle:
                try:
                    handle.close()
                except OSError:
                    pass
            record["returncode"] = record.get("process").poll() if record.get("process") else None
            record["process"] = None
            record["log_handle"] = None
        self.stopped_at = utc_now()
        self._event("stress_off", auto_stop_reason=self.auto_stop_reason)
        self._write_state_locked(system_memory())
        if not from_monitor and self.monitor_thread and self.monitor_thread.is_alive():
            thread = self.monitor_thread
            self.monitor_thread = None
            self.lock.release()
            try:
                thread.join(timeout=2.0)
            finally:
                self.lock.acquire()

    def stop(self) -> dict[str, Any]:
        with self.lock:
            self._stop_locked()
            return self.status()

    def _public_processes(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for record in self.processes:
            proc = record.get("process")
            returncode = proc.poll() if proc else record.get("returncode")
            result.append({
                "module": record.get("module"),
                "kind": record.get("kind"),
                "pid": record.get("pid"),
                "started": record.get("started"),
                "alive": bool(proc and returncode is None),
                "returncode": returncode,
                "error": record.get("error"),
                "log": record.get("log"),
                "declared_command": record.get("declared_command"),
            })
        return result

    def _state_payload(self, current: dict[str, int | None]) -> dict[str, Any]:
        baseline_used = self.baseline.get("used_bytes")
        current_used = current.get("used_bytes")
        peak = self.peak_used_bytes
        delta = current_used - baseline_used if isinstance(current_used, int) and isinstance(baseline_used, int) else None
        peak_delta = peak - baseline_used if isinstance(peak, int) and isinstance(baseline_used, int) else None
        processes = self._public_processes()
        return {
            "schema_version": "0.1",
            "active": self.active,
            "started_at_utc": self.started_at,
            "stopped_at_utc": self.stopped_at,
            "auto_stop_reason": self.auto_stop_reason,
            "baseline_memory": self.baseline,
            "current_memory": current,
            "current_used_delta_bytes": delta,
            "peak_used_bytes": peak,
            "peak_used_delta_bytes": peak_delta,
            "processes_started": sum(1 for p in processes if p["started"]),
            "processes_alive": sum(1 for p in processes if p["alive"]),
            "processes": processes,
            "runnable_count": (self.plan or {}).get("runnable_count", 0),
            "skipped_count": (self.plan or {}).get("skipped_count", 0),
            "browser_surfaces": "activated by STRESS_ALL.html while switch is ON",
            "truth_boundary": "RAM pressure is whole-system used-memory delta from the pre-stress baseline; unrelated OS/application changes can contribute to that delta",
        }

    def _write_state_locked(self, current: dict[str, int | None]) -> None:
        write_json(self.root / STATE_FILE, self._state_payload(current))
        if self.plan is not None:
            write_json(self.root / "RUNNABLE_PLAN.json", self.plan)

    def status(self) -> dict[str, Any]:
        with self.lock:
            current = system_memory()
            used = current.get("used_bytes")
            if self.active and isinstance(used, int):
                if self.peak_used_bytes is None or used > self.peak_used_bytes:
                    self.peak_used_bytes = used
            payload = self._state_payload(current)
            self._write_state_locked(current)
            return payload


def stress_html() -> str:
    return r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AXM — Activate All Stress</title><style>:root{--bg:#080b11;--panel:#121824;--line:#29364d;--text:#edf5ff;--muted:#98a8bd;--on:#78e6a2;--off:#ff9292;--accent:#79c8ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,Segoe UI,sans-serif}main{max-width:1000px;margin:auto;padding:30px}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0}.switch{display:flex;align-items:center;gap:18px}.switch button{font-size:24px;font-weight:800;padding:16px 28px;border:0;border-radius:14px;cursor:pointer}.on{background:var(--on)}.off{background:var(--off)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.big{font-size:28px;font-weight:800;color:var(--accent)}.muted{color:var(--muted)}progress{width:100%;height:22px}code{color:#bfe3ff}.hiddenPool{position:fixed;left:-20000px;top:-20000px;width:1024px;height:768px;overflow:hidden}.hiddenPool iframe{width:1024px;height:768px;border:0}</style></head><body><main><h1>AXM — Activate All</h1><p class="muted">Deliberate stress mode. ON starts every structurally runnable application entrypoint and loads every browser surface concurrently. OFF terminates the spawned process trees and unloads the browser pool.</p><div class="card switch"><button id="toggle" class="on">TURN ON</button><div><b id="state">OFF</b><div class="muted">Keep this page open during the stress run.</div></div></div><div class="grid"><div class="card"><div class="big" id="used">—</div><div class="muted">system RAM used</div></div><div class="card"><div class="big" id="delta">—</div><div class="muted">delta vs baseline</div></div><div class="card"><div class="big" id="peak">—</div><div class="muted">peak delta</div></div><div class="card"><div class="big" id="procs">—</div><div class="muted">runtime processes alive</div></div><div class="card"><div class="big" id="browser">0</div><div class="muted">browser surfaces active</div></div></div><div class="card"><b>RAM pressure</b><progress id="ram" value="0" max="100"></progress><div id="memline" class="muted"></div></div><div class="card"><b>Truth boundary</b><div class="muted">The RAM number is whole-system pressure measured against the pre-ON baseline, so other programs can affect the delta. Stress mode executes application run entrypoints only; test/build/check/lint commands remain excluded. An emergency reserve auto-stops spawned runtimes if available RAM falls below 256 MiB or 2% of physical RAM.</div></div><p><a href="OPEN_ME.html">← Capability Lab</a></p></main><div id="pool" class="hiddenPool"></div><script>const $=id=>document.getElementById(id),pool=$('pool');let active=false,surfaces=[];const fmt=n=>Number.isFinite(n)?(n/1073741824).toFixed(2)+' GiB':'—';async function loadRegistry(){try{const r=await fetch('USER_FACING_SURFACES.json',{cache:'no-store'});const j=await r.json();surfaces=j.surfaces||[]}catch(e){surfaces=[]}}function browserOn(){pool.innerHTML='';for(const s of surfaces){const f=document.createElement('iframe');f.sandbox='allow-scripts allow-same-origin allow-forms allow-pointer-lock allow-modals';f.src=s.route;pool.appendChild(f)}$('browser').textContent=String(pool.children.length)}function browserOff(){pool.innerHTML='';$('browser').textContent='0'}async function post(path){const r=await fetch(path,{method:'POST',headers:{'content-type':'application/json'},body:'{}'});if(!r.ok)throw new Error(await r.text());return r.json()}async function status(){try{const r=await fetch('/api/stress/status',{cache:'no-store'});const s=await r.json();active=!!s.active;$('state').textContent=active?'ON':'OFF';$('toggle').textContent=active?'TURN OFF':'TURN ON';$('toggle').className=active?'off':'on';const m=s.current_memory||{};$('used').textContent=fmt(m.used_bytes);$('delta').textContent=fmt(s.current_used_delta_bytes);$('peak').textContent=fmt(s.peak_used_delta_bytes);$('procs').textContent=(s.processes_alive??0)+' / '+(s.processes_started??0);if(m.total_bytes&&m.used_bytes!=null){$('ram').value=100*m.used_bytes/m.total_bytes;$('memline').textContent=(100*m.used_bytes/m.total_bytes).toFixed(1)+'% used · '+fmt(m.available_bytes)+' available'}if(!active&&pool.children.length)browserOff();if(s.auto_stop_reason)$('memline').textContent+=' · AUTO STOP: '+s.auto_stop_reason}catch(e){$('state').textContent='SERVER OFFLINE'}}$('toggle').onclick=async()=>{try{if(active){browserOff();await post('/api/stress/stop')}else{await loadRegistry();await post('/api/stress/start');browserOn()}await status()}catch(e){alert(String(e))}};loadRegistry().then(status);setInterval(status,1000);addEventListener('beforeunload',()=>{if(active)navigator.sendBeacon('/api/stress/stop',new Blob(['{}'],{type:'application/json'}))});</script></body></html>'''


def install_stress_controls(snapshot: Path) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    if not (snapshot / "STACK_ANALYSIS.json").exists():
        raise ValueError("stress controls require STACK_ANALYSIS.json")
    (snapshot / "STRESS_ALL.html").write_text(stress_html(), encoding="utf-8")

    windows_on = r'''@echo off
powershell -NoProfile -Command "Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/stress/start -ContentType application/json -Body '{}' | ConvertTo-Json -Depth 4"
if errorlevel 1 echo Start AXM first with START_AXM.cmd, then retry.
pause
'''
    windows_off = r'''@echo off
powershell -NoProfile -Command "Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/stress/stop -ContentType application/json -Body '{}' | ConvertTo-Json -Depth 4"
if errorlevel 1 echo AXM local server was not reachable.
pause
'''
    (snapshot / "STRESS_ALL_ON.cmd").write_text(windows_on, encoding="utf-8")
    (snapshot / "STRESS_ALL_OFF.cmd").write_text(windows_off, encoding="utf-8")

    unix_on = """#!/usr/bin/env sh\nset -eu\ncurl -fsS -X POST -H 'content-type: application/json' -d '{}' http://127.0.0.1:8765/api/stress/start\necho\n"""
    unix_off = """#!/usr/bin/env sh\nset -eu\ncurl -fsS -X POST -H 'content-type: application/json' -d '{}' http://127.0.0.1:8765/api/stress/stop\necho\n"""
    for name, body in (("STRESS_ALL_ON.sh", unix_on), ("STRESS_ALL_OFF.sh", unix_off)):
        path = snapshot / name
        path.write_text(body, encoding="utf-8")
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            pass

    return {
        "installed": True,
        "interface": "STRESS_ALL.html",
        "windows_on": "STRESS_ALL_ON.cmd",
        "windows_off": "STRESS_ALL_OFF.cmd",
        "unix_on": "STRESS_ALL_ON.sh",
        "unix_off": "STRESS_ALL_OFF.sh",
        "state": "evidence/stress-all/STRESS_STATE.json",
        "truth_boundary": "stress mode starts application entrypoints only; browser surfaces are activated by the stress page; tests/build/check/lint remain excluded",
    }


if __name__ == "__main__":
    raise SystemExit("stress_all.py is a library/controller; use the generated STRESS_ALL.html or local server API")
