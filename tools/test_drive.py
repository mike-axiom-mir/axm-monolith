#!/usr/bin/env python3
"""Guided first-test workflow for AXM Monolith.

This script exists for the human test day. It deliberately separates:

  preflight -> prepare exact plan -> build that exact plan -> open dashboard -> record human evidence

It never releases the repository build hold itself. The hold must already be deliberately
released in config/assembly.json. It never executes discovered module tests automatically.
It never writes into source module directories; human results live beside the generated build.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
import webbrowser
from typing import Any

import assemble

DEFAULT_WORKSPACE = Path("../axm-monolith-test")
PLAN_NAME = "CANDIDATE_PLAN.json"
PLAN_SUMMARY = "PLAN_SUMMARY.md"
SNAPSHOT_DIR = "snapshot"
RESULTS_NAME = "HUMAN_TEST_RESULTS.json"


class TestDriveError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TestDriveError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TestDriveError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plan_digest(plan: dict[str, Any]) -> str:
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_saved_plan(plan: dict[str, Any], config: dict[str, Any]) -> None:
    owner = str(config["owner"]).lower()
    if (plan.get("selection") or {}).get("visibility") != "public-only":
        raise TestDriveError("saved plan does not preserve the public-only selection boundary")
    modules = plan.get("modules")
    if not isinstance(modules, list) or not modules:
        raise TestDriveError("saved plan has no modules")

    excluded = assemble.exclusion_map(config)
    seen: set[str] = set()
    for module in modules:
        if not isinstance(module, dict):
            raise TestDriveError("saved plan contains a non-object module")
        full = str(module.get("full_name", ""))
        name = str(module.get("name", ""))
        commit = str(module.get("commit", ""))
        clone_url = str(module.get("clone_url", ""))
        if not full.startswith(owner + "/"):
            raise TestDriveError(f"plan module outside configured owner: {full}")
        if full.lower() in excluded:
            raise TestDriveError(f"plan contains excluded module: {full}")
        if full.lower() in seen:
            raise TestDriveError(f"duplicate module in plan: {full}")
        seen.add(full.lower())
        if not name:
            raise TestDriveError(f"plan module missing name: {full}")
        if len(commit) != 40 or any(c not in "0123456789abcdefABCDEF" for c in commit):
            raise TestDriveError(f"plan module has invalid commit SHA: {full}")
        if clone_url != f"https://github.com/{full}.git":
            raise TestDriveError(f"plan module has unexpected clone URL: {full}")


def preflight(config_path: Path, workspace: Path) -> dict[str, Any]:
    config = assemble.load_config(config_path)
    git_version = assemble.run_git(["--version"])
    workspace_parent = workspace.resolve().parent
    workspace_parent.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(workspace_parent)
    report = {
        "checked_at_utc": utc_now(),
        "python": sys.version.split()[0],
        "git": git_version,
        "workspace": str(workspace.resolve()),
        "free_disk_bytes": usage.free,
        "free_disk_gib": round(usage.free / (1024 ** 3), 2),
        "build_enabled": bool(config.get("build_enabled", False)),
        "hold_reason": config.get("hold_reason"),
        "selection_visibility": (config.get("selection") or {}).get("visibility"),
        "excluded_repositories": config.get("excluded_repositories", []),
        "automatic_module_test_execution": False,
    }
    return report


def prepare_plan(config_path: Path, workspace: Path) -> dict[str, Any]:
    config = assemble.load_config(config_path)
    if not bool(config.get("build_enabled", False)):
        raise TestDriveError(
            "the monolith hold is still active. Finish/reconcile the growth batch and deliberately release build_enabled before preparing the snapshot plan"
        )

    workspace.mkdir(parents=True, exist_ok=True)
    plan_path = workspace / PLAN_NAME
    snapshot = workspace / SNAPSHOT_DIR
    if snapshot.exists() and any(snapshot.iterdir()):
        raise TestDriveError(f"workspace already contains a materialized snapshot: {snapshot}")

    plan = assemble.resolve_plan(config)
    validate_saved_plan(plan, config)
    digest = plan_digest(plan)
    plan["test_drive"] = {
        "prepared_at_utc": utc_now(),
        "plan_sha256_before_test_drive_metadata": digest,
        "status": "candidate_plan_not_built",
        "instruction": "Review this exact plan. Building later must use this file rather than refreshing repository heads.",
    }
    write_json(plan_path, plan)

    eligible = [m["full_name"] for m in plan["modules"]]
    rejected = plan.get("excluded_or_rejected", [])
    lines = [
        "# AXM Monolith Candidate Plan",
        "",
        "This is a point-in-time candidate plan. It has **not** materialized source repositories.",
        "",
        f"- Prepared: `{plan['test_drive']['prepared_at_utc']}`",
        f"- Modules: **{len(eligible)}**",
        f"- Plan file: `{PLAN_NAME}`",
        "",
        "## Included",
        "",
    ]
    lines += [f"- `{name}`" for name in eligible]
    lines += ["", "## Excluded / rejected", ""]
    lines += [f"- `{item.get('repository')}` — {item.get('reason')}" for item in rejected] or ["- none reported"]
    lines += [
        "",
        "## Before building",
        "",
        "Confirm this list represents the AXM public identity set you intend to test. If not, change `config/assembly.json` and prepare a new plan instead of editing this plan by hand.",
        "",
    ]
    (workspace / PLAN_SUMMARY).write_text("\n".join(lines), encoding="utf-8")
    return {"plan_path": str(plan_path), "summary_path": str(workspace / PLAN_SUMMARY), "module_count": len(eligible)}


def build_from_saved_plan(config_path: Path, workspace: Path, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise TestDriveError("explicit --confirm-build is required")
    config = assemble.load_config(config_path)
    if not bool(config.get("build_enabled", False)):
        raise TestDriveError("build hold is active; refusing materialization")

    plan_path = workspace / PLAN_NAME
    plan = read_json(plan_path)
    validate_saved_plan(plan, config)
    snapshot = workspace / SNAPSHOT_DIR
    assemble.safe_output_dir(snapshot)
    modules_dir = snapshot / "modules"
    modules_dir.mkdir()

    # The exact saved plan becomes the lock. No head refresh happens here.
    write_json(snapshot / "axm-stack.lock.json", plan)
    strip_git = bool((config.get("output") or {}).get("strip_nested_git", True))
    materialized = [assemble.materialize_module(m, modules_dir, strip_git=strip_git) for m in plan["modules"]]

    manifest: dict[str, Any] = {
        "schema_version": "0.3-test-drive",
        "created_at_utc": utc_now(),
        "source_lock": "axm-stack.lock.json",
        "candidate_plan_source": f"../{PLAN_NAME}",
        "candidate_plan_sha256": plan_digest(plan),
        "module_count": len(materialized),
        "modules": materialized,
        "namespace_rule": "source repositories remain isolated under modules/<repo>; cross-module links require explicit analysis/evidence",
        "source_mutation": "none",
        "automatic_module_test_execution": False,
    }
    write_json(snapshot / "MONOLITH_MANIFEST.json", manifest)

    inventory = [
        "# AXM Monolith Inventory",
        "",
        f"Modules: {len(materialized)}",
        "",
        "Built from the saved candidate plan. Repository heads were not refreshed during materialization.",
        "",
    ]
    inventory += [f"- `{item['repository']}` @ `{item['commit']}` → `{item['path']}`" for item in materialized]
    inventory += ["", "No source repository was modified.", ""]
    (snapshot / "INVENTORY.md").write_text("\n".join(inventory), encoding="utf-8")

    analysis = assemble.run_stack_analysis(snapshot)
    manifest["analysis"] = analysis
    write_json(snapshot / "MONOLITH_MANIFEST.json", manifest)

    return {
        "snapshot": str(snapshot),
        "module_count": len(materialized),
        "dashboard": str(snapshot / "OPEN_ME.html"),
        "human_queue": str(snapshot / "HUMAN_TEST_QUEUE.json"),
        "automated_queue": str(snapshot / "AUTOMATED_TEST_QUEUE.json"),
        "analysis": analysis,
    }


def open_dashboard(workspace: Path) -> str:
    dashboard = (workspace / SNAPSHOT_DIR / "OPEN_ME.html").resolve()
    if not dashboard.exists():
        raise TestDriveError(f"dashboard not found: {dashboard}; build the saved plan first")
    webbrowser.open(dashboard.as_uri())
    return str(dashboard)


def load_human_results(snapshot: Path) -> dict[str, Any]:
    path = snapshot / RESULTS_NAME
    if path.exists():
        data = read_json(path)
        if isinstance(data, dict):
            return data
    return {"schema_version": "0.1", "snapshot": str(snapshot.resolve()), "started_at_utc": utc_now(), "results": []}


def save_human_result(snapshot: Path, result: dict[str, Any]) -> None:
    data = load_human_results(snapshot)
    results = data.setdefault("results", [])
    # One current record per module; old record is retained in history.
    previous = [r for r in results if r.get("module") == result.get("module")]
    if previous:
        result["previous_records"] = previous
        data["results"] = [r for r in results if r.get("module") != result.get("module")]
    data["results"].append(result)
    data["updated_at_utc"] = utc_now()
    write_json(snapshot / RESULTS_NAME, data)


def guided_human_session(workspace: Path) -> None:
    snapshot = workspace / SNAPSHOT_DIR
    queue_path = snapshot / "HUMAN_TEST_QUEUE.json"
    payload = read_json(queue_path)
    queue = payload.get("queue", []) if isinstance(payload, dict) else []
    if not queue:
        print("No human-validation items were generated for this snapshot.")
        return

    existing = load_human_results(snapshot)
    done = {r.get("module") for r in existing.get("results", [])}
    pending = [item for item in queue if item.get("module") not in done]
    if not pending:
        print(f"All {len(queue)} current human-test modules already have a recorded result in {snapshot / RESULTS_NAME}")
        return

    print(f"AXM human test queue: {len(pending)} pending of {len(queue)} total")
    print("Statuses: p=pass, f=fail, u=uncertain, s=skip, q=quit")
    for index, item in enumerate(pending, start=1):
        print("\n" + "=" * 72)
        print(f"[{index}/{len(pending)}] {item.get('module')}  priority={item.get('priority')}")
        print(f"source: {item.get('repository')}")
        for task in item.get("tasks", []):
            print(f"  - {task}")
        if item.get("entrypoints"):
            print("Suggested entrypoints (NOT run automatically):")
            for entry in item["entrypoints"]:
                print(f"  {entry.get('command')}")
        while True:
            choice = input("Result [p/f/u/s/q]: ").strip().lower()
            if choice in {"p", "f", "u", "s", "q"}:
                break
        if choice == "q":
            print("Stopped. Existing results were preserved.")
            return
        status = {"p": "pass", "f": "fail", "u": "uncertain", "s": "skipped"}[choice]
        notes = input("Notes (optional): ").strip()
        save_human_result(snapshot, {
            "module": item.get("module"),
            "repository": item.get("repository"),
            "status": status,
            "notes": notes,
            "recorded_at_utc": utc_now(),
            "truth_boundary": "human observation recorded for this exact snapshot; it does not automatically generalize to later repository revisions",
        })
        print(f"Recorded {status}.")


def status(workspace: Path, config_path: Path) -> dict[str, Any]:
    config = assemble.load_config(config_path)
    plan_path = workspace / PLAN_NAME
    snapshot = workspace / SNAPSHOT_DIR
    results_path = snapshot / RESULTS_NAME
    result_count = 0
    if results_path.exists():
        payload = read_json(results_path)
        if isinstance(payload, dict):
            result_count = len(payload.get("results", []))
    return {
        "build_enabled": bool(config.get("build_enabled", False)),
        "plan_prepared": plan_path.exists(),
        "snapshot_built": (snapshot / "MONOLITH_MANIFEST.json").exists(),
        "dashboard_ready": (snapshot / "OPEN_ME.html").exists(),
        "human_results_recorded": result_count,
        "workspace": str(workspace.resolve()),
    }


def interactive_menu(config_path: Path, workspace: Path) -> int:
    print("AXM Monolith — guided test drive")
    while True:
        state = status(workspace, config_path)
        print("\nCurrent state:")
        for key, value in state.items():
            print(f"  {key}: {value}")
        print("\n1) Preflight (no network snapshot)\n2) Prepare exact candidate plan\n3) Build saved plan + analyze\n4) Open dashboard\n5) Record human test results\n6) Exit")
        choice = input("Choose: ").strip()
        try:
            if choice == "1": print(json.dumps(preflight(config_path, workspace), indent=2))
            elif choice == "2": print(json.dumps(prepare_plan(config_path, workspace), indent=2))
            elif choice == "3":
                confirm = input("Build the EXACT saved plan? Type BUILD: ").strip() == "BUILD"
                print(json.dumps(build_from_saved_plan(config_path, workspace, confirm=confirm), indent=2))
            elif choice == "4": print(f"Opened: {open_dashboard(workspace)}")
            elif choice == "5": guided_human_session(workspace)
            elif choice == "6": return 0
            else: print("Unknown choice.")
        except (TestDriveError, assemble.AssemblyError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Guided AXM Monolith first-test workflow")
    p.add_argument("--config", default="config/assembly.json")
    p.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    sub = p.add_subparsers(dest="command")
    sub.add_parser("preflight")
    sub.add_parser("prepare")
    b = sub.add_parser("build")
    b.add_argument("--confirm-build", action="store_true")
    sub.add_parser("open")
    sub.add_parser("human")
    sub.add_parser("status")
    return p


def main() -> int:
    args = parser().parse_args()
    config_path = Path(args.config)
    workspace = Path(args.workspace)
    try:
        if args.command is None:
            return interactive_menu(config_path, workspace)
        if args.command == "preflight":
            print(json.dumps(preflight(config_path, workspace), indent=2, sort_keys=True))
        elif args.command == "prepare":
            print(json.dumps(prepare_plan(config_path, workspace), indent=2, sort_keys=True))
        elif args.command == "build":
            print(json.dumps(build_from_saved_plan(config_path, workspace, confirm=args.confirm_build), indent=2, sort_keys=True))
        elif args.command == "open":
            print(open_dashboard(workspace))
        elif args.command == "human":
            guided_human_session(workspace)
        elif args.command == "status":
            print(json.dumps(status(workspace, config_path), indent=2, sort_keys=True))
        else:
            raise TestDriveError(f"unknown command: {args.command}")
        return 0
    except (TestDriveError, assemble.AssemblyError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
