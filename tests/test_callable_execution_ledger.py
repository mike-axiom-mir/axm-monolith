import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

registry_spec = importlib.util.spec_from_file_location("callable_registry", ROOT / "tools" / "callable_registry.py")
callable_registry = importlib.util.module_from_spec(registry_spec)
assert registry_spec.loader
registry_spec.loader.exec_module(callable_registry)

ledger_spec = importlib.util.spec_from_file_location("callable_execution_ledger", ROOT / "tools" / "callable_execution_ledger.py")
ledger_tool = importlib.util.module_from_spec(ledger_spec)
assert ledger_spec.loader
ledger_spec.loader.exec_module(ledger_tool)


def canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_hash(path: Path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class CallableExecutionLedgerTests(unittest.TestCase):
    def write(self, path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def make_snapshot(self, root: Path):
        module = root / "modules" / "demo-module"
        module.mkdir(parents=True)
        source = module / "callable.mjs"
        self.write(source, "export function double(value) { return { doubled: value * 2 }; }\n")
        self.write(module / "AXM_MODULE.json", json.dumps({
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
        }, indent=2))
        callable_registry.write_registry(root)
        registry = json.loads((root / "CALLABLE_CAPABILITY_REGISTRY.json").read_text())
        return module, source, registry["entries"][0]

    def receipt(self, source: Path, entry, *, status="exercised_with_receipt", execution=True, result=None):
        response = {"ok": True, "result": result} if status == "exercised_with_receipt" else {
            "ok": False,
            "error": {"name": "Error", "message": "expected failure"}
        }
        value = {
            "schema": "axm.monolith.callable-invocation-receipt/v0.1",
            "address": entry["address"],
            "module": entry["module"],
            "capability": entry["capability"],
            "manifest_sha256": entry["manifest_sha256"],
            "request_sha256": canonical_hash({"schema": "axm.callable-invocation-request/v0.1", "args": [21]}),
            "source_capability_execution": execution,
            "declared_callable": entry["callable"],
            "source_file": entry["callable"]["path"],
            "source_file_sha256": file_hash(source),
            "export": entry["callable"]["export"],
            "runtime": entry["callable"]["runtime"],
            "exit_code": 0 if status == "exercised_with_receipt" else 3,
            "response": response,
            "response_sha256": canonical_hash(response),
            "status": status,
        }
        if status == "exercised_with_receipt":
            value["result"] = result
        return value

    def test_success_receipt_is_accepted_without_mutating_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, source, entry = self.make_snapshot(root)
            receipts = root / "evidence"
            receipts.mkdir()
            self.write(receipts / "receipt.json", json.dumps(self.receipt(source, entry, result={"doubled": 42}), indent=2))
            ledger = ledger_tool.build_ledger(root, receipts)
            self.assertEqual(ledger["summary"]["accepted_exercised_receipts"], 1)
            self.assertEqual(ledger["summary"]["exercised_address_count"], 1)
            self.assertEqual(ledger["executed_addresses"], ["demo-module::demo.double"])
            self.assertTrue(ledger["capabilities"][0]["source_capability_execution"])
            registry = json.loads((root / "CALLABLE_CAPABILITY_REGISTRY.json").read_text())
            self.assertEqual(registry["entries"][0]["status"], "declared_callable_not_exercised")
            self.assertFalse(registry["entries"][0]["source_capability_execution"])

    def test_manifest_identity_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, source, entry = self.make_snapshot(root)
            receipts = root / "evidence"
            receipts.mkdir()
            value = self.receipt(source, entry, result=42)
            value["manifest_sha256"] = "sha256:" + "0" * 64
            self.write(receipts / "receipt.json", json.dumps(value))
            ledger = ledger_tool.build_ledger(root, receipts)
            self.assertEqual(ledger["summary"]["blocked_invalid_receipts"], 1)
            self.assertEqual(ledger["summary"]["accepted_exercised_receipts"], 0)
            self.assertIn("manifest hash", " ".join(ledger["receipts"][0]["errors"]))

    def test_source_bytes_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, source, entry = self.make_snapshot(root)
            receipts = root / "evidence"
            receipts.mkdir()
            value = self.receipt(source, entry, result=42)
            value["source_file_sha256"] = "sha256:" + "1" * 64
            self.write(receipts / "receipt.json", json.dumps(value))
            ledger = ledger_tool.build_ledger(root, receipts)
            self.assertEqual(ledger["summary"]["blocked_invalid_receipts"], 1)
            self.assertIn("captured source bytes", " ".join(ledger["receipts"][0]["errors"]))

    def test_failed_source_execution_is_preserved_but_not_counted_as_exercised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, source, entry = self.make_snapshot(root)
            receipts = root / "evidence"
            receipts.mkdir()
            value = self.receipt(source, entry, status="source_execution_failed", execution=False)
            self.write(receipts / "failure.json", json.dumps(value))
            ledger = ledger_tool.build_ledger(root, receipts)
            self.assertEqual(ledger["summary"]["observed_non_success_receipts"], 1)
            self.assertEqual(ledger["summary"]["accepted_exercised_receipts"], 0)
            self.assertEqual(ledger["executed_addresses"], [])
            self.assertFalse(ledger["capabilities"][0]["source_capability_execution"])

    def test_policy_block_before_source_execution_is_evidence_not_invalid_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, entry = self.make_snapshot(root)
            receipts = root / "evidence"
            receipts.mkdir()
            value = {
                "schema": "axm.monolith.callable-invocation-receipt/v0.1",
                "address": entry["address"],
                "module": entry["module"],
                "capability": entry["capability"],
                "manifest_sha256": entry["manifest_sha256"],
                "request_sha256": canonical_hash({"schema": "axm.callable-invocation-request/v0.1", "args": [21]}),
                "source_capability_execution": False,
                "declared_callable": entry["callable"],
                "status": "blocked_explicit_execution_opt_in_required"
            }
            self.write(receipts / "blocked.json", json.dumps(value))
            ledger = ledger_tool.build_ledger(root, receipts)
            self.assertEqual(ledger["summary"]["observed_non_success_receipts"], 1)
            self.assertEqual(ledger["summary"]["blocked_invalid_receipts"], 0)

    def test_request_json_is_ignored_and_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, source, entry = self.make_snapshot(root)
            receipts = root / "evidence"
            receipts.mkdir()
            self.write(receipts / "request.json", json.dumps({"schema": "axm.callable-invocation-request/v0.1", "args": [21]}))
            self.write(receipts / "receipt.json", json.dumps(self.receipt(source, entry, result=42), indent=2))
            one = root / "ledger-one.json"
            two = root / "ledger-two.json"
            ledger_tool.write_ledger(root, receipts, one)
            ledger_tool.write_ledger(root, receipts, two)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            value = json.loads(one.read_text())
            self.assertEqual(value["summary"]["ignored_non_receipt_json"], 1)
            self.assertEqual(value["summary"]["receipt_files_recorded"], 1)


if __name__ == "__main__":
    unittest.main()
