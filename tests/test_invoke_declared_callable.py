import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

registry_spec = importlib.util.spec_from_file_location("callable_registry", ROOT / "tools" / "callable_registry.py")
callable_registry = importlib.util.module_from_spec(registry_spec)
assert registry_spec.loader
registry_spec.loader.exec_module(callable_registry)

invoke_spec = importlib.util.spec_from_file_location("invoke_declared_callable", ROOT / "tools" / "invoke_declared_callable.py")
invoke_declared_callable = importlib.util.module_from_spec(invoke_spec)
assert invoke_spec.loader
invoke_spec.loader.exec_module(invoke_declared_callable)


@unittest.skipUnless(shutil.which("node"), "Node.js is required for JavaScript callable execution tests")
class DeclaredCallableInvocationTests(unittest.TestCase):
    def write(self, path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def make_js_snapshot(self, root: Path, *, command=False):
        module = root / "modules" / "demo-module"
        module.mkdir(parents=True)
        marker = root / "EXECUTED"
        if command:
            manifest = {
                "schema_version": "1.4",
                "capabilities": [{
                    "id": "demo.command",
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "command",
                        "runtime": "shell",
                        "command": f"touch {marker}",
                        "authority": "none"
                    }
                }]
            }
        else:
            marker_literal = json.dumps(str(marker))
            self.write(module / "callable.mjs", (
                "import { writeFileSync } from 'node:fs';\n"
                f"writeFileSync({marker_literal}, 'executed');\n"
                "export function double(value) { return { value, doubled: value * 2 }; }\n"
                "export function explode() { throw new Error('expected explosion'); }\n"
            ))
            manifest = {
                "schema_version": "1.4",
                "capabilities": [{
                    "id": "demo.double",
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "module-export",
                        "runtime": "javascript-esm",
                        "path": "callable.mjs",
                        "export": "double",
                        "authority": "none",
                        "network": "none"
                    }
                }]
            }
        self.write(module / "AXM_MODULE.json", json.dumps(manifest, indent=2))
        callable_registry.write_registry(root)
        return marker

    def request(self, *args):
        return {"schema": "axm.callable-invocation-request/v0.1", "args": list(args)}

    def test_execution_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = self.make_js_snapshot(root)
            receipt = invoke_declared_callable.invoke_declared_callable(
                root, "demo-module::demo.double", self.request(21), allow_javascript_esm=False
            )
            self.assertEqual(receipt["status"], "blocked_explicit_execution_opt_in_required")
            self.assertFalse(receipt["source_capability_execution"])
            self.assertFalse(marker.exists(), "module must not even be imported without explicit execution opt-in")

    def test_successful_module_export_emits_identity_bound_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = self.make_js_snapshot(root)
            receipt = invoke_declared_callable.invoke_declared_callable(
                root, "demo-module::demo.double", self.request(21), allow_javascript_esm=True
            )
            self.assertEqual(receipt["status"], "exercised_with_receipt")
            self.assertTrue(receipt["source_capability_execution"])
            self.assertEqual(receipt["result"], {"value": 21, "doubled": 42})
            self.assertTrue(marker.exists())
            self.assertRegex(receipt["manifest_sha256"], r"^sha256:[a-f0-9]{64}$")
            self.assertRegex(receipt["source_file_sha256"], r"^sha256:[a-f0-9]{64}$")
            self.assertRegex(receipt["request_sha256"], r"^sha256:[a-f0-9]{64}$")
            self.assertRegex(receipt["response_sha256"], r"^sha256:[a-f0-9]{64}$")
            self.assertIn("no merge/CANON", receipt["truth_boundary"])

    def test_invalid_request_is_blocked_before_source_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = self.make_js_snapshot(root)
            receipt = invoke_declared_callable.invoke_declared_callable(
                root,
                "demo-module::demo.double",
                {"schema": "wrong", "args": [21]},
                allow_javascript_esm=True,
            )
            self.assertEqual(receipt["status"], "blocked_invalid_invocation_request")
            self.assertFalse(marker.exists())

    def test_command_declaration_is_not_executed_by_v0_1_invoker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = self.make_js_snapshot(root, command=True)
            receipt = invoke_declared_callable.invoke_declared_callable(
                root,
                "demo-module::demo.command",
                self.request(),
                allow_javascript_esm=True,
            )
            self.assertEqual(receipt["status"], "blocked_unsupported_callable_kind")
            self.assertFalse(marker.exists())

    def test_declared_export_failure_is_preserved_as_failure_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "modules" / "failure-module"
            module.mkdir(parents=True)
            self.write(module / "failure.mjs", "export function explode() { throw new Error('expected explosion'); }\n")
            self.write(module / "AXM_MODULE.json", json.dumps({
                "schema_version": "1.4",
                "capabilities": [{
                    "id": "failure.explode",
                    "callable": {
                        "schema": "axm.callable-capability/v0.1",
                        "kind": "module-export",
                        "runtime": "javascript-esm",
                        "path": "failure.mjs",
                        "export": "explode",
                        "authority": "none"
                    }
                }]
            }))
            callable_registry.write_registry(root)
            receipt = invoke_declared_callable.invoke_declared_callable(
                root, "failure-module::failure.explode", self.request(), allow_javascript_esm=True
            )
            self.assertEqual(receipt["status"], "source_execution_failed")
            self.assertFalse(receipt["source_capability_execution"])
            self.assertEqual(receipt["response"]["error"]["message"], "expected explosion")


if __name__ == "__main__":
    unittest.main()
