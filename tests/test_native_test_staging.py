from __future__ import annotations
import hashlib, importlib.util, json, stat, tempfile
from pathlib import Path
import unittest

TOOL=Path(__file__).resolve().parents[1]/"tools"/"native_test_staging.py"
spec=importlib.util.spec_from_file_location("native_test_staging",TOOL)
nts=importlib.util.module_from_spec(spec); spec.loader.exec_module(nts)

def h(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()

class NativeTestStagingTests(unittest.TestCase):
 def fixture(self):
  td=tempfile.TemporaryDirectory(); base=Path(td.name); mod=base/"snapshot/modules/demo"; work=base/"copy"; (mod/"tests").mkdir(parents=True)
  (mod/"AXM_MONOLITH_SOURCE.json").write_text(json.dumps({"repository":"demo/repo","commit":"a"*40}),encoding="utf-8")
  (mod/"run_tests.sh").write_text("#!/usr/bin/env bash\necho ok\n",encoding="utf-8")
  (mod/"tests/semantic.py").write_text("# shell files require owner execute\n",encoding="utf-8")
  (mod/"PACKAGE_MANIFEST.json").write_text(json.dumps({"files":{"run_tests.sh":{},"tests/semantic.py":{}}}),encoding="utf-8")
  import shutil; shutil.copytree(mod,work)
  profile={"repository":"demo/repo","commit":"a"*40,"launcher":"run_tests.sh","launcher_sha256":h(mod/"run_tests.sh"),"manifest_sha256":h(mod/"PACKAGE_MANIFEST.json"),"semantic_evidence":"tests/semantic.py","semantic_evidence_sha256":h(mod/"tests/semantic.py")}
  return td,base,mod,work,profile
 def test_stages_only_disposable_copy(self):
  td,base,mod,work,p=self.fixture(); self.addCleanup(td.cleanup)
  before=(mod/"AXM_MONOLITH_SOURCE.json").read_bytes(); r=nts.prepare(base/"snapshot","demo",work,p)
  self.assertEqual("STAGED_NATIVE_TEST_SEMANTICS",r["status"]); self.assertFalse((work/"AXM_MONOLITH_SOURCE.json").exists()); self.assertEqual(before,(mod/"AXM_MONOLITH_SOURCE.json").read_bytes()); self.assertTrue((work/"run_tests.sh").stat().st_mode & stat.S_IXUSR)
 def test_commit_drift_holds(self):
  td,base,mod,work,p=self.fixture(); self.addCleanup(td.cleanup); p["commit"]="b"*40
  self.assertEqual("HOLD",nts.prepare(base/"snapshot","demo",work,p)["status"])
 def test_evidence_hash_drift_holds(self):
  td,base,mod,work,p=self.fixture(); self.addCleanup(td.cleanup); (mod/"run_tests.sh").write_text("changed",encoding="utf-8")
  self.assertEqual("HOLD",nts.prepare(base/"snapshot","demo",work,p)["status"])
 def test_other_repository_not_applicable(self):
  td,base,mod,work,p=self.fixture(); self.addCleanup(td.cleanup); p["repository"]="other/repo"
  self.assertEqual("NOT_APPLICABLE",nts.prepare(base/"snapshot","demo",work,p)["status"])

if __name__=="__main__": unittest.main()
