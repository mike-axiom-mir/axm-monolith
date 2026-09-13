import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "callable_registry.py"
spec = importlib.util.spec_from_file_location("callable_registry", MODULE_PATH)
callable_registry = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(callable_registry)


class CallableRegistryTests(unittest.TestCase):
    def write(self, path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def module(self, root: Path, name: str) -> Path:
        path = root / "modules" / name
        path.mkdir(parents=True)
        return path

    def test_valid_module_export_is_preserved_but_not_promoted_to_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.module(root, "consumer")
            self.write(module / "src" / "callable.mjs", "export function run(value) { return value; }\n")
            self.write(module / "AXM_MODULE.json", json.dumps({
                "schema_version": "1.4",
                "capabilities": [{
                    "id": "example.callable",
                    "provides": ["example.output"],
                    "accepts": ["example.input"],
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "module-export",
                        "runtime": "javascript-esm",
                        "path": "src/callable.mjs",
                        "export": "run",
                        "input_contract": "example.input/v0.1",
                        "output_contract": "example.output/v0.1",
                        "authority": "none",
                        "network": "none"
                    }
                }]
            }))
            result = callable_registry.build_registry(root)
            self.assertEqual(result["summary"]["declared_callable_not_exercised"], 1)
            entry = result["entries"][0]
            self.assertEqual(entry["address"], "consumer::example.callable")
            self.assertEqual(entry["status"], "declared_callable_not_exercised")
            self.assertFalse(entry["source_capability_execution"])
            self.assertEqual(entry["callable"]["export"], "run")
            self.assertEqual(entry["errors"], [])

    def test_path_traversal_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.module(root, "bad-path")
            self.write(module / "AXM_MODULE.json", json.dumps({
                "capabilities": [{
                    "id": "bad.callable",
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "module-export",
                        "runtime": "python",
                        "path": "../escape.py",
                        "export": "run",
                        "authority": "none"
                    }
                }]
            }))
            result = callable_registry.build_registry(root)
            entry = result["entries"][0]
            self.assertEqual(entry["status"], "blocked_invalid_callable_declaration")
            self.assertFalse(entry["source_capability_execution"])
            self.assertTrue(any("safe repository-relative" in error for error in entry["errors"]))

    def test_non_none_authority_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.module(root, "bad-authority")
            self.write(module / "tool.py", "def main(): return 0\n")
            self.write(module / "AXM_MODULE.json", json.dumps({
                "capabilities": [{
                    "id": "authority.claim",
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "command",
                        "runtime": "python",
                        "command": "python tool.py",
                        "path": "tool.py",
                        "authority": "merge"
                    }
                }]
            }))
            result = callable_registry.build_registry(root)
            entry = result["entries"][0]
            self.assertEqual(entry["status"], "blocked_invalid_callable_declaration")
            self.assertIn("authority must be exactly none", entry["errors"])

    def test_command_is_declared_metadata_only_and_never_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.module(root, "command-module")
            marker = root / "MUST_NOT_EXIST"
            self.write(module / "AXM_MODULE.json", json.dumps({
                "capabilities": [{
                    "id": "command.callable",
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "command",
                        "runtime": "shell",
                        "command": f"touch {marker}",
                        "authority": "none"
                    }
                }]
            }))
            result = callable_registry.build_registry(root)
            self.assertEqual(result["entries"][0]["status"], "declared_callable_not_exercised")
            self.assertFalse(marker.exists(), "registry collection must never execute declared commands")

    def test_manifest_without_callable_does_not_create_fake_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.module(root, "ordinary")
            self.write(module / "AXM_MODULE.json", json.dumps({
                "capabilities": [{"id": "ordinary.capability", "provides": ["artifact"]}]
            }))
            result = callable_registry.build_registry(root)
            self.assertEqual(result["summary"]["callable_declaration_count"], 0)
            self.assertEqual(result["entries"], [])

    def test_registry_output_is_byte_deterministic_for_same_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = self.module(root, "stable")
            self.write(module / "main.py", "def run(value): return value\n")
            self.write(module / "AXM_MODULE.json", json.dumps({
                "capabilities": [{
                    "id": "stable.callable",
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "module-export",
                        "runtime": "python",
                        "path": "main.py",
                        "export": "run",
                        "authority": "none"
                    }
                }]
            }, indent=2))
            one = root / "one.json"
            two = root / "two.json"
            callable_registry.write_registry(root, one)
            callable_registry.write_registry(root, two)
            self.assertEqual(one.read_bytes(), two.read_bytes())


if __name__ == "__main__":
    unittest.main()
