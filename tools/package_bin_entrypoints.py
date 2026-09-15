#!/usr/bin/env python3
"""Derive bounded Node CLI entrypoints from package.json `bin` declarations.

This rule was learned from the axm-102-grammer monolith wiring campaign. It is
intentionally small and fail-closed: only relative paths that resolve inside the
module and already exist as files are returned. Discovery is not execution;
callability still requires the normal native probe/evidence path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
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


def declared_node_bins(module_dir: str | Path, package: dict[str, Any]) -> list[dict[str, str]]:
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

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for name, target in declared:
        safe = _safe_existing_target(root, target)
        if safe is None or safe in seen:
            continue
        seen.add(safe)
        result.append({
            "kind": "node",
            "path": safe,
            "command": f"node {safe}",
            "evidence": f"declared-package-bin:{name}",
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
        "schema": "axm.monolith.package-bin-entrypoints/v0.1",
        "status": "PASS",
        "entrypoints": rows,
        "truth_boundary": "package.json bin declarations are structural evidence only; runtime callability requires separate probe/execution evidence.",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
