#!/usr/bin/env python3
"""Re-run exact-ref native smoke recipes learned from real AXM monolith wiring.

Recipes are fail-closed: a changed repository ref or missing VERIFIED native-command evidence is
HOLD, never auto-trusted. Execution uses the packaged Execution Fabric copied-workspace boundary.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any

RECIPES = [
 {"id":"game-assets-forge-self-test","address":"Axm-game-assets::native.command/python-file-cli/forge.py","repository":"mike-axiom-mir/Axm-game-assets","commit":"aaae29c81422366610e6c0ed75e2af6794b100f6","args":["self-test"]},
 {"id":"universal-creation-cli-help","address":"axm-universal-creation::native.command/python-project-script/axm-uc","repository":"mike-axiom-mir/axm-universal-creation","commit":"78b16c01b543733688d7d036552b63679c87c10b","args":["--help"]},
 {"id":"framestate-cli-help","address":"axm-framestate::native.command/python-project-script/framestate","repository":"mike-axiom-mir/axm-framestate","commit":"60ea68ba72e4ad4df8dc5746c6bb18fcd6569a34","args":["--help"]},
 {"id":"machine-voice-cli-help","address":"axm-machine-voice::native.command/python-project-script/axm-machine-voice","repository":"mike-axiom-mir/axm-machine-voice","commit":"b77f6d083db2951d19e082e712fdaa3061ced956","args":["--help"]},
 {"id":"city-p2p-cli-help","address":"axm-city-multiplayer::native.command/python-project-script/axm-p2p","repository":"mike-axiom-mir/axm-city-multiplayer","commit":"002c4465667f9ffbdb6adda06afae8596d340d76","args":["--help"]},
 {"id":"walmi-public-capability-verify","address":"axm-walmi::native.command/python-file-cli/tools/verify_public_capability.py","repository":"mike-axiom-mir/axm-walmi","commit":"c8913f3a6f42a6498f83d5876b8aee9c56df694f","args":["--root","."]},
 {"id":"front-door-validate","address":"axm-front-door::native.command/python-file-cli/scripts/axm_site.py","repository":"mike-axiom-mir/axm-front-door","commit":"05e25b557d076551ac740c4e043a9ccbbb0160ba","args":["validate"]},
 {"id":"living-city-headless-main","address":"axm-living-city-simulator::native.command/node-file-cli/runtime/headless-simulator.js","repository":"mike-axiom-mir/axm-living-city-simulator","commit":"a299db639e87b2fa0dea1ded1bf651ab86e9cd3c","args":["--help"]},
 {"id":"grammar-102-capability-snapshot-export","address":"axm-102-grammer::native.command/node-file-cli/bin/axm-grammar-glass-snapshot.js","repository":"mike-axiom-mir/axm-102-grammer","commit":"ff58375b65a4033041e6de957263d4146aa7429e","args":["create","--commit","ff58375b65a4033041e6de957263d4146aa7429e","--repo","mike-axiom-mir/axm-102-grammer"]},
 {"id":"factual-space-cli-help","address":"axm-factual-space-simulator::native.command/python-project-script/axm-star-sim","repository":"mike-axiom-mir/axm-factual-space-simulator","commit":"4ce1726c03fc775276de56d127bf6b393a1139cd","args":["--help"]},
 {"id":"factual-rooted-crew-verify-roots","address":"axm-factual-space-simulator::native.command/python-project-script/axm-rooted-crew","repository":"mike-axiom-mir/axm-factual-space-simulator","commit":"4ce1726c03fc775276de56d127bf6b393a1139cd","args":["verify-roots"]},
 {"id":"factual-ship-blueprint-validate","address":"axm-factual-space-simulator::native.command/python-project-script/axm-ship-blueprint","repository":"mike-axiom-mir/axm-factual-space-simulator","commit":"4ce1726c03fc775276de56d127bf6b393a1139cd","args":["validate"]},
 {"id":"factual-ship-interior-validate","address":"axm-factual-space-simulator::native.command/python-project-script/axm-ship-interior","repository":"mike-axiom-mir/axm-factual-space-simulator","commit":"4ce1726c03fc775276de56d127bf6b393a1139cd","args":["validate"]},
 {"id":"factual-handoff-full-audit","address":"axm-factual-space-simulator::native.command/python-project-script/axm-handoff","repository":"mike-axiom-mir/axm-factual-space-simulator","commit":"4ce1726c03fc775276de56d127bf6b393a1139cd","args":["audit","--full"]},
 {"id":"factual-package-seal-check","address":"axm-factual-space-simulator::native.command/python-project-script/axm-package-seal","repository":"mike-axiom-mir/axm-factual-space-simulator","commit":"4ce1726c03fc775276de56d127bf6b393a1139cd","args":["--check"]},
]

def gate(endpoint: dict[str, Any] | None, recipe: dict[str, Any]) -> tuple[bool,str]:
    if not endpoint: return False,"HOLD_ENDPOINT_MISSING"
    if endpoint.get("repository") != recipe["repository"] or endpoint.get("commit") != recipe["commit"]:
        return False,"HOLD_RECIPE_REF_MISMATCH"
    adapter=endpoint.get("adapter") or {}
    if adapter.get("status") != "callable_native_command_verified" or adapter.get("source_capability_execution") is not True:
        return False,"HOLD_NO_VERIFIED_NATIVE_EVIDENCE"
    return True,"READY"

def run(snapshot: str|Path, execute: bool=False) -> dict[str,Any]:
    root=Path(snapshot).resolve()
    fabric_path=root/"EXECUTION_FABRIC.json"
    if not fabric_path.is_file(): raise RuntimeError("EXECUTION_FABRIC.json missing")
    fabric_data=json.loads(fabric_path.read_text(encoding="utf-8"))
    endpoints={str(x.get("address")):x for x in fabric_data.get("endpoints",[]) if isinstance(x,dict) and x.get("address")}
    runtime=None
    if execute:
        sys.path.insert(0,str(root))
        import AXM_EXECUTION_FABRIC as ef
        runtime=ef.ExecutionFabric(root)
    results=[]
    for recipe in RECIPES:
        ep=endpoints.get(recipe["address"]); ready,status=gate(ep,recipe)
        row={**recipe,"status":status,"executed":False}
        if execute and ready:
            receipt=runtime.invoke({"request_id":f"learned-smoke.{recipe['id']}","capability":recipe["address"],"operation":"run-native","inputs":{"args":recipe["args"]},"timeout_seconds":90},record=True)
            r=receipt.get("result") or {}
            passed=r.get("status")=="passed" and r.get("source_capability_executed") is True and r.get("source_snapshot_mutated") is False
            row.update({"status":"PASS" if passed else "HOLD_EXECUTION_DID_NOT_PASS","executed":True,"receipt_path":receipt.get("receipt_path"),"receipt_sha256":receipt.get("receipt_sha256")})
        results.append(row)
    payload={"schema":"axm.monolith.learned-native-smokes/v0.1","mode":"execute" if execute else "plan","status":"PASS" if all(x["status"]==("PASS" if execute else "READY") for x in results) else "HOLD","recipes":results,"truth_boundary":"Only exact pinned refs with retained VERIFIED native-command evidence are eligible. Changed refs are HOLD until revalidated; copied-workspace smoke success is not CANON or product acceptance."}
    (root/"TOTALITY_NATIVE_SMOKES.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return payload

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("snapshot",type=Path); ap.add_argument("--run",action="store_true"); a=ap.parse_args()
    try: out=run(a.snapshot,a.run)
    except Exception as e: print(json.dumps({"status":"HOLD","error":str(e)},indent=2)); return 2
    print(json.dumps({"status":out["status"],"mode":out["mode"],"count":len(out["recipes"])},indent=2)); return 0 if out["status"]=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
