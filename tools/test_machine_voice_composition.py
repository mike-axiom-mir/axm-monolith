#!/usr/bin/env python3
"""Run the first local AXM Monolith -> Machine Voice composition proof.

This tool keeps repository authority boundaries intact:
- Monolith exports only its explicit checked-in assembly-control state.
- Machine Voice remains a separate sibling/staged module and consumes the exported snapshot
  through its public zero-install machine channel.
- A fresh NOTICE emission proves this exact local runtime path executed.
- A later duplicate_semantic_event rejection also counts as a healthy composition result
  because the persistent Machine Voice journal is correctly suppressing repeat speech.
- If Monolith exports silence, this command reports the path as not exercised rather than
  inventing a communication event.
- This tool does not release the assembly hold, copy repository mains, or grant authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from export_machine_voice_state import export_from_config, write_json


ROOT = Path(__file__).resolve().parents[1]
RESULT_SCHEMA = "axm.monolith.machine-voice-composition-result/v0.1"
MACHINE_CHANNEL_PROTOCOL = "axm-machine-voice/machine-channel/0.1"
ACTIVE_REF = "activity:assembly-control"
EXPECTED_KIND = "notice"
EXPECTED_SOURCE = {"kind": "module", "id": "axm-monolith"}
DEFAULT_OUTPUT_DIR = ROOT / ".generated" / "machine-voice-composition"
DEFAULT_MACHINE_VOICE_ROOT = ROOT.parent / "axm-machine-voice"


def _write_result(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_single_json_object(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError(f"Machine Voice must emit exactly one non-empty stdout line, got {len(lines)}")
    value = json.loads(lines[0])
    if not isinstance(value, dict):
        raise ValueError("Machine Voice stdout must contain one JSON object")
    return value


def _validate_fresh_emission(snapshot: Mapping[str, Any], envelope: Mapping[str, Any]) -> None:
    packet = envelope.get("packet")
    if not isinstance(packet, Mapping):
        raise ValueError("emitted Machine Voice result is missing packet object")
    if packet.get("kind") != EXPECTED_KIND:
        raise ValueError(f"expected packet kind {EXPECTED_KIND!r}, got {packet.get('kind')!r}")
    if packet.get("event_id") != snapshot.get("event_id"):
        raise ValueError("Machine Voice packet event_id does not match exported Monolith snapshot")
    if packet.get("source") != EXPECTED_SOURCE:
        raise ValueError("Machine Voice packet source does not preserve module:axm-monolith")
    relevance = packet.get("relevance")
    if not isinstance(relevance, list) or {"kind": "activity", "id": "assembly-control"} not in relevance:
        raise ValueError("Machine Voice packet does not preserve assembly-control relevance")
    metadata = packet.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("producer") != "grounded-notice/0.1":
        raise ValueError("Machine Voice packet was not produced by grounded-notice/0.1")


def run_local_composition(
    *,
    config_path: Path,
    machine_voice_root: Path,
    output_dir: Path,
    python_executable: str = sys.executable,
    reset_journal: bool = False,
) -> dict[str, Any]:
    """Run the local composition and return a machine-readable evidence result.

    The caller receives a normal result for three healthy states:
    - verified_fresh_emission: Machine Voice emitted the real Monolith notice;
    - verified_duplicate_suppression: an earlier identical notice is in the journal;
    - not_exercised_no_snapshot: the current Monolith state legitimately exported silence.

    Other conditions raise instead of being converted into a plausible PASS.
    """

    config_path = config_path.resolve()
    machine_voice_root = machine_voice_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result_path = output_dir / "MACHINE_VOICE_COMPOSITION_RESULT.json"
    snapshot_path = output_dir / "MACHINE_VOICE_NOTICE.json"
    journal_path = output_dir / "MACHINE_VOICE_COMMUNICATION.jsonl"

    snapshot = export_from_config(config_path)
    base_result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "config": str(config_path),
        "machine_voice_root": str(machine_voice_root),
        "active_ref": ACTIVE_REF,
        "snapshot_path": str(snapshot_path),
        "journal_path": str(journal_path),
        "result_path": str(result_path),
        "truth_boundary": (
            "Local process composition evidence only. A successful run proves this exported "
            "Monolith state was consumed by this local Machine Voice runtime; it does not "
            "grant merge/CANON/execution authority or verify unrelated AXM module composition."
        ),
    }

    if snapshot is None:
        result = {
            **base_result,
            "passed": True,
            "status": "not_exercised_no_snapshot",
            "composition_exercised": False,
            "fresh_speech_emitted": False,
            "duplicate_suppressed": False,
        }
        _write_result(result_path, result)
        return result

    write_json(snapshot_path, snapshot)

    launcher = machine_voice_root / "machine_voice.py"
    if not launcher.is_file():
        raise ValueError(f"Machine Voice launcher not found: {launcher}")

    if reset_journal and journal_path.exists():
        journal_path.unlink()

    command = [
        python_executable,
        str(launcher),
        "snapshot",
        str(snapshot_path),
        "--active-ref",
        ACTIVE_REF,
        "--journal",
        str(journal_path),
    ]
    completed = subprocess.run(
        command,
        cwd=str(machine_voice_root),
        capture_output=True,
        text=True,
        check=False,
    )
    envelope = _parse_single_json_object(completed.stdout)

    if envelope.get("protocol") != MACHINE_CHANNEL_PROTOCOL:
        raise ValueError("Machine Voice returned an unexpected machine-channel protocol")
    if completed.returncode != 0:
        raise ValueError(
            "Machine Voice process failed with exit code "
            f"{completed.returncode}: {envelope.get('error') or envelope.get('reasons')}"
        )
    if completed.stderr.strip():
        raise ValueError("Machine Voice wrote unexpected stderr during composition proof")

    status = envelope.get("status")
    if status == "emitted":
        _validate_fresh_emission(snapshot, envelope)
        verification = "verified_fresh_emission"
        fresh = True
        duplicate = False
    elif status == "rejected" and set(envelope.get("reasons") or []) == {"duplicate_semantic_event"}:
        verification = "verified_duplicate_suppression"
        fresh = False
        duplicate = True
    else:
        raise ValueError(
            "Exported triggered Monolith notice did not produce the expected Machine Voice "
            f"emission or duplicate suppression: status={status!r}, reasons={envelope.get('reasons')!r}"
        )

    result = {
        **base_result,
        "passed": True,
        "status": verification,
        "composition_exercised": True,
        "fresh_speech_emitted": fresh,
        "duplicate_suppressed": duplicate,
        "machine_channel": envelope,
        "expected_floorvoice_for_notice_kind": "I noticed something.",
        "floorvoice_mapping_reexecuted_by_this_runner": False,
    }
    _write_result(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the local Monolith -> Machine Voice composition proof in one command."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "assembly.json",
        help="Monolith assembly config (default: repository config/assembly.json).",
    )
    parser.add_argument(
        "--machine-voice-root",
        type=Path,
        default=DEFAULT_MACHINE_VOICE_ROOT,
        help="Local axm-machine-voice repository root (default: sibling ../axm-machine-voice).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Local generated evidence directory (default: .generated/machine-voice-composition).",
    )
    parser.add_argument(
        "--reset-journal",
        action="store_true",
        help="Explicitly remove only this proof journal before running, forcing a fresh-emission check.",
    )
    args = parser.parse_args()

    result_path = args.output_dir.resolve() / "MACHINE_VOICE_COMPOSITION_RESULT.json"
    try:
        result = run_local_composition(
            config_path=args.config,
            machine_voice_root=args.machine_voice_root,
            output_dir=args.output_dir,
            reset_journal=args.reset_journal,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        failed = {
            "schema": RESULT_SCHEMA,
            "passed": False,
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "truth_boundary": "Failure is reported as failure; this runner does not synthesize a successful composition result.",
        }
        _write_result(result_path, failed)
        print(json.dumps(failed, sort_keys=True, separators=(",", ":")))
        return 1

    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
