#!/usr/bin/env python3
"""Install the executable plumbing layer into an AXM Monolith snapshot.

This is the repository-owned boundary between co-location and execution. It always refreshes
the static/leaf catalogues, exports candidate pipelines, builds the native callable registry,
installs the local front door, and copies the bounded invocation/ledger runtimes into the
snapshot. It never promotes a catalogue entry or graph edge to executable evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import callable_registry
import inspect_stack
import one_click
import pipeline_fabric


SCHEMA = "axm.monolith.plumbing-receipt/v0.1"
RUNTIME_FILES = (
    "inspect_stack.py",
    "user_surface.py",
    "one_click.py",
    "serve_snapshot.py",
    "stress_all.py",
    "stress_all_v2.py",
    "monolith_plumbing.py",
    "finalize_connected_snapshot.py",
    "callable_registry.py",
    "invoke_declared_callable.py",
    "callable_execution_ledger.py",
    "js_callable_runner.mjs",
    "python_callable_runner.py",
    "pipeline_fabric.py",
    "ghost_studio_asset_trial.py",
    "ghost_studio_reference_kit.py",
    "ghost_studio_pipeline.py",
)


class PlumbingError(RuntimeError):
    pass


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _install_execution_lab(snapshot: Path) -> str:
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AXM Execution Lab</title><style>:root{color-scheme:dark;--bg:#070b10;--panel:#111a24;--line:#2e4258;--text:#edf6ff;--muted:#9bb0c4;--cyan:#61d7ff;--amber:#ffc86a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#142738,var(--bg) 55%);color:var(--text);font:15px/1.5 system-ui,sans-serif}main{width:min(1050px,calc(100% - 28px));margin:auto;padding:30px 0 70px}section{margin:18px 0;padding:18px;background:var(--panel);border:1px solid var(--line);border-radius:14px}h1,h2{color:var(--cyan)}label{display:block;margin:10px 0 4px;color:var(--muted)}input,textarea{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;background:#071019;color:var(--text)}textarea{min-height:110px;font-family:ui-monospace,monospace}button{margin-top:12px;padding:10px 14px;border:0;border-radius:8px;background:var(--cyan);color:#00131c;font-weight:800;cursor:pointer}.warn{border-color:#795f2e;color:#ffe0a1}pre{overflow:auto;max-height:430px;background:#05080c;padding:12px;border-radius:8px}.small{color:var(--muted);font-size:13px}a{color:var(--cyan)}</style></head><body><main><p><a href="OPEN_ME.html">← AXM front door</a></p><h1>AXM Execution Lab</h1><p class="warn">A catalogue address is not execution. These controls require an explicit confirmation phrase and write receipts into this exact snapshot.</p><section><h2>Native callable registry</h2><div id="summary">Loading…</div><label>Exact module::capability address</label><input id="address" placeholder="module::capability"><label>Invocation request JSON</label><textarea id="request">{"schema":"axm.callable-invocation-request/v0.1","args":[]}</textarea><button id="invoke">Execute exact declared callable</button></section><section><h2>Blackline 3D workflow</h2><p class="small">Reference is optional and must already exist inside the snapshot. Output must not exist.</p><label>Output path</label><input id="workflow-output" value="outputs/blackline-3d"><label>Reference path inside snapshot (optional)</label><input id="reference" placeholder="reference/blackline.png"><button id="workflow">Execute exact workflow</button></section><section><h2>Result</h2><pre id="result">No execution requested.</pre></section><script>const out=document.getElementById('result');async function jsonFetch(url,options){const response=await fetch(url,options),text=await response.text();let value;try{value=JSON.parse(text)}catch{value={raw:text}}out.textContent=JSON.stringify(value,null,2);if(!response.ok)throw new Error('Request blocked: '+response.status);return value}fetch('/api/capabilities').then(r=>r.json()).then(v=>{document.getElementById('summary').textContent=`${v.summary.callable_declaration_count} declarations · ${v.summary.declared_callable_not_exercised} valid, not exercised · ${v.summary.blocked_invalid_callable_declaration} blocked`;const first=v.entries.find(e=>e.status==='declared_callable_not_exercised');if(first)document.getElementById('address').value=first.address}).catch(e=>document.getElementById('summary').textContent=e.message);document.getElementById('invoke').onclick=async()=>{try{await jsonFetch('/api/invoke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm_execution:'EXECUTE_EXACT_DECLARED_CALLABLE',address:document.getElementById('address').value,request:JSON.parse(document.getElementById('request').value)})})}catch(e){out.textContent+='\n'+e.message}};document.getElementById('workflow').onclick=async()=>{const reference=document.getElementById('reference').value.trim();try{await jsonFetch('/api/workflow',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm_execution:'EXECUTE_EXACT_WORKFLOW',workflow:'ghost-studio.blackline-3d.v0.4',output:document.getElementById('workflow-output').value,reference:reference||null})})}catch(e){out.textContent+='\n'+e.message}};</script></main></body></html>'''
    path = snapshot / "EXECUTION_LAB.html"
    path.write_text(html, encoding="utf-8")
    front = snapshot / "OPEN_ME.html"
    text = front.read_text(encoding="utf-8", errors="replace")
    marker = "AXM_EXECUTION_LAB_LINK_V0_1"
    if marker not in text:
        widget = '<div id="AXM_EXECUTION_LAB_LINK_V0_1" style="position:fixed;right:16px;bottom:66px;z-index:99999"><a href="EXECUTION_LAB.html" style="display:block;padding:10px 14px;background:#0b1720;border:1px solid #427a94;border-radius:999px;color:#9ce8ff;text-decoration:none;font:600 13px system-ui">⚙ Execution Lab</a></div>'
        text = text.replace("</body>", widget + "</body>", 1) if "</body>" in text else text + widget
        front.write_text(text, encoding="utf-8")
    return path.name


def _install_runtime(snapshot: Path) -> list[str]:
    tools = Path(__file__).resolve().parent
    installed: list[str] = []
    for name in RUNTIME_FILES:
        source = tools / name
        if not source.is_file():
            raise PlumbingError(f"required runtime is missing: {source}")
        target = snapshot / name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        installed.append(name)

    windows = r'''@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: RUN_DECLARED_CAPABILITY.cmd module::capability --request request.json --receipt receipt.json --allow-python
  exit /b 2
)
python invoke_declared_callable.py "%CD%" %*
exit /b %ERRORLEVEL%
'''
    (snapshot / "RUN_DECLARED_CAPABILITY.cmd").write_text(windows, encoding="utf-8")
    unix = '''#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ "$#" -eq 0 ]; then
  echo "Usage: ./RUN_DECLARED_CAPABILITY.sh module::capability --request request.json --receipt receipt.json --allow-python" >&2
  exit 2
fi
exec "${PYTHON_BIN:-python3}" invoke_declared_callable.py "$PWD" "$@"
'''
    unix_path = snapshot / "RUN_DECLARED_CAPABILITY.sh"
    unix_path.write_text(unix, encoding="utf-8")
    try:
        unix_path.chmod(unix_path.stat().st_mode | 0o111)
    except OSError:
        pass
    installed.extend(("RUN_DECLARED_CAPABILITY.cmd", "RUN_DECLARED_CAPABILITY.sh"))
    blackline_windows = r'''@echo off
setlocal
cd /d "%~dp0"
python ghost_studio_pipeline.py --snapshot "%CD%" %*
exit /b %ERRORLEVEL%
'''
    (snapshot / "RUN_BLACKLINE_PIPELINE.cmd").write_text(blackline_windows, encoding="utf-8")
    blackline_unix = '''#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec "${PYTHON_BIN:-python3}" ghost_studio_pipeline.py --snapshot "$PWD" "$@"
'''
    blackline_unix_path = snapshot / "RUN_BLACKLINE_PIPELINE.sh"
    blackline_unix_path.write_text(blackline_unix, encoding="utf-8")
    try:
        blackline_unix_path.chmod(blackline_unix_path.stat().st_mode | 0o111)
    except OSError:
        pass
    installed.extend(("RUN_BLACKLINE_PIPELINE.cmd", "RUN_BLACKLINE_PIPELINE.sh"))
    return installed


def plumb_snapshot(snapshot: str | Path, *, refresh_analysis: bool = True) -> dict[str, Any]:
    root = Path(snapshot).resolve()
    if root.is_symlink() or not (root / "modules").is_dir():
        raise PlumbingError("snapshot must be a real directory containing modules/")

    if refresh_analysis:
        analysis = inspect_stack.analyze_build(root)
    else:
        analysis_path = root / "STACK_ANALYSIS.json"
        if not analysis_path.is_file():
            raise PlumbingError("snapshot analysis is missing")
        analysis = {"summary": json.loads(analysis_path.read_text(encoding="utf-8"))["summary"]}
    pipelines = pipeline_fabric.export_pipeline_fabric(root)
    callables = callable_registry.write_registry(root)
    launchers = one_click.install_snapshot_launchers(root)
    runtime_files = _install_runtime(root)
    execution_lab = _install_execution_lab(root)

    callable_summary = callables["summary"]
    summary = analysis["summary"]
    receipt = {
        "schema": SCHEMA,
        "status": "PLUMBING_INSTALLED_WITH_EXPLICIT_EXECUTION_BOUNDARY",
        "catalogue": {
            "aggregate_capabilities": summary.get("aggregate_capability_count", summary.get("capability_count", 0)),
            "declared_leaf_ids": summary.get("declared_leaf_capability_count", 0),
            "leaf_declaration_occurrences": summary.get("leaf_declaration_occurrence_count", 0),
            "total_catalogued_addresses": summary.get("total_catalogued_capability_count", summary.get("capability_count", 0)),
        },
        "native_callable_registry": {
            "declarations": callable_summary["callable_declaration_count"],
            "valid_not_exercised": callable_summary["declared_callable_not_exercised"],
            "blocked_invalid": callable_summary["blocked_invalid_callable_declaration"],
            "source_callable_executed": 0,
        },
        "candidate_pipeline_fabric": pipelines,
        "one_front_door": launchers,
        "installed_runtime_files": runtime_files,
        "execution_lab": execution_lab,
        "outputs": {
            "leaf_registry": "LEAF_CAPABILITY_REGISTRY.json",
            "callable_registry": "CALLABLE_CAPABILITY_REGISTRY.json",
            "pipeline_registry": "PIPELINE_FABRIC.json",
            "receipt": "PLUMBING_RECEIPT.json",
            "execution_lab": execution_lab,
        },
        "truth_boundary": (
            "Plumbing installation makes discovery, invocation and evidence recording available. "
            "Only a validated execution receipt can prove an exact callable ran; catalogue addresses "
            "and candidate graph edges remain non-executable claims until then."
        ),
    }
    _write_json(root / "PLUMBING_RECEIPT.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install AXM Monolith discovery, callable and one-launch plumbing")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = plumb_snapshot(args.snapshot)
    except (PlumbingError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"monolith plumbing: BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], **result["catalogue"], **result["native_callable_registry"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
