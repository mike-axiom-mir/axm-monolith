from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "export_machine_voice_state.py"
SPEC = importlib.util.spec_from_file_location("export_machine_voice_state", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class MachineVoiceStateExportTests(unittest.TestCase):
    def test_checked_in_assembly_config_emits_real_grounded_notice_snapshot(self):
        config_path = ROOT / "config" / "assembly.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIs(config["build_enabled"], False)
        self.assertTrue(config["hold_reason"].strip())

        snapshot = MODULE.export_from_config(config_path)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["schema"], "axm-machine-voice/notice-snapshot/0.1")
        self.assertEqual(snapshot["source"], {"kind": "module", "id": "axm-monolith"})
        self.assertEqual(snapshot["activity"], {"kind": "activity", "id": "assembly-control"})
        self.assertEqual(snapshot["next_operations"], ["inspect"])

        signal = snapshot["signal"]
        self.assertIs(signal["triggered"], True)
        self.assertEqual(signal["observation"], {"kind": "observation", "id": "assembly-build-held"})
        self.assertEqual(signal["rule"], {"kind": "notice-rule", "id": "assembly-build-hold-active-v0.1"})
        self.assertEqual(
            signal["observation_evidence"],
            {"kind": "evidence", "id": "config-assembly-json-build-enabled-false"},
        )
        self.assertEqual(set(snapshot), {"schema", "event_id", "source", "activity", "signal", "next_operations"})
        self.assertEqual(
            set(signal),
            {
                "observation",
                "rule",
                "subjects",
                "triggered",
                "observation_evidence",
                "rule_evidence",
                "trigger_evidence",
            },
        )

    def test_enabled_build_is_normal_silence(self):
        config = {"build_enabled": True, "hold_reason": "not relevant while enabled"}
        self.assertIsNone(MODULE.build_assembly_hold_notice(config))

    def test_false_build_requires_explicit_reason(self):
        for config in (
            {"build_enabled": False},
            {"build_enabled": False, "hold_reason": ""},
            {"build_enabled": False, "hold_reason": 123},
        ):
            with self.assertRaisesRegex(ValueError, "hold_reason"):
                MODULE.build_assembly_hold_notice(config)

    def test_build_enabled_must_be_boolean(self):
        for value in (None, 0, 1, "false"):
            with self.assertRaisesRegex(ValueError, "boolean"):
                MODULE.build_assembly_hold_notice({"build_enabled": value, "hold_reason": "x"})

    def test_hold_reason_change_changes_semantic_evidence_identity(self):
        first = MODULE.build_assembly_hold_notice({"build_enabled": False, "hold_reason": "reason A"})
        second = MODULE.build_assembly_hold_notice({"build_enabled": False, "hold_reason": "reason B"})
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(
            first["signal"]["trigger_evidence"]["id"],
            second["signal"]["trigger_evidence"]["id"],
        )
        self.assertNotEqual(first["signal"]["subjects"][1]["id"], second["signal"]["subjects"][1]["id"])

    def test_write_json_creates_machine_readable_snapshot(self):
        snapshot = MODULE.build_assembly_hold_notice({"build_enabled": False, "hold_reason": "bounded hold"})
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "MACHINE_VOICE_NOTICE.json"
            MODULE.write_json(path, snapshot)
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, snapshot)


if __name__ == "__main__":
    unittest.main()
