from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from test_machine_voice_composition import RESULT_SCHEMA  # noqa: E402


class MachineVoiceLocalCompositionContractTests(unittest.TestCase):
    def test_manifest_declares_runner_without_fake_ci_runtime_upgrade(self):
        manifest = json.loads((ROOT / "AXM_MODULE.json").read_text(encoding="utf-8"))
        capabilities = {item["id"]: item for item in manifest["capabilities"]}
        capability = capabilities["test.machine-voice-local-composition"]
        self.assertIn("composition.test-result", capability["provides"])
        self.assertIn("interface.machine-json", capability["accepts"])
        status = capability["evidence"]["status"]
        self.assertEqual(
            status,
            "orchestrator_fixture_tested_real_cross_repository_runtime_requires_local_run",
        )
        self.assertIn("fake external process", capability["evidence"]["boundary"])
        self.assertIn("real Machine Voice", capability["evidence"]["boundary"])

        entrypoints = {item["path"]: item for item in manifest["entrypoints"]}
        self.assertEqual(
            entrypoints["tools/test_machine_voice_composition.py"]["command"],
            "python tools/test_machine_voice_composition.py",
        )

    def test_docs_expose_one_command_and_evidence_ladder(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        bridge = (ROOT / "MACHINE_VOICE_BRIDGE.md").read_text(encoding="utf-8")
        combined = readme + "\n" + bridge
        self.assertIn("python tools/test_machine_voice_composition.py", combined)
        self.assertIn("verified_fresh_emission", combined)
        self.assertIn("verified_duplicate_suppression", combined)
        self.assertIn("not_exercised_no_snapshot", combined)
        self.assertIn("fake external process", combined)
        self.assertIn("real cross-repository runtime", combined.lower())
        self.assertIn("--reset-journal", combined)

    def test_result_schema_and_generated_evidence_names_are_stable(self):
        runner = (TOOLS / "test_machine_voice_composition.py").read_text(encoding="utf-8")
        self.assertEqual(RESULT_SCHEMA, "axm.monolith.machine-voice-composition-result/v0.1")
        for name in (
            "MACHINE_VOICE_NOTICE.json",
            "MACHINE_VOICE_COMMUNICATION.jsonl",
            "MACHINE_VOICE_COMPOSITION_RESULT.json",
        ):
            self.assertIn(name, runner)
        self.assertIn(".generated", runner)

    def test_assembly_hold_is_released_but_confirmation_remains_required(self):
        config = json.loads((ROOT / "config" / "assembly.json").read_text(encoding="utf-8"))
        self.assertIs(config["build_enabled"], True)
        self.assertIsNone(config["hold_reason"])
        self.assertTrue(config["finalization"]["package_requires_explicit_confirmation"])


if __name__ == "__main__":
    unittest.main()
