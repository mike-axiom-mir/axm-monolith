#!/usr/bin/env python3
"""Generate newbie-friendly one-click launchers inside a materialized AXM snapshot.

The launchers start the local-only snapshot server and open OPEN_ME.html, which is the
Capability Lab/front door for the whole captured stack. They do not eagerly execute every
module runtime; capabilities remain dormant/on-demand unless the user or machine selects them.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

SERVER_NAME = "AXM_LOCAL_SERVER.py"
WINDOWS_LAUNCHER = "START_AXM.cmd"
UNIX_LAUNCHER = "START_AXM.sh"
START_NOTE = "START_HERE.txt"


def install_snapshot_launchers(snapshot: Path) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    if not (snapshot / "OPEN_ME.html").exists():
        raise ValueError(f"missing Capability Lab: {snapshot / 'OPEN_ME.html'}")

    source_server = Path(__file__).resolve().parent / "serve_snapshot.py"
    if not source_server.exists():
        raise ValueError(f"missing local snapshot server: {source_server}")

    target_server = snapshot / SERVER_NAME
    shutil.copy2(source_server, target_server)

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

It intentionally does NOT start every module process at once. Modules/capabilities are
activated on demand from the front door. This avoids wasting resources and avoids pretending
that every independently evolved runtime is already safe to execute together.

LOCAL ONLY
==========
The launcher binds to 127.0.0.1 by default. It does not expose this snapshot to the LAN or internet.

TRUTH BOUNDARY
==============
"Present in the monolith" does not mean "verified compatible". The interface preserves the
snapshot's evidence labels, unknowns, candidate connections, and human/machine test results.
'''
    (snapshot / START_NOTE).write_text(note, encoding="utf-8")

    return {
        "installed": True,
        "windows": WINDOWS_LAUNCHER,
        "unix": UNIX_LAUNCHER,
        "server": SERVER_NAME,
        "start_here": START_NOTE,
        "default_url": "http://127.0.0.1:8765/OPEN_ME.html",
        "launch_model": "one front door; modules and capabilities activate on demand",
        "network_boundary": "127.0.0.1 only by default",
    }
