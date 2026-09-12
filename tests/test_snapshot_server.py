import base64
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "serve_snapshot.py"
spec = importlib.util.spec_from_file_location("serve_snapshot", MODULE_PATH)
serve_snapshot = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(serve_snapshot)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class SnapshotServerTests(unittest.TestCase):
    def test_command_validation_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            serve_snapshot.validate_command({"actions": [{"type": "launch_missiles"}]})

    def test_persist_evidence_externalizes_canvas_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "module": "demo",
                "surface": "demo:0",
                "label": "frame-1",
                "canvases": [{
                    "index": 0,
                    "data_url": "data:image/png;base64," + base64.b64encode(PNG).decode("ascii"),
                }],
            }
            summary = serve_snapshot.persist_evidence(root, payload, 1)
            record_path = root / summary["record"]
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            canvas = record["canvases"][0]
            self.assertNotIn("data_url", canvas)
            self.assertTrue((root / canvas["capture_path"]).exists())
            self.assertEqual(canvas["bytes"], len(PNG))

    def test_server_state_exposes_reversible_stress_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "STACK_ANALYSIS.json").write_text(json.dumps({"modules": []}), encoding="utf-8")
            state = serve_snapshot.ServerState(root)
            self.assertFalse(state.stress.status()["active"])
            self.assertTrue(state.stress.start()["active"])
            self.assertFalse(state.stress.stop()["active"])


if __name__ == "__main__":
    unittest.main()
