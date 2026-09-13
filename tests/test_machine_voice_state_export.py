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
    def test_checked_in_enabled_assembly_config_is_normal_silence(self):
        config_path = ROOT / "config" / "assembly.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIs(config["build_enabled"], True)
        self.assertIsNone(config["hold_reason"])
        self.assertIsNone(MODULE.export_from_config(config_path))

    def test_enabled_build_is_normal_silence(self):
        config = {"build_enabled": True, "hold_reason": None}
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
