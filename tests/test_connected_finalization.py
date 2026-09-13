from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

plumbing_spec = importlib.util.spec_from_file_location("monolith_plumbing", TOOLS / "monolith_plumbing.py")
monolith_plumbing = importlib.util.module_from_spec(plumbing_spec)
assert plumbing_spec.loader
plumbing_spec.loader.exec_module(monolith_plumbing)

finalizer_spec = importlib.util.spec_from_file_location("finalize_connected_snapshot", TOOLS / "finalize_connected_snapshot.py")
finalizer = importlib.util.module_from_spec(finalizer_spec)
assert finalizer_spec.loader
finalizer_spec.loader.exec_module(finalizer)

workflow_spec = importlib.util.spec_from_file_location("ghost_studio_pipeline", TOOLS / "ghost_studio_pipeline.py")
workflow = importlib.util.module_from_spec(workflow_spec)
assert workflow_spec.loader
workflow_spec.loader.exec_module(workflow)


class ConnectedFinalizationTests(unittest.TestCase):
    def write(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def snapshot(self, root: Path) -> Path:
        snapshot = root / "snapshot"
        module = snapshot / "modules" / "demo-module"
        module.mkdir(parents=True)
        self.write(module / "run.py", "def double(value):\n    return {'doubled': value * 2}\n")
        self.write(module / "AXM_MONOLITH_SOURCE.json", json.dumps({
            "repository": "mike-axiom-mir/demo-module",
            "commit": "a" * 40,
            "visibility": "public",
        }))
        self.write(module / "AXM_MODULE.json", json.dumps({
            "capabilities": [{
                "id": "demo.double",
                "provides": ["number.doubled"],
                "accepts": ["number"],
                "callable": {
                    "schema": "axm.callable-capability/v0.1",
                    "kind": "module-export",
                    "runtime": "python",
                    "path": "run.py",
                    "export": "double",
                    "authority": "none",
                    "network": "none",
                },
            }],
        }))
        return snapshot

    def test_plumbing_is_installed_before_any_execution_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = self.snapshot(Path(tmp))
            receipt = monolith_plumbing.plumb_snapshot(snapshot)
            self.assertEqual(receipt["status"], "PLUMBING_INSTALLED_WITH_EXPLICIT_EXECUTION_BOUNDARY")
            self.assertEqual(receipt["native_callable_registry"]["declarations"], 1)
            self.assertEqual(receipt["native_callable_registry"]["source_callable_executed"], 0)
            for name in (
                "LEAF_CAPABILITY_REGISTRY.json",
                "CALLABLE_CAPABILITY_REGISTRY.json",
                "PIPELINE_FABRIC.json",
                "PLUMBING_RECEIPT.json",
                "START_AXM.cmd",
                "START_AXM.sh",
                "invoke_declared_callable.py",
            ):
                self.assertTrue((snapshot / name).is_file(), name)

    def test_finalizer_executes_required_native_callable_then_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.snapshot(root)
            plan = root / "plan.json"
            self.write(plan, json.dumps({
                "schema": "axm.monolith.invocation-plan/v0.1",
                "invocations": [{
                    "address": "demo-module::demo.double",
                    "request": {"schema": "axm.callable-invocation-request/v0.1", "args": [21]},
                    "allow_execution": True,
                    "required": True,
                }],
            }))
            archive = root / "connected.zip"
            result = finalizer.finalize(
                snapshot,
                archive,
                folder_name="AXM-Test",
                invocation_plan=plan,
                required_addresses=["demo-module::demo.double"],
            )
            self.assertEqual(result["status"], "PACKAGED_AFTER_REQUIRED_EVIDENCE_PASS")
            self.assertEqual(result["invocations"]["ledger_summary"]["accepted_exercised_receipts"], 1)
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                self.assertIn("AXM-Test/SNAPSHOT_FILE_RECEIPT.json", names)
                self.assertIn("AXM-Test/START_AXM.cmd", names)

    def test_package_gate_rejects_unproven_required_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.snapshot(root)
            monolith_plumbing.plumb_snapshot(snapshot)
            with self.assertRaisesRegex(finalizer.FinalizationError, "CALLABLE_EXECUTION_LEDGER"):
                finalizer.package_snapshot(
                    snapshot,
                    root / "must-not-exist.zip",
                    folder_name="AXM-Test",
                    required_workflow=None,
                    required_addresses=["demo-module::demo.double"],
                )

    def test_ghost_review_rejects_missing_glb_and_accepts_complete_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            self.write(snapshot / "modules" / "axm-ghost-studio" / "GAME_CHARTER.md", "# Blackline Relay\n")
            attempt = root / "attempt"
            self.write(attempt / "role-assets" / "TRIAL_RECEIPT.json", json.dumps({
                "status": "EXECUTED_AND_STRUCTURALLY_VERIFIED",
            }))
            glb = struct.pack("<4sII", b"glTF", 2, 12)
            for asset in workflow.ROLE_ASSETS:
                path = attempt / "role-assets" / "deliveries" / f"{asset}.glb"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(glb)
            accepted = workflow.review_attempt(snapshot, attempt, reference_required=False)
            self.assertEqual(accepted["status"], "ACCEPTED_STRUCTURAL")
            (attempt / "role-assets" / "deliveries" / "blackline-runner-drone.glb").unlink()
            rejected = workflow.review_attempt(snapshot, attempt, reference_required=False)
            self.assertEqual(rejected["status"], "REJECTED")
            self.assertTrue(any(item["status"] == "MISSING_GLB" for item in rejected["failures"]))

    def test_workflow_output_must_stay_inside_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            with self.assertRaisesRegex(workflow.WorkflowError, "inside the assembled snapshot"):
                workflow.run_workflow(snapshot, root / "outside")

    def test_package_revalidates_bound_blackline_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            self.write(snapshot / "modules" / "axm-ghost-studio" / "GAME_CHARTER.md", "# Blackline Relay\n")
            attempt = snapshot / "outputs" / "blackline" / "attempts" / "001"
            self.write(attempt / "role-assets" / "TRIAL_RECEIPT.json", json.dumps({
                "status": "EXECUTED_AND_STRUCTURALLY_VERIFIED",
            }))
            glb = struct.pack("<4sII", b"glTF", 2, 12)
            for asset in workflow.ROLE_ASSETS:
                path = attempt / "role-assets" / "deliveries" / f"{asset}.glb"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(glb)
            receipt = {
                "schema": workflow.SCHEMA,
                "workflow": workflow.WORKFLOW_ID,
                "status": "EXECUTED_END_TO_END_AND_STRUCTURALLY_ACCEPTED",
                "output": "outputs/blackline",
                "accepted_attempt": 1,
                "reference_required": False,
                "delivery_count": 3,
            }
            evidence = snapshot / "evidence" / "workflows" / f"{workflow.WORKFLOW_ID}.json"
            self.write(evidence, json.dumps(receipt))
            self.assertEqual(finalizer._load_workflow(snapshot, workflow.WORKFLOW_ID)["output"], "outputs/blackline")

            (attempt / "role-assets" / "deliveries" / "blackline-runner-drone.glb").unlink()
            with self.assertRaisesRegex(finalizer.FinalizationError, "no longer passes"):
                finalizer._load_workflow(snapshot, workflow.WORKFLOW_ID)


if __name__ == "__main__":
    unittest.main()
