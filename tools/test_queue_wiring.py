#!/usr/bin/env python3
"""Deterministic test-queue wiring learned from the current AXM totality build.

This corrects three exact generated-test invocation gaps observed while wiring the selected
monolith. It only changes generated monolith metadata/runtime contracts, never donor bytes:

1. ``src/`` Python layouts: annotate a generic unittest command so an executor may retry the
   same command with ``src`` prepended to PYTHONPATH *only after* a real import failure in a
   disposable copy.
2. Nonstandard unittest filenames: if default ``test*.py`` discovery has no target but files
   under ``tests/`` explicitly call ``unittest.main(...)``, replace the known-zero discovery
   command with an exact named-unittest command.
3. Missing ``tests/`` directory: if the inspector inferred Python tests from explicit
   ``test_*.py``/``*_test.py`` files elsewhere, replace the impossible ``-s tests`` command
   with bounded direct execution of only those files that explicitly call ``unittest.main``.

A generated test command is still only a test candidate until separately executed. Passing
it is test evidence, not product execution, interoperability, authority, or CANON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ANALYSIS_NAME = "STACK_ANALYSIS.json"
QUEUE_NAME = "AUTOMATED_TEST_QUEUE.json"
RECEIPT_NAME = "TEST_QUEUE_WIRING_RECEIPT.json"
GENERIC_UNITTEST = "python -m unittest discover -s tests -v"
MAX_EXPLICIT_UNITTEST_TARGETS = 16


class WiringError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WiringError(f"missing required file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise WiringError(f"invalid JSON in {path.name}: {exc}") from exc


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
        raise WiringError(f"module path escapes snapshot: {module}") from exc
    if candidate.is_symlink() or not candidate.is_dir():
        raise WiringError(f"module directory missing or unsafe: {module}")
    return candidate


def _contains_unittest_main(path: Path) -> bool:
    try:
        return "unittest.main(" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _named_unittest_modules(module_root: Path) -> list[str]:
    tests = module_root / "tests"
    if not tests.is_dir() or tests.is_symlink():
        return []
    if any(path.is_file() and not path.is_symlink() for path in tests.rglob("test*.py")):
        return []
    result: list[str] = []
    for path in sorted(tests.rglob("*.py")):
        if not path.is_file() or path.is_symlink() or not _contains_unittest_main(path):
            continue
        result.append(".".join(path.relative_to(module_root).with_suffix("").parts))
        if len(result) >= MAX_EXPLICIT_UNITTEST_TARGETS:
            break
    return result


def _direct_unittest_scripts(module_root: Path) -> list[str]:
    tests = module_root / "tests"
    if tests.exists():
        return []
    candidates = sorted({*module_root.rglob("test_*.py"), *module_root.rglob("*_test.py")})
    result: list[str] = []
    for path in candidates:
        if not path.is_file() or path.is_symlink() or not _contains_unittest_main(path):
            continue
        result.append(path.relative_to(module_root).as_posix())
        if len(result) >= MAX_EXPLICIT_UNITTEST_TARGETS:
            break
    return result


def _src_environment() -> dict[str, Any]:
    return {
        "retry_on_import_failure": True,
        "PYTHONPATH_prepend": "src",
        "scope": "disposable-test-copy-only",
    }


def _named_command(modules: list[str]) -> str:
    return "python -m unittest -v " + " ".join(modules)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("module") or ""), str(item.get("command") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _transform_items(items: list[Any], module: str, module_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    named = _named_unittest_modules(module_root)
    direct = _direct_unittest_scripts(module_root)
    out: list[dict[str, Any]] = []
    info: dict[str, Any] = {"src_annotated": False, "named": [], "direct": []}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if item.get("command") != GENERIC_UNITTEST:
            out.append(item)
            continue
        if (module_root / "src").is_dir():
            item["execution_environment"] = _src_environment()
            info["src_annotated"] = True
        if named:
            item.update({
                "command": _named_command(named),
                "kind": "test-suite",
                "evidence": "generated-nonstandard-unittest-main",
                "safety": "executes exact unittest.main source modules in an isolated copied workspace",
            })
            info["named"] = named
            out.append(item)
        elif direct:
            info["direct"] = direct
            for rel in direct:
                replacement = dict(item)
                replacement.update({
                    "command": f"python {rel}",
                    "kind": "test-suite",
                    "evidence": "generated-direct-unittest-script",
                    "safety": "executes one exact unittest.main source file in an isolated copied workspace",
                })
                out.append(replacement)
        else:
            out.append(item)
    return _dedupe(out), info


def apply(snapshot: str | Path) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    if root.is_symlink() or not root.is_dir() or not (root / "modules").is_dir():
        raise WiringError("snapshot must be one real directory containing modules/")
    analysis = _read_json(root / ANALYSIS_NAME)
    queue_doc = _read_json(root / QUEUE_NAME)
    profiles = analysis.get("modules")
    queue = queue_doc.get("queue")
    if not isinstance(profiles, list) or not isinstance(queue, list):
        raise WiringError("analysis/test queue shape is invalid")

    donor_hashes: dict[str, dict[str, str]] = {}
    profile_info: dict[str, dict[str, Any]] = {}
    queue_by_module: dict[str, list[dict[str, Any]]] = {}
    for item in queue:
        if isinstance(item, dict):
            queue_by_module.setdefault(str(item.get("module") or ""), []).append(item)

    new_queue: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        module = str(profile.get("module") or "")
        if not module:
            continue
        module_root = _safe_module_root(root, module)
        donor_hashes[module] = {
            p.relative_to(module_root).as_posix(): _sha256(p)
            for p in module_root.rglob("*") if p.is_file() and not p.is_symlink()
        }
        transformed_profile, info = _transform_items(
            profile.get("tests", []) if isinstance(profile.get("tests"), list) else [], module, module_root
        )
        profile["tests"] = [{k: v for k, v in item.items() if k not in {"module", "status"}} for item in transformed_profile]
        transformed_queue, queue_info = _transform_items(queue_by_module.get(module, []), module, module_root)
        new_queue.extend(transformed_queue)
        info["src_annotated"] = bool(info["src_annotated"] or queue_info["src_annotated"])
        info["named"] = info["named"] or queue_info["named"]
        info["direct"] = info["direct"] or queue_info["direct"]
        profile_info[module] = info

    known = set(profile_info)
    for item in queue:
        if not isinstance(item, dict) or str(item.get("module") or "") not in known:
            if isinstance(item, dict):
                new_queue.append(dict(item))
    new_queue = _dedupe(new_queue)
    new_queue.sort(key=lambda item: (str(item.get("module") or ""), str(item.get("command") or "")))
    queue_doc["queue"] = new_queue
    analysis["automated_test_queue"] = new_queue
    _write_json(root / ANALYSIS_NAME, analysis)
    _write_json(root / QUEUE_NAME, queue_doc)

    for module, before in donor_hashes.items():
        module_root = _safe_module_root(root, module)
        after = {
            p.relative_to(module_root).as_posix(): _sha256(p)
            for p in module_root.rglob("*") if p.is_file() and not p.is_symlink()
        }
        if before != after:
            raise WiringError(f"donor bytes changed while wiring test queue: {module}")

    src = sorted(module for module, info in profile_info.items() if info["src_annotated"])
    named = [
        {"module": module, "unittest_modules": info["named"], "command": _named_command(info["named"])}
        for module, info in sorted(profile_info.items()) if info["named"]
    ]
    direct = [
        {"module": module, "scripts": info["direct"]}
        for module, info in sorted(profile_info.items()) if info["direct"]
    ]
    receipt = {
        "schema": "axm.monolith.learned-test-queue-wiring/v0.2",
        "status": "PASS",
        "src_layout_retry_candidate_count": len(src),
        "src_layout_retry_candidates": src,
        "zero_discovery_named_replacement_count": len(named),
        "zero_discovery_named_replacements": named,
        "missing_tests_dir_direct_replacement_count": len(direct),
        "missing_tests_dir_direct_replacements": direct,
        "donor_bytes_unchanged": True,
        "truth_boundary": (
            "This learned rule corrects generated test invocation metadata only. Src-layout retry is permitted only after an actual import failure in a disposable copy; "
            "replacement test commands come only from exact source files with unittest.main. No rule proves a test passes, semantic correctness, interoperability, product acceptance, authority, or CANON."
        ),
    }
    _write_json(root / RECEIPT_NAME, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply learned AXM test-queue wiring")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = apply(args.snapshot)
    except (WiringError, OSError, ValueError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
