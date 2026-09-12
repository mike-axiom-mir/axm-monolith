import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "user_surface.py"
spec = importlib.util.spec_from_file_location("user_surface", MODULE_PATH)
user_surface = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(user_surface)


class UserSurfaceTests(unittest.TestCase):
    def make_snapshot(self, root: Path):
        module = root / "modules" / "demo-game"
        module.mkdir(parents=True)
        (module / "index.html").write_text(
            '<!doctype html><canvas id="game"></canvas><script>addEventListener("keydown",()=>{})</script>',
            encoding="utf-8",
        )
        (root / "OPEN_ME.html").write_text(
            "<!doctype html><title>old dashboard</title><p>dashboard</p>", encoding="utf-8"
        )
        analysis = {
            "modules": [{
                "module": "demo-game",
                "repository": "mike-axiom-mir/demo-game",
                "commit": "a" * 40,
                "entrypoints": [{"kind": "browser", "path": "index.html", "command": "open index.html"}],
                "capabilities": [{
                    "id": "game.demo",
                    "description": "demo",
                    "source": "structural",
                    "evidence_status": "detected_not_verified",
                }],
                "tags": ["game"],
            }]
        }
        (root / "STACK_ANALYSIS.json").write_text(json.dumps(analysis), encoding="utf-8")

    def test_generate_makes_capability_lab_default_and_preserves_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_snapshot(root)
            result = user_surface.generate_user_surface(root)
            self.assertEqual(result["surface_count"], 1)
            self.assertTrue((root / "STACK_DASHBOARD.html").exists())
            self.assertIn("old dashboard", (root / "STACK_DASHBOARD.html").read_text(encoding="utf-8"))
            lab = (root / "OPEN_ME.html").read_text(encoding="utf-8")
            self.assertIn(user_surface.LAB_MARKER, lab)
            self.assertIn("AI-native keyboard", lab)
            self.assertIn("Capture visual state", lab)
            registry = json.loads((root / "USER_FACING_SURFACES.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["surfaces"][0]["route"], "modules/demo-game/index.html")
            self.assertTrue(registry["capabilities"][0]["launchable_user_surface"])

    def test_nested_html_is_exposed_as_structural_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "modules" / "demo"
            (module / "web").mkdir(parents=True)
            (module / "web" / "index.html").write_text("<p>x</p>", encoding="utf-8")
            analysis = {
                "modules": [{
                    "module": "demo",
                    "repository": "x/demo",
                    "commit": None,
                    "entrypoints": [],
                    "capabilities": [],
                    "tags": [],
                }]
            }
            registry = user_surface.build_surface_registry(root, analysis)
            self.assertEqual(registry["surface_count"], 1)
            self.assertEqual(registry["surfaces"][0]["route"], "modules/demo/web/index.html")


if __name__ == "__main__":
    unittest.main()
