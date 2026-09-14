from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("schema_probe_wiring", ROOT / "tools" / "schema_probe_wiring.py")
assert SPEC and SPEC.loader
schema_probe_wiring = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(schema_probe_wiring)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SchemaProbeWiringTests(unittest.TestCase):
    def make_snapshot(self, base: Path, *, existing_tests: bool = False, with_schema: bool = True) -> Path:
        root = base / "snapshot"
        module = root / "modules" / "schema-only"
        module.mkdir(parents=True)
        if with_schema:
            write_json(module / "schemas" / "state.schema.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"})
        tests = ([{"kind": "test-suite", "command": "python -m unittest discover -s tests -v", "safety": "executes module test code", "evidence": "structural"}] if existing_tests else [])
        write_json(root / "STACK_ANALYSIS.json", {
            "schema_version": "0.3",
            "automated_test_queue": [],
            "modules": [{
                "module": "schema-only",
                "repository": "example/schema-only",
                "commit": "a" * 40,
                "tests": tests,
                "capabilities": [{"id": "contract.schema", "source": "structural-scan"}],
                "uncertainties": [schema_probe_wiring.NO_TEST_UNCERTAINTY] if not existing_tests else [],
            }],
        })
        write_json(root / "AUTOMATED_TEST_QUEUE.json", {"schema_version": "0.3", "queue": []})
        return root

    def test_schema_only_module_gets_bounded_idempotent_probe_without_donor_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_snapshot(Path(td))
            donor = root / "modules" / "schema-only" / "schemas" / "state.schema.json"
            before = digest(donor)

            first = schema_probe_wiring.apply(root)
            second = schema_probe_wiring.apply(root)

            self.assertEqual(first["status"], "PASS")
            self.assertEqual(first["generated_probe_count"], 1)
            self.assertEqual(second["generated_probe_count"], 0, "second pass sees generated tests and must not duplicate them")
            self.assertEqual(before, digest(donor))

            analysis = json.loads((root / "STACK_ANALYSIS.json").read_text(encoding="utf-8"))
            profile = analysis["modules"][0]
            self.assertEqual(profile["tests"][0]["kind"], "schema-json-probe")
            self.assertEqual(profile["tests"][0]["command"], "python -m json.tool schemas/state.schema.json")
            self.assertTrue(any(cap.get("id") == "evidence.test-suite" for cap in profile["capabilities"]))
            self.assertNotIn(schema_probe_wiring.NO_TEST_UNCERTAINTY, profile["uncertainties"])
            queue = json.loads((root / "AUTOMATED_TEST_QUEUE.json").read_text(encoding="utf-8"))["queue"]
            self.assertEqual(len(queue), 1)

    def test_existing_test_queue_is_not_replaced_by_schema_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_snapshot(Path(td), existing_tests=True)
            result = schema_probe_wiring.apply(root)
            self.assertEqual(result["generated_probe_count"], 0)
            profile = json.loads((root / "STACK_ANALYSIS.json").read_text(encoding="utf-8"))["modules"][0]
            self.assertEqual(profile["tests"][0]["kind"], "test-suite")

    def test_module_without_schema_remains_unwired(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_snapshot(Path(td), with_schema=False)
            result = schema_probe_wiring.apply(root)
            self.assertEqual(result["generated_probe_count"], 0)
            profile = json.loads((root / "STACK_ANALYSIS.json").read_text(encoding="utf-8"))["modules"][0]
            self.assertEqual(profile["tests"], [])
            self.assertIn(schema_probe_wiring.NO_TEST_UNCERTAINTY, profile["uncertainties"])


if __name__ == "__main__":
    unittest.main()
