import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "inspect_stack.py"
spec = importlib.util.spec_from_file_location("inspect_stack", MODULE_PATH)
inspect_stack = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(inspect_stack)


class StackInspectorTests(unittest.TestCase):
    def write(self, path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def make_module(self, root: Path, name: str, readme: str = "") -> Path:
        module = root / "modules" / name
        module.mkdir(parents=True)
        self.write(
            module / "AXM_MONOLITH_SOURCE.json",
            json.dumps({"repository": f"mike-axiom-mir/{name}", "commit": "a" * 40, "visibility": "public"}),
        )
        if readme:
            self.write(module / "README.md", readme)
        return module

    def test_analyze_emits_dashboard_and_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            creation = self.make_module(root, "axm-universal-creation", "# AXM Universal Creation\n\nCreate software deterministically.\n")
            self.write(creation / "index.html", "<!doctype html>")
            self.write(creation / "app.js", 'console.log("x")')
            self.write(creation / "tests" / "smoke.mjs", 'console.log("ok")')
            institution = self.make_module(root, "axm-institution-fabric", "# Institution Fabric\n\nPersistent lanes.\n")
            self.write(
                institution / "AXM_MODULE.json",
                json.dumps({
                    "schema_version": "0.1",
                    "capabilities": [{
                        "id": "institution.native",
                        "description": "Institution lane manager",
                        "provides": ["workflow.lane"],
                        "accepts": ["artifact.software"],
                        "evidence": {"status": "declared_not_verified"},
                    }],
                }),
            )
            result = inspect_stack.analyze_build(root)
            self.assertTrue((root / "OPEN_ME.html").exists())
            self.assertTrue((root / "CAPABILITY_REGISTRY.json").exists())
            self.assertTrue((root / "CONNECTION_GRAPH.json").exists())
            self.assertGreaterEqual(result["summary"]["module_count"], 2)
            dashboard = (root / "OPEN_ME.html").read_text(encoding="utf-8")
            self.assertIn("axm-universal-creation", dashboard)
            self.assertIn("axm-institution-fabric", dashboard)

    def test_native_manifest_is_stronger_than_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.make_module(root, "axm-institution-fabric", "# Institution Fabric")
            self.write(module / "AXM_MODULE.json", json.dumps({
                "capabilities": [{
                    "id": "institution.workflow",
                    "description": "native",
                    "provides": ["workflow.lane"],
                    "accepts": ["objective"],
                }]
            }))
            profile = inspect_stack.module_profile(module)
            capability = next(c for c in profile["capabilities"] if c["id"] == "institution.workflow")
            self.assertEqual(capability["source"], "native-manifest")
            self.assertEqual(capability["confidence"], 1.0)

    def test_graph_never_claims_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            producer = self.make_module(root, "producer")
            consumer = self.make_module(root, "consumer")
            self.write(producer / "AXM_MODULE.json", json.dumps({"capabilities": [{"id": "p", "provides": ["artifact.software"], "accepts": []}]}))
            self.write(consumer / "AXM_MODULE.json", json.dumps({"capabilities": [{"id": "c", "provides": [], "accepts": ["artifact.software"]}]}))
            graph = inspect_stack.build_connection_graph([
                inspect_stack.module_profile(producer), inspect_stack.module_profile(consumer)
            ])
            self.assertTrue(graph["edges"])
            self.assertEqual(graph["edges"][0]["status"], "declared_contract_match_not_tested")
            self.assertIn("not_tested", graph["edges"][0]["status"])

    def test_route_uses_candidate_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self.make_module(root, "a")
            b = self.make_module(root, "b")
            c = self.make_module(root, "c")
            self.write(a / "AXM_MODULE.json", json.dumps({"capabilities": [{"id": "a", "provides": ["artifact.software"], "accepts": []}]}))
            self.write(b / "AXM_MODULE.json", json.dumps({"capabilities": [{"id": "b", "provides": ["evidence"], "accepts": ["artifact.software"]}]}))
            self.write(c / "AXM_MODULE.json", json.dumps({"capabilities": [{"id": "c", "provides": [], "accepts": ["evidence"]}]}))
            inspect_stack.analyze_build(root)
            route = inspect_stack.route_between(root, "a", "c")
            self.assertTrue(route["found"])
            self.assertEqual(route["modules"], ["a", "b", "c"])
            self.assertEqual(route["status"], "candidate_route_not_verified")

    def test_human_queue_marks_game_and_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.make_module(root, "axm-ghost-studio", "# Ghost Studio\n\nGame studio.\n")
            self.write(module / "index.html", "<!doctype html>")
            self.write(module / "game.js", 'console.log("game")')
            queue = inspect_stack.human_test_queue([inspect_stack.module_profile(module)])
            self.assertEqual(queue[0]["module"], "axm-ghost-studio")
            self.assertGreaterEqual(queue[0]["priority"], 4)


if __name__ == "__main__":
    unittest.main()
