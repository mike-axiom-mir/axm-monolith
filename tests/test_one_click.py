import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "one_click.py"
spec = importlib.util.spec_from_file_location("one_click", MODULE_PATH)
one_click = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(one_click)


class OneClickLauncherTests(unittest.TestCase):
    def test_install_requires_capability_lab(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                one_click.install_snapshot_launchers(Path(tmp))

    def test_install_generates_newbie_launch_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "OPEN_ME.html").write_text("<html>lab</html>", encoding="utf-8")
            result = one_click.install_snapshot_launchers(root)
            self.assertTrue(result["installed"])
            self.assertTrue((root / "START_AXM.cmd").exists())
            self.assertTrue((root / "START_AXM.sh").exists())
            self.assertTrue((root / "START_HERE.txt").exists())
            self.assertTrue((root / "AXM_LOCAL_SERVER.py").exists())
            self.assertIn("127.0.0.1", result["default_url"])
            self.assertIn("on demand", result["launch_model"])

    def test_windows_launcher_opens_local_front_door_not_every_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "OPEN_ME.html").write_text("<html>lab</html>", encoding="utf-8")
            one_click.install_snapshot_launchers(root)
            text = (root / "START_AXM.cmd").read_text(encoding="utf-8")
            self.assertIn("AXM_LOCAL_SERVER.py", text)
            self.assertIn("--open", text)
            self.assertNotIn("modules\\", text)


if __name__ == "__main__":
    unittest.main()
