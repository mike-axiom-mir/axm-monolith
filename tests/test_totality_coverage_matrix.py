import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import totality_coverage_matrix as matrix


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_fixture(root: Path, *, missing_beta_probe: bool = False):
    modules = []
    endpoints = []
    probes = []
    for name, state in (("alpha", "VERIFIED_EXECUTABLE"), ("beta", "TEST_EVIDENCE")):
        modules.append({
            "module": name,
            "repository": f"owner/{name}",
            "commit": name * 8,
            "contract_path": f"analysis/contracts/{name}.json",
            "contract_sha256": "sha256:" + name,
            "endpoint_count": 1,
            "actionable_endpoint_count": 1,
            "blocked_endpoint_count": 0,
            "highest_observed_state": state,
        })
        endpoints.append({
            "module": name,
            "address": f"{name}::x",
            "adapter": {"status": "callable_native_command_verified" if name == "alpha" else "executable_test_evidence"},
        })
        if not (missing_beta_probe and name == "beta"):
            probes.append({
                "capability": f"{name}::x",
                "status": "native_command_verified_ready" if name == "alpha" else "test_adapter_ready",
                "receipt": f"evidence/{name}.json",
            })
    write_json(root / "MODULE_CONNECTIVE_CONTRACTS.json", {"modules": modules})
    write_json(root / "EXECUTION_FABRIC.json", {"endpoints": endpoints})
    write_json(root / "evidence/execution-fabric/PROBE_ALL.json", {"results": probes})
    write_json(root / "evidence/execution-fabric/TEST_ALL_BROAD.json", {"modules": [{
        "module": "beta",
        "status": "passed",
        "command_count": 1,
        "counts": {"passed": 1},
        "commands": [{"status": "passed", "classification": "passed"}],
        "source_snapshot_mutated": False,
    }]})
    write_json(root / "GOLDEN_PATHS.json", {
        "workfloor_paths": [{"id": "path-a", "candidate_modules": ["alpha", "beta"]}],
        "native_execution_smokes": [{
            "module": "alpha",
            "id": "smoke-a",
            "status": "PASS",
            "address": "alpha::x",
            "source_capability_executed": True,
            "source_snapshot_mutated": False,
            "receipt_path": "receipt.json",
        }],
    })


class TotalityCoverageMatrixTests(unittest.TestCase):
    def test_separates_native_execution_from_test_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "snapshot"
            root.mkdir()
            make_fixture(root)
            payload = matrix.generate(root)
            states = {row["module"]: row["integration_state"] for row in payload["modules"]}
            self.assertEqual(states, {"alpha": "EXECUTED", "beta": "TEST_EVIDENCE"})
            self.assertTrue(payload["summary"]["all_modules_bounded_probed"])
            self.assertTrue((root / "TEST_MATRIX.json").is_file())
            self.assertTrue((root / "START_HERE_TEST.md").is_file())

    def test_missing_probe_fails_closed_in_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "snapshot"
            root.mkdir()
            make_fixture(root, missing_beta_probe=True)
            payload = matrix.generate(root)
            self.assertEqual(payload["summary"]["probe_covered_module_count"], 1)
            self.assertFalse(payload["summary"]["all_modules_bounded_probed"])
            beta = next(row for row in payload["modules"] if row["module"] == "beta")
            self.assertEqual(beta["bounded_probe"]["probe_count"], 0)


if __name__ == "__main__":
    unittest.main()
