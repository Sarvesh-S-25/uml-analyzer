"""The central claim under test: which edits should and should not cost an LLM call."""
import unittest

from core.graph_builder import build_implementation_graph
from core.graph_diff import (
    decide_gate,
    diff_graphs,
    find_renames,
    impact_set,
    is_label_isomorphic,
)
from tests.helpers import (
    arch_base,
    arch_comment_only,
    arch_new_method,
    arch_renamed,
)


def gate(strategy, old_arch, new_arch, **kwargs):
    return decide_gate(
        strategy,
        build_implementation_graph(old_arch),
        build_implementation_graph(new_arch),
        old_arch["project_text_sha256"],
        new_arch["project_text_sha256"],
        old_arch["project_structure_sha256"],
        new_arch["project_structure_sha256"],
        **kwargs,
    )


class GraphConstructionTests(unittest.TestCase):
    def test_call_edges_are_recovered(self):
        graph = build_implementation_graph(arch_base())
        relations = {data.get("relation") for _, _, data in graph.edges(data=True)}
        self.assertIn("contains", relations)
        self.assertIn("calls", relations)

    def test_every_declaration_becomes_a_node(self):
        graph = build_implementation_graph(arch_base())
        kinds = [data["kind"] for _, data in graph.nodes(data=True)]
        self.assertEqual(kinds.count("module"), 1)
        self.assertEqual(kinds.count("class"), 2)
        self.assertEqual(kinds.count("method"), 2)


class FingerprintTests(unittest.TestCase):
    def test_comment_edit_moves_text_hash_only(self):
        base, commented = arch_base(), arch_comment_only()
        self.assertNotEqual(base["project_text_sha256"], commented["project_text_sha256"])
        self.assertEqual(
            base["project_structure_sha256"], commented["project_structure_sha256"]
        )


class GateTests(unittest.TestCase):
    def test_cold_start_always_invokes(self):
        decision = decide_gate(
            "structural", None, build_implementation_graph(arch_base()),
            None, "t", None, "s",
        )
        self.assertTrue(decision.should_invoke_llm)
        self.assertIn("cold start", decision.reason)

    def test_identical_input_is_a_cache_hit(self):
        decision = gate("structural", arch_base(), arch_base())
        self.assertFalse(decision.should_invoke_llm)
        self.assertEqual(decision.to_dict()["decision"], "reused-cached-version")

    def test_structural_gate_absorbs_a_comment_the_content_gate_pays_for(self):
        base, commented = arch_base(), arch_comment_only()
        # This contrast is the experiment: same edit, two gates, different cost.
        self.assertTrue(gate("content", base, commented).should_invoke_llm)
        self.assertFalse(gate("structural", base, commented).should_invoke_llm)

    def test_always_strategy_ignores_the_gate(self):
        self.assertTrue(gate("always", arch_base(), arch_base()).should_invoke_llm)

    def test_real_addition_triggers_every_strategy(self):
        base, extended = arch_base(), arch_new_method()
        for strategy in ("content", "structural", "isomorphism"):
            with self.subTest(strategy=strategy):
                decision = gate(strategy, base, extended)
                self.assertTrue(decision.should_invoke_llm)
                self.assertTrue(decision.impact_nodes)

    def test_uml_change_forces_reanalysis_even_with_unchanged_code(self):
        decision = gate("structural", arch_base(), arch_base(), uml_changed=True)
        self.assertTrue(decision.should_invoke_llm)


class IsomorphismTests(unittest.TestCase):
    def test_rename_preserves_shape(self):
        old = build_implementation_graph(arch_base())
        new = build_implementation_graph(arch_renamed())
        self.assertIs(is_label_isomorphic(old, new), True)

    def test_addition_breaks_shape(self):
        old = build_implementation_graph(arch_base())
        new = build_implementation_graph(arch_new_method())
        self.assertIs(is_label_isomorphic(old, new), False)

    def test_isomorphism_gate_absorbs_a_rename_that_structural_pays_for(self):
        base, renamed = arch_base(), arch_renamed()
        self.assertTrue(gate("structural", base, renamed).should_invoke_llm)

        decision = gate("isomorphism", base, renamed)
        self.assertFalse(decision.should_invoke_llm)
        self.assertIs(decision.isomorphic, True)

    def test_rename_mapping_is_recoverable(self):
        old = build_implementation_graph(arch_base())
        new = build_implementation_graph(arch_renamed())
        mapping = find_renames(old, new)
        self.assertTrue(mapping)
        self.assertTrue(all(source != target for source, target in mapping.items()))


class DeltaTests(unittest.TestCase):
    def test_delta_is_empty_for_identical_graphs(self):
        graph = build_implementation_graph(arch_base())
        self.assertTrue(diff_graphs(graph, graph).is_empty)

    def test_delta_reports_additions(self):
        delta = diff_graphs(
            build_implementation_graph(arch_base()),
            build_implementation_graph(arch_new_method()),
        )
        self.assertFalse(delta.is_empty)
        self.assertGreater(len(delta.added_nodes), 0)
        self.assertGreater(delta.summary()["unchanged_nodes"], 0)

    def test_impact_set_expands_by_radius(self):
        graph = build_implementation_graph(arch_base())
        seed = {n for n, d in graph.nodes(data=True) if d["kind"] == "method"}
        narrow = impact_set(graph, seed, radius=0)
        wide = impact_set(graph, seed, radius=1)
        self.assertEqual(len(narrow), len(seed))
        self.assertGreater(len(wide), len(narrow))

    def test_impact_set_ignores_unknown_nodes(self):
        graph = build_implementation_graph(arch_base())
        self.assertEqual(impact_set(graph, {"nonexistent"}, radius=2), [])


if __name__ == "__main__":
    unittest.main()
