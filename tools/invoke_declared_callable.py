#!/usr/bin/env python3
"""Explicitly invoke one source-declared callable from a materialized AXM snapshot.

v0.2 supports explicitly opted-in `module-export` callables for two runtimes:

- `javascript-esm`
- `python`

Invocation is never performed during assembly or registry generation.  The tool never uses
a shell.  A source declaration still grants no permission to execute by itself.

Truth boundary: a successful receipt proves only that the exact captured source export ran
for the exact supplied JSON arguments in this environment. It grants no merge/CANON,
installation, network, risk-acceptance, safety, quality, or cross-capability authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

REQUEST_SCHEMA = "axm.callable-invocation-request/v0.1"
RECEIPT_SCHEMA = "axm.monolith.callable-invocation-receipt/v0.1"
REGISTRY_SCHEMA = "axm.monolith.callable-capability-registry/v0.1"


class InvocationError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvocationError(f"cannot read valid JSON: {path}") from exc


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _safe_target(snapshot: Path, module: str, relative: str) -> Path:
    modules_root = (snapshot / "modules").resolve()
    module_root = (modules_root / module).resolve()
    try:
        module_root.relative_to(modules_root)
    except ValueError as exc:
        raise InvocationError("module path escapes snapshot") from exc
    if not module_root.is_dir() or module_root.is_symlink():
        raise InvocationError(f"module directory is missing or unsafe: {module}")
    if not isinstance(relative, str) or not relative:
        raise InvocationError("callable path is missing")
    target = (module_root / relative).resolve()
    try:
        target.relative_to(module_root)
    except ValueError as exc:
        raise InvocationError("callable target escapes source module") from exc
    if not target.is_file() or target.is_symlink():
        raise InvocationError("callable target is missing or symlinked")
    return target


def _base_receipt(entry: dict[str, Any], request: Any) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "address": entry.get("address"),
        "module": entry.get("module"),
        "capability": entry.get("capability"),
        "manifest_sha256": entry.get("manifest_sha256"),
        "request_sha256": _canonical_sha256(request),
        "source_capability_execution": False,
        "truth_boundary": (
            "This receipt is scoped to one explicit invocation of one captured source callable. "
            "It grants no merge/CANON, installation, network, risk-acceptance, safety, quality, "
            "or unrelated-capability authority."
        ),
    }


def _runtime_command(
    descriptor: dict[str, Any],
    target: Path,
    *,
    allow_javascript_esm: bool,
    allow_python: bool,
    node_command: str,
    python_command: str,
) -> tuple[list[str] | None, str | None]:
    runtime = descriptor.get("runtime")
    export_name = str(descriptor.get("export") or "")
    tools = Path(__file__).resolve().parent

    if runtime == "javascript-esm":
        if not allow_javascript_esm:
            return None, "blocked_explicit_execution_opt_in_required"
        node = shutil.which(node_command)
        if not node:
            return None, "blocked_missing_javascript_runtime"
        runner = tools / "js_callable_runner.mjs"
        if not runner.is_file():
            raise InvocationError("JavaScript callable runner is missing")
        return [node, str(runner), str(target), export_name], None

    if runtime == "python":
        if not allow_python:
            return None, "blocked_explicit_execution_opt_in_required"
        python = shutil.which(python_command)
        if not python:
            return None, "blocked_missing_python_runtime"
        runner = tools / "python_callable_runner.py"
        if not runner.is_file():
            raise InvocationError("Python callable runner is missing")
        return [python, str(runner), str(target), export_name], None

    return None, "blocked_unsupported_callable_runtime"


def invoke_declared_callable(
    snapshot: str | Path,
    address: str,
    request: Any,
    *,
    allow_javascript_esm: bool = False,
    allow_python: bool = False,
    node_command: str = "node",
    python_command: str = sys.executable,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    registry_path = root / "CALLABLE_CAPABILITY_REGISTRY.json"
    registry = _read_json(registry_path)
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise InvocationError("unsupported callable registry schema")

    entries = [entry for entry in registry.get("entries", []) if entry.get("address") == address]
    if len(entries) != 1:
        raise InvocationError(f"expected exactly one callable registry entry for {address}")
    entry = entries[0]
    receipt = _base_receipt(entry, request)

    if entry.get("status") != "declared_callable_not_exercised" or entry.get("errors"):
        receipt.update(status="blocked_registry_entry_not_callable", errors=entry.get("errors") or [])
        return receipt

    descriptor = entry.get("callable") or {}
    receipt["declared_callable"] = descriptor
    if descriptor.get("authority") != "none":
        receipt.update(status="blocked_callable_authority_claim")
        return receipt
    if descriptor.get("kind") != "module-export":
        receipt.update(status="blocked_unsupported_callable_kind")
        return receipt

    if not isinstance(request, dict) or request.get("schema") != REQUEST_SCHEMA or not isinstance(request.get("args"), list):
        receipt.update(status="blocked_invalid_invocation_request")
        return receipt

    target = _safe_target(root, str(entry.get("module") or ""), descriptor.get("path"))
    command, blocked_status = _runtime_command(
        descriptor,
        target,
        allow_javascript_esm=allow_javascript_esm,
        allow_python=allow_python,
        node_command=node_command,
        python_command=python_command,
    )
    if blocked_status:
        receipt.update(status=blocked_status)
        return receipt
    assert command is not None

    receipt["source_file"] = target.relative_to(root / "modules" / str(entry.get("module"))).as_posix()
    receipt["source_file_sha256"] = _sha256_file(target)
    receipt["export"] = descriptor.get("export")
    receipt["runtime"] = descriptor.get("runtime")

    try:
        completed = subprocess.run(
            command,
            input=json.dumps(request, separators=(",", ":"), ensure_ascii=False),
            text=True,
            capture_output=True,
            cwd=str(target.parent),
            timeout=float(timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired:
        receipt.update(status="source_execution_timeout", exit_code=None)
        return receipt

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    receipt["exit_code"] = completed.returncode
    if stderr:
        receipt["stderr"] = stderr[:4000]
    try:
        response = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        receipt.update(status="source_execution_invalid_response", stdout=stdout[:4000])
        return receipt

    receipt["response_sha256"] = _canonical_sha256(response)
    receipt["response"] = response
    if completed.returncode == 0 and isinstance(response, dict) and response.get("ok") is True:
        receipt.update(
            status="exercised_with_receipt",
            source_capability_execution=True,
            result=response.get("result"),
        )
        return receipt

    receipt.update(status="source_execution_failed")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicitly invoke one source-declared AXM callable")
    parser.add_argument("snapshot", help="materialized snapshot root containing CALLABLE_CAPABILITY_REGISTRY.json")
    parser.add_argument("address", help="exact module::capability address")
    parser.add_argument("--request", required=True, help="JSON invocation request file")
    parser.add_argument("--receipt", required=True, help="path for the invocation receipt")
    parser.add_argument("--allow-javascript-esm", action="store_true", help="explicitly permit JavaScript ESM source execution")
    parser.add_argument("--allow-python", action="store_true", help="explicitly permit Python source execution")
    parser.add_argument("--node", default="node", help="Node.js executable name/path")
    parser.add_argument("--python", default=sys.executable, help="Python executable name/path")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    request = _read_json(Path(args.request))
    try:
        receipt = invoke_declared_callable(
            args.snapshot,
            args.address,
            request,
            allow_javascript_esm=args.allow_javascript_esm,
            allow_python=args.allow_python,
            node_command=args.node,
            python_command=args.python,
            timeout_seconds=args.timeout,
        )
    except InvocationError as exc:
        print(f"declared callable invocation: BLOCKED: {exc}")
        return 2

    target = Path(args.receipt)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"address": receipt.get("address"), "status": receipt.get("status")}, sort_keys=True))
    return 0 if receipt.get("status") == "exercised_with_receipt" else 3


if __name__ == "__main__":
    raise SystemExit(main())
