#!/usr/bin/env python3
"""One-command AXM Monolith plumbing, evidence gate, and packaging.

The command intentionally fails closed. A snapshot is always re-inspected and plumbed before
packaging. Optional native invocation plans produce validated execution ledgers. A required
named workflow must carry its own accepted receipt. The word "connected" is never inferred
from co-location, catalogue size, or candidate graph edges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from typing import Any
import zipfile

import callable_execution_ledger
import ghost_studio_pipeline
import invoke_declared_callable
import monolith_plumbing


SCHEMA = "axm.monolith.connected-finalization/v0.2"
PACKAGE_SCHEMA = "axm.monolith.snapshot-file-receipt/v0.2"
PLAN_SCHEMA = "axm.monolith.invocation-plan/v0.1"


class FinalizationError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"cannot read valid JSON: {path}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not name:
        raise FinalizationError("folder name must contain safe filename characters")
    return name


def run_invocation_plan(snapshot: Path, plan_path: Path) -> dict[str, Any]:
    plan = _read_json(plan_path)
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise FinalizationError(f"invocation plan schema must be {PLAN_SCHEMA}")
    invocations = plan.get("invocations")
    if not isinstance(invocations, list):
        raise FinalizationError("invocation plan must contain an invocations array")
    receipts = snapshot / "evidence" / "callable-invocations"
    receipts.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, item in enumerate(invocations, start=1):
        if not isinstance(item, dict):
            raise FinalizationError(f"invocation {index} must be an object")
        address = item.get("address")
        request = item.get("request")
        if not isinstance(address, str) or not address or item.get("allow_execution") is not True:
            raise FinalizationError(f"invocation {index} lacks address or explicit allow_execution=true")
        receipt = invoke_declared_callable.invoke_declared_callable(
            snapshot,
            address,
            request,
            allow_javascript_esm=True,
            allow_python=True,
            timeout_seconds=float(item.get("timeout_seconds", 30.0)),
        )
        filename = f"{index:03d}-{hashlib.sha256(address.encode('utf-8')).hexdigest()[:16]}.json"
        _write_json(receipts / filename, receipt)
        result = {"address": address, "status": receipt.get("status"), "required": bool(item.get("required", True)), "receipt": f"evidence/callable-invocations/{filename}"}
        results.append(result)

    ledger = callable_execution_ledger.write_ledger(snapshot, receipts, strict=True)
    failed_required = [item for item in results if item["required"] and item["status"] != "exercised_with_receipt"]
    if failed_required:
        raise FinalizationError(f"required callable invocations did not execute: {[item['address'] for item in failed_required]}")
    return {
        "schema": PLAN_SCHEMA,
        "invocation_count": len(results),
        "required_count": sum(item["required"] for item in results),
        "results": results,
        "ledger": "CALLABLE_EXECUTION_LEDGER.json",
        "ledger_summary": ledger["summary"],
    }


def _load_workflow(snapshot: Path, workflow_id: str | None) -> dict[str, Any] | None:
    if workflow_id is None:
        return None
    path = snapshot / "evidence" / "workflows" / f"{workflow_id}.json"
    value = _read_json(path)
    if value.get("workflow") != workflow_id:
        raise FinalizationError("required workflow receipt identity mismatch")
    if value.get("status") != "EXECUTED_END_TO_END_AND_STRUCTURALLY_ACCEPTED":
        raise FinalizationError(f"required workflow did not pass: {value.get('status')}")
    if workflow_id == ghost_studio_pipeline.WORKFLOW_ID:
        output_value = value.get("output")
        accepted_attempt = value.get("accepted_attempt")
        if not isinstance(output_value, str) or not isinstance(accepted_attempt, int):
            raise FinalizationError("Blackline workflow receipt lacks its bound output or accepted attempt")
        output = (snapshot / output_value).resolve()
        try:
            output.relative_to(snapshot.resolve())
        except ValueError as exc:
            raise FinalizationError("Blackline workflow output escapes the snapshot") from exc
        review = ghost_studio_pipeline.review_attempt(
            snapshot,
            output / "attempts" / f"{accepted_attempt:03d}",
            reference_required=value.get("reference_required") is True,
        )
        if review.get("status") != "ACCEPTED_STRUCTURAL":
            raise FinalizationError("Blackline workflow output no longer passes structural review")
        if review.get("delivery_count") != value.get("delivery_count"):
            raise FinalizationError("Blackline workflow delivery count changed after execution")
    return value


def _snapshot_files(snapshot: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(snapshot.rglob("*"), key=lambda item: item.relative_to(snapshot).as_posix().lower()):
        relative = path.relative_to(snapshot)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise FinalizationError(f"refusing symlink in package: {relative.as_posix()}")
        if path.is_file() and path.name != "SNAPSHOT_FILE_RECEIPT.json":
            files.append(path)
    return files


def _zip_file(archive: zipfile.ZipFile, source: Path, name: str) -> None:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise FinalizationError(f"unsafe archive path: {name}")
    info = zipfile.ZipInfo(pure.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100644 & 0xFFFF) << 16
    archive.writestr(info, source.read_bytes())


def package_snapshot(
    snapshot: Path,
    output_zip: Path,
    *,
    folder_name: str,
    required_workflow: str | None,
    required_addresses: list[str],
) -> dict[str, Any]:
    plumbing = _read_json(snapshot / "PLUMBING_RECEIPT.json")
    if plumbing.get("status") != "PLUMBING_INSTALLED_WITH_EXPLICIT_EXECUTION_BOUNDARY":
        raise FinalizationError("snapshot plumbing receipt is missing or not accepted")
    workflow = _load_workflow(snapshot, required_workflow)

    ledger: dict[str, Any] | None = None
    if required_addresses:
        ledger = _read_json(snapshot / "CALLABLE_EXECUTION_LEDGER.json")
        executed = set(ledger.get("executed_addresses") or [])
        missing = sorted(set(required_addresses) - executed)
        if missing:
            raise FinalizationError(f"required callable addresses lack accepted receipts: {missing}")

    if output_zip.exists():
        raise FinalizationError(f"output ZIP already exists: {output_zip}")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    folder = _safe_name(folder_name)
    files = _snapshot_files(snapshot)
    file_records = [{
        "path": path.relative_to(snapshot).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    } for path in files]
    receipt = {
        "schema": PACKAGE_SCHEMA,
        "snapshot": snapshot.name,
        "file_count_excluding_receipt": len(file_records),
        "bytes_excluding_receipt": sum(item["bytes"] for item in file_records),
        "files": file_records,
        "required_workflow": ({"id": required_workflow, "status": workflow["status"]} if workflow else None),
        "required_callable_addresses": required_addresses,
        "callable_execution": ledger.get("summary") if ledger else None,
        "plumbing": plumbing,
        "truth_boundary": (
            "File hashes prove package integrity. Workflow/callable receipts prove only the explicitly "
            "required routes. Unbound leaf declarations and candidate compositions remain unexecuted."
        ),
    }
    receipt_path = snapshot / "SNAPSHOT_FILE_RECEIPT.json"
    _write_json(receipt_path, receipt)

    fd, temporary_name = tempfile.mkstemp(prefix=f".{output_zip.name}-", suffix=".tmp", dir=output_zip.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for path in files:
                _zip_file(archive, path, f"{folder}/{path.relative_to(snapshot).as_posix()}")
            _zip_file(archive, receipt_path, f"{folder}/SNAPSHOT_FILE_RECEIPT.json")
        os.replace(temporary, output_zip)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    sidecar = {
        "schema": "axm.monolith.connected-zip-result/v0.2",
        "zip": str(output_zip),
        "zip_bytes": output_zip.stat().st_size,
        "zip_sha256": _sha256(output_zip),
        "folder_name": folder,
        "archive_file_count": len(files) + 1,
        "required_workflow": required_workflow,
        "required_callable_addresses": required_addresses,
        "truth_boundary": receipt["truth_boundary"],
    }
    _write_json(Path(str(output_zip) + ".receipt.json"), sidecar)
    return sidecar


def finalize(
    snapshot: str | Path,
    output_zip: str | Path,
    *,
    folder_name: str,
    invocation_plan: str | Path | None = None,
    required_addresses: list[str] | None = None,
    blackline_output: str | Path | None = None,
    blackline_reference: str | Path | None = None,
    reuse_blackline: bool = False,
    required_workflow: str | None = None,
) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    plumbing = monolith_plumbing.plumb_snapshot(root)
    invocations = run_invocation_plan(root, Path(invocation_plan)) if invocation_plan else None

    workflow: dict[str, Any] | None = None
    if blackline_output is not None:
        workflow_output = Path(blackline_output)
        if not workflow_output.is_absolute():
            workflow_output = root / workflow_output
        if reuse_blackline:
            workflow = _read_json(workflow_output / "WORKFLOW_RECEIPT.json")
            if workflow.get("status") != "EXECUTED_END_TO_END_AND_STRUCTURALLY_ACCEPTED":
                raise FinalizationError("reused Blackline workflow receipt is not accepted")
            try:
                expected_output = workflow_output.resolve().relative_to(root).as_posix()
            except ValueError as exc:
                raise FinalizationError("reused Blackline output must stay inside the snapshot") from exc
            if workflow.get("workflow") != ghost_studio_pipeline.WORKFLOW_ID or workflow.get("output") != expected_output:
                raise FinalizationError("reused Blackline workflow identity or output binding mismatch")
            evidence = root / "evidence" / "workflows"
            evidence.mkdir(parents=True, exist_ok=True)
            _write_json(evidence / f"{ghost_studio_pipeline.WORKFLOW_ID}.json", workflow)
        else:
            workflow = ghost_studio_pipeline.run_workflow(root, workflow_output, reference=blackline_reference)
        required_workflow = ghost_studio_pipeline.WORKFLOW_ID

    package = package_snapshot(
        root,
        Path(output_zip).resolve(),
        folder_name=folder_name,
        required_workflow=required_workflow,
        required_addresses=list(required_addresses or []),
    )
    return {
        "schema": SCHEMA,
        "status": "PACKAGED_AFTER_REQUIRED_EVIDENCE_PASS",
        "plumbing": plumbing,
        "invocations": invocations,
        "workflow": workflow,
        "package": package,
        "truth_boundary": (
            "This gate proves package integrity plus only the exact required workflow/callable evidence. "
            "It preserves every unrelated execution gap."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plumb, evidence-gate and package an AXM Monolith snapshot")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output-zip", required=True, type=Path)
    parser.add_argument("--folder-name", required=True)
    parser.add_argument("--invocation-plan", type=Path)
    parser.add_argument("--require-address", action="append", default=[])
    parser.add_argument("--blackline-output", type=Path)
    parser.add_argument("--blackline-reference", type=Path)
    parser.add_argument("--reuse-blackline", action="store_true")
    parser.add_argument("--require-workflow")
    parser.add_argument("--confirm-finalize", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_finalize:
        parser.error("--confirm-finalize is required")
    try:
        result = finalize(
            args.snapshot,
            args.output_zip,
            folder_name=args.folder_name,
            invocation_plan=args.invocation_plan,
            required_addresses=args.require_address,
            blackline_output=args.blackline_output,
            blackline_reference=args.blackline_reference,
            reuse_blackline=args.reuse_blackline,
            required_workflow=args.require_workflow,
        )
    except (FinalizationError, monolith_plumbing.PlumbingError, ghost_studio_pipeline.WorkflowError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"connected finalization: BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
