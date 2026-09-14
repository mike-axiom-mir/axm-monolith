import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "totality_native_smokes.py"
spec = importlib.util.spec_from_file_location("totality_native_smokes", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class TotalityNativeSmokeGateTest(unittest.TestCase):
    def setUp(self):
        self.recipe = {"repository": "x/y", "commit": "a" * 40}
        self.endpoint = {
            "repository": "x/y",
            "commit": "a" * 40,
            "adapter": {
                "status": "callable_native_command_verified",
                "source_capability_execution": True,
            },
        }

    def test_ready_requires_exact_ref_and_verified_evidence(self):
        self.assertEqual((True, "READY"), mod.gate(self.endpoint, self.recipe))

    def test_changed_ref_is_hold(self):
        endpoint = {**self.endpoint, "commit": "b" * 40}
        self.assertEqual((False, "HOLD_RECIPE_REF_MISMATCH"), mod.gate(endpoint, self.recipe))

    def test_unverified_native_command_is_hold(self):
        endpoint = {
            **self.endpoint,
            "adapter": {
                "status": "native_command_discovered_unprobed",
                "source_capability_execution": False,
            },
        }
        self.assertEqual((False, "HOLD_NO_VERIFIED_NATIVE_EVIDENCE"), mod.gate(endpoint, self.recipe))

    def test_missing_endpoint_is_hold(self):
        self.assertEqual((False, "HOLD_ENDPOINT_MISSING"), mod.gate(None, self.recipe))


if __name__ == "__main__":
    unittest.main()
