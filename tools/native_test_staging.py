#!/usr/bin/env python3
"""Evidence-pinned native test staging learned from current AXM wiring.

Only changes disposable execution copies. The packaged donor tree is never
modified. A learned profile applies only when repository, commit, launcher,
package-manifest and semantic-evidence hashes still match exactly.
"""
from __future__ import annotations
import hashlib, json, os, stat
from pathlib import Path
from typing import Any

SOURCE="AXM_MONOLITH_SOURCE.json"
MANIFEST="PACKAGE_MANIFEST.json"
PROFILE={
 "repository":"mike-axiom-mir/axm-factual-space-simulator",
 "commit":"4ce1726c03fc775276de56d127bf6b393a1139cd",
 "launcher":"run_tests.sh",
 "launcher_sha256":"19fb70f8efcd82471bb5999f3ae643db5544756ba78ef6f828e759192f57def9",
 "manifest_sha256":"6a64ff8f9d4d60e6d9a07bd2d0455a45c56b9ef3a805e347bff24ed144a07345",
 "semantic_evidence":"tests/test_posix_launchers.py",
 "semantic_evidence_sha256":"7745b5a68f69c23628f934d388b11946dad1a1bf964c6004db75fb595fcc811f",
}

class NativeTestStagingError(RuntimeError): pass

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()

def read(path:Path)->Any:
 try: return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,UnicodeDecodeError,json.JSONDecodeError) as e: raise NativeTestStagingError(str(e)) from e

def manifest_paths(value:Any)->set[str]:
 if not isinstance(value,dict): raise NativeTestStagingError("manifest is not an object")
 files=value.get("files") or value.get("entries") or value.get("managed_files")
 if isinstance(files,dict): return {str(x).replace("\\","/").lstrip("./") for x in files}
 if not isinstance(files,list): raise NativeTestStagingError("manifest has no supported file list")
 out=set()
 for item in files:
  x=item if isinstance(item,str) else str((item or {}).get("path") or (item or {}).get("file") or "") if isinstance(item,dict) else ""
  if x: out.add(x.replace("\\","/").lstrip("./"))
 return out

def prepare(snapshot:str|Path,module:str,copy_root:str|Path,profile:dict[str,str]|None=None)->dict[str,Any]:
 p=dict(PROFILE if profile is None else profile)
 root=Path(snapshot).resolve(); modules=(root/"modules").resolve(); source=(modules/module).resolve()
 try: source.relative_to(modules)
 except ValueError: return {"status":"HOLD","reason":"module path escapes modules/"}
 if source.is_symlink() or not source.is_dir(): return {"status":"HOLD","reason":"unsafe/missing module"}
 record_path=source/SOURCE
 if not record_path.is_file() or record_path.is_symlink(): return {"status":"NOT_APPLICABLE","reason":"no safe source record"}
 record=read(record_path)
 if record.get("repository")!=p["repository"]: return {"status":"NOT_APPLICABLE","reason":"no learned profile"}
 if str(record.get("commit") or "").lower()!=p["commit"]: return {"status":"HOLD","reason":"pinned commit drift"}
 try:
  launcher=source/p["launcher"]; manifest=source/MANIFEST; evidence=source/p["semantic_evidence"]
  for path,want in ((launcher,p["launcher_sha256"]),(manifest,p["manifest_sha256"]),(evidence,p["semantic_evidence_sha256"])):
   if path.is_symlink() or not path.is_file() or sha(path)!=want: raise NativeTestStagingError(f"evidence mismatch: {path.relative_to(source)}")
  work=Path(copy_root).resolve()
  if work.is_symlink() or not work.is_dir(): raise NativeTestStagingError("unsafe/missing execution copy")
  marker=(work/SOURCE).resolve(); marker.relative_to(work)
  paths=manifest_paths(read(manifest)); removed=False
  if SOURCE not in paths and marker.is_file() and not marker.is_symlink(): marker.unlink(); removed=True
  restored=[]
  for script in sorted(work.rglob("*.sh")):
   if script.is_symlink() or not script.is_file(): raise NativeTestStagingError("unsafe shell entrypoint")
   script.resolve().relative_to(work)
   mode=script.stat().st_mode
   if not mode & stat.S_IXUSR: os.chmod(script,mode|stat.S_IXUSR); restored.append(script.relative_to(work).as_posix())
  return {"status":"STAGED_NATIVE_TEST_SEMANTICS","preferred_command":"bash run_tests.sh","removed_monolith_marker":removed,"restored_owner_execute":restored,"source_snapshot_mutated":False,"truth_boundary":"Disposable test-copy repair only; TEST_EVIDENCE, not product execution or acceptance."}
 except (NativeTestStagingError,OSError,ValueError) as e:
  return {"status":"HOLD","reason":str(e),"source_snapshot_mutated":False}
