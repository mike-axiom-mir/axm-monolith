#!/usr/bin/env python3
"""Execute and review the bounded Blackline Relay 3D workflow.

The workflow adapter binds three existing repository responsibilities without pretending
that every catalogue capability is callable: Universal Creation provides the visual recipe,
Game Assets provides geometry/material/GLB machinery, and Ghost Studio supplies the exact
consumer charter plus a structural acceptance review. Rejected attempts remain evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from typing import Any

import ghost_studio_asset_trial
import ghost_studio_reference_kit


WORKFLOW_ID = "ghost-studio.blackline-3d.v0.4"
SCHEMA = "axm.monolith.workflow-execution/v0.2"
ROLE_ASSETS = (
    "blackline-energy-core",
    "blackline-relay-beacon",
    "blackline-runner-drone",
)


class WorkflowError(RuntimeError):
    pass


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_glb(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "MISSING_GLB"
    data = path.read_bytes()
    if len(data) < 12:
        return False, "TRUNCATED_GLB"
    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(data):
        return False, "INVALID_GLB_2"
    return True, "PASS"


def review_attempt(snapshot: str | Path, attempt: str | Path, *, reference_required: bool) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    candidate = Path(attempt).resolve()
    checks: list[dict[str, Any]] = []

    charter = root / "modules" / "axm-ghost-studio" / "GAME_CHARTER.md"
    charter_ok = charter.is_file() and "Blackline Relay" in charter.read_text(encoding="utf-8", errors="replace")
    checks.append({"check": "ghost-studio-charter", "status": "PASS" if charter_ok else "WRONG_CONSUMER_CHARTER"})

    trial_receipt_path = candidate / "role-assets" / "TRIAL_RECEIPT.json"
    try:
        trial_receipt = json.loads(trial_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        trial_receipt = {}
    checks.append({
        "check": "role-asset-receipt",
        "status": "PASS" if trial_receipt.get("status") == "EXECUTED_AND_STRUCTURALLY_VERIFIED" else "INVALID_TRIAL_RECEIPT",
    })
    for asset in ROLE_ASSETS:
        path = candidate / "role-assets" / "deliveries" / f"{asset}.glb"
        valid, status = _valid_glb(path)
        checks.append({"check": f"role-glb:{asset}", "status": status, "path": path.relative_to(candidate).as_posix(), "sha256": _sha256(path) if valid else None})

    kit_receipt: dict[str, Any] = {}
    if reference_required:
        kit_receipt_path = candidate / "environment-kit" / "KIT_RECEIPT.json"
        try:
            kit_receipt = json.loads(kit_receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            kit_receipt = {}
        kit_ok = kit_receipt.get("status") == "EXECUTED_AND_STRUCTURALLY_VERIFIED"
        checks.append({"check": "environment-kit-receipt", "status": "PASS" if kit_ok else "INVALID_KIT_RECEIPT"})
        assets = ((kit_receipt.get("execution") or {}).get("assets") or {}) if isinstance(kit_receipt, dict) else {}
        for asset_id, record in sorted(assets.items()):
            relative = ((record or {}).get("delivery") or {}).get("path")
            path = candidate / "environment-kit" / "assets" / str(asset_id) / str(relative or "")
            valid, status = _valid_glb(path)
            checks.append({"check": f"environment-glb:{asset_id}", "status": status, "path": path.relative_to(candidate).as_posix(), "sha256": _sha256(path) if valid else None})

    failures = [check for check in checks if check["status"] != "PASS"]
    delivery_count = len(ROLE_ASSETS) + int(((kit_receipt.get("execution") or {}).get("delivery_count") or 0))
    return {
        "schema": "axm.ghost-studio.machine-review/v0.1",
        "status": "ACCEPTED_STRUCTURAL" if not failures else "REJECTED",
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(failures),
        "failures": failures,
        "delivery_count": delivery_count,
        "truth_boundary": (
            "Structural review proves file identity, receipts and GLB 2 containers for this attempt. "
            "It does not prove engine import, performance, animation, gameplay feel, visual approval or CANON."
        ),
    }


def run_workflow(
    snapshot: str | Path,
    output: str | Path,
    *,
    reference: str | Path | None = None,
    max_attempts: int = 2,
    exercise_rejection: bool = False,
) -> dict[str, Any]:
    if max_attempts < 1 or max_attempts > 5:
        raise WorkflowError("max_attempts must be between 1 and 5")
    root = Path(snapshot).resolve()
    destination = Path(output).resolve()
    try:
        output_relative = destination.relative_to(root)
    except ValueError as exc:
        raise WorkflowError("workflow output must stay inside the assembled snapshot") from exc
    if not output_relative.parts:
        raise WorkflowError("workflow output cannot replace the snapshot root")
    if destination.exists():
        raise WorkflowError("workflow output must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    attempts: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None
    try:
        for number in range(1, max_attempts + 1):
            attempt = stage / "attempts" / f"{number:03d}"
            ghost_studio_asset_trial.run_trial(root, attempt / "role-assets")
            if reference is not None:
                ghost_studio_reference_kit.run(root, reference, attempt / "environment-kit")
            if exercise_rejection and number == 1:
                (attempt / "role-assets" / "deliveries" / "blackline-runner-drone.glb").unlink()
            review = review_attempt(root, attempt, reference_required=reference is not None)
            _write_json(attempt / "MACHINE_REVIEW.json", review)
            attempts.append({
                "attempt": number,
                "status": review["status"],
                "review": f"attempts/{number:03d}/MACHINE_REVIEW.json",
                "failure_count": review["failure_count"],
            })
            if review["status"] == "ACCEPTED_STRUCTURAL":
                accepted = review
                break

        stages = [
            {"capability": "axm-universal-creation::creation.universal", "status": "EXECUTED", "execution_kind": "captured-source-import"},
            {"capability": "Axm-game-assets::asset.game", "status": "EXECUTED", "execution_kind": "captured-source-import"},
            {"capability": "axm-ghost-studio::game.studio", "status": "EXECUTED_STRUCTURAL_REVIEW", "execution_kind": "charter-bound-workflow-adapter"},
        ]
        receipt = {
            "schema": SCHEMA,
            "workflow": WORKFLOW_ID,
            "status": "EXECUTED_END_TO_END_AND_STRUCTURALLY_ACCEPTED" if accepted else "REJECTED_AFTER_BOUNDED_REVIEW",
            "attempts": attempts,
            "iteration_count": len(attempts),
            "rejection_count": sum(item["status"] == "REJECTED" for item in attempts),
            "accepted_attempt": next((item["attempt"] for item in attempts if item["status"] == "ACCEPTED_STRUCTURAL"), None),
            "output": output_relative.as_posix(),
            "reference_required": reference is not None,
            "delivery_count": accepted["delivery_count"] if accepted else 0,
            "check_count": accepted["check_count"] if accepted else 0,
            "stages": stages,
            "source_capability_executed": bool(accepted),
            "source_callable_contract_executed": False,
            "truth_boundary": (
                "This receipt proves only the exact Blackline workflow through captured source imports and a "
                "charter-bound structural review. It does not claim that the three abstract catalogue IDs have "
                "native callable contracts or that unrelated monolith capabilities are wired."
            ),
        }
        _write_json(stage / "WORKFLOW_RECEIPT.json", receipt)
        _write_json(stage / "WORKFLOW_REGISTRY.json", {
            "schema": "axm.monolith.workflow-registry/v0.1",
            "workflows": [{"id": WORKFLOW_ID, "stages": stages, "receipt": "WORKFLOW_RECEIPT.json"}],
        })
        workflow_evidence = root / "evidence" / "workflows"
        workflow_evidence.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage / "WORKFLOW_RECEIPT.json", workflow_evidence / f"{WORKFLOW_ID}.json")
        stage.replace(destination)
        return receipt
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute the Blackline Relay 3D workflow through an AXM snapshot")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--exercise-rejection", action="store_true")
    parser.add_argument("--confirm-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_run:
        parser.error("--confirm-run is required")
    try:
        result = run_workflow(
            args.snapshot, args.output, reference=args.reference,
            max_attempts=args.max_attempts, exercise_rejection=args.exercise_rejection,
        )
    except (WorkflowError, ghost_studio_asset_trial.TrialError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Ghost Studio workflow: BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "EXECUTED_END_TO_END_AND_STRUCTURALLY_ACCEPTED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
