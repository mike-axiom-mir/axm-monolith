#!/usr/bin/env python3
"""Derive bounded Node CLI entrypoints from package.json `bin` declarations.

This rule was learned from real monolith wiring and is intentionally fail-closed:
only relative targets that resolve inside the module and already exist as files
are returned. Bin aliases that resolve to the same file are grouped. If the
package declares an AXM capability discovery command whose command name matches
one of those aliases, its remaining tokens become the bounded startup probe;
otherwise the candidate uses ``--help``. Discovery is not execution and does
not grant callability.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Any


def _safe_existing_target(module_dir: Path, raw_target: str) -> str | None:
    if not isinstance(raw_target, str) or not raw_target.strip():
        return None
    raw = raw_target.strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    root = module_dir.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    if not resolved.is_file():
        return None
    return resolved.relative_to(root).as_posix()


def _probe_for_aliases(package: dict[str, Any], aliases: list[str]) -> tuple[list[str], str]:
    capability = package.get("axmCapability")
    if not isinstance(capability, dict):
        return ["--help"], "default-help"
    entrypoints = capability.get("entrypoints")
    if not isinstance(entrypoints, dict):
        return ["--help"], "default-help"
    command = entrypoints.get("command")
    discovery = entrypoints.get("discoveryCommand")
    if not isinstance(command, str) or command not in aliases or not isinstance(discovery, str):
        return ["--help"], "default-help"
    try:
        tokens = shlex.split(discovery)
    except ValueError:
        return ["--help"], "default-help"
    if len(tokens) >= 2 and tokens[0] == command and tokens[1:]:
        return tokens[1:], "axmCapability.discoveryCommand"
    return ["--help"], "default-help"


def declared_node_bins(module_dir: str | Path, package: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(module_dir)
    raw_bin = package.get("bin")
    declared: list[tuple[str, str]] = []
    if isinstance(raw_bin, str):
        name = str(package.get("name") or "package-bin")
        declared.append((name, raw_bin))
    elif isinstance(raw_bin, dict):
        for name, target in sorted(raw_bin.items(), key=lambda item: str(item[0])):
            if isinstance(name, str) and isinstance(target, str):
                declared.append((name, target))

    grouped: dict[str, list[str]] = {}
    for name, target in declared:
        safe = _safe_existing_target(root, target)
        if safe is None:
            continue
        grouped.setdefault(safe, []).append(name)

    result: list[dict[str, Any]] = []
    for safe in sorted(grouped):
        aliases = sorted(set(grouped[safe]))
        probe_args, probe_source = _probe_for_aliases(package, aliases)
        result.append({
            "kind": "node",
            "path": safe,
            "command": f"node {safe}",
            "evidence": f"declared-package-bin:{aliases[0]}",
            "aliases": aliases,
            "probe_args": probe_args,
            "probe_source": probe_source,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit safe existing package.json bin entrypoints")
    parser.add_argument("module_dir", type=Path)
    args = parser.parse_args()
    package_path = args.module_dir / "package.json"
    if not package_path.is_file():
        print(json.dumps({"status": "HOLD", "reason": "package.json missing", "entrypoints": []}, indent=2))
        return 1
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": f"invalid package.json: {exc}", "entrypoints": []}, indent=2))
        return 1
    if not isinstance(package, dict):
        print(json.dumps({"status": "HOLD", "reason": "package.json root is not an object", "entrypoints": []}, indent=2))
        return 1
    rows = declared_node_bins(args.module_dir, package)
    print(json.dumps({
        "schema": "axm.monolith.package-bin-entrypoints/v0.2",
        "status": "PASS",
        "entrypoints": rows,
        "truth_boundary": "package.json bin declarations are structural evidence only; probe_args are bounded candidate probes, not runtime proof; callability requires a separate successful probe/execution receipt.",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
