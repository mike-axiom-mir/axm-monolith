from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ghost_studio_asset_trial", ROOT / "tools" / "ghost_studio_asset_trial.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GhostStudioAssetTrialTests(unittest.TestCase):
    def _snapshot(self, root: Path, *, include_all: bool = True) -> Path:
        build = root / "build"
        modules = list(MODULE.REQUIRED_MODULES if include_all else MODULE.REQUIRED_MODULES[:-1])
        records = []
        for name in modules:
            module = build / "modules" / name
            module.mkdir(parents=True)
            records.append({"name": name, "repository": f"mike-axiom-mir/{name}", "commit": "a" * 40})
        ghost = build / "modules" / "axm-ghost-studio"
        ghost.mkdir(parents=True, exist_ok=True)
        (ghost / "GAME_CHARTER.md").write_text("# Game 001 Charter — Blackline Relay\n", encoding="utf-8")
        (build / "axm-stack.lock.json").write_text(
            json.dumps({"schema_version": "0.3", "modules": records}), encoding="utf-8"
        )
        return build

    def test_preflight_binds_exact_required_modules_and_charter(self):
        with tempfile.TemporaryDirectory() as temp:
            state = MODULE.load_snapshot(self._snapshot(Path(temp)))
            self.assertEqual(set(state["module_records"]), set(MODULE.REQUIRED_MODULES))
            self.assertTrue(state["lock_sha256"].startswith("sha256:"))
            self.assertTrue(state["charter_sha256"].startswith("sha256:"))

    def test_preflight_rejects_missing_asset_forge(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(MODULE.TrialError, "lacks required modules"):
                MODULE.load_snapshot(self._snapshot(Path(temp), include_all=False))

    def test_preflight_rejects_wrong_ghost_studio_body(self):
        with tempfile.TemporaryDirectory() as temp:
            build = self._snapshot(Path(temp))
            (build / "modules" / "axm-ghost-studio" / "GAME_CHARTER.md").write_text(
                "# unrelated game\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(MODULE.TrialError, "expected Blackline Relay"):
                MODULE.load_snapshot(build)

    def test_receipt_paths_are_portable_and_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            result = MODULE._portable_receipt_paths(
                {"path": str(stage / "generated" / "asset.png"), "files": [{"path": "map.png"}]},
                stage,
            )
            self.assertEqual(result["path"], "generated/asset.png")
            self.assertEqual(result["files"][0]["path"], "map.png")
            with self.assertRaisesRegex(MODULE.TrialError, "escaped"):
                MODULE._portable_receipt_paths({"path": "/outside/asset.png"}, stage)


if __name__ == "__main__":
    unittest.main()
