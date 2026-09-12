import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "stress_all_v2.py"
spec = importlib.util.spec_from_file_location("stress_all_v2_under_test", MODULE_PATH)
stress = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(stress)


class AdaptiveStressTests(unittest.TestCase):
    def test_policy_is_98_trigger_90_target(self):
        self.assertEqual(stress.PRESSURE_TRIGGER, 0.98)
        self.assertEqual(stress.PRESSURE_TARGET, 0.90)
        self.assertAlmostEqual(stress.utilization({"total_bytes": 1000, "used_bytes": 980}), 0.98)

    def test_pressure_trigger_is_logged_before_shedding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = stress.StressController(root)
            memory = {"total_bytes": 1000, "used_bytes": 980, "available_bytes": 20}
            with controller.lock:
                controller._begin_shedding_locked(memory)
            self.assertEqual(controller.pressure_state, "shedding")
            self.assertTrue(controller.browser_shed_requested)
            self.assertEqual(controller.shed_history, [])
            events = (root / "evidence" / "stress-all" / "EVENTS.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event": "pressure_trigger"', events)
            self.assertIn('"target_percent": 90.0', events)

    def test_browser_shed_records_what_and_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = stress.StressController(root)
            original = stress.base.system_memory
            stress.base.system_memory = lambda: {
                "total_bytes": 1000,
                "used_bytes": 940,
                "available_bytes": 60,
            }
            try:
                with controller.lock:
                    controller.active = True
                    controller.pressure_state = "shedding"
                    controller.pressure_cycle = 1
                status = controller.report_browser_shed({
                    "surface": "demo:0",
                    "module": "demo",
                    "route": "modules/demo/index.html",
                })
            finally:
                stress.base.system_memory = original
            self.assertEqual(status["shed_count"], 1)
            item = status["shed_history"][0]
            self.assertEqual(item["kind"], "browser-surface")
            self.assertEqual(item["module"], "demo")
            self.assertIn("98%", item["reason"])
            self.assertIn("90%", item["reason"])
            history = json.loads((root / "evidence" / "stress-all" / "SHED_HISTORY.json").read_text(encoding="utf-8"))
            self.assertEqual(history["history"][0]["surface"], "demo:0")

    def test_generated_stress_page_exposes_adaptive_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "STACK_ANALYSIS.json").write_text(json.dumps({"modules": []}), encoding="utf-8")
            result = stress.install_stress_controls(root)
            html = (root / "STRESS_ALL.html").read_text(encoding="utf-8")
            self.assertEqual(result["adaptive_pressure"]["trigger_used_percent"], 98.0)
            self.assertEqual(result["adaptive_pressure"]["target_used_percent"], 90.0)
            self.assertIn("/api/stress/browser-shed", html)
            self.assertIn("SHED_HISTORY.json", html)
            self.assertIn("90%", html)


if __name__ == "__main__":
    unittest.main()
