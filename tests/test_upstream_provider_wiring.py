import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import upstream_provider_wiring as wiring


class UpstreamProviderWiringTests(unittest.TestCase):
    def build_snapshot(self, *, provider_commit="a" * 40, submodule_path="planet-upstream", git_url=None):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        modules = root / "modules"
        consumer = modules / "consumer"
        provider = modules / "provider"
        consumer.mkdir(parents=True)
        provider.mkdir(parents=True)
        repo = "mike-axiom-mir/foundation-planet-experiments"
        expected = "b" * 40
        (consumer / "UPSTREAM_PLANET.json").write_text(json.dumps({
            "schema": wiring.MANIFEST_SCHEMA,
            "source_repository": repo,
            "source_commit": expected,
            "submodule_path": submodule_path,
        }), encoding="utf-8")
        (consumer / "AXM_MONOLITH_SOURCE.json").write_text(json.dumps({"repository": "mike-axiom-mir/consumer", "commit": "c" * 40}), encoding="utf-8")
        (consumer / ".gitmodules").write_text(
            f'[submodule "planet-upstream"]\n\tpath = {submodule_path}\n\turl = {git_url or f"https://github.com/{repo}.git"}\n',
            encoding="utf-8",
        )
        (provider / "AXM_MONOLITH_SOURCE.json").write_text(json.dumps({"repository": repo, "commit": provider_commit}), encoding="utf-8")
        (provider / "payload.txt").write_text("provider donor bytes\n", encoding="utf-8")
        return tmp, root

    def test_exact_selected_provider_stages_only_into_isolated_copy(self):
        tmp, root = self.build_snapshot(provider_commit="b" * 40)
        self.addCleanup(tmp.cleanup)
        consumer_copy = root / "work"
        consumer_copy.mkdir()
        before = wiring._tree_fingerprint(root / "modules" / "provider")
        result = wiring.stage(root, "consumer", consumer_copy)
        after = wiring._tree_fingerprint(root / "modules" / "provider")
        self.assertEqual(result["status"], "STAGED_EXACT_PROVIDER_COPY")
        self.assertEqual(before, after)
        self.assertTrue((consumer_copy / "planet-upstream" / "payload.txt").is_file())
        self.assertTrue(result["provider_donor_unchanged"])

    def test_commit_mismatch_is_hold(self):
        tmp, root = self.build_snapshot(provider_commit="a" * 40)
        self.addCleanup(tmp.cleanup)
        result = wiring.resolve(root, "consumer")
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("match count is 0", result["reason"])

    def test_unsafe_submodule_path_is_hold(self):
        tmp, root = self.build_snapshot(provider_commit="b" * 40, submodule_path="../escape")
        self.addCleanup(tmp.cleanup)
        result = wiring.resolve(root, "consumer")
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("unsafe submodule_path", result["reason"])

    def test_gitmodules_mismatch_is_hold(self):
        tmp, root = self.build_snapshot(provider_commit="b" * 40, git_url="https://github.com/mike-axiom-mir/wrong.git")
        self.addCleanup(tmp.cleanup)
        result = wiring.resolve(root, "consumer")
        self.assertEqual(result["status"], "HOLD")
        self.assertIn(".gitmodules does not match", result["reason"])


if __name__ == "__main__":
    unittest.main()
