#!/usr/bin/env python3
"""Generate the AXM Monolith capability/use interface and AI-native user-facing test surface.

The generated interface is intentionally local-first. It can launch browser-facing module
entrypoints inside a same-origin iframe, drive them with a deterministic synthetic input bus,
and capture structural visual state plus exact PNG captures for readable canvas surfaces.

Truth boundary:
- synthetic DOM events are not trusted browser events (`isTrusted` remains false);
- DOM/layout capture is not a whole-window screenshot;
- canvas PNG capture is pixel evidence only for canvases that can be read without taint;
- a launchable surface is not proof that the capability works correctly;
- non-browser capabilities remain inspectable until a specific execution adapter exists.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.3"
LAB_MARKER = "AXM_AI_NATIVE_SURFACE_V0_3"

INPUT_PROTOCOL: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "name": "AXM AI-native user input bus",
    "truth_boundary": (
        "Synthetic keyboard/pointer events are machine-generated browser events and are not trusted user activation. "
        "They can test ordinary event handling but cannot prove flows that require a real trusted gesture."
    ),
    "actions": {
        "tap_key": {"required": ["key"], "optional": ["code", "duration_ms", "ctrl", "alt", "shift", "meta"]},
        "key_down": {"required": ["key"], "optional": ["code", "ctrl", "alt", "shift", "meta"]},
        "key_up": {"required": ["key"], "optional": ["code", "ctrl", "alt", "shift", "meta"]},
        "type_text": {"required": ["text"], "optional": ["interval_ms"]},
        "wait": {"required": ["ms"], "optional": []},
        "click": {"required": ["x", "y"], "optional": ["button"]},
        "click_selector": {"required": ["selector"], "optional": ["button"]},
        "focus_selector": {"required": ["selector"], "optional": []},
        "reload": {"required": [], "optional": []},
        "snapshot": {"required": [], "optional": ["label"]},
    },
    "default_keyboard": [
        "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "w", "a", "s", "d",
        "Enter", " ", "Escape", "Tab", "r", "Shift", "Control",
    ],
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def browser_entrypoints(module: dict[str, Any], module_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in module.get("entrypoints", []):
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").replace("\\", "/").lstrip("/")
        kind = str(entry.get("kind") or "")
        if path and path.lower().endswith((".html", ".htm")) and path not in seen:
            seen.add(path)
            entries.append({**entry, "path": path, "source": "analysis-entrypoint"})
        elif kind == "browser" and path and path not in seen:
            seen.add(path)
            entries.append({**entry, "path": path, "source": "analysis-entrypoint"})

    # Structural fallback for repos whose existing inspector did not promote nested HTML.
    if module_root.is_dir():
        candidates = sorted(
            (p for p in module_root.rglob("*.html") if p.is_file()),
            key=lambda p: (0 if p.name.lower() == "index.html" else 1, len(p.parts), p.as_posix().lower()),
        )
        for path in candidates[:24]:
            rel = path.relative_to(module_root).as_posix()
            if rel not in seen:
                seen.add(rel)
                entries.append({
                    "kind": "browser",
                    "path": rel,
                    "command": f"open {rel}",
                    "evidence": "user-surface structural HTML fallback",
                    "source": "structural-html-fallback",
                })
    return entries


def build_surface_registry(snapshot: Path, analysis: dict[str, Any]) -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []
    capabilities: list[dict[str, Any]] = []
    modules_root = snapshot / "modules"

    for module in analysis.get("modules", []):
        if not isinstance(module, dict):
            continue
        module_name = str(module.get("module") or "").strip()
        if not module_name:
            continue
        module_caps = module.get("capabilities", []) if isinstance(module.get("capabilities"), list) else []
        cap_ids = [str(cap.get("id")) for cap in module_caps if isinstance(cap, dict) and cap.get("id")]
        module_root = modules_root / module_name
        entries = browser_entrypoints(module, module_root)

        for cap in module_caps:
            if not isinstance(cap, dict):
                continue
            capabilities.append({
                "module": module_name,
                "repository": module.get("repository"),
                "id": cap.get("id"),
                "description": cap.get("description"),
                "source": cap.get("source"),
                "evidence_status": cap.get("evidence_status"),
                "launchable_user_surface": bool(entries),
            })

        for index, entry in enumerate(entries):
            rel = str(entry.get("path") or "").lstrip("/")
            route = f"modules/{module_name}/{rel}"
            surfaces.append({
                "id": f"{module_name}:{index}",
                "module": module_name,
                "repository": module.get("repository"),
                "commit": module.get("commit"),
                "route": route,
                "entrypoint": entry,
                "capabilities": cap_ids,
                "tags": module.get("tags", []),
                "input": {
                    "keyboard": "synthetic-dom-keyboard",
                    "pointer": "synthetic-dom-pointer",
                    "text": "focus-aware-input",
                    "trusted_user_activation": False,
                },
                "visual_state": {
                    "dom_layout": "available_when_same_origin",
                    "canvas_png": "available_when_canvas_is_readable",
                    "whole_window_screenshot": "not_provided_by_standard-library-harness",
                },
                "evidence_status": "launchable_not_runtime_verified",
            })

    surfaces.sort(key=lambda item: (item["module"].lower(), item["route"].lower()))
    capabilities.sort(key=lambda item: (str(item.get("id") or "").lower(), item["module"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "surface_count": len(surfaces),
        "capability_count": len(capabilities),
        "surfaces": surfaces,
        "capabilities": capabilities,
        "truth_boundary": (
            "A listed browser surface is structurally launchable from the snapshot. It is not automatically proven correct. "
            "AI-native input uses synthetic events; canvas PNGs are exact canvas pixels when capture succeeds, while DOM visual state is structural/layout evidence rather than a whole-window screenshot."
        ),
    }


def render_lab(registry: dict[str, Any]) -> str:
    registry_json = json.dumps(registry, separators=(",", ":")).replace("</", "<\\/")
    protocol_json = json.dumps(INPUT_PROTOCOL, separators=(",", ":")).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AXM — Capability Lab</title>
<style>
:root{{--bg:#070a10;--panel:#111722;--line:#263348;--text:#eef5ff;--muted:#96a7bf;--accent:#79c8ff;--ok:#82e6a7;--warn:#ffd27a;--bad:#ff8d8d}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,Segoe UI,sans-serif}}
header{{display:flex;gap:16px;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--line);background:#090d14;position:sticky;top:0;z-index:5}}
header h1{{font-size:20px;margin:0}} a{{color:var(--accent)}} .muted{{color:var(--muted)}}
.layout{{display:grid;grid-template-columns:minmax(250px,320px) 1fr minmax(270px,360px);height:calc(100vh - 62px)}}
.side{{overflow:auto;padding:14px;border-right:1px solid var(--line);background:#0b1018}} .right{{border-left:1px solid var(--line);border-right:0}}
main{{display:flex;flex-direction:column;min-width:0}} .toolbar{{padding:10px;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
button,select,input,textarea{{background:#0d1420;color:var(--text);border:1px solid var(--line);border-radius:9px;padding:8px}} button{{cursor:pointer}} button:hover{{border-color:var(--accent)}}
#frame{{border:0;width:100%;height:100%;background:white}} .frameWrap{{flex:1;min-height:0;background:#05070b}}
.card{{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:10px;margin:8px 0}} .cap{{cursor:pointer}} .cap:hover{{border-color:var(--accent)}}
.pill{{display:inline-block;padding:2px 7px;border:1px solid #34445f;border-radius:999px;margin:2px;font-size:11px}}
.keys{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}} .keys button{{min-height:38px}} textarea{{width:100%;min-height:180px;font-family:ui-monospace,monospace;font-size:12px}}
.status{{font-size:12px;padding:7px;border-radius:8px;background:#0a1019;border:1px solid var(--line)}} .ok{{color:var(--ok)}} .warn{{color:var(--warn)}} .bad{{color:var(--bad)}}
@media(max-width:1050px){{.layout{{grid-template-columns:250px 1fr}}.right{{position:fixed;right:0;top:62px;bottom:0;width:330px;z-index:4;box-shadow:-8px 0 24px #0008}}}}
</style></head>
<body data-marker="{LAB_MARKER}">
<header><div><h1>AXM — Capability Lab</h1><div class="muted">Use captured capabilities and exercise user-facing states with an AI-native input bus.</div></div><div><a href="STACK_DASHBOARD.html">Stack map</a> · <a href="STACK_REPORT.md">Report</a></div></header>
<div class="layout">
<aside class="side"><input id="search" placeholder="Search capability/module…" style="width:100%"><div id="surfaceSummary" class="card"></div><div id="caps"></div></aside>
<main><div class="toolbar"><select id="surface"></select><button id="load">Load surface</button><button id="reload">Reload</button><button id="capture">Capture visual state</button><span id="surfaceState" class="status">No surface loaded.</span></div><div class="frameWrap"><iframe id="frame" sandbox="allow-scripts allow-same-origin allow-forms allow-pointer-lock allow-modals"></iframe></div></main>
<aside class="side right"><h3>AI-native keyboard</h3><div class="muted small">Synthetic input for ordinary user-facing event paths. `isTrusted` remains false.</div>
<div class="keys" id="keys"></div><h3>Action script</h3><textarea id="script">[\n  {{"type":"tap_key","key":"ArrowUp","duration_ms":120}},\n  {{"type":"wait","ms":250}},\n  {{"type":"snapshot","label":"after-up"}}\n]</textarea>
<div style="display:flex;gap:7px;margin-top:8px"><button id="run">Run script</button><button id="save">Snapshot + save evidence</button></div>
<h3>Evidence</h3><div id="server" class="status warn">Checking local evidence server…</div><pre id="evidence" class="card" style="white-space:pre-wrap;max-height:34vh;overflow:auto"></pre></aside>
</div>
<script type="application/json" id="registry">{registry_json}</script><script type="application/json" id="protocol">{protocol_json}</script>
<script>
const R=JSON.parse(document.getElementById('registry').textContent),P=JSON.parse(document.getElementById('protocol').textContent),frame=document.getElementById('frame');
const $=id=>document.getElementById(id),sleep=ms=>new Promise(r=>setTimeout(r,Math.max(0,Number(ms)||0)));let current=null,serverOnline=false,errors=[],session=(crypto.randomUUID?crypto.randomUUID():String(Date.now()));
const KEYMAP={{ArrowUp:['ArrowUp','ArrowUp'],ArrowDown:['ArrowDown','ArrowDown'],ArrowLeft:['ArrowLeft','ArrowLeft'],ArrowRight:['ArrowRight','ArrowRight'],Enter:['Enter','Enter'],' ':[' ','Space'],Escape:['Escape','Escape'],Tab:['Tab','Tab'],Shift:['Shift','ShiftLeft'],Control:['Control','ControlLeft'],w:['w','KeyW'],a:['a','KeyA'],s:['s','KeyS'],d:['d','KeyD'],r:['r','KeyR']}};
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function populate(){{const sel=$('surface');sel.innerHTML=R.surfaces.map((s,i)=>`<option value="${{i}}">${{esc(s.module)}} — ${{esc(s.entrypoint.path)}}</option>`).join('');$('surfaceSummary').innerHTML=`<b>${{R.surface_count}}</b> launchable browser surfaces<br><b>${{R.capability_count}}</b> mapped capabilities<div class="muted">Non-browser capabilities remain inspectable until an execution adapter exists.</div>`;renderCaps('');const keys=['↑','←','↓','→','W','A','S','D','Enter','Space','Esc','R'];const map={{'↑':'ArrowUp','↓':'ArrowDown','←':'ArrowLeft','→':'ArrowRight','W':'w','A':'a','S':'s','D':'d','Space':' ','Esc':'Escape'}};$('keys').innerHTML=keys.map(k=>`<button data-key="${{esc(map[k]||k)}}">${{esc(k)}}</button>`).join('');document.querySelectorAll('#keys button').forEach(b=>b.onclick=()=>runActions([{{type:'tap_key',key:b.dataset.key,duration_ms:90}}]));if(R.surfaces.length){{$('surface').value='0';}}}}
function renderCaps(q){{q=(q||'').toLowerCase();const html=R.capabilities.filter(c=>!q||JSON.stringify(c).toLowerCase().includes(q)).map(c=>`<div class="card cap" data-module="${{esc(c.module)}}"><b>${{esc(c.id)}}</b><div class="muted">${{esc(c.module)}} · ${{esc(c.evidence_status)}}</div><div>${{esc(c.description||'')}}</div><div class="${{c.launchable_user_surface?'ok':'warn'}}">${{c.launchable_user_surface?'user surface available':'inspect-only in this lab'}}</div></div>`).join('');$('caps').innerHTML=html||'<div class="muted">No matches.</div>';document.querySelectorAll('.cap').forEach(el=>el.onclick=()=>{{const idx=R.surfaces.findIndex(s=>s.module===el.dataset.module);if(idx>=0){{$('surface').value=String(idx);loadSurface(idx)}}}})}}
$('search').oninput=e=>renderCaps(e.target.value);
function selectedSurface(){{const i=Number($('surface').value);return R.surfaces[i]||null}}
async function loadSurface(index=null){{const s=index===null?selectedSurface():R.surfaces[index];if(!s)return;current=s;errors=[];$('surfaceState').textContent=`Loading ${{s.module}}…`;await new Promise(resolve=>{{frame.onload=()=>resolve();frame.src=s.route}});try{{const w=frame.contentWindow;w.addEventListener('error',e=>errors.push({{kind:'error',message:e.message,filename:e.filename,line:e.lineno}}));w.addEventListener('unhandledrejection',e=>errors.push({{kind:'unhandledrejection',message:String(e.reason)}}));}}catch(e){{errors.push({{kind:'harness-access',message:String(e)}})}}$('surfaceState').textContent=`Loaded ${{s.module}}`;return s}}
$('load').onclick=()=>loadSurface();$('reload').onclick=async()=>{{if(!current)return;await loadSurface(R.surfaces.indexOf(current))}};
function doc(){{try{{return frame.contentDocument}}catch(e){{throw new Error('iframe is not same-origin/readable: '+e)}}}}
function keySpec(a){{const k=String(a.key??''),pair=KEYMAP[k]||[k,a.code||k];return {{key:k,code:a.code||pair[1],bubbles:true,cancelable:true,ctrlKey:!!a.ctrl,altKey:!!a.alt,shiftKey:!!a.shift,metaKey:!!a.meta}}}}
function dispatchKey(type,a){{const d=doc(),w=frame.contentWindow,target=d.activeElement||d.body||d.documentElement,ev=new w.KeyboardEvent(type,keySpec(a));target.dispatchEvent(ev);return {{defaultPrevented:ev.defaultPrevented,isTrusted:ev.isTrusted}}}}
async function typeText(text,interval=18){{const d=doc(),w=frame.contentWindow,target=d.activeElement||d.body;for(const ch of String(text)){{dispatchKey('keydown',{{key:ch,code:''}});if(target&&('value' in target)&&(target.tagName==='INPUT'||target.tagName==='TEXTAREA')){{const start=target.selectionStart??target.value.length,end=target.selectionEnd??start;target.value=target.value.slice(0,start)+ch+target.value.slice(end);try{{target.setSelectionRange(start+1,start+1)}}catch(_e){{}}target.dispatchEvent(new w.InputEvent('input',{{bubbles:true,inputType:'insertText',data:ch}}));}}else if(target&&target.isContentEditable){{d.execCommand('insertText',false,ch)}}dispatchKey('keyup',{{key:ch,code:''}});await sleep(interval)}}}}
function clickAt(x,y,button=0){{const d=doc(),w=frame.contentWindow,el=d.elementFromPoint(Number(x),Number(y));if(!el)throw new Error('no element at coordinates');for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']){{const C=type.startsWith('pointer')?w.PointerEvent:w.MouseEvent;el.dispatchEvent(new C(type,{{bubbles:true,cancelable:true,clientX:Number(x),clientY:Number(y),button:Number(button)||0}}))}}return describeElement(el)}}
function describeElement(el){{if(!el)return null;const r=el.getBoundingClientRect();return {{tag:el.tagName,id:el.id||null,classes:el.className?String(el.className).slice(0,200):null,role:el.getAttribute&&el.getAttribute('role'),text:(el.innerText||el.textContent||'').trim().slice(0,180),rect:{{x:r.x,y:r.y,width:r.width,height:r.height}}}}}}
async function hashDataUrl(url){{const b64=url.split(',')[1]||'',bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0)),digest=await crypto.subtle.digest('SHA-256',bytes);return Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('')}}
async function captureState(label='snapshot'){{if(!current)throw new Error('load a surface first');const d=doc(),w=frame.contentWindow,visible=[];for(const el of Array.from(d.querySelectorAll('*')).slice(0,2500)){{const r=el.getBoundingClientRect(),cs=w.getComputedStyle(el);if(r.width<=0||r.height<=0||cs.display==='none'||cs.visibility==='hidden'||Number(cs.opacity)===0)continue;if(visible.length>=600)break;const item=describeElement(el);item.style={{display:cs.display,visibility:cs.visibility,opacity:cs.opacity,color:cs.color,backgroundColor:cs.backgroundColor,fontSize:cs.fontSize,transform:cs.transform,zIndex:cs.zIndex}};if(el.tagName==='INPUT'||el.tagName==='TEXTAREA'||el.tagName==='SELECT')item.value=el.type==='password'?'<redacted>':String(el.value??'').slice(0,300);visible.push(item)}}const canvases=[];for(const [i,c] of Array.from(d.querySelectorAll('canvas')).entries()){{try{{const data_url=c.toDataURL('image/png');canvases.push({{index:i,width:c.width,height:c.height,data_url,sha256:await hashDataUrl(data_url),status:'canvas_png_captured'}})}}catch(e){{canvases.push({{index:i,width:c.width,height:c.height,status:'canvas_capture_blocked_or_tainted',error:String(e)}})}}}}return {{schema_version:'0.3',session,surface:current.id,module:current.module,route:current.route,label,captured_at:new Date().toISOString(),input_truth:{{synthetic_events:true,trusted_user_activation:false}},visual_truth:{{dom_layout:'structural',canvas_png:'pixel_exact_when_status_is_canvas_png_captured',whole_window_screenshot:false}},viewport:{{width:w.innerWidth,height:w.innerHeight,devicePixelRatio:w.devicePixelRatio}},document:{{title:d.title,url:w.location.pathname,body_text:(d.body?.innerText||'').slice(0,4000),active_element:describeElement(d.activeElement)}},visible_elements:visible,canvases,errors:[...errors]}}}}
async function saveEvidence(state){{if(serverOnline){{const res=await fetch('/api/evidence',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify(state)}});if(!res.ok)throw new Error('evidence save failed '+res.status);return await res.json()}}const blob=new Blob([JSON.stringify(state,null,2)],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`axm-visual-state-${{Date.now()}}.json`;a.click();URL.revokeObjectURL(a.href);return {{saved:'browser-download-fallback'}}}}
async function executeAction(a){{switch(String(a.type||'')){{case'tap_key':dispatchKey('keydown',a);await sleep(a.duration_ms??70);dispatchKey('keyup',a);return;case'key_down':dispatchKey('keydown',a);return;case'key_up':dispatchKey('keyup',a);return;case'type_text':await typeText(a.text,a.interval_ms);return;case'wait':await sleep(a.ms);return;case'click':return clickAt(a.x,a.y,a.button);case'click_selector':{{const el=doc().querySelector(a.selector);if(!el)throw new Error('selector not found: '+a.selector);const r=el.getBoundingClientRect();return clickAt(r.left+r.width/2,r.top+r.height/2,a.button)}}case'focus_selector':{{const el=doc().querySelector(a.selector);if(!el)throw new Error('selector not found: '+a.selector);el.focus();return describeElement(el)}}case'reload':await loadSurface(R.surfaces.indexOf(current));return;case'snapshot':{{const state=await captureState(a.label||'script-snapshot');const saved=await saveEvidence(state);$('evidence').textContent=JSON.stringify({{saved,state:{{...state,canvases:state.canvases.map(c=>({{...c,data_url:c.data_url?'[png data omitted from preview]':undefined}}))}}}},null,2);return saved}}default:throw new Error('unsupported action type: '+a.type)}}}}
async function runActions(actions){{if(!current)await loadSurface();for(const a of actions)await executeAction(a)}}
$('run').onclick=async()=>{{try{{await runActions(JSON.parse($('script').value));$('surfaceState').textContent='Action script completed.'}}catch(e){{$('surfaceState').textContent='ERROR: '+e;$('surfaceState').className='status bad'}}}};
$('capture').onclick=$('save').onclick=async()=>{{try{{const state=await captureState('manual');const saved=await saveEvidence(state);$('evidence').textContent=JSON.stringify({{saved,state:{{...state,canvases:state.canvases.map(c=>({{...c,data_url:c.data_url?'[png data omitted from preview]':undefined}}))}}}},null,2)}}catch(e){{$('evidence').textContent='ERROR: '+e}}}};
async function health(){{if(location.protocol==='file:'){{serverOnline=false;$('server').textContent='Offline file mode: input works where browser file-origin rules allow it; evidence downloads locally instead of server persistence.';return}}try{{const r=await fetch('/api/health');serverOnline=r.ok;$('server').textContent=serverOnline?'Local evidence server connected. AI command queue active.':'Evidence server unavailable.';$('server').className='status '+(serverOnline?'ok':'warn')}}catch(e){{serverOnline=false;$('server').textContent='Evidence server unavailable: '+e}}}}
async function poll(){{if(!serverOnline)return;try{{const r=await fetch('/api/next-command');if(r.status===200){{const cmd=await r.json();if(cmd.surface){{const idx=R.surfaces.findIndex(s=>s.id===cmd.surface||s.module===cmd.surface);if(idx>=0&&(!current||current.id!==R.surfaces[idx].id))await loadSurface(idx)}}await runActions(cmd.actions||[]);await fetch('/api/command-result',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{id:cmd.id,status:'completed',completed_at:new Date().toISOString(),surface:current?.id||null}})}})}}}}catch(e){{console.warn('AI command poll failed',e)}}}}
populate();health().then(()=>setInterval(poll,500));const q=new URLSearchParams(location.search);if(q.get('module')){{const idx=R.surfaces.findIndex(s=>s.module===q.get('module'));if(idx>=0){{$('surface').value=String(idx);loadSurface(idx)}}}}
</script></body></html>'''


def generate_user_surface(snapshot: Path) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    analysis_path = snapshot / "STACK_ANALYSIS.json"
    if not analysis_path.exists():
        raise ValueError(f"missing {analysis_path}; run stack analysis first")
    analysis = read_json(analysis_path)
    if not isinstance(analysis, dict):
        raise ValueError("STACK_ANALYSIS.json must contain an object")

    registry = build_surface_registry(snapshot, analysis)
    write_json(snapshot / "USER_FACING_SURFACES.json", registry)
    write_json(snapshot / "AI_NATIVE_INPUT_PROTOCOL.json", INPUT_PROTOCOL)

    current_open = snapshot / "OPEN_ME.html"
    dashboard = snapshot / "STACK_DASHBOARD.html"
    if current_open.exists():
        existing = current_open.read_text(encoding="utf-8", errors="replace")
        if LAB_MARKER not in existing and not dashboard.exists():
            dashboard.write_text(existing, encoding="utf-8")
    if not dashboard.exists():
        dashboard.write_text(
            "<!doctype html><meta charset='utf-8'><title>AXM Stack Dashboard</title><p>Stack dashboard was not generated before the capability lab.</p>",
            encoding="utf-8",
        )

    lab = render_lab(registry)
    current_open.write_text(lab, encoding="utf-8")
    (snapshot / "AI_TEST_LAB.html").write_text(lab, encoding="utf-8")

    return {
        "schema_version": SCHEMA_VERSION,
        "surface_count": registry["surface_count"],
        "capability_count": registry["capability_count"],
        "default_interface": "OPEN_ME.html",
        "stack_dashboard": "STACK_DASHBOARD.html",
        "surface_registry": "USER_FACING_SURFACES.json",
        "input_protocol": "AI_NATIVE_INPUT_PROTOCOL.json",
        "truth_boundary": registry["truth_boundary"],
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate AXM capability/user-facing test surface")
    p.add_argument("snapshot", type=Path)
    return p


def main() -> int:
    args = parser().parse_args()
    print(json.dumps(generate_user_surface(args.snapshot), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
