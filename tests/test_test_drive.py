import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"

assemble_spec = importlib.util.spec_from_file_location("assemble", TOOLS / "assemble.py")
assemble = importlib.util.module_from_spec(assemble_spec)
assert assemble_spec.loader
assemble_spec.loader.exec_module(assemble)

import sys
sys.modules["assemble"] = assemble

spec = importlib.util.spec_from_file_location("test_drive", TOOLS / "test_drive.py")
test_drive = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(test_drive)


class TestDriveTests(unittest.TestCase):
    def config(self, enabled=True):
        return {
            "build_enabled": enabled,
            "owner": "mike-axiom-mir",
            "selection": {"visibility": "public-only", "include_forks": False, "include_archived": False},
            "excluded_repositories": [
                {"repository": "mike-axiom-mir/axm-collaboration-platform", "reason": "protected boundary"},
                {"repository": "mike-axiom-mir/axm-monolith", "reason": "self"},
            ],
            "output": {"strip_nested_git": True},
        }

    def plan(self):
        return {
            "schema_version": "0.2",
            "owner": "mike-axiom-mir",
            "selection": {"visibility": "public-only"},
            "modules": [
                {
                    "name": "axm-state-research",
                    "full_name": "mike-axiom-mir/axm-state-research",
                    "clone_url": "https://github.com/mike-axiom-mir/axm-state-research.git",
                    "default_branch": "main",
                    "commit": "a" * 40,
                }
            ],
            "excluded_or_rejected": [],
        }

    def test_saved_plan_accepts_public_owner_module(self):
        test_drive.validate_saved_plan(self.plan(), self.config())

    def test_saved_plan_rejects_excluded_repo(self):
        plan = self.plan()
        plan["modules"][0] = {
            "name": "axm-collaboration-platform",
            "full_name": "mike-axiom-mir/axm-collaboration-platform",
            "clone_url": "https://github.com/mike-axiom-mir/axm-collaboration-platform.git",
            "default_branch": "main",
            "commit": "b" * 40,
        }
        with self.assertRaises(test_drive.TestDriveError):
            test_drive.validate_saved_plan(plan, self.config())

    def test_saved_plan_rejects_foreign_owner(self):
        plan = self.plan()
        plan["modules"][0]["full_name"] = "someone-else/axm-state-research"
        plan["modules"][0]["clone_url"] = "https://github.com/someone-else/axm-state-research.git"
        with self.assertRaises(test_drive.TestDriveError):
            test_drive.validate_saved_plan(plan, self.config())

    def test_saved_plan_rejects_bad_sha(self):
        plan = self.plan()
        plan["modules"][0]["commit"] = "main"
        with self.assertRaises(test_drive.TestDriveError):
            test_drive.validate_saved_plan(plan, self.config())

    def test_plan_digest_is_deterministic(self):
        a = self.plan()
        b = json.loads(json.dumps(a))
        self.assertEqual(test_drive.plan_digest(a), test_drive.plan_digest(b))

    def test_build_needs_explicit_confirmation_before_any_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "assembly.json"
            config_path.write_text(json.dumps(self.config()), encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / test_drive.PLAN_NAME).write_text(json.dumps(self.plan()), encoding="utf-8")
            with self.assertRaises(test_drive.TestDriveError):
                test_drive.build_from_saved_plan(config_path, workspace, confirm=False)
            self.assertFalse((workspace / test_drive.SNAPSHOT_DIR).exists())

    def test_build_hold_blocks_saved_plan_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "assembly.json"
            config_path.write_text(json.dumps(self.config(enabled=False)), encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / test_drive.PLAN_NAME).write_text(json.dumps(self.plan()), encoding="utf-8")
            with self.assertRaises(test_drive.TestDriveError):
                test_drive.build_from_saved_plan(config_path, workspace, confirm=True)
            self.assertFalse((workspace / test_drive.SNAPSHOT_DIR).exists())

    def test_human_result_is_snapshot_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "snapshot"
            snapshot.mkdir()
            test_drive.save_human_result(snapshot, {"module": "demo", "status": "uncertain"})
            payload = json.loads((snapshot / test_drive.RESULTS_NAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["results"][0]["module"], "demo")
            self.assertEqual(payload["results"][0]["status"], "uncertain")


if __name__ == "__main__":
    unittest.main()
