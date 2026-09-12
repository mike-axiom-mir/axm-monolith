import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "assemble.py"
spec = importlib.util.spec_from_file_location("assemble", MODULE_PATH)
assemble = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(assemble)


class AssemblyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.config = {
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


if __name__ == "__main__":
    unittest.main()
