#!/usr/bin/env python3
"""Build an evidence-backed all-module AXM totality test matrix.

Reads only already-produced monolith evidence. It does not mutate donor modules,
execute code, promote candidate composition, or grant authority.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "axm.monolith.totality-test-matrix/v0.1"
ROOTS = ["Truth", "Agency / non-domination", "Continuity", "Wisdom before speed"]

class MatrixError(RuntimeError):
    pass

def read_json(path: Path, *, required: bool = True) -> Any:
    if not path.is_file():
        if required:
            raise MatrixError(f"required evidence missing: {path.name}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MatrixError(f"cannot read {path}: {exc}") from exc

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return 'sha256:'+h.hexdigest()

def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n", encoding="utf-8")

def probe_by_module(payload: dict[str,Any]) -> dict[str,dict[str,Any]]:
    grouped: dict[str,list[dict[str,Any]]] = collections.defaultdict(list)
    for item in payload.get('results') or []:
        cap=str(item.get('capability') or '')
        module=cap.split('::',1)[0] if '::' in cap else ''
        if module:
            grouped[module].append(item)
    out={}
    for module,items in grouped.items():
        counts=collections.Counter(str(x.get('status') or 'unknown') for x in items)
        out[module]={
            'probe_count':len(items),
            'status_counts':dict(sorted(counts.items())),
            'all_probe_dispatches_recorded':all(bool(x.get('receipt')) for x in items),
        }
    return out

def tests_by_module(payload: dict[str,Any]|None) -> dict[str,dict[str,Any]]:
    out={}
    if not payload:
        return out
    for item in payload.get('modules') or []:
        module=str(item.get('module') or '')
        if not module:
            continue
        failure_classes=collections.Counter()
        for command in item.get('commands') or []:
            if command.get('status') != 'passed':
                failure_classes[str(command.get('classification') or command.get('status') or 'unknown')] += 1
        out[module]={
            'status':item.get('status'),
            'command_count':int(item.get('command_count') or 0),
            'status_counts':item.get('counts') or {},
            'failure_class_counts':dict(sorted(failure_classes.items())),
            'source_snapshot_mutated':item.get('source_snapshot_mutated'),
        }
    return out

def golden_membership(payload: dict[str,Any]|None) -> tuple[dict[str,list[str]],dict[str,list[dict[str,Any]]]]:
    candidate:dict[str,list[str]]=collections.defaultdict(list)
    executed:dict[str,list[dict[str,Any]]]=collections.defaultdict(list)
    if payload:
        for path in payload.get('workfloor_paths') or []:
            pid=str(path.get('id') or '')
            for module in path.get('candidate_modules') or []:
                candidate[str(module)].append(pid)
        for smoke in payload.get('native_execution_smokes') or []:
            module=str(smoke.get('module') or '')
            if module:
                executed[module].append({
                    'id':smoke.get('id'), 'status':smoke.get('status'), 'address':smoke.get('address'),
                    'source_capability_executed':smoke.get('source_capability_executed'),
                    'source_snapshot_mutated':smoke.get('source_snapshot_mutated'),
                    'receipt_path':smoke.get('receipt_path'),
                })
    return dict(candidate),dict(executed)

def integration_state(module:dict[str,Any], probe:dict[str,Any]|None, test:dict[str,Any]|None, native:list[dict[str,Any]]) -> tuple[str,str]:
    if any(x.get('status')=='PASS' and x.get('source_capability_executed') is True for x in native):
        return 'EXECUTED','at least one pinned native source command passed in a temporary copied workspace'
    if test:
        if test.get('status')=='passed':
            return 'TEST_EVIDENCE','broad module test evidence passed in a temporary copied workspace'
        return 'TEST_EVIDENCE','broad module test evidence exists with visible failures/timeouts/environment limits'
    high=str(module.get('highest_observed_state') or '')
    if high=='WORKFLOW_SCOPED':
        return 'WORKFLOW_SCOPED','callability is verified only inside a named workflow envelope'
    if high in {'VERIFIED_EXECUTABLE','TEST_EVIDENCE'}:
        return 'INSPECTED','stronger adapter evidence exists, but this matrix has no retained executed/test result for the module'
    if probe and probe.get('probe_count',0)>0:
        return 'INSPECTED','bounded execution-fabric probes resolved module surfaces without proving source execution'
    return 'NOT_TESTED','no retained bounded probe or test evidence was found for this module'

def next_action(row:dict[str,Any]) -> str:
    if row['integration_state']=='EXECUTED':
        return 'Use in additional cross-repo paths only where consumer/provider semantics are independently evidenced.'
    test=row['tests']
    if test and test.get('status')=='completed_with_failures':
        classes=', '.join(test.get('failure_class_counts',{})) or 'visible test failures'
        return f'Keep current wiring; resolve or classify the retained test limitations ({classes}) before stronger claims.'
    if row['verified_native_ready_count']>0:
        return 'Run only the exact verified native command(s) with bounded safe arguments to upgrade retained execution evidence.'
    if row['actionable_endpoint_count']>0:
        return 'Use the existing actionable inspection/test/workflow surfaces in a real cross-repo path; do not promote token matches alone.'
    return 'HOLD: no currently actionable endpoint is evidenced; wait for donor/native contract evidence rather than inventing an adapter.'

def build(root:Path)->dict[str,Any]:
    root=root.resolve()
    registry=read_json(root/'MODULE_CONNECTIVE_CONTRACTS.json')
    probe=read_json(root/'evidence/execution-fabric/PROBE_ALL.json')
    tests=read_json(root/'evidence/execution-fabric/TEST_ALL_BROAD.json', required=False)
    golden=read_json(root/'GOLDEN_PATHS.json', required=False)
    fabric=read_json(root/'EXECUTION_FABRIC.json')
    if not isinstance(registry,dict) or not isinstance(registry.get('modules'),list):
        raise MatrixError('MODULE_CONNECTIVE_CONTRACTS.json has no module list')
    modules=registry['modules']
    probe_map=probe_by_module(probe)
    test_map=tests_by_module(tests)
    candidate_map,native_map=golden_membership(golden)
    ready_by_module=collections.Counter()
    for endpoint in fabric.get('endpoints') or []:
        if (endpoint.get('adapter') or {}).get('status')=='callable_native_command_verified':
            ready_by_module[str(endpoint.get('module') or '')]+=1
    rows=[]
    for item in sorted(modules,key=lambda x:str(x.get('module') or '').lower()):
        module=str(item.get('module') or '')
        p=probe_map.get(module)
        t=test_map.get(module)
        native=native_map.get(module,[])
        state,reason=integration_state(item,p,t,native)
        row={
            'module':module,
            'repository':item.get('repository'),
            'commit':item.get('commit'),
            'contract_path':item.get('contract_path'),
            'contract_sha256':item.get('contract_sha256'),
            'endpoint_count':int(item.get('endpoint_count') or 0),
            'actionable_endpoint_count':int(item.get('actionable_endpoint_count') or 0),
            'blocked_endpoint_count':int(item.get('blocked_endpoint_count') or 0),
            'highest_observed_adapter_state':item.get('highest_observed_state'),
            'verified_native_ready_count':int(ready_by_module.get(module,0)),
            'bounded_probe':p or {'probe_count':0,'status_counts':{},'all_probe_dispatches_recorded':False},
            'tests':t,
            'native_execution':native,
            'golden_path_candidate_membership':sorted(set(candidate_map.get(module,[]))),
            'integration_state':state,
            'integration_state_reason':reason,
            'truth_flags':{
                'candidate_is_verified_interop':False,
                'probe_is_source_execution':False,
                'test_adapter_is_tests_passed':False,
                'module_grants_canon':False,
            },
        }
        row['next_action']=next_action(row)
        rows.append(row)
    states=collections.Counter(r['integration_state'] for r in rows)
    probe_covered=sum(1 for r in rows if r['bounded_probe']['probe_count']>0)
    test_covered=sum(1 for r in rows if r['tests'] is not None)
    native_executed=sum(1 for r in rows if r['integration_state']=='EXECUTED')
    modules_with_failures=sum(1 for r in rows if r['tests'] and r['tests'].get('status')!='passed')
    all_probe_receipts=all(r['bounded_probe']['probe_count']>0 and r['bounded_probe']['all_probe_dispatches_recorded'] for r in rows)
    payload={
        'schema':SCHEMA,
        'snapshot':root.name,
        'roots':ROOTS,
        'authority':{'canon':False,'merge':False,'product_acceptance':False},
        'inputs':{
            'module_contracts':{'path':'MODULE_CONNECTIVE_CONTRACTS.json','sha256':sha256(root/'MODULE_CONNECTIVE_CONTRACTS.json')},
            'execution_fabric':{'path':'EXECUTION_FABRIC.json','sha256':sha256(root/'EXECUTION_FABRIC.json')},
            'probe_all':{'path':'evidence/execution-fabric/PROBE_ALL.json','sha256':sha256(root/'evidence/execution-fabric/PROBE_ALL.json')},
            'test_all_broad':({'path':'evidence/execution-fabric/TEST_ALL_BROAD.json','sha256':sha256(root/'evidence/execution-fabric/TEST_ALL_BROAD.json')} if tests else None),
            'golden_paths':({'path':'GOLDEN_PATHS.json','sha256':sha256(root/'GOLDEN_PATHS.json')} if golden else None),
        },
        'summary':{
            'module_count':len(rows),
            'probe_covered_module_count':probe_covered,
            'all_modules_bounded_probed':probe_covered==len(rows) and all_probe_receipts,
            'test_evidence_module_count':test_covered,
            'module_without_test_queue_count':len(rows)-test_covered,
            'native_executed_module_count':native_executed,
            'modules_with_visible_test_failures_or_limits':modules_with_failures,
            'integration_state_counts':dict(sorted(states.items())),
            'endpoint_count':sum(r['endpoint_count'] for r in rows),
            'actionable_endpoint_count':sum(r['actionable_endpoint_count'] for r in rows),
            'blocked_endpoint_count':sum(r['blocked_endpoint_count'] for r in rows),
        },
        'modules':rows,
        'truth_boundary':(
            'This matrix correlates exact pinned module identity, connective contracts, bounded execution-fabric probes, broad copied-workspace test evidence, '
            'retained native smoke execution, and golden-path candidate membership. Probe success is not source execution; test evidence is not product acceptance; '
            'candidate path membership is not semantic interoperability; visible failures and HOLD/BLOCKED states remain visible.'
        ),
    }
    return payload

def render_md(payload:dict[str,Any])->str:
    s=payload['summary']
    lines=[
        '# AXM Totality Test Matrix','',
        f"Snapshot: `{payload['snapshot']}`",'',
        '## Coverage','',
        f"- Modules represented: **{s['module_count']}/{s['module_count']}**",
        f"- Modules bounded-probed through the execution fabric: **{s['probe_covered_module_count']}/{s['module_count']}**",
        f"- Modules with broad copied-workspace test evidence: **{s['test_evidence_module_count']}/{s['module_count']}**",
        f"- Modules with retained passing native source execution: **{s['native_executed_module_count']}/{s['module_count']}**",
        f"- Endpoints: **{s['endpoint_count']} total · {s['actionable_endpoint_count']} actionable · {s['blocked_endpoint_count']} blocked**",
        f"- Modules with visible broad-test failures/timeouts/environment limits: **{s['modules_with_visible_test_failures_or_limits']}**",'',
        'Integration states are evidence classes, not maturity grades. Candidate path membership is not verified interoperability.','',
        '## Per module','',
        '| Module | State | Probe | Broad tests | Native exec | Actionable / blocked | Next evidence move |',
        '|---|---|---:|---|---:|---:|---|',
    ]
    for r in payload['modules']:
        test='NO TEST QUEUE' if r['tests'] is None else str(r['tests'].get('status') or 'unknown')
        native=sum(1 for x in r['native_execution'] if x.get('status')=='PASS' and x.get('source_capability_executed') is True)
        action=str(r['next_action']).replace('|','/').replace('\n',' ')
        lines.append(f"| `{r['module']}` | **{r['integration_state']}** | {r['bounded_probe']['probe_count']} | {test} | {native} | {r['actionable_endpoint_count']} / {r['blocked_endpoint_count']} | {action} |")
    lines += ['', '## Truth boundary','', payload['truth_boundary'],'', 'Roots: **Truth · Agency/non-domination · Continuity · Wisdom before speed**','']
    return '\n'.join(lines)

def render_start(payload:dict[str,Any])->str:
    s=payload['summary']
    return f'''# START HERE — AXM Totality Test\n\nThis checkpoint is a **test build of the current selected AXM totality**, not CANON and not product acceptance.\n\n## Fastest human path\n\n1. Open `START_HERE.txt` for the packaged launcher basics.\n2. Run `START_AXM.cmd` on Windows or `./START_AXM.sh` on Linux/macOS.\n3. Open the local Workfloor / wired-monolith surface exposed by the launcher.\n4. Keep `TEST_MATRIX.md` beside you: it tells you what is actually evidenced, what only has test/inspection evidence, and what is blocked/HOLD.\n5. Use `GOLDEN_PATHS_REPORT.md` for the retained cross-repo paths already exercised.\n\n## What this checkpoint currently proves\n\n- **{s['probe_covered_module_count']}/{s['module_count']} modules** have a bounded execution-fabric probe record.\n- **{s['test_evidence_module_count']}/{s['module_count']} modules** have broad copied-workspace test evidence.\n- **{s['native_executed_module_count']}/{s['module_count']} modules** retain passing native source-command execution evidence.\n- **{s['actionable_endpoint_count']} endpoints** are currently actionable by evidenced adapters; **{s['blocked_endpoint_count']}** remain explicitly blocked.\n\n## Read status literally\n\n- `EXECUTED`: retained native source command actually ran successfully in an isolated copied workspace.\n- `TEST_EVIDENCE`: module tests ran; the row tells you whether they passed or had visible failures/limits.\n- `WORKFLOW_SCOPED`: callable only through the named workflow evidence.\n- `INSPECTED`: the monolith can inspect/resolve the surface, but that is not source execution.\n- `HOLD` / `BLOCKED`: do not force it; evidence is missing or insufficient.\n- `NOT_TESTED`: no retained bounded test/probe evidence was found.\n\n## Important\n\nDo not read candidate provider/consumer matches as verified interoperability. Do not read a test adapter as "tests passed." Do not read archive integrity as semantic correctness. The four roots remain the merge gate: **Truth, Agency/non-domination, Continuity, Wisdom before speed.**\n'''

def generate(snapshot:str|Path)->dict[str,Any]:
    root=Path(snapshot).resolve()
    payload=build(root)
    write_json(root/'TEST_MATRIX.json',payload)
    (root/'TEST_MATRIX.md').write_text(render_md(payload),encoding='utf-8')
    (root/'START_HERE_TEST.md').write_text(render_start(payload),encoding='utf-8')
    return payload

def main(argv=None)->int:
    p=argparse.ArgumentParser(description='Build evidence-backed all-module AXM totality test matrix')
    p.add_argument('snapshot',type=Path)
    args=p.parse_args(argv)
    try:
        payload=generate(args.snapshot)
    except MatrixError as exc:
        print(json.dumps({'status':'HOLD','error':str(exc)}))
        return 2
    print(json.dumps({'status':'PASS','summary':payload['summary'],'outputs':['TEST_MATRIX.json','TEST_MATRIX.md','START_HERE_TEST.md']},indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
