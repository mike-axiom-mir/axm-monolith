import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "one_click.py"
spec = importlib.util.spec_from_file_location("one_click", MODULE_PATH)
one_click = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(one_click)


class OneClickLauncherTests(unittest.TestCase):
    def prepare(self, root: Path) -> None:
        (root / "OPEN_ME.html").write_text("<html><body>lab</body></html>", encoding="utf-8")
        (root / "STACK_ANALYSIS.json").write_text(json.dumps({"modules": []}), encoding="utf-8")

    def test_install_requires_capability_lab(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                one_click.install_snapshot_launchers(Path(tmp))

    def test_install_generates_newbie_launch_surface_and_stress_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            result = one_click.install_snapshot_launchers(root)
            self.assertTrue(result["installed"])
            for name in (
                "START_AXM.cmd", "START_AXM.sh", "START_HERE.txt", "AXM_LOCAL_SERVER.py",
                "STRESS_ALL.html", "STRESS_ALL_ON.cmd", "STRESS_ALL_OFF.cmd",
            ):
                self.assertTrue((root / name).exists(), name)
            self.assertIn("127.0.0.1", result["default_url"])
            self.assertIn("on demand", result["launch_model"])
            self.assertTrue(result["stress_controls"]["installed"])
            self.assertIn("AXM_STRESS_ALL_LINK_V0_1", (root / "OPEN_ME.html").read_text(encoding="utf-8"))

    def test_windows_launcher_opens_local_front_door_not_every_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            one_click.install_snapshot_launchers(root)
            text = (root / "START_AXM.cmd").read_text(encoding="utf-8")
            self.assertIn("AXM_LOCAL_SERVER.py", text)
            self.assertIn("--open", text)
            self.assertNotIn("modules\\", text)


if __name__ == "__main__":
    unittest.main()
