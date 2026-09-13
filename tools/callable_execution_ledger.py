#!/usr/bin/env python3
"""Build a deterministic evidence ledger from explicit AXM callable invocation receipts.

The callable registry remains a declaration registry.  This tool separately records which
exact invocation receipts survive identity checks against the captured source snapshot.
It never executes capability code and never promotes unrelated declarations.

Truth boundary: an accepted receipt proves only the exact captured source export executed
for the exact request represented by that receipt in its recorded environment.  The ledger
does not grant merge/CANON, installation, network, safety, quality, or risk authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

LEDGER_SCHEMA = "axm.monolith.callable-execution-ledger/v0.1"
REGISTRY_SCHEMA = "axm.monolith.callable-capability-registry/v0.1"
RECEIPT_SCHEMA = "axm.monolith.callable-invocation-receipt/v0.1"
SHA256_PREFIX = "sha256:"


class LedgerError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LedgerError(f"cannot read valid JSON: {path}") from exc


def _sha256_bytes(value: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith(SHA256_PREFIX):
        return False
    digest = value[len(SHA256_PREFIX):]
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _registry(snapshot: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = snapshot / "CALLABLE_CAPABILITY_REGISTRY.json"
    value = _read_json(path)
    if not isinstance(value, dict) or value.get("schema") != REGISTRY_SCHEMA:
        raise LedgerError("snapshot has no supported callable capability registry")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise LedgerError("callable capability registry entries must be an array")
    by_address: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise LedgerError("callable capability registry contains a non-object entry")
        address = entry.get("address")
        if not isinstance(address, str) or not address:
            raise LedgerError("callable capability registry entry is missing an address")
        if address in by_address:
            raise LedgerError(f"duplicate callable registry address: {address}")
        by_address[address] = entry
    return value, by_address


def _module_root(snapshot: Path, module: str) -> Path | None:
    modules = (snapshot / "modules").resolve()
    candidate = modules / module
    if candidate.is_symlink():
        return None
    resolved = candidate.resolve()
    try:
        resolved.relative_to(modules)
    except ValueError:
        return None
    return resolved if resolved.is_dir() else None


def _source_file(snapshot: Path, entry: dict[str, Any], receipt: dict[str, Any]) -> Path | None:
    module = entry.get("module")
    descriptor = entry.get("callable") or {}
    relative = descriptor.get("path")
    if not isinstance(module, str) or not isinstance(relative, str) or not relative:
        return None
    root = _module_root(snapshot, module)
    if root is None:
        return None
    candidate = root / relative
    if candidate.is_symlink():
        return None
    target = candidate.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if not target.is_file():
        return None
    if receipt.get("source_file") != target.relative_to(root).as_posix():
        return None
    return target


def _validate_receipt(snapshot: Path, registry_by_address: dict[str, dict[str, Any]], receipt: Any) -> tuple[str, list[str], dict[str, Any] | None]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return "blocked_invalid_receipt", ["receipt must be an object"], None
    if receipt.get("schema") != RECEIPT_SCHEMA:
        return "ignored_non_receipt", [], None

    address = receipt.get("address")
    entry = registry_by_address.get(address) if isinstance(address, str) else None
    if entry is None:
        errors.append("receipt address does not exist exactly once in callable registry")
        return "blocked_receipt_registry_mismatch", errors, None

    descriptor = entry.get("callable") or {}
    if entry.get("status") != "declared_callable_not_exercised" or entry.get("errors"):
        errors.append("registry entry is not a valid declared callable")
    if receipt.get("module") != entry.get("module") or receipt.get("capability") != entry.get("capability"):
        errors.append("receipt module/capability identity does not match registry address")
    if receipt.get("manifest_sha256") != entry.get("manifest_sha256"):
        errors.append("receipt manifest hash does not match registry manifest hash")
    if not _valid_sha256(receipt.get("manifest_sha256")):
        errors.append("receipt manifest hash is not a valid SHA-256 identity")

    runtime = descriptor.get("runtime")
    export = descriptor.get("export")
    if receipt.get("runtime") != runtime:
        errors.append("receipt runtime does not match declared runtime")
    if receipt.get("export") != export:
        errors.append("receipt export does not match declared export")
    if descriptor.get("authority") != "none":
        errors.append("declared callable authority is not none")

    target = _source_file(snapshot, entry, receipt)
    if target is None:
        errors.append("receipt source file does not resolve to declared captured source")
    else:
        actual_source_hash = _sha256_file(target)
        if receipt.get("source_file_sha256") != actual_source_hash:
            errors.append("receipt source-file hash does not match captured source bytes")
    if not _valid_sha256(receipt.get("source_file_sha256")):
        errors.append("receipt source-file hash is not a valid SHA-256 identity")
    if not _valid_sha256(receipt.get("request_sha256")):
        errors.append("receipt request hash is not a valid SHA-256 identity")

    response = receipt.get("response")
    if not _valid_sha256(receipt.get("response_sha256")):
        errors.append("receipt response hash is not a valid SHA-256 identity")
    elif receipt.get("response_sha256") != _canonical_sha256(response):
        errors.append("receipt response hash does not match canonical response")

    status = receipt.get("status")
    execution_flag = receipt.get("source_capability_execution")
    if status == "exercised_with_receipt":
        if execution_flag is not True:
            errors.append("successful receipt must set source_capability_execution true")
        if not isinstance(response, dict) or response.get("ok") is not True:
            errors.append("successful receipt must contain an ok response")
        elif receipt.get("result") != response.get("result"):
            errors.append("successful receipt result does not match response result")
        classification = "accepted_exercised_receipt"
    else:
        if execution_flag is not False:
            errors.append("non-success receipt must not claim source_capability_execution")
        classification = "observed_non_success_receipt"

    if errors:
        return "blocked_invalid_receipt", errors, entry
    return classification, [], entry


def build_ledger(snapshot: str | Path, receipts: str | Path) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    receipt_root = Path(receipts).resolve()
    if not receipt_root.is_dir():
        raise LedgerError("receipts path must be a directory")
    registry, by_address = _registry(root)

    ledger_entries: list[dict[str, Any]] = []
    ignored = 0
    for path in sorted(receipt_root.rglob("*.json"), key=lambda item: item.relative_to(receipt_root).as_posix().lower()):
        try:
            value = _read_json(path)
        except LedgerError as exc:
            ledger_entries.append({
                "receipt_file": path.relative_to(receipt_root).as_posix(),
                "receipt_file_sha256": _sha256_file(path),
                "classification": "blocked_invalid_receipt_json",
                "address": None,
                "status": None,
                "source_capability_execution": False,
                "errors": [str(exc)],
            })
            continue
        classification, errors, registry_entry = _validate_receipt(root, by_address, value)
        if classification == "ignored_non_receipt":
            ignored += 1
            continue
        address = value.get("address") if isinstance(value, dict) else None
        record = {
            "receipt_file": path.relative_to(receipt_root).as_posix(),
            "receipt_file_sha256": _sha256_file(path),
            "classification": classification,
            "address": address,
            "status": value.get("status") if isinstance(value, dict) else None,
            "source_capability_execution": classification == "accepted_exercised_receipt",
            "manifest_sha256": value.get("manifest_sha256") if isinstance(value, dict) else None,
            "source_file": value.get("source_file") if isinstance(value, dict) else None,
            "source_file_sha256": value.get("source_file_sha256") if isinstance(value, dict) else None,
            "request_sha256": value.get("request_sha256") if isinstance(value, dict) else None,
            "response_sha256": value.get("response_sha256") if isinstance(value, dict) else None,
            "runtime": value.get("runtime") if isinstance(value, dict) else None,
            "export": value.get("export") if isinstance(value, dict) else None,
            "errors": errors,
        }
        if registry_entry is not None:
            record["registry_status"] = registry_entry.get("status")
        ledger_entries.append(record)

    ledger_entries.sort(key=lambda item: (str(item.get("address") or ""), item["receipt_file"], item["receipt_file_sha256"]))
    accepted = [entry for entry in ledger_entries if entry["classification"] == "accepted_exercised_receipt"]
    invalid = [entry for entry in ledger_entries if entry["classification"].startswith("blocked_")]
    non_success = [entry for entry in ledger_entries if entry["classification"] == "observed_non_success_receipt"]
    executed_addresses = sorted({str(entry["address"]) for entry in accepted if entry.get("address")})

    by_capability: list[dict[str, Any]] = []
    all_addresses = sorted({str(entry["address"]) for entry in ledger_entries if entry.get("address")})
    for address in all_addresses:
        matches = [entry for entry in ledger_entries if entry.get("address") == address]
        accepted_matches = [entry for entry in matches if entry["classification"] == "accepted_exercised_receipt"]
        by_capability.append({
            "address": address,
            "receipt_count": len(matches),
            "accepted_exercised_receipts": len(accepted_matches),
            "source_capability_execution": bool(accepted_matches),
            "receipt_file_sha256": sorted(entry["receipt_file_sha256"] for entry in matches),
        })

    return {
        "schema": LEDGER_SCHEMA,
        "source_registry_sha256": _sha256_file(root / "CALLABLE_CAPABILITY_REGISTRY.json"),
        "summary": {
            "registry_declared_callable_count": len(registry.get("entries", [])),
            "receipt_files_recorded": len(ledger_entries),
            "ignored_non_receipt_json": ignored,
            "accepted_exercised_receipts": len(accepted),
            "observed_non_success_receipts": len(non_success),
            "blocked_invalid_receipts": len(invalid),
            "exercised_address_count": len(executed_addresses),
        },
        "executed_addresses": executed_addresses,
        "capabilities": by_capability,
        "receipts": ledger_entries,
        "truth_boundary": (
            "This ledger records exact validated invocation receipts separately from source declarations. "
            "An accepted receipt proves only that exact captured source invocation. It does not promote unrelated "
            "capabilities or grant merge/CANON, installation, network, safety, quality, or risk authority."
        ),
    }


def write_ledger(snapshot: str | Path, receipts: str | Path, output: str | Path | None = None, *, strict: bool = False) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    ledger = build_ledger(root, receipts)
    target = Path(output) if output is not None else root / "CALLABLE_EXECUTION_LEDGER.json"
    if not target.is_absolute():
        target = root / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if strict and ledger["summary"]["blocked_invalid_receipts"]:
        raise LedgerError("invalid callable invocation receipts were found; ledger written with blocked entries")
    return ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AXM callable execution evidence ledger from invocation receipts")
    parser.add_argument("snapshot", help="materialized snapshot root containing CALLABLE_CAPABILITY_REGISTRY.json")
    parser.add_argument("--receipts", required=True, help="directory containing invocation receipt JSON files")
    parser.add_argument("--output", help="output path (default: CALLABLE_EXECUTION_LEDGER.json in snapshot root)")
    parser.add_argument("--strict", action="store_true", help="exit nonzero after writing when invalid receipt evidence is present")
    args = parser.parse_args(argv)
    try:
        ledger = write_ledger(args.snapshot, args.receipts, args.output, strict=args.strict)
    except LedgerError as exc:
        print(f"callable execution ledger: BLOCKED: {exc}")
        return 2
    print(json.dumps(ledger["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
