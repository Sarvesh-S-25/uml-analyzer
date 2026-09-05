"""End-to-end pipeline behaviour: versioning, reuse, reporting, UML handling."""
import json
import pathlib
import shutil
import tempfile
import unittest

from core.graph_store import GraphVersionStore
from core.pipeline import run_analysis
from core.run_ledger import RunLedger
from tests.helpers import (
    arch_base,
    arch_comment_only,
    arch_layering_violation,
    arch_new_method,
    arch_renamed,
    write_project,
)


class PipelineTestCase(unittest.TestCase):
    """Drives the real pipeline with an injected architecture, so gating,
    versioning, and reporting are exercised without a native parser build."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.project = write_project(self.tmp / "proj")
        self.architecture = arch_base()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def analyse(self, architecture=None, **kwargs):
        if architecture is not None:
            self.architecture = architecture
        return run_analysis(
            str(self.project),
            parse_source=lambda _source_dir: self.architecture,
            **kwargs,
        )


class VersioningTests(PipelineTestCase):
    def test_cold_start_then_cache_hit(self):
        first = self.analyse(gate_strategy="structural")
        self.assertEqual(first["version"], 1)
        self.assertTrue(first["gate"]["should_invoke_llm"])
        self.assertIn("cold start", first["gate"]["reason"])

        second = self.analyse(gate_strategy="structural")
        self.assertEqual(second["version"], 2)
        self.assertFalse(second["gate"]["should_invoke_llm"])
        self.assertEqual(second["reused_from_version"], 1)

    def test_force_bypasses_the_gate(self):
        self.analyse(gate_strategy="structural")
        forced = self.analyse(gate_strategy="structural", force=True)
        self.assertEqual(forced["gate"]["strategy"], "always")
        self.assertTrue(forced["gate"]["should_invoke_llm"])

    def test_only_three_versions_are_retained(self):
        for _ in range(5):
            self.analyse(gate_strategy="structural")

        store = GraphVersionStore(str(self.project))
        versions = store.list_versions()
        self.assertEqual(len(versions), 3)
        self.assertEqual([v["version"] for v in versions], [5, 4, 3])
        # dropped snapshots lose their graph file, not just their index entry
        self.assertIsNone(store.load_graph(1))
        self.assertIsNone(store.load_graph(2))
        self.assertIsNotNone(store.load_graph(5))

    def test_version_diff_reports_additions(self):
        self.analyse(gate_strategy="structural")
        self.analyse(arch_new_method(), gate_strategy="structural")

        diff = GraphVersionStore(str(self.project)).diff(1, 2)
        self.assertEqual((diff["from_version"], diff["to_version"]), (1, 2))
        self.assertGreater(diff["summary"]["added_nodes"], 0)

    def test_missing_version_diff_raises(self):
        for _ in range(4):
            self.analyse(gate_strategy="structural")
        with self.assertRaises(FileNotFoundError):
            GraphVersionStore(str(self.project)).diff(1, 4)


class GatingBehaviourTests(PipelineTestCase):
    def test_comment_edit_does_not_re_invoke(self):
        self.analyse(gate_strategy="structural")
        result = self.analyse(arch_comment_only(), gate_strategy="structural")
        self.assertFalse(result["gate"]["should_invoke_llm"])

    def test_structural_change_is_detected_and_scoped(self):
        self.analyse(gate_strategy="structural")
        result = self.analyse(arch_new_method(), gate_strategy="structural")
        self.assertTrue(result["gate"]["should_invoke_llm"])
        self.assertGreater(result["gate"]["impact_node_count"], 0)
        delta = result["gate"]["delta"]
        self.assertGreater(delta["added_nodes"] + delta["changed_nodes"], 0)

    def test_rename_under_isomorphism_gate_is_reused_and_relabelled(self):
        self.analyse(gate_strategy="isomorphism")
        result = self.analyse(arch_renamed(), gate_strategy="isomorphism")
        self.assertFalse(result["gate"]["should_invoke_llm"])
        self.assertTrue(result["renamed_components"])

    def test_rename_under_structural_gate_re_invokes(self):
        self.analyse(gate_strategy="structural")
        result = self.analyse(arch_renamed(), gate_strategy="structural")
        self.assertTrue(result["gate"]["should_invoke_llm"])


class ReportingTests(PipelineTestCase):
    def test_rule_engine_finds_designed_but_missing_members(self):
        result = self.analyse(gate_strategy="structural")
        difference = result["difference"]
        self.assertIn("AuditLog", difference["missing_classes"])
        missing_methods = [
            method
            for element in difference["element_differences"]
            for method in element["missing_methods"]
        ]
        self.assertIn("refund", missing_methods)
        self.assertGreaterEqual(result["similarity_score_rule_based"], 0)
        self.assertLessEqual(result["similarity_score_rule_based"], 100)

    def test_missing_relation_is_reported(self):
        result = self.analyse(gate_strategy="structural")
        self.assertTrue(
            any("AuditLog" in relation for relation in result["difference"]["missing_relations"])
        )

    def test_graph_payload_is_populated_for_the_frontend(self):
        result = self.analyse(gate_strategy="structural")
        graph = result["graph_data"]
        self.assertTrue(graph["nodes"], "graph_data.nodes drives the UI and must not be empty")
        self.assertIn("links", graph)
        self.assertEqual(result["networkx_nodes"], len(graph["nodes"]))
        self.assertEqual(result["networkx_edges"], len(graph["links"]))
        self.assertIn("missing", {node["status"] for node in graph["nodes"]})

    def test_layering_violations_carry_evidence(self):
        result = self.analyse(arch_layering_violation(), gate_strategy="structural")
        violations = result["rule_violations"]
        self.assertTrue(violations)
        self.assertIn("evidence", violations[0])
        self.assertEqual(violations[0]["confidence"], "heuristic")

    def test_clean_architecture_produces_no_violations(self):
        self.assertEqual(self.analyse(gate_strategy="structural")["rule_violations"], [])


class UmlHandlingTests(PipelineTestCase):
    def test_malformed_uml_is_surfaced_not_swallowed(self):
        (self.project / "uml" / "design.mdj").write_text("{ not valid json", encoding="utf-8")
        result = self.analyse(gate_strategy="structural")
        self.assertTrue(result["uml"]["error"])
        self.assertEqual(result["uml"]["element_count"], 0)

    def test_absent_uml_is_not_an_error(self):
        (self.project / "uml" / "design.mdj").unlink()
        result = self.analyse(gate_strategy="structural")
        self.assertIsNone(result["uml"]["error"])
        self.assertIsNone(result["uml"]["filename"])

    def test_relations_are_parsed(self):
        result = self.analyse(gate_strategy="structural")
        self.assertEqual(result["uml"]["element_count"], 3)
        self.assertGreaterEqual(result["uml"]["relation_count"], 2)

    def test_changing_the_uml_forces_reanalysis(self):
        self.analyse(gate_strategy="structural")
        model = json.loads((self.project / "uml" / "design.mdj").read_text())
        model["ownedElements"][0]["ownedElements"].append(
            {"_type": "UMLClass", "_id": "c9", "name": "Invoice", "attributes": [], "operations": []}
        )
        (self.project / "uml" / "design.mdj").write_text(json.dumps(model), encoding="utf-8")

        result = self.analyse(gate_strategy="structural")
        self.assertTrue(result["gate"]["should_invoke_llm"])
        self.assertIn("UML", result["gate"]["reason"])


class LedgerTests(PipelineTestCase):
    def test_every_run_is_recorded(self):
        self.analyse(gate_strategy="structural")
        self.analyse(gate_strategy="structural")

        ledger = RunLedger(str(self.project))
        rows = ledger.rows()
        self.assertEqual(len(rows), 2)
        # The gate permitted the cold start and blocked the repeat.
        self.assertTrue(rows[0]["gate_allowed_llm"])
        self.assertFalse(rows[1]["gate_allowed_llm"])
        # In offline mode no model is reached on either run; the ledger keeps
        # that separate from the gate decision.
        self.assertFalse(rows[0]["llm_invoked"])

        metrics = ledger.metrics()
        self.assertEqual(metrics["total_runs"], 2)
        self.assertEqual(metrics["reanalyses"], 1)
        self.assertEqual(metrics["cached_runs"], 1)
        self.assertEqual(metrics["cache_hit_rate"], 0.5)
        self.assertIn("structural", metrics["by_strategy"])
        self.assertEqual(metrics["by_strategy"]["structural"]["reanalyses"], 1)

    def test_metrics_are_empty_before_any_run(self):
        self.assertEqual(RunLedger(str(self.project)).metrics()["total_runs"], 0)


class DeterminismTests(PipelineTestCase):
    def test_offline_mode_is_reproducible(self):
        first = self.analyse(gate_strategy="always", force=True)
        second = self.analyse(gate_strategy="always", force=True)
        # The no-LLM control condition must be exactly reproducible, otherwise
        # it cannot serve as a baseline.
        self.assertEqual(first["similarity_score"], second["similarity_score"])
        self.assertEqual(first["ai_gaps"], second["ai_gaps"])
        self.assertEqual(first["networkx_nodes"], second["networkx_nodes"])

    def test_offline_results_are_labelled_as_such(self):
        result = self.analyse(gate_strategy="always", force=True)
        self.assertEqual(result["llm"]["model"], "deterministic-offline")
        self.assertFalse(result["llm"]["invoked"])


if __name__ == "__main__":
    unittest.main()
