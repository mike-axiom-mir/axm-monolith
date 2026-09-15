import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "package_bin_entrypoints.py"
spec = importlib.util.spec_from_file_location("package_bin_entrypoints", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class PackageBinEntrypointTest(unittest.TestCase):
    def test_dict_bins_become_existing_node_entrypoints(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "bin").mkdir()
            (root / "bin" / "alpha.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            (root / "bin" / "beta.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            rows = mod.declared_node_bins(root, {
                "name": "example",
                "bin": {"beta": "./bin/beta.js", "alpha": "bin/alpha.js"},
            })
            self.assertEqual(["bin/alpha.js", "bin/beta.js"], [r["path"] for r in rows])
            self.assertEqual("declared-package-bin:alpha", rows[0]["evidence"])
            self.assertEqual("node bin/alpha.js", rows[0]["command"])
            self.assertEqual(["--help"], rows[0]["probe_args"])

    def test_string_bin_uses_package_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "cli.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            rows = mod.declared_node_bins(root, {"name": "pkg-cli", "bin": "./cli.js"})
            self.assertEqual(1, len(rows))
            self.assertEqual("declared-package-bin:pkg-cli", rows[0]["evidence"])
            self.assertEqual(["pkg-cli"], rows[0]["aliases"])

    def test_missing_and_escaping_targets_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root.parent / "outside.js"
            outside.write_text("x", encoding="utf-8")
            try:
                rows = mod.declared_node_bins(root, {
                    "bin": {"missing": "bin/nope.js", "escape": "../outside.js"},
                })
                self.assertEqual([], rows)
            finally:
                outside.unlink(missing_ok=True)

    def test_aliases_are_grouped_by_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "cli.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            rows = mod.declared_node_bins(root, {"bin": {"z": "cli.js", "a": "./cli.js"}})
            self.assertEqual(1, len(rows))
            self.assertEqual(["a", "z"], rows[0]["aliases"])

    def test_matching_axm_discovery_command_supplies_bounded_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "cli.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            package = {
                "bin": {"demo": "cli.js"},
                "axmCapability": {"entrypoints": {"command": "demo", "discoveryCommand": "demo describe"}},
            }
            row = mod.declared_node_bins(root, package)[0]
            self.assertEqual(["describe"], row["probe_args"])
            self.assertEqual("axmCapability.discoveryCommand", row["probe_source"])

    def test_mismatched_discovery_command_does_not_cross_bind(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "cli.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            package = {
                "bin": {"demo": "cli.js"},
                "axmCapability": {"entrypoints": {"command": "other", "discoveryCommand": "other describe"}},
            }
            self.assertEqual(["--help"], mod.declared_node_bins(root, package)[0]["probe_args"])


if __name__ == "__main__":
    unittest.main()
