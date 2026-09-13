#!/usr/bin/env python3
"""Deterministic inspector for an already materialized AXM monolith build.

The inspector never modifies source module directories. It inventories module structure,
loads optional native AXM module manifests, derives explicitly labelled structural/inferred
capabilities, maps candidate interfaces, and emits a local offline dashboard.

Truth boundary: discovered/inferred capability is not proof of runtime interoperability.
Connections remain candidate/declared until separately exercised and evidenced.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import Any, Iterable

SCHEMA_VERSION = "0.3"
MANIFEST_NAMES = ("AXM_MODULE.json", "axm-module.json", ".axm/module.json")
README_NAMES = ("README.md", "README.MD", "readme.md", "README.txt")
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", "dist", "build", "coverage", ".cache",
}
LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".jsx": "JavaScript", ".html": "HTML",
    ".css": "CSS", ".json": "JSON", ".md": "Markdown", ".toml": "TOML", ".yml": "YAML",
    ".yaml": "YAML", ".rs": "Rust", ".go": "Go", ".c": "C", ".h": "C/C++",
    ".cpp": "C++", ".hpp": "C++", ".java": "Java", ".kt": "Kotlin", ".sh": "Shell",
    ".ps1": "PowerShell", ".sql": "SQL", ".wasm": "WebAssembly",
}
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".wav", ".mp3", ".ogg", ".glb", ".gltf", ".obj", ".fbx"}
LEAF_LEVELS = {"atom", "organ", "capability", "prototype", "shadow", "tool"}

DOMAIN_RULES: list[dict[str, Any]] = [
    {"id":"creation.universal","description":"General creation / software construction capability is described by this module.","terms":("universal-creation","universal creation","creation machine"),"provides":("artifact","artifact.software","capability.generated"),"accepts":("objective","specification","capability.request"),"tags":("creation","software")},
    {"id":"creation.grammar","description":"Grammar-driven creation or direction vocabulary is described by this module.","terms":("grammer","grammar"),"provides":("creation.grammar","specification"),"accepts":("objective","direction"),"tags":("creation","grammar")},
    {"id":"institution.workflow","description":"Institution / specialist-lane work organization is described by this module.","terms":("institution-fabric","institution fabric","the building"),"provides":("workflow.lane","artifact.handoff","workflow.institution"),"accepts":("objective","capability","artifact","evidence","state"),"tags":("institution","workflow")},
    {"id":"state.directional","description":"Directional / grounded state-transition evaluation is described by this module.","terms":("directional-state","directional state","the field"),"provides":("decision.transition","state.constraint","evidence.transition"),"accepts":("state","transition.proposal","evidence"),"tags":("state","governance")},
    {"id":"state.machine-floor","description":"Machine/state-floor execution or state research is described by this module.","terms":("state-research","machine floor","floor-born","framestate","frame state"),"provides":("state","state.snapshot","state.transition","evidence.replay"),"accepts":("objective","state","mutation","transition.proposal"),"tags":("state","machine-floor")},
    {"id":"asset.game","description":"Reusable game-asset capability is described by this module.","terms":("game-assets","game assets"),"provides":("artifact.game-asset","asset"),"accepts":("asset.request","specification"),"tags":("assets","game")},
    {"id":"asset.material-surface","description":"Material / surface generation or representation is described by this module.","terms":("material-surface","material surface"),"provides":("artifact.material","asset.material","asset"),"accepts":("material.request","specification"),"tags":("assets","materials")},
    {"id":"game.studio","description":"Game-studio coordination / game-production capability is described by this module.","terms":("ghost-studio","ghost studio","game studio"),"provides":("workflow.game-studio","artifact.game-build","evidence.game"),"accepts":("game.objective","artifact.game-asset","artifact","evidence","state"),"tags":("game","studio")},
    {"id":"game.hub","description":"Local game-hub / launch surface is described by this module.","terms":("local-game-hub","game hub"),"provides":("interface.game-hub","interface.local"),"accepts":("artifact.game-build","game"),"tags":("game","interface","local")},
    {"id":"simulation","description":"Simulation capability is described by this module.","terms":("simulator","simulation"),"provides":("artifact.simulation","state.simulation","evidence.simulation"),"accepts":("scenario","state","specification"),"tags":("simulation",)},
    {"id":"intelligence.experiential","description":"Experimental learning / experience-growing intelligence capability is described by this module.","terms":("walmi","waldo","mirror research"),"provides":("intelligence.experimental","state.experience"),"accepts":("experience","observation","state","objective"),"tags":("intelligence","learning")},
    {"id":"capability.ignition","description":"Capability ignition / activation fabric is described by this module.","terms":("ignition-fabric","ignition fabric"),"provides":("capability.ignition",),"accepts":("capability","capability.definition","state"),"tags":("capability",)},
    {"id":"capability.parallel","description":"Parallel capability composition / execution is described by this module.","terms":("parallel-capability","parallel capability"),"provides":("capability.parallel","workflow.parallel"),"accepts":("capability","objective","state"),"tags":("capability","parallel")},
    {"id":"network.multiplayer","description":"Multiplayer / network coordination capability is described by this module.","terms":("multiplayer","p2p","peer-to-peer"),"provides":("network.multiplayer","network.session"),"accepts":("game","game.state","state"),"tags":("network","game")},
    {"id":"discovery.assistant","description":"Discovery / exploration assistance is described by this module.","terms":("discovery-buddy","discovery buddy"),"provides":("discovery","evidence.discovery"),"accepts":("objective","question","state"),"tags":("discovery",)},
    {"id":"interface.machine-voice","description":"Machine voice / expression interface is described by this module.","terms":("machine-voice","machine voice"),"provides":("interface.machine-voice","artifact.audio"),"accepts":("message","state","expression"),"tags":("interface","audio")},
    {"id":"research.matter-transfer","description":"Matter-transfer research/experiment capability is described by this module; no physical-achievement claim is implied.","terms":("matter-transfer","matter transfer"),"provides":("research.matter-transfer","evidence.research"),"accepts":("experiment","hypothesis","evidence"),"tags":("research",)},
]


def read_text(path: Path, max_bytes: int = 1_000_000) -> str:
    try:
        if path.stat().st_size > max_bytes:
            with path.open("rb") as handle:
                raw = handle.read(max_bytes)
            return raw.decode("utf-8", errors="replace")
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return ""


def iter_module_files(module_dir: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(module_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        root_path = Path(root)
        for name in names:
            path = root_path / name
            try:
                if path.is_file(): files.append(path)
            except OSError: continue
    files.sort(key=lambda p: p.relative_to(module_dir).as_posix().lower())
    return files


def source_record(module_dir: Path) -> dict[str, Any]:
    path = module_dir / "AXM_MONOLITH_SOURCE.json"
    if not path.exists(): return {"repository": module_dir.name, "commit": None, "visibility": "unknown"}
    try: return json.loads(read_text(path))
    except json.JSONDecodeError: return {"repository": module_dir.name, "commit": None, "visibility": "unknown", "source_record_error":"invalid JSON"}


def read_readme(module_dir: Path) -> tuple[str | None, str]:
    for name in README_NAMES:
        path = module_dir / name
        if path.exists(): return name, read_text(path, max_bytes=400_000)
    return None, ""


def first_readme_description(readme: str, fallback: str) -> str:
    if not readme.strip(): return fallback
    for paragraph in re.split(r"\n\s*\n", readme):
        p = paragraph.strip()
        if not p or p.startswith("#") or p.startswith("```"): continue
        p = re.sub(r"[`*_>#]", "", p); p = re.sub(r"\s+", " ", p).strip()
        if p: return p[:420]
    return fallback


def load_native_manifest(module_dir: Path) -> tuple[str | None, dict[str, Any] | None, str | None]:
    for name in MANIFEST_NAMES:
        path = module_dir / name
        if not path.exists(): continue
        try: data = json.loads(read_text(path))
        except json.JSONDecodeError as exc: return name, None, f"invalid native manifest JSON: {exc}"
        if not isinstance(data, dict): return name, None, "native manifest must be a JSON object"
        return name, data, None
    return None, None, None


def language_counts(files: Iterable[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in files:
        language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        if language: counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def parse_package_json(module_dir: Path) -> dict[str, Any] | None:
    path = module_dir / "package.json"
    if not path.exists(): return None
    try:
        data = json.loads(read_text(path)); return data if isinstance(data, dict) else None
    except json.JSONDecodeError: return None


def parse_pyproject(module_dir: Path) -> dict[str, Any] | None:
    path = module_dir / "pyproject.toml"
    if not path.exists(): return None
    try: return tomllib.loads(read_text(path))
    except (tomllib.TOMLDecodeError, ValueError): return None


def detect_entrypoints(module_dir: Path, files: list[Path], package: dict[str, Any] | None, pyproject: dict[str, Any] | None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []; rels = {p.relative_to(module_dir).as_posix() for p in files}
    for candidate, kind, command in [("index.html","browser","open index.html"),("main.py","python","python main.py"),("app.py","python","python app.py"),("cli.py","python","python cli.py"),("server.py","python","python server.py")]:
        if candidate in rels: entries.append({"kind":kind,"path":candidate,"command":command,"evidence":"structural"})
    if package:
        scripts = package.get("scripts") or {}
        if isinstance(scripts, dict):
            for name in scripts:
                if name in {"start","dev","serve","preview","build","test","check","lint"}: entries.append({"kind":"npm-script","path":"package.json","command":f"npm run {name}","evidence":"declared-package-script"})
        main = package.get("main")
        if isinstance(main, str): entries.append({"kind":"node","path":main,"command":f"node {main}","evidence":"declared-package-main"})
    if pyproject:
        project = pyproject.get("project") or {}; scripts = project.get("scripts") or {} if isinstance(project, dict) else {}
        if isinstance(scripts, dict):
            for name, target in scripts.items(): entries.append({"kind":"python-script","path":"pyproject.toml","command":name,"evidence":f"declared target {target}"})
    seen=set(); result=[]
    for entry in entries:
        key=(entry.get("command",""),entry.get("path",""))
        if key not in seen: seen.add(key); result.append(entry)
    return result


def discover_tests(module_dir: Path, files: list[Path], package: dict[str, Any] | None) -> list[dict[str, str]]:
    rels=[p.relative_to(module_dir).as_posix() for p in files]; test_files=[r for r in rels if r.startswith("tests/") or Path(r).name.startswith("test_") or ".test." in Path(r).name or Path(r).name.endswith("_test.py")]; tests=[]
    if test_files:
        if any(r.endswith(".py") for r in test_files): tests.append({"kind":"test-suite","command":"python -m unittest discover -s tests -v","safety":"executes module test code","evidence":"structural"})
        for rel in sorted(r for r in test_files if r.endswith((".mjs",".js",".cjs")))[:30]: tests.append({"kind":"node-test","command":f"node {rel}","safety":"executes module test code","evidence":"structural"})
    if package:
        scripts=package.get("scripts") or {}
        if isinstance(scripts, dict):
            for name in sorted(scripts):
                if any(token in name.lower() for token in ("test","check","lint")): tests.append({"kind":"npm-test","command":f"npm run {name}","safety":"executes package script","evidence":"declared-package-script"})
    if any(r.endswith(".py") for r in rels): tests.append({"kind":"syntax-probe","command":"python -m compileall -q .","safety":"syntax compilation only","evidence":"generated-safe-probe"})
    return tests


def native_capabilities(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest: return []
    raw=manifest.get("capabilities",[])
    if not isinstance(raw,list): return []
    result=[]
    for idx,item in enumerate(raw):
        if isinstance(item,str): result.append({"id":item,"description":item,"source":"native-manifest","evidence_status":"declared_not_verified","confidence":1.0,"provides":[item],"accepts":[],"tags":[]}); continue
        if not isinstance(item,dict): continue
        cid=str(item.get("id") or item.get("name") or f"native.{idx}"); evidence=item.get("evidence"); status=str(evidence.get("status") if isinstance(evidence,dict) and evidence.get("status") else item.get("evidence_status") or "declared_not_verified")
        result.append({"id":cid,"description":str(item.get("description") or cid),"source":"native-manifest","evidence_status":status,"confidence":1.0,"provides":[str(x) for x in item.get("provides",[]) if str(x).strip()],"accepts":[str(x) for x in item.get("accepts",[]) if str(x).strip()],"tags":[str(x) for x in item.get("tags",[]) if str(x).strip()]})
    return result


def structural_capabilities(module_dir: Path, files: list[Path], languages: dict[str,int], tests: list[dict[str,str]], entrypoints: list[dict[str,str]]) -> list[dict[str,Any]]:
    rels={p.relative_to(module_dir).as_posix() for p in files}; caps=[]
    def add(cid,desc,provides,accepts,tags): caps.append({"id":cid,"description":desc,"source":"structural-scan","evidence_status":"detected_not_executed","confidence":0.9,"provides":provides,"accepts":accepts,"tags":tags})
    if "index.html" in rels and any(p.suffix.lower() in {".js",".mjs",".ts"} for p in files): add("runtime.browser-app","Locally materialized browser application structure detected.",["artifact.browser-app","interface.browser"],["browser","input"],["browser","ui"])
    if languages.get("Python"): add("runtime.python","Python source is present.",["runtime.python"],["source.python"],["python"])
    if languages.get("JavaScript") or languages.get("TypeScript"): add("runtime.javascript","JavaScript/TypeScript source is present.",["runtime.javascript"],["source.javascript"],["javascript"])
    if tests: add("evidence.test-suite","Automated test or static-check entry points are present.",["evidence.test-suite"],["source.module"],["testing","evidence"])
    if any("schema" in p.name.lower() or "/schemas/" in f"/{p.relative_to(module_dir).as_posix().lower()}" for p in files): add("contract.schema","Machine-readable schema/contract files are present.",["contract.schema"],["state","artifact"],["schema","contract"])
    if entrypoints: add("interface.entrypoint","One or more executable/launch entry points are structurally discoverable.",["interface.entrypoint"],["objective","input"],["interface"])
    if any(p.suffix.lower() in ASSET_SUFFIXES for p in files): add("asset.static","Static visual/audio/3D asset files are present.",["asset"],["asset.request"],["assets"])
    return caps


def inferred_domain_capabilities(module_name: str, readme: str, files: list[Path], module_dir: Path) -> list[dict[str,Any]]:
    corpus=" ".join([module_name.lower(),readme[:250000].lower()]+[p.relative_to(module_dir).as_posix().lower() for p in files[:1500]]); caps=[]
    for rule in DOMAIN_RULES:
        hits=sorted({term for term in rule["terms"] if term in corpus})
        if not hits: continue
        caps.append({"id":rule["id"],"description":rule["description"],"source":"inference-rule","evidence_status":"inferred_not_verified","confidence":0.65 if len(hits)==1 else min(0.88,0.65+0.06*(len(hits)-1)),"provides":list(rule["provides"]),"accepts":list(rule["accepts"]),"tags":list(rule["tags"]),"matched_terms":hits})
    return caps


def merge_capabilities(capabilities: list[dict[str,Any]]) -> list[dict[str,Any]]:
    rank={"native-manifest":3,"structural-scan":2,"inference-rule":1}; by_id={}
    for cap in capabilities:
        cid=str(cap["id"]); current=by_id.get(cid)
        if current is None or rank.get(cap.get("source",""),0)>rank.get(current.get("source",""),0): by_id[cid]=cap
        else:
            for key in ("provides","accepts","tags"): current[key]=sorted(set(current.get(key,[]))|set(cap.get(key,[])))
    return [by_id[k] for k in sorted(by_id)]


def module_profile(module_dir: Path) -> dict[str,Any]:
    files=iter_module_files(module_dir); source=source_record(module_dir); readme_name,readme=read_readme(module_dir); package=parse_package_json(module_dir); pyproject=parse_pyproject(module_dir); languages=language_counts(files); entrypoints=detect_entrypoints(module_dir,files,package,pyproject); tests=discover_tests(module_dir,files,package); manifest_name,manifest,manifest_error=load_native_manifest(module_dir)
    capabilities=merge_capabilities(native_capabilities(manifest)+structural_capabilities(module_dir,files,languages,tests,entrypoints)+inferred_domain_capabilities(module_dir.name,readme,files,module_dir)); total_bytes=0
    for path in files:
        try: total_bytes += path.stat().st_size
        except OSError: pass
    tags=sorted({tag for cap in capabilities for tag in cap.get("tags",[])}); uncertainties=[]
    if not manifest: uncertainties.append("No native AXM module manifest; capability semantics rely on structural/inferred inspection.")
    if manifest_error: uncertainties.append(manifest_error)
    if not entrypoints: uncertainties.append("No obvious launch/CLI entrypoint detected.")
    if not tests: uncertainties.append("No automated test/static-check command detected.")
    if not capabilities: uncertainties.append("No capability could be identified deterministically from current structure/readme heuristics.")
    return {"schema_version":SCHEMA_VERSION,"module":module_dir.name,"repository":source.get("repository",module_dir.name),"commit":source.get("commit"),"description":first_readme_description(readme,f"Module {module_dir.name}"),"source_record":source,"native_manifest":manifest_name,"native_manifest_error":manifest_error,"readme":readme_name,"file_count":len(files),"total_bytes":total_bytes,"languages":languages,"entrypoints":entrypoints,"tests":tests,"capabilities":capabilities,"tags":tags,"uncertainties":uncertainties}


def interface_match(provided: str, accepted: str) -> tuple[bool,str]:
    p,a=provided.strip().lower(),accepted.strip().lower()
    if not p or not a: return False,""
    if p==a: return True,"exact"
    broad={"artifact","asset","state","evidence","capability","objective","interface","game","input","specification"}
    if a in broad and p.startswith(a+"."): return True,"consumer-broad"
    if p in broad and a.startswith(p+"."): return True,"producer-broad"
    return False,""


def build_connection_graph(modules: list[dict[str,Any]]) -> dict[str,Any]:
    edges=[]
    for producer in modules:
        for consumer in modules:
            if producer["module"]==consumer["module"]: continue
            for pcap in producer["capabilities"]:
                for provided in pcap.get("provides",[]):
                    for ccap in consumer["capabilities"]:
                        for accepted in ccap.get("accepts",[]):
                            matched,mode=interface_match(provided,accepted)
                            if not matched: continue
                            exact_native=mode=="exact" and pcap.get("source")=="native-manifest" and ccap.get("source")=="native-manifest"
                            if exact_native: status,score="declared_contract_match_not_tested",3
                            elif mode=="exact" and "inference-rule" not in {pcap.get("source"),ccap.get("source")}: status,score="structurally_possible_not_tested",2
                            else: status,score="inferred_candidate_not_tested",1
                            edges.append({"from":producer["module"],"to":consumer["module"],"provided":provided,"accepted":accepted,"match":mode,"status":status,"score":score,"producer_capability":pcap["id"],"consumer_capability":ccap["id"],"truth_boundary":"candidate interface relation only; runtime interoperability has not been established by this graph"})
    unique={}
    for edge in edges:
        key=(edge["from"],edge["to"],edge["provided"],edge["accepted"]); current=unique.get(key)
        if current is None or edge["score"]>current["score"]: unique[key]=edge
    final=sorted(unique.values(),key=lambda e:(-e["score"],e["from"].lower(),e["to"].lower(),e["provided"]))
    return {"schema_version":SCHEMA_VERSION,"node_count":len(modules),"edge_count":len(final),"nodes":[{"module":m["module"],"repository":m["repository"],"tags":m["tags"]} for m in modules],"edges":final,"truth_boundary":"No edge is VERIFIED by graph construction alone; status describes evidence class only."}


def composition_candidates(graph: dict[str,Any], max_candidates: int=80) -> list[dict[str,Any]]:
    adjacency={}
    for edge in graph["edges"]: adjacency.setdefault(edge["from"],[]).append(edge)
    candidates=[]; seen=set()
    for start in sorted(adjacency):
        stack=[(start,[start],[],0)]
        while stack:
            node,path,edges,score=stack.pop()
            if 2<=len(path)<=4:
                key=tuple(path)
                if key not in seen: seen.add(key); candidates.append({"modules":path[:],"interfaces":[e["provided"] for e in edges],"score":score,"status":"candidate_unverified","truth_boundary":"graph-derived composition hypothesis; no cross-module execution is implied"})
            if len(path)>=4: continue
            for edge in adjacency.get(node,[])[:50]:
                nxt=edge["to"]
                if nxt not in path: stack.append((nxt,path+[nxt],edges+[edge],score+int(edge["score"])))
    candidates.sort(key=lambda c:(-c["score"],-len(c["modules"]),"|".join(c["modules"]).lower())); return candidates[:max_candidates]


def human_test_queue(modules: list[dict[str,Any]]) -> list[dict[str,Any]]:
    queue=[]
    for module in modules:
        tags=set(module["tags"]); entry_kinds={e["kind"] for e in module["entrypoints"]}; tasks=[]; priority=0
        if "game" in tags: tasks.append("Play a short normal-input session and record what is actually understandable, usable, fun/confusing, and where it fails."); priority+=4
        if {"ui","browser","interface"}&tags or "browser" in entry_kinds: tasks.append("Open the visible interface and visually inspect actual rendered output; do not infer visual quality from code alone."); priority+=3
        if "audio" in tags: tasks.append("Listen to the actual output and record audibility/clarity; do not infer listening quality from asset presence."); priority+=2
        if "simulation" in tags: tasks.append("Run one representative scenario and compare the observed result with the module's stated scope."); priority+=2
        inferred=[c for c in module["capabilities"] if c.get("source")=="inference-rule"]
        if inferred and not tasks: tasks.append("Confirm whether the inferred capability description matches what this module really does before relying on it in a composition."); priority+=1
        if tasks: queue.append({"module":module["module"],"repository":module["repository"],"priority":priority,"tasks":tasks,"entrypoints":module["entrypoints"],"truth_boundary":"human validation request; completion should be recorded as new evidence rather than assumed"})
    queue.sort(key=lambda x:(-x["priority"],x["module"].lower())); return queue


def automated_test_queue(modules: list[dict[str,Any]]) -> list[dict[str,Any]]:
    return [{"module":m["module"],**test,"status":"discovered_not_run"} for m in modules for test in m["tests"]]


def _json_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _leaf_occurrences(value: Any, *, path: str, pointer: str = "") -> list[dict[str, str]]:
    """Return exact machine-readable capability identifiers with provenance.

    This deliberately does not infer identifiers from prose. It records explicit IDs in
    atom/organ/capability-like objects and string IDs in capability arrays. Duplicate
    occurrences are retained so template/reference density is not confused with identity.
    """
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        level = str(value.get("level") or "").strip().lower()
        declared = value.get("capability_id") if isinstance(value.get("capability_id"), str) else value.get("id")
        path_parts = {part.lower() for part in Path(path).parts}
        path_level = "atom" if "atoms" in path_parts else "organ" if "organs" in path_parts else ""
        if isinstance(declared, str) and declared.strip() and (level in LEAF_LEVELS or path_level):
            found.append({
                "id": declared.strip(),
                "level": level or path_level,
                "path": path,
                "pointer": pointer or "/",
                "declaration": "object-id",
            })
        for key in ("capabilities", "capability_ids"):
            items = value.get(key)
            if isinstance(items, list):
                base = f"{pointer}/{_json_pointer_token(key)}"
                for index, item in enumerate(items):
                    if isinstance(item, str) and item.strip():
                        found.append({
                            "id": item.strip(),
                            "level": "capability",
                            "path": path,
                            "pointer": f"{base}/{index}",
                            "declaration": f"{key}-item",
                        })
                    elif isinstance(item, dict):
                        item_id = item.get("capability_id") if isinstance(item.get("capability_id"), str) else item.get("id")
                        item_level = str(item.get("level") or "").strip().lower()
                        item_path_parts = {part.lower() for part in Path(path).parts}
                        if (isinstance(item_id, str) and item_id.strip()
                                and item_level not in LEAF_LEVELS
                                and not ({"atoms", "organs"} & item_path_parts)):
                            found.append({
                                "id": item_id.strip(),
                                "level": "capability",
                                "path": path,
                                "pointer": f"{base}/{index}",
                                "declaration": f"{key}-object",
                            })
        for key, item in value.items():
            found.extend(_leaf_occurrences(
                item,
                path=path,
                pointer=f"{pointer}/{_json_pointer_token(str(key))}",
            ))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_leaf_occurrences(item, path=path, pointer=f"{pointer}/{index}"))
    return found


def build_leaf_capability_registry(build_root: Path) -> dict[str, Any]:
    root = build_root.resolve()
    modules_root = root / "modules"
    if not modules_root.is_dir():
        raise ValueError(f"not an AXM monolith build: missing {modules_root}")
    by_address: dict[str, dict[str, Any]] = {}
    invalid_json_files = 0
    json_files_scanned = 0
    occurrence_count = 0
    for module_dir in sorted((p for p in modules_root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        for json_path in (p for p in iter_module_files(module_dir) if p.suffix.lower() == ".json"):
            try:
                payload = json.loads(read_text(json_path, max_bytes=8_000_000))
            except json.JSONDecodeError:
                invalid_json_files += 1
                continue
            json_files_scanned += 1
            relative = json_path.relative_to(module_dir).as_posix()
            for occurrence in _leaf_occurrences(payload, path=relative):
                occurrence_count += 1
                address = f"{module_dir.name}::leaf::{occurrence['id']}"
                entry = by_address.setdefault(address, {
                    "address": address,
                    "module": module_dir.name,
                    "id": occurrence["id"],
                    "levels": [],
                    "occurrences": [],
                    "status": "declared_not_exercised",
                    "source_capability_execution": False,
                })
                if occurrence["level"] not in entry["levels"]:
                    entry["levels"].append(occurrence["level"])
                entry["occurrences"].append({key: occurrence[key] for key in ("path", "pointer", "declaration", "level")})
    entries = sorted(by_address.values(), key=lambda item: item["address"].lower())
    for entry in entries:
        entry["levels"].sort()
        entry["occurrences"].sort(key=lambda item: (item["path"].lower(), item["pointer"], item["declaration"]))
    return {
        "schema": "axm.monolith.leaf-capability-registry/v0.1",
        "summary": {
            "declared_leaf_capability_count": len(entries),
            "declaration_occurrence_count": occurrence_count,
            "json_files_scanned": json_files_scanned,
            "invalid_json_files_skipped": invalid_json_files,
            "source_callable_count": 0,
        },
        "entries": entries,
        "truth_boundary": (
            "A declared leaf ID is an exact machine-readable identifier with source provenance. "
            "It is not automatically a callable function, unique implementation, verified capability, "
            "permission, compatibility proof, merge authority, or CANON."
        ),
    }


def stack_summary(modules,graph,human_queue,automated_queue,compositions,leaf_registry=None):
    capabilities=[cap for m in modules for cap in m["capabilities"]]; evidence_counts={}
    for cap in capabilities: evidence_counts[cap.get("evidence_status","unknown")]=evidence_counts.get(cap.get("evidence_status","unknown"),0)+1
    leaf_summary=(leaf_registry or {}).get("summary",{})
    return {"module_count":len(modules),"file_count":sum(m["file_count"] for m in modules),"total_bytes":sum(m["total_bytes"] for m in modules),"capability_count":len(capabilities),"aggregate_capability_count":len(capabilities),"declared_leaf_capability_count":leaf_summary.get("declared_leaf_capability_count",0),"leaf_declaration_occurrence_count":leaf_summary.get("declaration_occurrence_count",0),"total_catalogued_capability_count":len(capabilities)+leaf_summary.get("declared_leaf_capability_count",0),"capability_evidence":dict(sorted(evidence_counts.items())),"candidate_connection_count":graph["edge_count"],"candidate_composition_count":len(compositions),"human_test_module_count":len(human_queue),"discovered_test_command_count":len(automated_queue),"native_manifest_module_count":sum(1 for m in modules if m["native_manifest"])}


def write_json(path: Path,payload: Any)->None: path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")


def render_report(analysis):
    s=analysis["summary"]; lines=["# AXM Full-Stack Capability Report","","This report describes one materialized public-stack snapshot. It does **not** upgrade inferred or co-located capabilities into verified interoperability.","","## Snapshot summary","",f"- Modules: **{s['module_count']}**",f"- Files: **{s['file_count']}**",f"- Bytes: **{s['total_bytes']}**",f"- Detected/declared capabilities: **{s['capability_count']}**",f"- Candidate cross-module interface edges: **{s['candidate_connection_count']}**",f"- Candidate composition chains shown: **{s['candidate_composition_count']}**",f"- Modules needing human validation: **{s['human_test_module_count']}**",f"- Discovered test/static-check commands: **{s['discovered_test_command_count']}**","","## Evidence classes",""]
    for status,count in s["capability_evidence"].items(): lines.append(f"- `{status}`: {count}")
    lines += ["","## Modules",""]
    for module in analysis["modules"]:
        caps=", ".join(c["id"] for c in module["capabilities"]) or "none detected"; lines += [f"### {module['module']}","",f"- Source: `{module['repository']}` @ `{module.get('commit') or 'unknown'}`",f"- Capabilities: {caps}",f"- Entry points: {len(module['entrypoints'])}; test commands: {len(module['tests'])}"]
        if module["uncertainties"]: lines.append("- Uncertainties: "+" | ".join(module["uncertainties"]))
        lines.append("")
    lines += ["## Truth boundary","","- Same snapshot does not mean same runtime.","- Candidate graph edges are not verified integrations.","- Inference-rule capabilities are leads for testing, not facts stronger than their evidence.","- Source modules remain authoritative for themselves.",""]
    return "\n".join(lines)


def render_dashboard(analysis):
    data=json.dumps(analysis,separators=(",",":")).replace("</","<\\/")
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AXM Assembly — Full Stack</title><style>:root{--bg:#080b11;--panel:#111722;--line:#263246;--text:#eef4ff;--muted:#96a5bd;--warn:#ffd479;--accent:#7cc8ff}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#070a0f,#0c1119);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}header{padding:28px max(22px,4vw);border-bottom:1px solid var(--line);background:#090d14dd;position:sticky;top:0;z-index:3;backdrop-filter:blur(10px)}h1{margin:0;font-size:clamp(26px,4vw,46px)}.sub,.muted{color:var(--muted)}main{padding:24px max(18px,4vw) 80px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}.big{font-size:28px;font-weight:800;color:var(--accent)}h2{margin-top:34px}h3{margin:0 0 8px}input{width:100%;padding:13px;background:#0a0f17;border:1px solid var(--line);border-radius:12px;color:var(--text)}.module-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin-top:14px}.pill{display:inline-block;border:1px solid #31415b;border-radius:999px;padding:3px 8px;margin:2px;color:#cde5ff}.cap{margin:7px 0;padding:8px 10px;border-left:3px solid var(--accent);background:#0c121b;border-radius:5px}.evidence{font-size:12px;color:var(--warn)}table{width:100%;border-collapse:collapse;background:var(--panel)}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.notice{padding:14px;border:1px solid #66562f;background:#19160d;border-radius:12px;color:#ffe5a2}.small{font-size:12px}code{color:#bfe3ff}</style></head><body><header><h1>AXM — The Assembly</h1><div class="sub">Full-stack snapshot explorer. Capability and connection labels preserve their evidence class.</div></header><main><div class="notice"><b>Truth boundary:</b> candidate connections and composition chains are hypotheses until exercised on the exact pinned stack.</div><section id="summary" class="grid" style="margin-top:16px"></section><h2>Search the entire stack</h2><input id="search" placeholder="module, capability, tag, runtime, interface…"><h2>Modules & capabilities</h2><div id="modules" class="module-grid"></div><h2>Candidate compositions</h2><div id="compositions" class="module-grid"></div><h2>Candidate connection graph</h2><div style="overflow:auto"><table><thead><tr><th>From</th><th>Interface</th><th>To</th><th>Status</th></tr></thead><tbody id="edges"></tbody></table></div><h2>Human test queue</h2><div id="human" class="module-grid"></div><h2>Discovered automated/static checks</h2><div style="overflow:auto"><table><thead><tr><th>Module</th><th>Command</th><th>Safety</th><th>Status</th></tr></thead><tbody id="tests"></tbody></table></div></main><script type="application/json" id="data">'''+data+'''</script><script>const D=JSON.parse(document.getElementById('data').textContent),S=D.summary,fmt=n=>new Intl.NumberFormat().format(n),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const summary=[['Modules',S.module_count],['Files',S.file_count],['Capabilities',S.capability_count],['Candidate edges',S.candidate_connection_count],['Candidate chains',S.candidate_composition_count],['Human-test modules',S.human_test_module_count],['Test commands',S.discovered_test_command_count],['Native manifests',S.native_manifest_module_count]];document.getElementById('summary').innerHTML=summary.map(([k,v])=>`<div class="card"><div class="big">${fmt(v)}</div><div class="muted">${esc(k)}</div></div>`).join('');function renderModules(filter=''){const q=filter.toLowerCase();document.getElementById('modules').innerHTML=D.modules.filter(m=>!q||JSON.stringify(m).toLowerCase().includes(q)).map(m=>`<article class="card"><h3>${esc(m.module)}</h3><div class="muted small">${esc(m.repository)} @ ${esc((m.commit||'unknown').slice(0,12))}</div><p>${esc(m.description)}</p><div>${m.tags.map(t=>`<span class="pill">${esc(t)}</span>`).join('')}</div><div>${m.capabilities.map(c=>`<div class="cap"><b>${esc(c.id)}</b><div class="small">${esc(c.description)}</div><div class="evidence">${esc(c.evidence_status)} · ${esc(c.source)}</div></div>`).join('')||'<div class="muted">No capability identified yet.</div>'}</div>${m.entrypoints.length?`<div class="small"><b>Entrypoints</b><br>${m.entrypoints.map(e=>`<code>${esc(e.command)}</code>`).join('<br>')}</div>`:''}${m.uncertainties.length?`<details><summary>Uncertainties (${m.uncertainties.length})</summary><ul>${m.uncertainties.map(u=>`<li>${esc(u)}</li>`).join('')}</ul></details>`:''}</article>`).join('')}renderModules();document.getElementById('search').addEventListener('input',e=>renderModules(e.target.value));document.getElementById('compositions').innerHTML=D.compositions.map(c=>`<div class="card"><b>${c.modules.map(esc).join(' → ')}</b><div class="small muted">interfaces: ${c.interfaces.map(esc).join(' → ')||'n/a'}</div><div class="evidence">${esc(c.status)} · score ${c.score}</div></div>`).join('')||'<div class="muted">No composition chains detected yet.</div>';document.getElementById('edges').innerHTML=D.graph.edges.slice(0,600).map(e=>`<tr><td>${esc(e.from)}</td><td><code>${esc(e.provided)}</code><div class="small muted">${esc(e.match)}</div></td><td>${esc(e.to)}</td><td>${esc(e.status)}</td></tr>`).join('');document.getElementById('human').innerHTML=D.human_test_queue.map(h=>`<div class="card"><h3>${esc(h.module)}</h3><div class="evidence">priority ${h.priority}</div><ul>${h.tasks.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>${h.entrypoints.map(e=>`<code>${esc(e.command)}</code>`).join('<br>')}</div>`).join('')||'<div class="muted">No human-specific validation tasks detected.</div>';document.getElementById('tests').innerHTML=D.automated_test_queue.map(t=>`<tr><td>${esc(t.module)}</td><td><code>${esc(t.command)}</code></td><td>${esc(t.safety)}</td><td>${esc(t.status)}</td></tr>`).join('');</script></body></html>'''


def analyze_build(build_root: Path) -> dict[str,Any]:
    build_root=build_root.resolve(); modules_dir=build_root/"modules"
    if not modules_dir.is_dir(): raise ValueError(f"not an AXM monolith build: missing {modules_dir}")
    modules=[module_profile(p) for p in sorted(modules_dir.iterdir(),key=lambda p:p.name.lower()) if p.is_dir()]; graph=build_connection_graph(modules); compositions=composition_candidates(graph); human_queue=human_test_queue(modules); automated_queue=automated_test_queue(modules); leaf_registry=build_leaf_capability_registry(build_root); summary=stack_summary(modules,graph,human_queue,automated_queue,compositions,leaf_registry)
    analysis={"schema_version":SCHEMA_VERSION,"summary":summary,"modules":modules,"graph":graph,"compositions":compositions,"human_test_queue":human_queue,"automated_test_queue":automated_queue,"truth_boundary":"This analysis distinguishes native declaration, structural detection, and inference. No candidate graph edge/composition is verified by analysis alone."}
    analysis_dir=build_root/"analysis"; analysis_dir.mkdir(exist_ok=True); per_module=analysis_dir/"modules"; per_module.mkdir(exist_ok=True)
    for module in modules: write_json(per_module/f"{module['module']}.json",module)
    write_json(build_root/"STACK_ANALYSIS.json",analysis); write_json(build_root/"CAPABILITY_REGISTRY.json",{"schema_version":SCHEMA_VERSION,"capabilities":[{"module":m["module"],"repository":m["repository"],**cap} for m in modules for cap in m["capabilities"]]}); write_json(build_root/"LEAF_CAPABILITY_REGISTRY.json",leaf_registry); write_json(build_root/"CONNECTION_GRAPH.json",graph); write_json(build_root/"COMPOSITION_CANDIDATES.json",{"schema_version":SCHEMA_VERSION,"compositions":compositions}); write_json(build_root/"HUMAN_TEST_QUEUE.json",{"schema_version":SCHEMA_VERSION,"queue":human_queue}); write_json(build_root/"AUTOMATED_TEST_QUEUE.json",{"schema_version":SCHEMA_VERSION,"queue":automated_queue,"truth_boundary":"commands are discovered, not executed automatically"}); (build_root/"STACK_REPORT.md").write_text(render_report(analysis),encoding="utf-8"); (build_root/"OPEN_ME.html").write_text(render_dashboard(analysis),encoding="utf-8")
    return {"summary":summary,"outputs":["OPEN_ME.html","STACK_REPORT.md","STACK_ANALYSIS.json","CAPABILITY_REGISTRY.json","LEAF_CAPABILITY_REGISTRY.json","CONNECTION_GRAPH.json","COMPOSITION_CANDIDATES.json","HUMAN_TEST_QUEUE.json","AUTOMATED_TEST_QUEUE.json","analysis/modules/"]}


def load_analysis(build_root: Path)->dict[str,Any]:
    path=build_root/"STACK_ANALYSIS.json"
    if not path.exists(): raise ValueError(f"missing {path}; run analyze first")
    return json.loads(path.read_text(encoding="utf-8"))


def query_analysis(build_root: Path,term: str)->list[dict[str,Any]]:
    data=load_analysis(build_root); q=term.lower().strip(); results=[]
    for module in data["modules"]:
        if q in json.dumps(module).lower(): results.append({"module":module["module"],"repository":module["repository"],"matching_capabilities":[cap["id"] for cap in module["capabilities"] if q in json.dumps(cap).lower()],"entrypoints":module["entrypoints"]})
    return results


def route_between(build_root: Path,start: str,target: str,max_hops: int=5)->dict[str,Any]:
    data=load_analysis(build_root); graph=data["graph"]; modules={n["module"] for n in graph["nodes"]}
    if start not in modules or target not in modules: raise ValueError("start/target module must exist in analyzed build")
    adjacency={}
    for edge in graph["edges"]: adjacency.setdefault(edge["from"],[]).append(edge)
    queue=[(start,[start],[])]; seen={start}
    while queue:
        node,path,edges=queue.pop(0)
        if node==target: return {"found":True,"modules":path,"edges":edges,"status":"candidate_route_not_verified"}
        if len(path)-1>=max_hops: continue
        for edge in sorted(adjacency.get(node,[]),key=lambda e:-e["score"]):
            nxt=edge["to"]
            if nxt in seen: continue
            seen.add(nxt); queue.append((nxt,path+[nxt],edges+[edge]))
    return {"found":False,"modules":[],"edges":[],"status":"no_candidate_route_detected"}


def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Inspect/query an already materialized AXM monolith snapshot"); sub=p.add_subparsers(dest="command",required=True); a=sub.add_parser("analyze"); a.add_argument("build",type=Path); q=sub.add_parser("query"); q.add_argument("build",type=Path); q.add_argument("term"); r=sub.add_parser("route"); r.add_argument("build",type=Path); r.add_argument("start"); r.add_argument("target"); r.add_argument("--max-hops",type=int,default=5); return p


def main()->int:
    args=parser().parse_args()
    try:
        if args.command=="analyze": print(json.dumps(analyze_build(args.build),indent=2,sort_keys=True)); return 0
        if args.command=="query": print(json.dumps(query_analysis(args.build,args.term),indent=2,sort_keys=True)); return 0
        if args.command=="route": print(json.dumps(route_between(args.build,args.start,args.target,args.max_hops),indent=2,sort_keys=True)); return 0
    except (ValueError,OSError,json.JSONDecodeError) as exc: print(f"ERROR: {exc}",file=sys.stderr); return 2
    return 2

if __name__=="__main__": raise SystemExit(main())
