import importlib.util
import json
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

    def test_string_bin_uses_package_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "cli.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            rows = mod.declared_node_bins(root, {"name": "pkg-cli", "bin": "./cli.js"})
            self.assertEqual(1, len(rows))
            self.assertEqual("declared-package-bin:pkg-cli", rows[0]["evidence"])

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

    def test_grammar_shape_discovers_both_bins_without_execution_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "bin").mkdir()
            for name in ("axm-grammar-capabilities.js", "axm-grammar-glass-snapshot.js"):
                (root / "bin" / name).write_text("#!/usr/bin/env node\n", encoding="utf-8")
            rows = mod.declared_node_bins(root, {
                "name": "axm-102-grammar-body",
                "bin": {
                    "axm-grammar-capabilities": "bin/axm-grammar-capabilities.js",
                    "axm-grammar-glass-snapshot": "bin/axm-grammar-glass-snapshot.js",
                },
            })
            self.assertEqual(2, len(rows))
            self.assertTrue(all(r["kind"] == "node" for r in rows))
            self.assertTrue(all(r["evidence"].startswith("declared-package-bin:") for r in rows))


if __name__ == "__main__":
    unittest.main()
