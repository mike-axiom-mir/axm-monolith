import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "module_connective_contracts.py"
spec = importlib.util.spec_from_file_location("module_connective_contracts", MODULE_PATH)
mcc = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mcc)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ModuleConnectiveContractsTest(unittest.TestCase):
    def make_snapshot(self, root: Path):
        (root / "modules" / "alpha").mkdir(parents=True)
        (root / "modules" / "beta").mkdir(parents=True)
        write_json(root / "analysis/modules/alpha.json", {
            "module": "alpha", "repository": "example/alpha", "commit": "a" * 40,
            "source_record": {"repository": "example/alpha", "commit": "a" * 40},
            "capabilities": [
                {"id": "make.widget", "accepts": ["input.seed"], "provides": ["artifact.widget"], "evidence_status": "declared"},
            ],
            "entrypoints": [{"kind": "python", "path": "run.py", "command": "python run.py"}],
            "tests": [{"kind": "python", "path": "tests/test_a.py", "command": "python -m unittest"}],
            "native_manifest": None,
            "uncertainties": ["fixture uncertainty"],
        })
        write_json(root / "analysis/modules/beta.json", {
            "module": "beta", "repository": "example/beta", "commit": "b" * 40,
            "source_record": {"repository": "example/beta", "commit": "b" * 40},
            "capabilities": [
                {"id": "use.widget", "accepts": ["artifact.widget"], "provides": ["result.report"], "evidence_status": "structural"},
            ],
            "entrypoints": [], "tests": [], "native_manifest": None, "uncertainties": [],
        })
        write_json(root / "EXECUTION_FABRIC.json", {
            "schema": "axm.monolith.execution-fabric/v0.1",
            "endpoints": [
                {"module": "alpha", "address": "alpha::make.widget", "capability": "make.widget", "registry_layer": "leaf", "declaration_source": "manifest", "evidence_status": "declared",
                 "adapter": {"status": "callable_native_command_verified", "kind": "native", "source_capability_execution": True}},
                {"module": "beta", "address": "beta::use.widget", "capability": "use.widget", "registry_layer": "leaf", "declaration_source": "structural", "evidence_status": "structural",
                 "adapter": {"status": "blocked_missing_callable_binding", "kind": "none"}},
            ]
        })

    def test_generates_all_sidecars_and_preserves_evidence_classes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_snapshot(root)
            registry = mcc.generate(root)
            result = mcc.verify(root)
            self.assertEqual("PASS", result["status"])
            self.assertEqual(2, registry["module_count"])
            self.assertEqual(2, registry["summary"]["endpoint_count"])
            self.assertEqual(1, registry["summary"]["actionable_endpoint_count"])
            self.assertEqual(1, registry["summary"]["blocked_endpoint_count"])
            alpha = json.loads((root / "analysis/contracts/alpha.json").read_text())
            beta = json.loads((root / "analysis/contracts/beta.json").read_text())
            self.assertEqual("VERIFIED_EXECUTABLE", alpha["execution_surface"]["highest_observed_state"])
            self.assertEqual("BLOCKED_MISSING_CALLABLE_BINDING", beta["execution_surface"]["highest_observed_state"])
            self.assertFalse(alpha["authority"]["contract_grants_execution"])
            links = registry["candidate_token_links"]
            self.assertEqual(1, len(links))
            self.assertEqual("artifact.widget", links[0]["token"])
            self.assertEqual("CANDIDATE_TOKEN_MATCH_NOT_VERIFIED", links[0]["status"])

    def test_tampered_contract_is_held(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_snapshot(root)
            mcc.generate(root)
            path = root / "analysis/contracts/alpha.json"
            path.write_text(path.read_text() + "\n", encoding="utf-8")
            result = mcc.verify(root)
            self.assertEqual("HOLD", result["status"])
            self.assertTrue(any("hash mismatch" in error for error in result["errors"]))

    def test_no_execution_fabric_is_explicit_hold_not_fake_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "modules" / "alpha").mkdir(parents=True)
            write_json(root / "analysis/modules/alpha.json", {
                "module": "alpha", "repository": "example/alpha", "commit": "a" * 40,
                "source_record": {}, "capabilities": [], "entrypoints": [], "tests": [],
                "native_manifest": None, "uncertainties": [],
            })
            registry = mcc.generate(root)
            result = mcc.verify(root)
            self.assertEqual("PASS", result["status"])
            self.assertEqual(0, registry["summary"]["endpoint_count"])
            contract = json.loads((root / "analysis/contracts/alpha.json").read_text())
            self.assertEqual("HOLD_NO_EXECUTION_FABRIC", contract["execution_surface"]["highest_observed_state"])


if __name__ == "__main__":
    unittest.main()
