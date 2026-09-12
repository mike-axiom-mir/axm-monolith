#!/usr/bin/env python3
"""Export grounded AXM Monolith state into a Machine Voice snapshot.

First integration target: the checked-in assembly hold state in config/assembly.json.

Truth boundary:
- this exporter does not run Machine Voice;
- it does not infer whether an assembly hold is good, bad, anomalous, or important;
- it emits only when `build_enabled` is explicitly false and a non-empty hold reason exists;
- the emitted object is shaped for `axm-machine-voice/notice-snapshot/0.1`;
- cross-repository runtime composition remains a separate verification step.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


NOTICE_SNAPSHOT_SCHEMA = "axm-machine-voice/notice-snapshot/0.1"
EXPORTER_RULE_ID = "assembly-build-hold-active-v0.1"
ACTIVITY_REF = {"kind": "activity", "id": "assembly-control"}
SOURCE_REF = {"kind": "module", "id": "axm-monolith"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _stable_id(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()[:16]


def build_assembly_hold_notice(config: dict[str, Any]) -> dict[str, Any] | None:
    """Return one strict Machine Voice notice snapshot for an explicit assembly hold.

    `None` is normal silence: it means the checked state does not satisfy this exact rule.
    """

    if not isinstance(config, dict):
        raise ValueError("assembly config must be a JSON object")

    build_enabled = config.get("build_enabled")
    if not isinstance(build_enabled, bool):
        raise ValueError("assembly config build_enabled must be a boolean")
    if build_enabled:
        return None

    hold_reason = config.get("hold_reason")
    if not isinstance(hold_reason, str) or not hold_reason.strip():
        raise ValueError("assembly hold requires a non-empty hold_reason")
    hold_reason = hold_reason.strip()

    reason_id = _stable_id(hold_reason)
    event_id = f"monolith-assembly-hold-{reason_id}"

    return {
        "schema": NOTICE_SNAPSHOT_SCHEMA,
        "event_id": event_id,
        "source": SOURCE_REF,
        "activity": ACTIVITY_REF,
        "signal": {
            "observation": {
                "kind": "observation",
                "id": "assembly-build-held",
            },
            "rule": {
                "kind": "notice-rule",
                "id": EXPORTER_RULE_ID,
            },
            "subjects": [
                {
                    "kind": "assembly-state",
                    "id": "build-enabled-false",
                },
                {
                    "kind": "assembly-hold-reason",
                    "id": reason_id,
                },
            ],
            "triggered": True,
            "observation_evidence": {
                "kind": "evidence",
                "id": "config-assembly-json-build-enabled-false",
            },
            "rule_evidence": {
                "kind": "evidence",
                "id": "export-machine-voice-state-assembly-hold-rule-v0.1",
            },
            "trigger_evidence": {
                "kind": "evidence",
                "id": f"config-assembly-json-hold-reason-{reason_id}",
            },
        },
        "next_operations": ["inspect"],
    }


def export_from_config(config_path: Path) -> dict[str, Any] | None:
    data = read_json(config_path)
    return build_assembly_hold_notice(data)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export current AXM Monolith assembly state as a strict Machine Voice notice snapshot."
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=Path("config/assembly.json"),
        help="Assembly config JSON (default: config/assembly.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the emitted snapshot to this file. Without --output, JSON is printed to stdout.",
    )
    args = parser.parse_args()

    snapshot = export_from_config(args.config)
    if snapshot is None:
        # Silence is part of the contract. No fake Machine Voice packet is emitted.
        return 0

    if args.output is not None:
        write_json(args.output, snapshot)
        print(args.output)
    else:
        print(json.dumps(snapshot, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
