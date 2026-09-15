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

    def test_walmi_exact_ref_recipe_is_retained(self):
        recipes = [r for r in mod.RECIPES if r.get("id") == "walmi-public-capability-verify"]
        self.assertEqual(1, len(recipes))
        self.assertEqual("mike-axiom-mir/axm-walmi", recipes[0]["repository"])
        self.assertEqual("c8913f3a6f42a6498f83d5876b8aee9c56df694f", recipes[0]["commit"])
        self.assertEqual("axm-walmi::native.command/python-file-cli/tools/verify_public_capability.py", recipes[0]["address"])
        self.assertEqual(["--root", "."], recipes[0]["args"])

    def test_front_door_exact_ref_recipe_is_retained(self):
        recipes = [r for r in mod.RECIPES if r.get("id") == "front-door-validate"]
        self.assertEqual(1, len(recipes))
        self.assertEqual("mike-axiom-mir/axm-front-door", recipes[0]["repository"])
        self.assertEqual("05e25b557d076551ac740c4e043a9ccbbb0160ba", recipes[0]["commit"])
        self.assertEqual("axm-front-door::native.command/python-file-cli/scripts/axm_site.py", recipes[0]["address"])
        self.assertEqual(["validate"], recipes[0]["args"])

    def test_living_city_exact_ref_recipe_is_retained(self):
        recipes = [r for r in mod.RECIPES if r.get("id") == "living-city-headless-main"]
        self.assertEqual(1, len(recipes))
        self.assertEqual("mike-axiom-mir/axm-living-city-simulator", recipes[0]["repository"])
        self.assertEqual("a299db639e87b2fa0dea1ded1bf651ab86e9cd3c", recipes[0]["commit"])
        self.assertEqual("axm-living-city-simulator::native.command/node-file-cli/runtime/headless-simulator.js", recipes[0]["address"])
        self.assertEqual(["--help"], recipes[0]["args"])


if __name__ == "__main__":
    unittest.main()
