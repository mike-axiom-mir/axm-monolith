#!/usr/bin/env python3
"""Collect source-declared callable capability descriptors from an AXM snapshot.

This tool does not execute source capability code.  It only validates and preserves a
small native declaration contract so a later execution fabric can distinguish
"a source identified a callable surface" from "Monolith guessed one".

Truth boundary: a valid declaration remains declared_callable_not_exercised.  It grants
no execution, merge, CANON, installation, network, device, or risk-acceptance authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

REGISTRY_SCHEMA = "axm.monolith.callable-capability-registry/v0.1"
CALLABLE_SCHEMA = "axm.callable-capability/v0.1"
MANIFEST_NAMES = ("AXM_MODULE.json", "axm-module.json", ".axm/module.json")
SAFE_EXPORT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
VALID_KINDS = {"module-export", "command"}


class CallableRegistryError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CallableRegistryError(f"cannot read valid JSON: {path}") from exc


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(module_dir: Path) -> tuple[Path | None, dict[str, Any] | None]:
    for name in MANIFEST_NAMES:
        path = module_dir / name
        if not path.is_file():
            continue
        value = _read_json(path)
        if not isinstance(value, dict):
            raise CallableRegistryError(f"native manifest must be an object: {path}")
        return path, value
    return None, None


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return None
    text = value.replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    if re.match(r"^[A-Za-z]:", text):
        return None
    return path.as_posix()


def validate_callable(module_dir: Path, raw: Any) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ["callable descriptor must be an object"]

    schema = raw.get("schema")
    kind = raw.get("kind")
    runtime = raw.get("runtime")
    authority = raw.get("authority")
    if schema != CALLABLE_SCHEMA:
        errors.append(f"schema must be {CALLABLE_SCHEMA}")
    if kind not in VALID_KINDS:
        errors.append("kind must be module-export or command")
    if not isinstance(runtime, str) or not runtime.strip():
        errors.append("runtime must be a non-empty string")
    if authority != "none":
        errors.append("authority must be exactly none")

    normalized: dict[str, Any] = {
        "schema": schema,
        "kind": kind,
        "runtime": runtime,
        "authority": authority,
    }
    for field in ("input_contract", "output_contract", "network", "notes"):
        if field in raw:
            normalized[field] = raw[field]

    if kind == "module-export":
        relative = _safe_relative_path(raw.get("path"))
        symbol = raw.get("export")
        if relative is None:
            errors.append("module-export path must be a safe repository-relative path")
        elif not (module_dir / relative).is_file():
            errors.append(f"module-export path does not exist: {relative}")
        if not isinstance(symbol, str) or not SAFE_EXPORT.fullmatch(symbol):
            errors.append("module-export export must be a simple symbol name")
        normalized["path"] = relative if relative is not None else raw.get("path")
        normalized["export"] = symbol
    elif kind == "command":
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            errors.append("command must be a non-empty string without NUL bytes")
        normalized["command"] = command
        if "path" in raw:
            relative = _safe_relative_path(raw.get("path"))
            if relative is None:
                errors.append("command path must be a safe repository-relative path when supplied")
            elif not (module_dir / relative).exists():
                errors.append(f"command path does not exist: {relative}")
            normalized["path"] = relative if relative is not None else raw.get("path")

    allowed = {
        "schema", "kind", "runtime", "path", "export", "command",
        "input_contract", "output_contract", "authority", "network", "notes",
    }
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        errors.append("unknown callable fields: " + ", ".join(unknown))

    return normalized, errors


def build_registry(build_root: str | Path) -> dict[str, Any]:
    root = Path(build_root).resolve()
    modules_root = root / "modules"
    if not modules_root.is_dir():
        raise CallableRegistryError("build must contain a modules directory")

    entries: list[dict[str, Any]] = []
    modules_scanned = 0
    manifests_seen = 0
    for module_dir in sorted((path for path in modules_root.iterdir() if path.is_dir()), key=lambda path: path.name.lower()):
        modules_scanned += 1
        manifest_path, manifest = _manifest(module_dir)
        if manifest_path is None or manifest is None:
            continue
        manifests_seen += 1
        capabilities = manifest.get("capabilities", [])
        if not isinstance(capabilities, list):
            continue
        for index, capability in enumerate(capabilities):
            if not isinstance(capability, dict) or "callable" not in capability:
                continue
            capability_id = str(capability.get("id") or capability.get("name") or f"native.{index}")
            descriptor, errors = validate_callable(module_dir, capability.get("callable"))
            entries.append({
                "address": f"{module_dir.name}::{capability_id}",
                "module": module_dir.name,
                "capability": capability_id,
                "manifest": manifest_path.relative_to(module_dir).as_posix(),
                "manifest_sha256": _sha256(manifest_path),
                "status": "blocked_invalid_callable_declaration" if errors else "declared_callable_not_exercised",
                "source_capability_execution": False,
                "callable": descriptor,
                "errors": errors,
            })

    entries.sort(key=lambda item: item["address"].lower())
    valid = sum(entry["status"] == "declared_callable_not_exercised" for entry in entries)
    invalid = len(entries) - valid
    return {
        "schema": REGISTRY_SCHEMA,
        "source": "native-module-manifests",
        "summary": {
            "modules_scanned": modules_scanned,
            "native_manifests_seen": manifests_seen,
            "callable_declaration_count": len(entries),
            "declared_callable_not_exercised": valid,
            "blocked_invalid_callable_declaration": invalid,
        },
        "entries": entries,
        "truth_boundary": (
            "This registry preserves source-declared callable surfaces only. A declaration is not execution evidence, "
            "interoperability proof, permission, authority, safety acceptance, or CANON. A later execution fabric must "
            "validate and exercise an exact binding before source_capability_execution can become true."
        ),
    }


def write_registry(build_root: str | Path, output: str | Path | None = None, *, strict: bool = False) -> dict[str, Any]:
    root = Path(build_root).resolve()
    registry = build_registry(root)
    target = Path(output) if output is not None else root / "CALLABLE_CAPABILITY_REGISTRY.json"
    if not target.is_absolute():
        target = root / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if strict and registry["summary"]["blocked_invalid_callable_declaration"]:
        raise CallableRegistryError("invalid callable declarations were found; registry written with blocked entries")
    return registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preserve native AXM callable capability declarations without executing them")
    parser.add_argument("build", help="materialized AXM build root containing modules/")
    parser.add_argument("--output", help="output path (default: CALLABLE_CAPABILITY_REGISTRY.json in build root)")
    parser.add_argument("--strict", action="store_true", help="exit nonzero after writing when invalid declarations are present")
    args = parser.parse_args(argv)
    try:
        registry = write_registry(args.build, args.output, strict=args.strict)
    except CallableRegistryError as exc:
        print(f"callable registry: BLOCKED: {exc}")
        return 2
    print(json.dumps(registry["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
