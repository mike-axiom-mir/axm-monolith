import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "assemble.py"
spec = importlib.util.spec_from_file_location("assemble", MODULE_PATH)
assemble = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(assemble)


class AssemblyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "build_enabled": True,
            "owner": "mike-axiom-mir",
            "selection": {
                "visibility": "public-only",
                "include_forks": False,
                "include_archived": False,
            },
            "excluded_repositories": [
                {
                    "repository": "mike-axiom-mir/axm-collaboration-platform",
                    "reason": "protected boundary",
                }
            ],
        }

    def repo(self, name, **overrides):
        data = {
            "name": name,
            "full_name": f"mike-axiom-mir/{name}",
            "owner": {"login": "mike-axiom-mir"},
            "private": False,
            "visibility": "public",
            "fork": False,
            "archived": False,
            "clone_url": f"https://github.com/mike-axiom-mir/{name}.git",
            "default_branch": "main",
        }
        data.update(overrides)
        return data

    def test_public_axm_repo_is_eligible(self):
        eligible, rejected = assemble.filter_repositories([self.repo("axm-state-research")], self.config)
        self.assertEqual([r["full_name"] for r in eligible], ["mike-axiom-mir/axm-state-research"])
        self.assertEqual(rejected, [])

    def test_private_repo_is_never_eligible(self):
        eligible, rejected = assemble.filter_repositories(
            [self.repo("private-project", private=True, visibility="private")], self.config
        )
        self.assertEqual(eligible, [])
        self.assertIn("private repository", rejected[0]["reason"])

    def test_collaboration_platform_is_excluded(self):
        eligible, rejected = assemble.filter_repositories(
            [self.repo("axm-collaboration-platform")], self.config
        )
        self.assertEqual(eligible, [])
        self.assertEqual(rejected[0]["reason"], "protected boundary")

    def test_monolith_cannot_include_itself(self):
        eligible, rejected = assemble.filter_repositories([self.repo("axm-monolith")], self.config)
        self.assertEqual(eligible, [])
        self.assertIn("recursively assemble itself", rejected[0]["reason"])

    def test_foreign_owner_is_rejected(self):
        foreign = self.repo("axm-copy")
        foreign["full_name"] = "someone-else/axm-copy"
        foreign["owner"] = {"login": "someone-else"}
        eligible, rejected = assemble.filter_repositories([foreign], self.config)
        self.assertEqual(eligible, [])
        self.assertEqual(rejected[0]["reason"], "owner mismatch")

    def test_build_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(assemble.AssemblyError):
                assemble.build_monolith(self.config, Path(tmp) / "out", confirm=False)

    def test_build_hold_blocks_materialization_even_with_confirmation(self):
        held = dict(self.config)
        held["build_enabled"] = False
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(assemble.AssemblyError):
                assemble.build_monolith(held, Path(tmp) / "out", confirm=True)

    def test_build_runs_repository_owned_plumbing_after_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            plan = {
                "schema_version": "0.3",
                "modules": [{
                    "name": "demo",
                    "full_name": "mike-axiom-mir/demo",
                    "clone_url": "https://github.com/mike-axiom-mir/demo.git",
                    "default_branch": "main",
                    "commit": "a" * 40,
                }],
            }
            with (
                mock.patch.object(assemble, "resolve_plan", return_value=plan),
                mock.patch.object(assemble, "materialize_module", return_value={
                    "repository": "mike-axiom-mir/demo",
                    "commit": "a" * 40,
                    "path": "modules/demo",
                    "materialized": True,
                }),
                mock.patch.object(assemble, "run_stack_analysis", return_value={"summary": {"module_count": 1}}) as analysis,
                mock.patch.object(assemble, "run_snapshot_plumbing", return_value={"status": "installed"}) as plumbing,
            ):
                manifest = assemble.build_monolith(self.config, output, confirm=True)
            analysis.assert_called_once_with(output)
            plumbing.assert_called_once_with(output, refresh_analysis=False)
            self.assertEqual(manifest["plumbing"]["status"], "installed")

    def test_github_api_retries_transient_server_error(self):
        payload = b'{"ok": true}'
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = payload
        response.__exit__.return_value = False
        failure = urllib.error.HTTPError(
            "https://api.github.com/example", 502, "temporary", {}, io.BytesIO(b"temporary")
        )
        opener = mock.Mock(side_effect=[failure, response])
        sleeper = mock.Mock()

        result = assemble.api_get_json(
            "https://api.github.com/example", attempts=2, opener=opener, sleeper=sleeper
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(opener.call_count, 2)
        sleeper.assert_called_once_with(0.5)

    def test_github_api_does_not_retry_non_transient_error(self):
        failure = urllib.error.HTTPError(
            "https://api.github.com/example", 404, "missing", {}, io.BytesIO(b"missing")
        )
        opener = mock.Mock(side_effect=failure)
        sleeper = mock.Mock()

        with self.assertRaisesRegex(assemble.AssemblyError, "after 1 attempt"):
            assemble.api_get_json(
                "https://api.github.com/example", attempts=4, opener=opener, sleeper=sleeper
            )

        opener.assert_called_once()
        sleeper.assert_not_called()

    def test_plan_falls_back_to_git_and_keeps_deterministic_order(self):
        repos = [self.repo("z-module"), self.repo("a-module")]

        def getter(url, _token):
            if "/users/" in url:
                return repos
            raise assemble.AssemblyError("temporary API failure")

        with mock.patch.object(assemble, "run_git", return_value=("b" * 40) + "\trefs/heads/main"):
            plan = assemble.resolve_plan(self.config, getter=getter)

        self.assertEqual([item["name"] for item in plan["modules"]], ["a-module", "z-module"])
        self.assertTrue(all(item["commit"] == "b" * 40 for item in plan["modules"]))
        self.assertTrue(all(item["head_resolution"] == "git-ls-remote-fallback" for item in plan["modules"]))


if __name__ == "__main__":
    unittest.main()
