from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from test_machine_voice_composition import (  # noqa: E402
    RESULT_SCHEMA,
    run_local_composition,
)


FAKE_TEMPLATE = r'''#!/usr/bin/env python3
import json
from pathlib import Path
import sys

MODE = {mode!r}
PROTOCOL = "axm-machine-voice/machine-channel/0.1"

snapshot = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
journal = Path(sys.argv[sys.argv.index("--journal") + 1])
journal.parent.mkdir(parents=True, exist_ok=True)
journal.write_text("fake-journal\n", encoding="utf-8")

if MODE == "emitted":
    result = {{
        "protocol": PROTOCOL,
        "status": "emitted",
        "reasons": [],
        "fingerprint": "fake-fingerprint",
        "packet": {{
            "event_id": snapshot["event_id"],
            "kind": "notice",
            "source": snapshot["source"],
            "relevance": [snapshot["activity"]],
            "metadata": {{"producer": "grounded-notice/0.1"}},
        }},
    }}
elif MODE == "duplicate":
    result = {{
        "protocol": PROTOCOL,
        "status": "rejected",
        "reasons": ["duplicate_semantic_event"],
        "fingerprint": "fake-fingerprint",
        "packet": None,
    }}
elif MODE == "no_candidate":
    result = {{
        "protocol": PROTOCOL,
        "status": "no_candidate",
        "reasons": ["fake"],
        "fingerprint": None,
        "packet": None,
    }}
elif MODE == "wrong_protocol":
    result = {{
        "protocol": "wrong/protocol",
        "status": "emitted",
        "reasons": [],
        "fingerprint": "fake-fingerprint",
        "packet": None,
    }}
else:
    raise SystemExit(9)

print(json.dumps(result, sort_keys=True, separators=(",", ":")))
'''


class MachineVoiceLocalCompositionTests(unittest.TestCase):
    def make_fake_machine_voice(self, base: Path, mode: str) -> Path:
        root = base / "axm-machine-voice"
        root.mkdir(parents=True)
        launcher = root / "machine_voice.py"
        launcher.write_text(FAKE_TEMPLATE.format(mode=mode), encoding="utf-8")
        return root

    def test_real_checked_in_monolith_hold_reaches_external_machine_process(self):
        with TemporaryDirectory() as temp:
            temp_root = Path(temp)
            machine_voice = self.make_fake_machine_voice(temp_root, "emitted")
            output = temp_root / "evidence"

            result = run_local_composition(
                config_path=ROOT / "config" / "assembly.json",
                machine_voice_root=machine_voice,
                output_dir=output,
            )

            self.assertEqual(result["schema"], RESULT_SCHEMA)
            self.assertTrue(result["passed"])
            self.assertTrue(result["composition_exercised"])
            self.assertTrue(result["fresh_speech_emitted"])
            self.assertEqual(result["status"], "verified_fresh_emission")
            self.assertEqual(result["machine_channel"]["packet"]["kind"], "notice")

            snapshot = json.loads((output / "MACHINE_VOICE_NOTICE.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["schema"], "axm-machine-voice/notice-snapshot/0.1")
            self.assertEqual(snapshot["source"], {"kind": "module", "id": "axm-monolith"})
            self.assertTrue((output / "MACHINE_VOICE_COMMUNICATION.jsonl").is_file())
            self.assertTrue((output / "MACHINE_VOICE_COMPOSITION_RESULT.json").is_file())

    def test_duplicate_suppression_is_a_verified_composition_result(self):
        with TemporaryDirectory() as temp:
            temp_root = Path(temp)
            machine_voice = self.make_fake_machine_voice(temp_root, "duplicate")
            result = run_local_composition(
                config_path=ROOT / "config" / "assembly.json",
                machine_voice_root=machine_voice,
                output_dir=temp_root / "evidence",
            )
            self.assertTrue(result["passed"])
            self.assertEqual(result["status"], "verified_duplicate_suppression")
            self.assertFalse(result["fresh_speech_emitted"])
            self.assertTrue(result["duplicate_suppressed"])

    def test_enabled_build_is_legitimate_silence_without_machine_voice_checkout(self):
        with TemporaryDirectory() as temp:
            temp_root = Path(temp)
            config = temp_root / "assembly.json"
            config.write_text(json.dumps({"build_enabled": True}), encoding="utf-8")
            result = run_local_composition(
                config_path=config,
                machine_voice_root=temp_root / "missing-machine-voice",
                output_dir=temp_root / "evidence",
            )
            self.assertTrue(result["passed"])
            self.assertFalse(result["composition_exercised"])
            self.assertEqual(result["status"], "not_exercised_no_snapshot")

    def test_missing_machine_voice_launcher_fails_closed_when_snapshot_exists(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "launcher not found"):
                run_local_composition(
                    config_path=ROOT / "config" / "assembly.json",
                    machine_voice_root=Path(temp) / "missing",
                    output_dir=Path(temp) / "evidence",
                )

    def test_unexpected_machine_voice_outcome_fails_closed(self):
        with TemporaryDirectory() as temp:
            temp_root = Path(temp)
            machine_voice = self.make_fake_machine_voice(temp_root, "no_candidate")
            with self.assertRaisesRegex(ValueError, "expected Machine Voice emission"):
                run_local_composition(
                    config_path=ROOT / "config" / "assembly.json",
                    machine_voice_root=machine_voice,
                    output_dir=temp_root / "evidence",
                )

    def test_wrong_machine_channel_protocol_fails_closed(self):
        with TemporaryDirectory() as temp:
            temp_root = Path(temp)
            machine_voice = self.make_fake_machine_voice(temp_root, "wrong_protocol")
            with self.assertRaisesRegex(ValueError, "unexpected machine-channel protocol"):
                run_local_composition(
                    config_path=ROOT / "config" / "assembly.json",
                    machine_voice_root=machine_voice,
                    output_dir=temp_root / "evidence",
                )

    def test_reset_journal_removes_only_proof_journal_before_runtime(self):
        with TemporaryDirectory() as temp:
            temp_root = Path(temp)
            machine_voice = self.make_fake_machine_voice(temp_root, "emitted")
            output = temp_root / "evidence"
            output.mkdir()
            journal = output / "MACHINE_VOICE_COMMUNICATION.jsonl"
            journal.write_text("old-proof-journal\n", encoding="utf-8")
            unrelated = output / "KEEP_ME.txt"
            unrelated.write_text("keep", encoding="utf-8")

            run_local_composition(
                config_path=ROOT / "config" / "assembly.json",
                machine_voice_root=machine_voice,
                output_dir=output,
                reset_journal=True,
            )

            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")
            self.assertEqual(journal.read_text(encoding="utf-8"), "fake-journal\n")


if __name__ == "__main__":
    unittest.main()
