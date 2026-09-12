#!/usr/bin/env python3
"""AXM Monolith capability-pipeline fabric.

Consumes an existing STACK_ANALYSIS.json produced by tools/inspect_stack.py and
derives a reusable capability-level graph, bounded pipeline candidates, goal
queries, and explicit gaps.

Truth boundary:
- this tool never executes a discovered pipeline;
- graph/pipeline discovery never upgrades an edge to VERIFIED;
- lexical adapter suggestions are leads only;
- source modules keep ownership of their semantics and authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCHEMA_VERSION = "0.1"
MAX_DEFAULT_HOPS = 4
EXTERNAL_INPUT_ROOTS = {
    "objective", "specification", "question", "input", "scenario", "experience",
    "observation", "hypothesis", "experiment", "request", "direction", "message",
    "expression", "browser",
}
STATUS_BY_MIN_SCORE = {
    3: "declared_contract_path_not_tested",
    2: "structurally_possible_path_not_tested",
    1: "inferred_candidate_path_not_tested",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_analysis(build_root: Path) -> dict[str, Any]:
    path = build_root / "STACK_ANALYSIS.json"
    if not path.exists():
        raise ValueError(f"missing {path}; run the Monolith stack inspector first")
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("modules"), list) or not isinstance(data.get("graph"), dict):
        raise ValueError("STACK_ANALYSIS.json does not contain the expected modules/graph structure")
    return data


def token_match(provided: str, accepted: str) -> tuple[bool, str]:
    p, a = provided.strip().lower(), accepted.strip().lower()
    if not p or not a:
        return False, ""
    if p == a:
        return True, "exact"
    broad = {
        "artifact", "asset", "state", "evidence", "capability", "objective",
        "interface", "game", "input", "specification", "workflow", "network",
        "runtime", "contract", "intelligence", "research",
    }
    if a in broad and p.startswith(a + "."):
        return True, "consumer-broad"
    if p in broad and a.startswith(p + "."):
        return True, "producer-broad"
    return False, ""


def capability_node_id(module: str, capability: str) -> str:
    return f"{module}::{capability}"


def build_pipeline_graph(analysis: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    by_node: dict[str, dict[str, Any]] = {}

    for module in sorted(analysis["modules"], key=lambda item: str(item.get("module", "")).lower()):
        module_name = str(module.get("module", ""))
        for cap in sorted(module.get("capabilities", []), key=lambda item: str(item.get("id", "")).lower()):
            cap_id = str(cap.get("id", ""))
            node_id = capability_node_id(module_name, cap_id)
            node = {
                "id": node_id,
                "module": module_name,
                "repository": module.get("repository"),
                "capability": cap_id,
                "description": cap.get("description"),
                "source": cap.get("source"),
                "evidence_status": cap.get("evidence_status", "unknown"),
                "confidence": cap.get("confidence"),
                "provides": sorted({str(x) for x in cap.get("provides", []) if str(x).strip()}),
                "accepts": sorted({str(x) for x in cap.get("accepts", []) if str(x).strip()}),
                "tags": sorted({str(x) for x in cap.get("tags", []) if str(x).strip()}),
            }
            nodes.append(node)
            by_node[node_id] = node

    edges: list[dict[str, Any]] = []
    for edge in analysis.get("graph", {}).get("edges", []):
        from_id = capability_node_id(str(edge.get("from", "")), str(edge.get("producer_capability", "")))
        to_id = capability_node_id(str(edge.get("to", "")), str(edge.get("consumer_capability", "")))
        if from_id not in by_node or to_id not in by_node:
            continue
        score = int(edge.get("score", 1))
        edges.append({
            "from": from_id,
            "to": to_id,
            "from_module": edge.get("from"),
            "to_module": edge.get("to"),
            "provided": edge.get("provided"),
            "accepted": edge.get("accepted"),
            "match": edge.get("match"),
            "evidence_status": edge.get("status", "unknown"),
            "score": score,
            "truth_boundary": "candidate capability relation only; no runtime execution is implied",
        })

    edges.sort(key=lambda item: (-item["score"], item["from"].lower(), item["to"].lower(), str(item["provided"])))
    incoming = {node["id"]: 0 for node in nodes}
    outgoing = {node["id"]: 0 for node in nodes}
    for edge in edges:
        incoming[edge["to"]] += 1
        outgoing[edge["from"]] += 1

    for node in nodes:
        node["incoming_candidate_edges"] = incoming[node["id"]]
        node["outgoing_candidate_edges"] = outgoing[node["id"]]

    return {
        "schema": "axm.monolith.pipeline-graph/v0.1",
        "schema_version": SCHEMA_VERSION,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "truth_boundary": "Capability-level candidate graph only. No edge or path becomes VERIFIED through graph construction.",
    }


def path_status(edges: list[dict[str, Any]]) -> str:
    if not edges:
        return "single_capability_not_pipeline"
    minimum = min(max(1, min(3, int(edge.get("score", 1)))) for edge in edges)
    return STATUS_BY_MIN_SCORE[minimum]


def pipeline_id(nodes: list[str]) -> str:
    return " -> ".join(nodes)


def discover_pipelines(
    graph: dict[str, Any],
    max_hops: int = MAX_DEFAULT_HOPS,
    max_candidates: int = 200,
) -> list[dict[str, Any]]:
    if max_hops < 1:
        raise ValueError("max_hops must be >= 1")
    node_map = {node["id"]: node for node in graph["nodes"]}
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in graph["edges"]:
        adjacency.setdefault(edge["from"], []).append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda item: (-item["score"], item["to"].lower(), str(item["provided"])))

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for start in sorted(node_map, key=str.lower):
        stack: list[tuple[str, list[str], list[dict[str, Any]]]] = [(start, [start], [])]
        while stack:
            current, path, edges = stack.pop()
            if edges:
                key = tuple(path)
                if key not in seen:
                    seen.add(key)
                    last = node_map[path[-1]]
                    candidates.append({
                        "id": pipeline_id(path),
                        "nodes": path[:],
                        "modules": [node_map[node]["module"] for node in path],
                        "capabilities": [node_map[node]["capability"] for node in path],
                        "interfaces": [edge["provided"] for edge in edges],
                        "terminal_outputs": last["provides"],
                        "edge_count": len(edges),
                        "score": sum(int(edge["score"]) for edge in edges),
                        "weakest_edge_score": min(int(edge["score"]) for edge in edges),
                        "status": path_status(edges),
                        "edges": edges[:],
                        "truth_boundary": "candidate pipeline only; execution, compatibility, usefulness, and safety remain unverified",
                    })
            if len(edges) >= max_hops:
                continue
            for edge in reversed(adjacency.get(current, [])):
                nxt = edge["to"]
                if nxt in path:
                    continue
                stack.append((nxt, path + [nxt], edges + [edge]))

    candidates.sort(
        key=lambda item: (
            -item["weakest_edge_score"],
            -item["score"],
            -item["edge_count"],
            item["id"].lower(),
        )
    )
    return candidates[:max_candidates]


def goal_match(output_token: str, goal: str) -> tuple[bool, str]:
    goal = goal.strip()
    if not goal:
        return False, ""
    matched, mode = token_match(output_token, goal)
    if matched:
        return matched, mode
    output_lower = output_token.lower()
    goal_lower = goal.lower()
    if output_lower.startswith(goal_lower + "."):
        return True, "goal-prefix"
    return False, ""


def query_goal(
    graph: dict[str, Any],
    goal: str,
    max_hops: int = MAX_DEFAULT_HOPS,
    max_results: int = 30,
) -> dict[str, Any]:
    pipelines = discover_pipelines(graph, max_hops=max_hops, max_candidates=1000)
    matches: list[dict[str, Any]] = []
    for pipeline in pipelines:
        modes = sorted({
            mode
            for output in pipeline["terminal_outputs"]
            for matched, mode in [goal_match(output, goal)]
            if matched
        })
        if not modes:
            continue
        matches.append({**pipeline, "goal": goal, "goal_match_modes": modes})
    matches.sort(
        key=lambda item: (
            -item["weakest_edge_score"],
            -item["score"],
            item["edge_count"],
            item["id"].lower(),
        )
    )
    return {
        "schema": "axm.monolith.pipeline-goal-query/v0.1",
        "goal": goal,
        "result_count": min(len(matches), max_results),
        "results": matches[:max_results],
        "truth_boundary": "Goal matches are graph-derived candidates, not executed plans or authorization to execute.",
    }


def token_root(token: str) -> str:
    return token.strip().lower().split(".", 1)[0]


def token_parts(token: str) -> tuple[str, ...]:
    return tuple(part for part in token.strip().lower().replace("-", ".").split(".") if part)


def lexical_adapter_relation(left: str, right: str) -> str | None:
    if token_match(left, right)[0] or token_match(right, left)[0]:
        return None
    a, b = token_parts(left), token_parts(right)
    if not a or not b:
        return None
    if len(a) > 1 and len(b) > 1 and a[-1] == b[-1]:
        return "shared_suffix"
    if set(a) & set(b) and a[0] != b[0]:
        return "shared_term"
    return None


def analyze_gaps(graph: dict[str, Any], max_adapter_candidates: int = 100) -> dict[str, Any]:
    providers: dict[str, list[str]] = {}
    consumers: dict[str, list[str]] = {}
    for node in graph["nodes"]:
        for token in node["provides"]:
            providers.setdefault(token, []).append(node["id"])
        for token in node["accepts"]:
            consumers.setdefault(token, []).append(node["id"])

    provided_tokens = sorted(providers)
    accepted_tokens = sorted(consumers)
    missing_internal: list[dict[str, Any]] = []
    external_inputs: list[dict[str, Any]] = []
    unused_outputs: list[dict[str, Any]] = []

    for accepted in accepted_tokens:
        matches = [provided for provided in provided_tokens if token_match(provided, accepted)[0]]
        if matches:
            continue
        item = {"token": accepted, "consumers": sorted(consumers[accepted])}
        if token_root(accepted) in EXTERNAL_INPUT_ROOTS:
            external_inputs.append({**item, "classification": "external_input_not_internal_gap"})
        else:
            missing_internal.append({
                **item,
                "classification": "missing_internal_provider",
                "truth_boundary": "absence is relative to the currently analyzed stack and declared/detected tokens",
            })

    for provided in provided_tokens:
        if any(token_match(provided, accepted)[0] for accepted in accepted_tokens):
            continue
        unused_outputs.append({
            "token": provided,
            "providers": sorted(providers[provided]),
            "classification": "currently_unconsumed_output",
        })

    adapter_candidates: list[dict[str, Any]] = []
    for provided in provided_tokens:
        for accepted in accepted_tokens:
            relation = lexical_adapter_relation(provided, accepted)
            if not relation:
                continue
            adapter_candidates.append({
                "provided": provided,
                "accepted": accepted,
                "providers": sorted(providers[provided]),
                "consumers": sorted(consumers[accepted]),
                "relation": relation,
                "status": "lexical_adapter_candidate_not_verified",
                "truth_boundary": "lexical similarity only; semantic compatibility and adapter necessity are unverified",
            })
    adapter_candidates.sort(key=lambda item: (item["relation"], item["provided"], item["accepted"]))

    return {
        "schema": "axm.monolith.pipeline-gaps/v0.1",
        "missing_internal_provider_count": len(missing_internal),
        "external_input_count": len(external_inputs),
        "unused_output_count": len(unused_outputs),
        "adapter_candidate_count": min(len(adapter_candidates), max_adapter_candidates),
        "missing_internal_providers": missing_internal,
        "external_inputs": external_inputs,
        "unused_outputs": unused_outputs,
        "adapter_candidates": adapter_candidates[:max_adapter_candidates],
        "truth_boundary": "Gap analysis is descriptive of this snapshot. It does not prove that a missing token needs a new repository or adapter.",
    }


def export_pipeline_fabric(
    build_root: Path,
    max_hops: int = MAX_DEFAULT_HOPS,
    max_candidates: int = 200,
) -> dict[str, Any]:
    build_root = build_root.resolve()
    analysis = load_analysis(build_root)
    graph = build_pipeline_graph(analysis)
    candidates = discover_pipelines(graph, max_hops=max_hops, max_candidates=max_candidates)
    gaps = analyze_gaps(graph)

    graph_path = build_root / "PIPELINE_GRAPH.json"
    candidates_path = build_root / "PIPELINE_CANDIDATES.json"
    gaps_path = build_root / "PIPELINE_GAPS.json"
    descriptor_path = build_root / "PIPELINE_FABRIC.json"

    write_json(graph_path, graph)
    write_json(candidates_path, {
        "schema": "axm.monolith.pipeline-candidates/v0.1",
        "schema_version": SCHEMA_VERSION,
        "max_hops": max_hops,
        "candidate_count": len(candidates),
        "pipelines": candidates,
        "truth_boundary": "Candidate pipelines are not executed, verified, safe, or authoritative by discovery alone.",
    })
    write_json(gaps_path, gaps)

    descriptor = {
        "schema": "axm.monolith.pipeline-fabric/v0.1",
        "schema_version": SCHEMA_VERSION,
        "source": "STACK_ANALYSIS.json",
        "outputs": {
            "graph": graph_path.name,
            "candidates": candidates_path.name,
            "gaps": gaps_path.name,
        },
        "capabilities": [
            "capability-level graph export",
            "bounded multi-capability pipeline discovery",
            "goal-token pipeline query",
            "missing-provider and unused-output analysis",
            "lexical adapter-gap leads",
        ],
        "authority": {
            "automatic_execution": False,
            "automatic_install": False,
            "automatic_merge": False,
            "automatic_canon": False,
        },
        "truth_boundary": "This fabric makes the stack's possibility space legible. It does not turn possibility into verified interoperability.",
    }
    write_json(descriptor_path, descriptor)
    return {
        "schema": descriptor["schema"],
        "graph_nodes": graph["node_count"],
        "graph_edges": graph["edge_count"],
        "pipeline_candidates": len(candidates),
        "missing_internal_providers": gaps["missing_internal_provider_count"],
        "adapter_candidates": gaps["adapter_candidate_count"],
        "outputs": [descriptor_path.name, graph_path.name, candidates_path.name, gaps_path.name],
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AXM Monolith capability-pipeline fabric")
    sub = p.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="derive reusable graph/candidates/gaps from STACK_ANALYSIS.json")
    export.add_argument("build", type=Path)
    export.add_argument("--max-hops", type=int, default=MAX_DEFAULT_HOPS)
    export.add_argument("--max-candidates", type=int, default=200)

    goal = sub.add_parser("goal", help="find candidate pipelines ending in a provided goal token")
    goal.add_argument("build", type=Path)
    goal.add_argument("goal")
    goal.add_argument("--max-hops", type=int, default=MAX_DEFAULT_HOPS)
    goal.add_argument("--max-results", type=int, default=30)

    gaps = sub.add_parser("gaps", help="show missing providers, external inputs, unused outputs and adapter leads")
    gaps.add_argument("build", type=Path)

    refresh = sub.add_parser("refresh", help="re-run Monolith stack analysis, then export pipeline fabric")
    refresh.add_argument("build", type=Path)
    refresh.add_argument("--max-hops", type=int, default=MAX_DEFAULT_HOPS)
    refresh.add_argument("--max-candidates", type=int, default=200)

    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "export":
            print(json.dumps(export_pipeline_fabric(args.build, args.max_hops, args.max_candidates), indent=2, sort_keys=True))
            return 0
        if args.command == "goal":
            graph = build_pipeline_graph(load_analysis(args.build))
            print(json.dumps(query_goal(graph, args.goal, args.max_hops, args.max_results), indent=2, sort_keys=True))
            return 0
        if args.command == "gaps":
            graph = build_pipeline_graph(load_analysis(args.build))
            print(json.dumps(analyze_gaps(graph), indent=2, sort_keys=True))
            return 0
        if args.command == "refresh":
            tools_dir = Path(__file__).resolve().parent
            if str(tools_dir) not in sys.path:
                sys.path.insert(0, str(tools_dir))
            from inspect_stack import analyze_build
            analyze_build(args.build)
            print(json.dumps(export_pipeline_fabric(args.build, args.max_hops, args.max_candidates), indent=2, sort_keys=True))
            return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
