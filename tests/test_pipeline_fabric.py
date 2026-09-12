import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "pipeline_fabric.py"
spec = importlib.util.spec_from_file_location("pipeline_fabric", MODULE_PATH)
pipeline_fabric = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(pipeline_fabric)


def cap(module, cid, provides=(), accepts=(), source="native-manifest", evidence="declared_not_verified"):
    return {
        "id": cid,
        "description": cid,
        "source": source,
        "evidence_status": evidence,
        "confidence": 1.0 if source == "native-manifest" else 0.9,
        "provides": list(provides),
        "accepts": list(accepts),
        "tags": [],
    }


def module(name, capabilities):
    return {
        "module": name,
        "repository": f"mike-axiom-mir/{name}",
        "capabilities": capabilities,
    }


class PipelineFabricTests(unittest.TestCase):
    def synthetic_analysis(self):
        modules = [
            module("creator", [cap("creator", "create", ["artifact.software"], ["objective"])]),
            module("tester", [cap("tester", "test", ["evidence.test"], ["artifact.software"])]),
            module("packager", [cap("packager", "package", ["artifact.release"], ["evidence.test", "artifact.missing"])]),
            module("voice", [cap("voice", "speak", ["artifact.audio"], ["message"])]),
        ]
        graph = {
            "nodes": [{"module": m["module"]} for m in modules],
            "edges": [
                {
                    "from": "creator", "to": "tester",
                    "provided": "artifact.software", "accepted": "artifact.software",
                    "match": "exact", "status": "declared_contract_match_not_tested", "score": 3,
                    "producer_capability": "create", "consumer_capability": "test",
                },
                {
                    "from": "tester", "to": "packager",
                    "provided": "evidence.test", "accepted": "evidence.test",
                    "match": "exact", "status": "structurally_possible_not_tested", "score": 2,
                    "producer_capability": "test", "consumer_capability": "package",
                },
            ],
        }
        return {"schema_version": "0.2", "modules": modules, "graph": graph}

    def test_capability_graph_preserves_edge_evidence(self):
        graph = pipeline_fabric.build_pipeline_graph(self.synthetic_analysis())
        self.assertEqual(graph["node_count"], 4)
        self.assertEqual(graph["edge_count"], 2)
        self.assertEqual(graph["edges"][0]["evidence_status"], "declared_contract_match_not_tested")
        self.assertTrue(all("not_tested" in edge["evidence_status"] for edge in graph["edges"]))

    def test_discovers_multi_capability_pipeline_with_weakest_edge_status(self):
        graph = pipeline_fabric.build_pipeline_graph(self.synthetic_analysis())
        pipelines = pipeline_fabric.discover_pipelines(graph, max_hops=3)
        target = next(
            item for item in pipelines
            if item["capabilities"] == ["create", "test", "package"]
        )
        self.assertEqual(target["status"], "structurally_possible_path_not_tested")
        self.assertEqual(target["weakest_edge_score"], 2)
        self.assertEqual(target["terminal_outputs"], ["artifact.release"])

    def test_goal_query_finds_release_pipeline(self):
        graph = pipeline_fabric.build_pipeline_graph(self.synthetic_analysis())
        result = pipeline_fabric.query_goal(graph, "artifact.release")
        self.assertGreaterEqual(result["result_count"], 1)
        self.assertTrue(any(item["capabilities"] == ["create", "test", "package"] for item in result["results"]))
        self.assertIn("not executed", result["truth_boundary"].lower())

    def test_gap_analysis_separates_external_input_from_internal_gap(self):
        graph = pipeline_fabric.build_pipeline_graph(self.synthetic_analysis())
        gaps = pipeline_fabric.analyze_gaps(graph)
        missing = {item["token"] for item in gaps["missing_internal_providers"]}
        external = {item["token"] for item in gaps["external_inputs"]}
        self.assertIn("artifact.missing", missing)
        self.assertIn("objective", external)
        self.assertIn("message", external)
        self.assertNotIn("objective", missing)

    def test_lexical_adapter_candidate_is_never_promoted(self):
        analysis = self.synthetic_analysis()
        analysis["modules"].append(
            module("materials", [cap("materials", "material", ["asset.material"], [])])
        )
        analysis["modules"].append(
            module("renderer", [cap("renderer", "render", [], ["artifact.material"])])
        )
        graph = pipeline_fabric.build_pipeline_graph(analysis)
        gaps = pipeline_fabric.analyze_gaps(graph)
        candidate = next(
            item for item in gaps["adapter_candidates"]
            if item["provided"] == "asset.material" and item["accepted"] == "artifact.material"
        )
        self.assertEqual(candidate["status"], "lexical_adapter_candidate_not_verified")

    def test_export_is_deterministic_and_reusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis = self.synthetic_analysis()
            (root / "STACK_ANALYSIS.json").write_text(
                json.dumps(analysis, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            first = pipeline_fabric.export_pipeline_fabric(root, max_hops=3)
            snapshot = {
                name: (root / name).read_bytes()
                for name in first["outputs"]
            }
            second = pipeline_fabric.export_pipeline_fabric(root, max_hops=3)
            self.assertEqual(first, second)
            for name, content in snapshot.items():
                self.assertEqual(content, (root / name).read_bytes())
            descriptor = json.loads((root / "PIPELINE_FABRIC.json").read_text(encoding="utf-8"))
            self.assertFalse(descriptor["authority"]["automatic_execution"])
            self.assertFalse(descriptor["authority"]["automatic_canon"])


if __name__ == "__main__":
    unittest.main()
