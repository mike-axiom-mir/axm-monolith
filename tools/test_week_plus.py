#!/usr/bin/env python3
"""AXM Monolith first-test launcher with capability lab and AI-native user-facing testing.

This wraps the existing exact-plan test drive rather than replacing its source/provenance
logic. Build remains deliberate and requires explicit confirmation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import one_click
import test_drive
import user_surface

DEFAULT_WORKSPACE = test_drive.DEFAULT_WORKSPACE


def snapshot_dir(workspace: Path) -> Path:
    return workspace / test_drive.SNAPSHOT_DIR


def enhance_snapshot(workspace: Path) -> dict[str, Any]:
    snapshot = snapshot_dir(workspace)
    if not (snapshot / "STACK_ANALYSIS.json").exists():
        raise test_drive.TestDriveError("snapshot analysis is missing; build the saved plan first")
    surface = user_surface.generate_user_surface(snapshot)
    launchers = one_click.install_snapshot_launchers(snapshot)
    return {**surface, "one_click": launchers}


def build_and_prepare(config: Path, workspace: Path, confirm: bool) -> dict[str, Any]:
    built = test_drive.build_from_saved_plan(config, workspace, confirm=confirm)
    surface = enhance_snapshot(workspace)
    return {**built, "capability_lab": surface}


def lab_status(workspace: Path) -> dict[str, Any]:
    snap = snapshot_dir(workspace)
    return {
        "snapshot": str(snap.resolve()),
        "capability_lab_ready": (snap / "OPEN_ME.html").exists() and (snap / "USER_FACING_SURFACES.json").exists(),
        "surface_registry_ready": (snap / "USER_FACING_SURFACES.json").exists(),
        "ai_input_protocol_ready": (snap / "AI_NATIVE_INPUT_PROTOCOL.json").exists(),
        "one_click_windows_ready": (snap / "START_AXM.cmd").exists(),
        "one_click_unix_ready": (snap / "START_AXM.sh").exists(),
    }


def start_lab(workspace: Path, port: int = 8765) -> dict[str, Any]:
    snap = snapshot_dir(workspace).resolve()
    if not (snap / "USER_FACING_SURFACES.json").exists():
        enhance_snapshot(workspace)
    server = Path(__file__).resolve().parent / "serve_snapshot.py"
    if not server.exists():
        raise test_drive.TestDriveError(f"missing local capability server: {server}")
    kwargs: dict[str, Any] = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(
        [sys.executable, str(server), "--snapshot", str(snap), "--port", str(port), "--open"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )
    time.sleep(0.35)
    if process.poll() is not None:
        raise test_drive.TestDriveError(
            f"capability lab server exited immediately (port {port} may already be in use). "
            f"Run: {sys.executable} {server} --snapshot {snap} --port {port} --open"
        )
    return {
        "started": True,
        "pid": process.pid,
        "url": f"http://127.0.0.1:{port}/OPEN_ME.html",
        "local_only": True,
        "note": "The server executes no source-module CLI commands. It serves captured browser surfaces and records snapshot-bound evidence.",
    }


def status(config: Path, workspace: Path) -> dict[str, Any]:
    return {**test_drive.status(workspace, config), **lab_status(workspace)}


def interactive(config: Path, workspace: Path, port: int) -> int:
    print("AXM Monolith — first test week")
    print("Capability use + AI-native keyboard/visual-state lab is the default user-facing surface after build.")
    print("Every completed snapshot also gets START_AXM.cmd / START_AXM.sh for one-click relaunch.")
    while True:
        try:
            current = status(config, workspace)
            print("\nCurrent state:")
            for key, value in current.items():
                print(f"  {key}: {value}")
            print(
                "\n1) Preflight (no snapshot capture)"
                "\n2) Prepare exact candidate plan"
                "\n3) Build EXACT saved plan + analyze + generate capability lab"
                "\n4) Open capability lab (AI keyboard + visual-state capture)"
                "\n5) Record guided human test results"
                "\n6) Regenerate capability lab + one-click launchers from existing snapshot"
                "\n7) Exit"
            )
            choice = input("Choose: ").strip()
            if choice == "1":
                print(json.dumps(test_drive.preflight(config, workspace), indent=2))
            elif choice == "2":
                print(json.dumps(test_drive.prepare_plan(config, workspace), indent=2))
            elif choice == "3":
                confirm = input("Build the EXACT saved plan? Type BUILD: ").strip() == "BUILD"
                print(json.dumps(build_and_prepare(config, workspace, confirm), indent=2))
            elif choice == "4":
                print(json.dumps(start_lab(workspace, port), indent=2))
            elif choice == "5":
                test_drive.guided_human_session(workspace)
            elif choice == "6":
                print(json.dumps(enhance_snapshot(workspace), indent=2))
            elif choice == "7":
                return 0
            else:
                print("Unknown choice.")
        except (test_drive.TestDriveError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AXM first-test launcher with capability lab")
    p.add_argument("--config", type=Path, default=Path("config/assembly.json"))
    p.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    p.add_argument("--port", type=int, default=8765)
    sub = p.add_subparsers(dest="command")
    sub.add_parser("preflight")
    sub.add_parser("prepare")
    b = sub.add_parser("build")
    b.add_argument("--confirm-build", action="store_true")
    sub.add_parser("lab")
    sub.add_parser("enhance")
    sub.add_parser("status")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if not args.command:
            return interactive(args.config, args.workspace, args.port)
        if args.command == "preflight":
            print(json.dumps(test_drive.preflight(args.config, args.workspace), indent=2))
            return 0
        if args.command == "prepare":
            print(json.dumps(test_drive.prepare_plan(args.config, args.workspace), indent=2))
            return 0
        if args.command == "build":
            print(json.dumps(build_and_prepare(args.config, args.workspace, args.confirm_build), indent=2))
            return 0
        if args.command == "lab":
            print(json.dumps(start_lab(args.workspace, args.port), indent=2))
            return 0
        if args.command == "enhance":
            print(json.dumps(enhance_snapshot(args.workspace), indent=2))
            return 0
        if args.command == "status":
            print(json.dumps(status(args.config, args.workspace), indent=2))
            return 0
        return 2
    except (test_drive.TestDriveError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
