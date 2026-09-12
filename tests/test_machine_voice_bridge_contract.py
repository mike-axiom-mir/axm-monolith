from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MachineVoiceBridgeContractTests(unittest.TestCase):
    def test_native_manifest_declares_state_export_without_runtime_overclaim(self):
        manifest = json.loads((ROOT / "AXM_MODULE.json").read_text(encoding="utf-8"))
        capabilities = {item["id"]: item for item in manifest["capabilities"]}
        bridge = capabilities["communication.machine-voice-state-export"]
        self.assertIn("assembly.config", bridge["accepts"])
        self.assertIn("communication.notice-snapshot", bridge["provides"])
        self.assertIn("state.snapshot", bridge["provides"])
        self.assertEqual(
            bridge["evidence"]["status"],
            "checked_in_state_tested_not_cross_repository_runtime_verified",
        )
        boundary = manifest["truth_boundary"].lower()
        self.assertIn("not cross-repository runtime verification", boundary)
        self.assertIn("no automatic execution", boundary)

    def test_docs_expose_exact_local_composition_without_claiming_ci_verified_it(self):
        bridge = (ROOT / "MACHINE_VOICE_BRIDGE.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = bridge + "\n" + readme
        self.assertIn("axm-machine-voice/notice-snapshot/0.1", bridge)
        self.assertIn("python tools/export_machine_voice_state.py", combined)
        self.assertIn("../axm-machine-voice/machine_voice.py snapshot", bridge)
        self.assertIn("--active-ref activity:assembly-control", bridge)
        self.assertIn("not yet claimed cross-repository verified", bridge)
        self.assertIn("build capability stays hard-disabled", readme)

    def test_exporter_does_not_embed_interpretation_fields(self):
        tool = (ROOT / "tools" / "export_machine_voice_state.py").read_text(encoding="utf-8")
        self.assertIn('NOTICE_SNAPSHOT_SCHEMA = "axm-machine-voice/notice-snapshot/0.1"', tool)
        for field in (
            "importance_claimed",
            "anomaly_claimed",
            "novelty_claimed",
            "failure_claimed",
            "recommendation_claimed",
            "interpretation_claimed",
        ):
            self.assertNotIn(f'"{field}"', tool)


if __name__ == "__main__":
    unittest.main()
