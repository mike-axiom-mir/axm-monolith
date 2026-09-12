#!/usr/bin/env python3
"""Import one AXM Invariant Lab counterexample packet as read-only Monolith evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SOURCE_SCHEMA = "axm.invariant-lab.counterexample/v0.1"
OUTPUT_SCHEMA = "axm.monolith.invariant-evidence-import/v0.1"
TOP_KEYS = {"schema", "model", "claim", "status", "bound", "invariant", "trace", "limitations", "authority"}
AUTHORITY_KEYS = {"merge", "canon", "execution", "promotion"}


class PacketError(ValueError):
    pass


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PacketError(f"{name} must be a non-empty string")
    return value


def validate_packet(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise PacketError("packet must be an object")
    missing = TOP_KEYS - set(packet)
    extra = set(packet) - TOP_KEYS
    if missing:
        raise PacketError("missing fields: " + ", ".join(sorted(missing)))
    if extra:
        raise PacketError("unexpected fields: " + ", ".join(sorted(extra)))
    if packet["schema"] != SOURCE_SCHEMA:
        raise PacketError("unsupported source schema")
    for key in ("model", "claim", "invariant"):
        _nonempty(packet[key], key)
    if packet["status"] not in {"FAIL", "HOLD"}:
        raise PacketError("status must be FAIL or HOLD")
    if isinstance(packet["bound"], bool) or not isinstance(packet["bound"], int) or packet["bound"] < 0:
        raise PacketError("bound must be an integer >= 0")
    limitations = packet["limitations"]
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise PacketError("limitations must be an array of strings")
    authority = packet["authority"]
    if not isinstance(authority, dict) or set(authority) != AUTHORITY_KEYS:
        raise PacketError("authority must contain exactly merge/canon/execution/promotion")
    if any(authority[key] is not False for key in sorted(AUTHORITY_KEYS)):
        raise PacketError("counterexample packet must grant no authority")
    trace = packet["trace"]
    if not isinstance(trace, list):
        raise PacketError("trace must be an array")
    for index, step in enumerate(trace):
        if not isinstance(step, dict) or set(step) != {"transition", "before", "after"}:
            raise PacketError(f"trace[{index}] must contain exactly transition/before/after")
        if not isinstance(step["transition"], str):
            raise PacketError(f"trace[{index}].transition must be a string")
        if not isinstance(step["before"], dict) or not isinstance(step["after"], dict):
            raise PacketError(f"trace[{index}] before/after must be objects")
    return packet


def import_packet_bytes(raw: bytes) -> dict[str, Any]:
    try:
        packet = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PacketError(f"invalid UTF-8 JSON: {exc}") from exc
    validate_packet(packet)
    return {
        "schema": OUTPUT_SCHEMA,
        "sourceSchema": SOURCE_SCHEMA,
        "sourceSha256": hashlib.sha256(raw).hexdigest(),
        "status": packet["status"],
        "model": packet["model"],
        "invariant": packet["invariant"],
        "claim": packet["claim"],
        "bound": packet["bound"],
        "traceLength": len(packet["trace"]),
        "limitations": list(packet["limitations"]),
        "effect": "evidence_only_no_pipeline_status_change",
        "authority": {
            "execution": False,
            "merge": False,
            "canon": False,
            "promotion": False,
            "installation": False,
        },
        "truthBoundary": "The packet is external bounded evidence only. Import does not prove donor runtime behavior, verify a pipeline, authorize action, or change Monolith candidate statuses.",
    }


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import AXM Invariant Lab counterexample evidence without granting authority")
    parser.add_argument("packet", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = import_packet_bytes(args.packet.read_bytes())
    except (OSError, PacketError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    text = stable_json(result)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
