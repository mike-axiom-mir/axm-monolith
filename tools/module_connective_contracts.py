#!/usr/bin/env python3
"""Generate truthful per-module connective sidecars for an assembled AXM snapshot.

This tool turns already-produced structural analysis plus the execution fabric into a compact,
machine-readable contract per module. It does not execute donor code, edit modules/, or promote
candidate token matches into verified interoperability.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "axm.monolith.module-connective-contract/v0.1"
REGISTRY_SCHEMA = "axm.monolith.module-connective-contract-registry/v0.1"
REPORT_NAME = "MODULE_CONNECTIVE_CONTRACTS_REPORT.md"
REGISTRY_NAME = "MODULE_CONNECTIVE_CONTRACTS.json"
CONTRACT_DIR = Path("analysis/contracts")
ROOTS = ["Truth", "Agency / non-domination", "Continuity", "Wisdom before speed"]

ADAPTER_STATE = {
    "callable_native_command_verified": "VERIFIED_EXECUTABLE",
    "callable_through_named_workflow": "WORKFLOW_SCOPED",
    "executable_test_evidence": "TEST_EVIDENCE",
    "executable_inspection": "INSPECTED",
    "launchable_local_surface": "LAUNCHABLE_NOT_EXECUTED",
    "native_command_discovered_unprobed": "DISCOVERED_UNPROBED",
    "blocked_missing_native_contract": "BLOCKED_MISSING_NATIVE_CONTRACT",
    "blocked_missing_callable_binding": "BLOCKED_MISSING_CALLABLE_BINDING",
}
STATE_RANK = {
    "VERIFIED_EXECUTABLE": 70,
    "WORKFLOW_SCOPED": 60,
    "TEST_EVIDENCE": 50,
    "INSPECTED": 40,
    "LAUNCHABLE_NOT_EXECUTED": 30,
    "DISCOVERED_UNPROBED": 20,
    "BLOCKED_MISSING_NATIVE_CONTRACT": 10,
    "BLOCKED_MISSING_CALLABLE_BINDING": 10,
    "HOLD_NO_EXECUTION_FABRIC": 0,
    "HOLD_NO_ENDPOINTS": 0,
}


class ContractError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON {path}: {exc}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def _module_analyses(root: Path) -> dict[str, dict[str, Any]]:
    directory = root / "analysis" / "modules"
    if not directory.is_dir():
        raise ContractError("analysis/modules is missing")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json"), key=lambda p: p.name.lower()):
        value = _read_json(path)
        if not isinstance(value, dict):
            raise ContractError(f"module analysis is not an object: {path}")
        module = str(value.get("module") or path.stem).strip()
        if not module:
            raise ContractError(f"module analysis has no module identity: {path}")
        if module in result:
            raise ContractError(f"duplicate module analysis identity: {module}")
        result[module] = value
    if not result:
        raise ContractError("no module analyses found")
    return result


def _execution_endpoints(root: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any] | None]:
    path = root / "EXECUTION_FABRIC.json"
    if not path.is_file():
        return {}, None
    fabric = _read_json(path)
    if not isinstance(fabric, dict) or not isinstance(fabric.get("endpoints"), list):
        raise ContractError("EXECUTION_FABRIC.json has no endpoint list")
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for endpoint in fabric["endpoints"]:
        if isinstance(endpoint, dict) and endpoint.get("module"):
            grouped[str(endpoint["module"])].append(endpoint)
    return dict(grouped), fabric


def _capability_tokens(analysis: dict[str, Any]) -> tuple[list[str], list[str], dict[str, int]]:
    accepts: set[str] = set()
    provides: set[str] = set()
    evidence = collections.Counter()
    for cap in analysis.get("capabilities") or []:
        if not isinstance(cap, dict):
            continue
        accepts.update(str(x) for x in cap.get("accepts") or [] if str(x).strip())
        provides.update(str(x) for x in cap.get("provides") or [] if str(x).strip())
        evidence[str(cap.get("evidence_status") or "unknown")] += 1
    return sorted(accepts), sorted(provides), dict(sorted(evidence.items()))


def _execution_surface(endpoints: list[dict[str, Any]], fabric_present: bool) -> dict[str, Any]:
    if not fabric_present:
        return {
            "endpoint_count": 0,
            "adapter_status_counts": {},
            "integration_states": ["HOLD_NO_EXECUTION_FABRIC"],
            "highest_observed_state": "HOLD_NO_EXECUTION_FABRIC",
            "actionable_endpoints": [],
            "blocked_endpoint_count": 0,
            "blocked_endpoint_examples": [],
            "full_endpoint_source": None,
        }
    counts = collections.Counter()
    actionable: list[dict[str, Any]] = []
    blocked_examples: list[dict[str, Any]] = []
    states: set[str] = set()
    for endpoint in endpoints:
        adapter = endpoint.get("adapter") if isinstance(endpoint.get("adapter"), dict) else {}
        status = str(adapter.get("status") or "no_adapter_status")
        counts[status] += 1
        state = ADAPTER_STATE.get(status, "HOLD_UNKNOWN_ADAPTER_STATUS")
        states.add(state)
        compact = {
            "address": endpoint.get("address"),
            "capability": endpoint.get("capability"),
            "registry_layer": endpoint.get("registry_layer"),
            "declaration_source": endpoint.get("declaration_source"),
            "evidence_status": endpoint.get("evidence_status"),
            "adapter_status": status,
            "adapter_kind": adapter.get("kind"),
            "workflow": adapter.get("workflow"),
            "source_capability_execution": adapter.get("source_capability_execution"),
        }
        if status.startswith("blocked_"):
            if len(blocked_examples) < 12:
                blocked_examples.append(compact)
        else:
            actionable.append(compact)
    if not endpoints:
        states = {"HOLD_NO_ENDPOINTS"}
    ordered_states = sorted(states, key=lambda s: (-STATE_RANK.get(s, 1), s))
    return {
        "endpoint_count": len(endpoints),
        "adapter_status_counts": dict(sorted(counts.items())),
        "integration_states": ordered_states,
        "highest_observed_state": ordered_states[0],
        "actionable_endpoints": sorted(actionable, key=lambda x: str(x.get("address") or "")),
        "blocked_endpoint_count": sum(v for k, v in counts.items() if k.startswith("blocked_")),
        "blocked_endpoint_examples": blocked_examples,
        "full_endpoint_source": "EXECUTION_FABRIC.json",
    }


def _native_manifest_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    manifest = analysis.get("native_manifest")
    if isinstance(manifest, dict):
        return {"present": True, "declared": manifest, "error": analysis.get("native_manifest_error")}
    return {"present": False, "declared": None, "error": analysis.get("native_manifest_error")}


def _discovered_commands(analysis: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    def compact(items: Any) -> list[dict[str, Any]]:
        out = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            out.append({k: item.get(k) for k in ("kind", "command", "path", "evidence", "safety") if item.get(k) is not None})
        return out
    return {"entrypoints": compact(analysis.get("entrypoints")), "tests": compact(analysis.get("tests"))}


def _contract(module: str, analysis: dict[str, Any], endpoints: list[dict[str, Any]], fabric_present: bool) -> dict[str, Any]:
    accepts, provides, cap_evidence = _capability_tokens(analysis)
    surface = _execution_surface(endpoints, fabric_present)
    return {
        "schema": SCHEMA,
        "module": module,
        "repository": analysis.get("repository"),
        "commit": analysis.get("commit"),
        "source_identity": analysis.get("source_record") or {},
        "source_integrity": {
            "donor_bytes_mutated_by_generator": False,
            "analysis_source": f"analysis/modules/{module}.json",
            "execution_source": "EXECUTION_FABRIC.json" if fabric_present else None,
        },
        "connective_tokens": {
            "accepts": accepts,
            "provides": provides,
            "status": "CANDIDATE_TOKEN_SURFACE_NOT_VERIFIED_INTEROP",
        },
        "capability_evidence_status_counts": cap_evidence,
        "native_manifest": _native_manifest_summary(analysis),
        "discovered_commands": _discovered_commands(analysis),
        "execution_surface": surface,
        "uncertainties": list(analysis.get("uncertainties") or []),
        "roots": ROOTS,
        "authority": {
            "contract_grants_execution": False,
            "contract_grants_merge": False,
            "contract_grants_canon": False,
            "candidate_token_match_is_verified_connection": False,
        },
        "truth_boundary": (
            "This sidecar compresses already-observed module analysis and execution-fabric evidence. "
            "It does not execute donor code, mutate modules/, prove semantic interoperability from matching tokens, "
            "or upgrade declarations/candidates into verified callability."
        ),
    }


def generate(snapshot: str | Path) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    if root.is_symlink() or not (root / "modules").is_dir():
        raise ContractError("snapshot must be a real directory containing modules/")
    analyses = _module_analyses(root)
    endpoint_map, fabric = _execution_endpoints(root)
    out_dir = root / CONTRACT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    modules_summary = []
    provider_index: dict[str, list[str]] = collections.defaultdict(list)
    consumer_index: dict[str, list[str]] = collections.defaultdict(list)
    total_adapter_counts = collections.Counter()
    highest_counts = collections.Counter()

    for module in sorted(analyses, key=str.lower):
        contract = _contract(module, analyses[module], endpoint_map.get(module, []), fabric is not None)
        path = out_dir / f"{module}.json"
        _write_json(path, contract)
        for token in contract["connective_tokens"]["provides"]:
            provider_index[token].append(module)
        for token in contract["connective_tokens"]["accepts"]:
            consumer_index[token].append(module)
        total_adapter_counts.update(contract["execution_surface"]["adapter_status_counts"])
        highest_counts[contract["execution_surface"]["highest_observed_state"]] += 1
        modules_summary.append({
            "module": module,
            "repository": contract["repository"],
            "commit": contract["commit"],
            "contract_path": path.relative_to(root).as_posix(),
            "contract_sha256": _sha256(path),
            "highest_observed_state": contract["execution_surface"]["highest_observed_state"],
            "integration_states": contract["execution_surface"]["integration_states"],
            "endpoint_count": contract["execution_surface"]["endpoint_count"],
            "blocked_endpoint_count": contract["execution_surface"]["blocked_endpoint_count"],
            "actionable_endpoint_count": len(contract["execution_surface"]["actionable_endpoints"]),
            "native_manifest_present": contract["native_manifest"]["present"],
        })

    token_links = []
    for token in sorted(set(provider_index) & set(consumer_index)):
        providers = sorted(set(provider_index[token]), key=str.lower)
        consumers = sorted(set(consumer_index[token]), key=str.lower)
        pairs = sum(1 for p in providers for c in consumers if p != c)
        if pairs:
            token_links.append({
                "token": token,
                "providers": providers,
                "consumers": consumers,
                "cross_module_pair_count": pairs,
                "status": "CANDIDATE_TOKEN_MATCH_NOT_VERIFIED",
            })

    registry = {
        "schema": REGISTRY_SCHEMA,
        "module_count": len(modules_summary),
        "contract_count": len(modules_summary),
        "execution_fabric_present": fabric is not None,
        "execution_fabric_schema": (fabric or {}).get("schema") if isinstance(fabric, dict) else None,
        "summary": {
            "highest_observed_state_counts": dict(sorted(highest_counts.items())),
            "adapter_status_counts": dict(sorted(total_adapter_counts.items())),
            "candidate_cross_module_token_count": len(token_links),
            "native_manifest_module_count": sum(1 for m in modules_summary if m["native_manifest_present"]),
            "actionable_endpoint_count": sum(m["actionable_endpoint_count"] for m in modules_summary),
            "blocked_endpoint_count": sum(m["blocked_endpoint_count"] for m in modules_summary),
            "endpoint_count": sum(m["endpoint_count"] for m in modules_summary),
        },
        "modules": modules_summary,
        "candidate_token_links": token_links,
        "roots": ROOTS,
        "authority": {
            "registry_grants_execution": False,
            "registry_grants_merge": False,
            "registry_grants_canon": False,
            "candidate_token_links_are_verified": False,
        },
        "truth_boundary": (
            "Every selected module gets a deterministic sidecar derived from retained analysis and execution evidence. "
            "Token links are candidate provider/consumer seams only. Adapter states remain distinct; blocked declarations stay blocked."
        ),
    }
    _write_json(root / REGISTRY_NAME, registry)

    lines = [
        "# AXM Module Connective Contracts", "",
        f"Modules with sidecars: **{len(modules_summary)} / {len(analyses)}**", "",
        "This layer makes each selected module's observed provider/consumer tokens, discovered commands, execution evidence, and blockers machine-readable without editing donor module bytes.", "",
        "## Current evidence totals", "",
        f"- endpoints represented: **{registry['summary']['endpoint_count']}**",
        f"- actionable/non-blocked execution-fabric endpoints: **{registry['summary']['actionable_endpoint_count']}**",
        f"- blocked endpoints retained explicitly: **{registry['summary']['blocked_endpoint_count']}**",
        f"- candidate cross-module token seams: **{registry['summary']['candidate_cross_module_token_count']}** (not verified interoperability)", "",
        "## Highest observed module state", "",
    ]
    for state, count in sorted(highest_counts.items()):
        lines.append(f"- `{state}`: {count}")
    lines += ["", "## Truth boundary", "", registry["truth_boundary"], ""]
    (root / REPORT_NAME).write_text("\n".join(lines), encoding="utf-8")
    return registry


def verify(snapshot: str | Path) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    analyses = _module_analyses(root)
    registry_path = root / REGISTRY_NAME
    if not registry_path.is_file():
        raise ContractError(f"{REGISTRY_NAME} is missing")
    registry = _read_json(registry_path)
    errors = []
    if registry.get("module_count") != len(analyses):
        errors.append("module_count does not match analysis/modules")
    module_entries = registry.get("modules") or []
    if len(module_entries) != len(analyses):
        errors.append("registry module entry count mismatch")
    endpoint_total = 0
    for entry in module_entries:
        module = str(entry.get("module") or "")
        if module not in analyses:
            errors.append(f"unknown module entry: {module}")
            continue
        path = root / str(entry.get("contract_path") or "")
        try:
            path.resolve().relative_to(root)
        except ValueError:
            errors.append(f"contract path escapes snapshot: {module}")
            continue
        if not path.is_file():
            errors.append(f"contract missing: {module}")
            continue
        if _sha256(path) != entry.get("contract_sha256"):
            errors.append(f"contract hash mismatch: {module}")
        contract = _read_json(path)
        if contract.get("repository") != analyses[module].get("repository") or contract.get("commit") != analyses[module].get("commit"):
            errors.append(f"source identity mismatch: {module}")
        endpoint_total += int((contract.get("execution_surface") or {}).get("endpoint_count") or 0)
        if (contract.get("authority") or {}).get("candidate_token_match_is_verified_connection") is not False:
            errors.append(f"candidate token authority boundary missing: {module}")
    fabric_path = root / "EXECUTION_FABRIC.json"
    if fabric_path.is_file():
        fabric = _read_json(fabric_path)
        if endpoint_total != len(fabric.get("endpoints") or []):
            errors.append("sidecar endpoint accounting does not equal EXECUTION_FABRIC endpoint count")
    if any(link.get("status") != "CANDIDATE_TOKEN_MATCH_NOT_VERIFIED" for link in registry.get("candidate_token_links") or []):
        errors.append("candidate token link silently promoted")
    return {
        "schema": "axm.monolith.module-connective-contract-selftest/v0.1",
        "status": "PASS" if not errors else "HOLD",
        "module_count": len(analyses),
        "contract_count": len(module_entries),
        "endpoint_count_accounted": endpoint_total,
        "errors": errors,
        "donor_mutation_performed": False,
        "truth_boundary": "PASS verifies generated sidecar identity, hashes, endpoint accounting, and candidate-link non-promotion only; it does not prove module interoperability or runtime success.",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate AXM per-module connective sidecars")
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    try:
        if not args.verify:
            generate(args.snapshot)
        result = verify(args.snapshot)
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
