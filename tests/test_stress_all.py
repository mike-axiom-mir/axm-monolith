import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "stress_all.py"
spec = importlib.util.spec_from_file_location("stress_all", MODULE_PATH)
stress_all = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(stress_all)


class StressAllTests(unittest.TestCase):
    def make_snapshot(self, root: Path) -> Path:
        snap = root / "snapshot"
        module = snap / "modules" / "demo"
        module.mkdir(parents=True)
        (module / "main.py").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        analysis = {
            "modules": [
                {
                    "module": "demo",
                    "repository": "mike-axiom-mir/demo",
                    "entrypoints": [
                        {"kind": "python", "path": "main.py", "command": "python main.py", "evidence": "structural"},
                        {"kind": "npm-script", "path": "package.json", "command": "npm run test", "evidence": "declared-package-script"},
                        {"kind": "browser", "path": "index.html", "command": "open index.html", "evidence": "structural"},
                    ],
                }
            ]
        }
        (snap / "STACK_ANALYSIS.json").write_text(json.dumps(analysis), encoding="utf-8")
        return snap

    def test_plan_runs_application_but_excludes_test_and_browser_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = self.make_snapshot(Path(tmp))
            plan = stress_all.runnable_plan(snap)
            self.assertEqual(plan["runnable_count"], 1)
            self.assertEqual(plan["runnable"][0]["module"], "demo")
            reasons = " ".join(item["reason"] for item in plan["skipped"])
            self.assertIn("not an application run script", reasons)
            self.assertIn("browser surface is activated", reasons)

    def test_switch_on_then_off_kills_spawned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = self.make_snapshot(Path(tmp))
            controller = stress_all.StressController(snap)
            started = controller.start()
            self.assertTrue(started["active"])
            self.assertGreaterEqual(started["processes_started"], 1)
            time.sleep(0.05)
            stopped = controller.stop()
            self.assertFalse(stopped["active"])
            self.assertEqual(stopped["processes_alive"], 0)
            self.assertTrue((snap / "evidence" / "stress-all" / "STRESS_STATE.json").exists())

    def test_install_controls_creates_on_off_switches(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = self.make_snapshot(Path(tmp))
            result = stress_all.install_stress_controls(snap)
            self.assertTrue(result["installed"])
            for name in ("STRESS_ALL.html", "STRESS_ALL_ON.cmd", "STRESS_ALL_OFF.cmd", "STRESS_ALL_ON.sh", "STRESS_ALL_OFF.sh"):
                self.assertTrue((snap / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
