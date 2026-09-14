#!/usr/bin/env python3
"""Learned deterministic wiring for schema-only AXM modules.

This rule came from wiring a real selected module (`axm-directional-state-fabric`) that
contained machine-readable JSON schemas but no executable test queue. It does one small
thing only: when a materialized module has no discovered tests and exposes bounded JSON
schema files, add JSON *syntax* probes to the generated monolith analysis/test queue.

Truth boundary: a passing probe proves only that the exact copied JSON file parses as JSON.
It does not validate JSON-Schema semantics, state behavior, interoperability, or CANON.
Donor module bytes are never changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

MAX_SCHEMA_PROBES_PER_MODULE = 16
QUEUE_NAME = "AUTOMATED_TEST_QUEUE.json"
ANALYSIS_NAME = "STACK_ANALYSIS.json"
RECEIPT_NAME = "SCHEMA_PROBE_WIRING_RECEIPT.json"
NO_TEST_UNCERTAINTY = "No automated test/static-check command detected."


class SchemaProbeWiringError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchemaProbeWiringError(f"missing required file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaProbeWiringError(f"invalid JSON in {path.name}: {exc}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_module_root(root: Path, module: str) -> Path:
    modules = (root / "modules").resolve()
    candidate = (modules / module).resolve()
    try:
        candidate.relative_to(modules)
    except ValueError as exc:
        raise SchemaProbeWiringError(f"module path escapes snapshot: {module}") from exc
    if candidate.is_symlink() or not candidate.is_dir():
        raise SchemaProbeWiringError(f"module directory missing or unsafe: {module}")
    return candidate


def _schema_paths(module_root: Path) -> list[str]:
    result: list[str] = []
    for path in sorted(module_root.rglob("*.json")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(module_root).as_posix()
        low = rel.lower()
        if low.endswith(".schema.json") or low.startswith("schemas/") or "/schemas/" in f"/{low}":
            result.append(rel)
            if len(result) >= MAX_SCHEMA_PROBES_PER_MODULE:
                break
    return result


def _probe(module: str, rel: str) -> dict[str, str]:
    return {
        "module": module,
        "kind": "schema-json-probe",
        "command": f"python -m json.tool {rel}",
        "safety": "JSON parse only; exact donor schema file in isolated copied workspace",
        "evidence": "generated-schema-json-syntax-probe",
        "status": "discovered_not_run",
    }


def _test_capability() -> dict[str, Any]:
    return {
        "id": "evidence.test-suite",
        "description": "Bounded static JSON schema syntax probes are present.",
        "source": "structural-scan",
        "evidence_status": "detected_not_executed",
        "confidence": 0.9,
        "provides": ["evidence.test-suite"],
        "accepts": ["source.module"],
        "tags": ["testing", "evidence", "schema"],
    }


def apply(snapshot: str | Path) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    if root.is_symlink() or not root.is_dir() or not (root / "modules").is_dir():
        raise SchemaProbeWiringError("snapshot must be one real directory containing modules/")

    analysis_path = root / ANALYSIS_NAME
    queue_path = root / QUEUE_NAME
    analysis = _read_json(analysis_path)
    queue = _read_json(queue_path)
    modules = analysis.get("modules")
    existing_queue = queue.get("queue")
    if not isinstance(modules, list) or not isinstance(existing_queue, list):
        raise SchemaProbeWiringError("analysis/test queue shape is invalid")

    donor_hashes_before: dict[str, dict[str, str]] = {}
    generated: list[dict[str, str]] = []
    touched_modules: list[str] = []

    for profile in modules:
        if not isinstance(profile, dict):
            continue
        module = str(profile.get("module") or "")
        if not module:
            continue
        module_root = _safe_module_root(root, module)
        if profile.get("tests"):
            continue
        schemas = _schema_paths(module_root)
        if not schemas:
            continue

        donor_hashes_before[module] = {rel: _sha256(module_root / rel) for rel in schemas}
        probes = [_probe(module, rel) for rel in schemas]
        profile["tests"] = [{k: v for k, v in item.items() if k not in {"module", "status"}} for item in probes]
        capabilities = profile.setdefault("capabilities", [])
        if not any(isinstance(cap, dict) and cap.get("id") == "evidence.test-suite" for cap in capabilities):
            capabilities.append(_test_capability())
            capabilities.sort(key=lambda cap: str(cap.get("id") or "") if isinstance(cap, dict) else "")
        uncertainties = profile.get("uncertainties")
        if isinstance(uncertainties, list):
            profile["uncertainties"] = [value for value in uncertainties if value != NO_TEST_UNCERTAINTY]
        generated.extend(probes)
        touched_modules.append(module)

    # Replace only generated schema probes for touched modules, preserving every other queue item.
    touched = set(touched_modules)
    retained = [
        item for item in existing_queue
        if not (
            isinstance(item, dict)
            and str(item.get("module") or "") in touched
            and item.get("kind") == "schema-json-probe"
            and item.get("evidence") == "generated-schema-json-syntax-probe"
        )
    ]
    combined = retained + generated
    combined.sort(key=lambda item: (str(item.get("module") or ""), str(item.get("command") or "")))
    queue["queue"] = combined
    queue.setdefault(
        "truth_boundary",
        "Discovered commands are test candidates only; they are not evidence that tests passed until separately executed.",
    )
    analysis["automated_test_queue"] = combined

    _write_json(analysis_path, analysis)
    _write_json(queue_path, queue)

    donor_hashes_after = {
        module: {rel: _sha256(_safe_module_root(root, module) / rel) for rel in paths}
        for module, paths in ((module, sorted(values)) for module, values in ((m, d.keys()) for m, d in donor_hashes_before.items()))
    }
    donor_unchanged = donor_hashes_before == donor_hashes_after
    if not donor_unchanged:
        raise SchemaProbeWiringError("donor schema bytes changed while applying generated wiring")

    receipt = {
        "schema": "axm.monolith.learned-schema-probe-wiring/v0.1",
        "status": "PASS",
        "touched_module_count": len(touched_modules),
        "touched_modules": sorted(touched_modules),
        "generated_probe_count": len(generated),
        "generated_kind": "schema-json-probe",
        "donor_schema_bytes_unchanged": True,
        "max_schema_probes_per_module": MAX_SCHEMA_PROBES_PER_MODULE,
        "truth_boundary": (
            "This learned rule generates JSON parse probes only for schema-bearing modules that otherwise have no discovered tests. "
            "It does not prove JSON-Schema semantics, behavior, interoperability, product acceptance, merge authority, or CANON."
        ),
    }
    _write_json(root / RECEIPT_NAME, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply learned schema-only test wiring to an AXM snapshot")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = apply(args.snapshot)
    except (SchemaProbeWiringError, OSError, ValueError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
