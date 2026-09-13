#!/usr/bin/env python3
"""Run one explicitly selected Python file export for AXM callable invocation.

This helper is intentionally tiny.  It receives the exact source file and export name as
argv, reads one JSON request on stdin, imports only that source file under an isolated
module name, invokes the export with positional JSON arguments, and emits one JSON result.
It is not used during assembly or capability discovery.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import traceback

REQUEST_SCHEMA = "axm.callable-invocation-request/v0.1"


def emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def fail(message: str, name: str = "Error") -> int:
    emit({"ok": False, "error": {"name": name, "message": message}})
    return 3


def main() -> int:
    if len(sys.argv) != 3:
        return fail("target path and export name are required", "TypeError")
    target = Path(sys.argv[1]).resolve()
    export_name = sys.argv[2]
    try:
        request = json.loads(sys.stdin.read())
        if not isinstance(request, dict) or request.get("schema") != REQUEST_SCHEMA:
            return fail("unsupported callable invocation request schema", "TypeError")
        args = request.get("args")
        if not isinstance(args, list):
            return fail("request.args must be an array", "TypeError")

        module_name = f"_axm_declared_callable_{target.stem}_{abs(hash(str(target)))}"
        spec = importlib.util.spec_from_file_location(module_name, target)
        if spec is None or spec.loader is None:
            return fail("could not load declared Python source file", "ImportError")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        callable_obj = getattr(module, export_name, None)
        if not callable(callable_obj):
            return fail(f"declared export is not callable: {export_name}", "TypeError")
        result = callable_obj(*args)
        emit({"ok": True, "result": result})
        return 0
    except Exception as exc:  # receipt boundary intentionally catches source exceptions
        # Do not leak an unbounded traceback into the machine-readable channel.
        message = str(exc) or exc.__class__.__name__
        _ = traceback.format_exc(limit=2)
        return fail(message, exc.__class__.__name__)


if __name__ == "__main__":
    raise SystemExit(main())
