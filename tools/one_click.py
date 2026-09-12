#!/usr/bin/env python3
"""Generate newbie-friendly one-click launchers inside a materialized AXM snapshot.

The launchers start the local-only snapshot server and open OPEN_ME.html, which is the
Capability Lab/front door for the whole captured stack. Normal launch remains on-demand.
A separate explicit Activate All switch is installed for deliberate RAM/runtime stress tests.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import stress_all_v2 as stress_all

SERVER_NAME = "AXM_LOCAL_SERVER.py"
STRESS_RUNTIME_NAME = "AXM_STRESS_ALL.py"
WINDOWS_LAUNCHER = "START_AXM.cmd"
UNIX_LAUNCHER = "START_AXM.sh"
START_NOTE = "START_HERE.txt"


def _inject_stress_link(snapshot: Path) -> None:
    path = snapshot / "OPEN_ME.html"
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "AXM_STRESS_ALL_LINK_V0_1"
    if marker in text:
        return
    widget = '''<div id="AXM_STRESS_ALL_LINK_V0_1" style="position:fixed;right:16px;bottom:16px;z-index:99999"><a href="STRESS_ALL.html" style="display:block;padding:10px 14px;background:#17100b;border:1px solid #7c5d2f;border-radius:999px;color:#ffd58b;text-decoration:none;font:600 13px system-ui">⚡ Activate All / RAM Stress</a></div>'''
    if "</body>" in text:
        text = text.replace("</body>", widget + "</body>", 1)
    else:
        text += widget
    path.write_text(text, encoding="utf-8")


def install_snapshot_launchers(snapshot: Path) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    if not (snapshot / "OPEN_ME.html").exists():
        raise ValueError(f"missing Capability Lab: {snapshot / 'OPEN_ME.html'}")

    tools_dir = Path(__file__).resolve().parent
    source_server = tools_dir / "serve_snapshot.py"
    source_stress_base = tools_dir / "stress_all.py"
    source_stress_adaptive = tools_dir / "stress_all_v2.py"
    if not source_server.exists():
        raise ValueError(f"missing local snapshot server: {source_server}")
    if not source_stress_base.exists():
        raise ValueError(f"missing base activate-all controller: {source_stress_base}")
    if not source_stress_adaptive.exists():
        raise ValueError(f"missing adaptive activate-all controller: {source_stress_adaptive}")

    shutil.copy2(source_server, snapshot / SERVER_NAME)
    shutil.copy2(source_stress_base, snapshot / "stress_all.py")
    shutil.copy2(source_stress_adaptive, snapshot / "stress_all_v2.py")
    shutil.copy2(source_stress_adaptive, snapshot / STRESS_RUNTIME_NAME)

    stress_controls = stress_all.install_stress_controls(snapshot)
    _inject_stress_link(snapshot)

    windows = r'''@echo off
setlocal
cd /d "%~dp0"
title AXM - The Assembly

echo.
echo ============================================
echo   AXM - THE ASSEMBLY
echo   Starting the complete captured stack...
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo This snapshot needs Python 3.11+ for the local AXM front door.
  echo Nothing was modified.
  pause
  exit /b 1
)

python AXM_LOCAL_SERVER.py --snapshot "%CD%" --port 8765 --open
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo AXM launcher exited with code %EXITCODE%.
  echo If port 8765 is already in use, close the older AXM window and try again.
  pause
)
exit /b %EXITCODE%
'''
    (snapshot / WINDOWS_LAUNCHER).write_text(windows, encoding="utf-8")

    unix = '''#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${AXM_PORT:-8765}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11+ was not found. Set PYTHON_BIN to your Python executable." >&2
  exit 1
fi
echo "AXM - The Assembly"
echo "Starting the complete captured stack at http://127.0.0.1:${PORT}/OPEN_ME.html"
exec "$PYTHON_BIN" AXM_LOCAL_SERVER.py --snapshot "$PWD" --port "$PORT" --open
'''
    unix_path = snapshot / UNIX_LAUNCHER
    unix_path.write_text(unix, encoding="utf-8")
    try:
        unix_path.chmod(unix_path.stat().st_mode | 0o111)
    except OSError:
        pass

    note = '''AXM — THE ASSEMBLY — START HERE

WINDOWS
=======
Double-click:

    START_AXM.cmd

LINUX / macOS
=============
Run:

    ./START_AXM.sh

WHAT THIS STARTS
================
This opens one local AXM front door for the ENTIRE captured public-stack snapshot.
The Capability Lab contains the stack map, capabilities, launchable user-facing surfaces,
AI-native keyboard/input testing, and visual-state evidence tools.

NORMAL MODE
===========
Normal launch intentionally keeps modules/capabilities dormant until they are used. This is
the newbie-friendly and resource-efficient mode.

ACTIVATE ALL / RAM STRESS
=========================
For a deliberate full-pressure experiment, open:

    STRESS_ALL.html

or on Windows use:

    STRESS_ALL_ON.cmd
    STRESS_ALL_OFF.cmd

The stress page is a real ON/OFF switch. ON loads every captured browser surface concurrently
and starts every structurally runnable APPLICATION entrypoint with a bounded adapter. OFF
terminates the process trees started by the switch and unloads the browser pool.

It records whole-machine RAM used, baseline-to-current delta, peak pressure and adaptive
shedding evidence under:

    evidence/stress-all/

ADAPTIVE RAM PRESSURE
=====================
The stress test is allowed to reach 98% physical RAM used so we can learn where the stack
actually becomes expensive. At that point it does NOT immediately throw the whole stress run
away.

Instead it first records the pressure trigger and the planned shedding order, then tries to
recover toward 90% RAM used:

    1. unload browser surfaces newest-first;
    2. if pressure is still above target, stop stress-spawned application runtimes newest-first;
    3. stop shedding when RAM is at or below 90% used.

Every shed item records what was turned off, why, order, and memory observations in:

    evidence/stress-all/SHED_HISTORY.json
    evidence/stress-all/EVENTS.jsonl

This should teach us which pieces disappear first under pressure and how much headroom each
step returns. A much deeper last-resort cutoff remains only if adaptive recovery cannot react
quickly enough.

Tests, build scripts, lint/check commands, and unknown shell commands are NOT included in
Activate All.

LOCAL ONLY
==========
The launcher binds to 127.0.0.1 by default. It does not expose this snapshot to the LAN or internet.

TRUTH BOUNDARY
==============
"Present in the monolith" does not mean "verified compatible". The interface preserves the
snapshot's evidence labels, unknowns, candidate connections, and human/machine test results.
RAM stress numbers are whole-system pressure relative to the pre-ON baseline, so other running
programs can contribute to both the trigger and the measured recovery.
'''
    (snapshot / START_NOTE).write_text(note, encoding="utf-8")

    return {
        "installed": True,
        "windows": WINDOWS_LAUNCHER,
        "unix": UNIX_LAUNCHER,
        "server": SERVER_NAME,
        "stress_runtime": STRESS_RUNTIME_NAME,
        "start_here": START_NOTE,
        "default_url": "http://127.0.0.1:8765/OPEN_ME.html",
        "launch_model": "one front door; modules and capabilities activate on demand",
        "stress_controls": stress_controls,
        "adaptive_ram_policy": {
            "trigger_used_percent": 98,
            "target_used_percent": 90,
            "shed_log": "evidence/stress-all/SHED_HISTORY.json",
        },
        "network_boundary": "127.0.0.1 only by default",
    }
