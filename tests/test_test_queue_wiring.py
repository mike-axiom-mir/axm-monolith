from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("test_queue_wiring", ROOT / "tools" / "test_queue_wiring.py")
assert SPEC and SPEC.loader
test_queue_wiring = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(test_queue_wiring)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestQueueWiringTests(unittest.TestCase):
    def make_snapshot(self, base: Path, module: str, tests: list[dict]) -> tuple[Path, Path]:
        root = base / "snapshot"
        donor = root / "modules" / module
        donor.mkdir(parents=True)
        write_json(root / "STACK_ANALYSIS.json", {
            "schema_version": "0.3",
            "modules": [{"module": module, "repository": f"example/{module}", "commit": "a" * 40, "tests": tests}],
            "automated_test_queue": [{"module": module, **item, "status": "discovered_not_run"} for item in tests],
        })
        write_json(root / "AUTOMATED_TEST_QUEUE.json", {
            "schema_version": "0.3",
            "queue": [{"module": module, **item, "status": "discovered_not_run"} for item in tests],
        })
        return root, donor

    def generic(self) -> dict:
        return {
            "kind": "test-suite",
            "command": test_queue_wiring.GENERIC_UNITTEST,
            "safety": "executes module test code",
            "evidence": "structural",
        }

    def test_src_layout_is_annotated_without_rewriting_command_or_donor(self):
        with tempfile.TemporaryDirectory() as td:
            root, donor = self.make_snapshot(Path(td), "src-layout", [self.generic()])
            (donor / "src" / "pkg").mkdir(parents=True)
            source = donor / "src" / "pkg" / "core.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            before = digest(source)
            result = test_queue_wiring.apply(root)
            queue = json.loads((root / "AUTOMATED_TEST_QUEUE.json").read_text())["queue"]
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["src_layout_retry_candidates"], ["src-layout"])
            self.assertEqual(queue[0]["command"], test_queue_wiring.GENERIC_UNITTEST)
            self.assertEqual(queue[0]["execution_environment"]["PYTHONPATH_prepend"], "src")
            self.assertTrue(queue[0]["execution_environment"]["retry_on_import_failure"])
            self.assertEqual(before, digest(source))

    def test_zero_default_discovery_becomes_exact_named_unittest(self):
        with tempfile.TemporaryDirectory() as td:
            root, donor = self.make_snapshot(Path(td), "named-tests", [self.generic()])
            tests = donor / "tests"
            tests.mkdir()
            (tests / "discovery_intake.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\nif __name__ == '__main__': unittest.main()\n",
                encoding="utf-8",
            )
            result = test_queue_wiring.apply(root)
            queue = json.loads((root / "AUTOMATED_TEST_QUEUE.json").read_text())["queue"]
            self.assertEqual(result["zero_discovery_named_replacement_count"], 1)
            self.assertEqual(queue[0]["command"], "python -m unittest -v tests.discovery_intake")
            self.assertEqual(queue[0]["evidence"], "generated-nonstandard-unittest-main")

    def test_missing_tests_dir_becomes_bounded_direct_unittest_scripts(self):
        with tempfile.TemporaryDirectory() as td:
            root, donor = self.make_snapshot(Path(td), "scattered-tests", [self.generic()])
            script = donor / "portable" / "test_portable.py"
            script.parent.mkdir(parents=True)
            script.write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\nif __name__ == '__main__': unittest.main()\n",
                encoding="utf-8",
            )
            (donor / "portable" / "test_not_explicit.py").write_text("print('not an explicit unittest runner')\n", encoding="utf-8")
            result = test_queue_wiring.apply(root)
            queue = json.loads((root / "AUTOMATED_TEST_QUEUE.json").read_text())["queue"]
            self.assertEqual(result["missing_tests_dir_direct_replacement_count"], 1)
            self.assertEqual([item["command"] for item in queue], ["python portable/test_portable.py"])
            self.assertEqual(queue[0]["evidence"], "generated-direct-unittest-script")

    def test_default_test_pattern_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            root, donor = self.make_snapshot(Path(td), "normal-tests", [self.generic()])
            tests = donor / "tests"
            tests.mkdir()
            (tests / "test_real.py").write_text("import unittest\n", encoding="utf-8")
            result = test_queue_wiring.apply(root)
            queue = json.loads((root / "AUTOMATED_TEST_QUEUE.json").read_text())["queue"]
            self.assertEqual(result["zero_discovery_named_replacement_count"], 0)
            self.assertEqual(queue[0]["command"], test_queue_wiring.GENERIC_UNITTEST)


if __name__ == "__main__":
    unittest.main()
