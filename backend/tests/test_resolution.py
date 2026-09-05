"""Call resolution: precision, and the reporting of what stays imprecise."""
import unittest

from core.graph_builder import (
    SymbolTable,
    build_implementation_graph,
    class_id,
    function_id,
    method_id,
)
from tests.helpers import arch_ambiguous_calls, arch_base, arch_cross_file


def edges_with(graph, relation):
    return {(u, v) for u, v, data in graph.edges(data=True) if data.get("relation") == relation}


class FieldResolutionTests(unittest.TestCase):
    def test_call_through_a_typed_field_resolves_to_that_class(self):
        graph = build_implementation_graph(arch_base())
        source = method_id("orders.py", "OrderService", "place")
        target = method_id("orders.py", "OrderRepository", "save")
        self.assertIn((source, target), edges_with(graph, "calls"))

    def test_resolution_is_attributed_to_the_field_bucket(self):
        graph = build_implementation_graph(arch_base())
        stats = graph.graph["call_resolution"]
        self.assertEqual(stats["field"], 1)
        self.assertEqual(stats["total_call_sites"], 1)
        self.assertEqual(stats["resolution_rate"], 1.0)


class CrossFileResolutionTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_implementation_graph(arch_cross_file())

    def test_call_resolves_across_files(self):
        source = method_id("app/service.py", "OrderService", "place")
        target = method_id("app/repository.py", "OrderRepository", "save")
        self.assertIn((source, target), edges_with(self.graph, "calls"))

    def test_instantiation_is_a_distinct_relation(self):
        source = method_id("app/service.py", "OrderService", "build")
        target = class_id("app/repository.py", "OrderRepository")
        self.assertIn((source, target), edges_with(self.graph, "instantiates"))

    def test_no_edge_to_the_unrelated_sibling_method(self):
        source = method_id("app/service.py", "OrderService", "place")
        unrelated = method_id("app/repository.py", "OrderRepository", "delete")
        self.assertNotIn((source, unrelated), edges_with(self.graph, "calls"))


class AmbiguityTests(unittest.TestCase):
    def test_ambiguous_call_is_left_unresolved_and_counted(self):
        graph = build_implementation_graph(arch_ambiguous_calls())
        stats = graph.graph["call_resolution"]
        self.assertEqual(stats["ambiguous"], 1)
        # The previous implementation linked to every same-named definition,
        # inflating the impact set. Nothing should be linked here.
        source = function_id("c.py", "run")
        self.assertEqual(
            [target for src, target in edges_with(graph, "calls") if src == source], []
        )

    def test_resolution_rate_reflects_the_ambiguity(self):
        graph = build_implementation_graph(arch_ambiguous_calls())
        stats = graph.graph["call_resolution"]
        self.assertEqual(stats["total_call_sites"], 1)
        self.assertEqual(stats["resolved"], 0)
        self.assertEqual(stats["resolution_rate"], 0.0)


class SymbolTableTests(unittest.TestCase):
    def setUp(self):
        self.table = SymbolTable(arch_cross_file())

    def test_module_resolution_handles_dotted_and_relative_forms(self):
        self.assertEqual(self.table.resolve_module("app.repository"), "app/repository.py")
        self.assertEqual(self.table.resolve_module("./repository"), "app/repository.py")
        self.assertEqual(self.table.resolve_module("app/repository.py"), "app/repository.py")

    def test_unknown_module_resolves_to_nothing(self):
        self.assertIsNone(self.table.resolve_module("django.db.models"))

    def test_imported_symbol_resolves_to_its_file(self):
        target = self.table.import_target("app/service.py", "OrderRepository")
        self.assertIsNotNone(target)
        self.assertEqual(target[0], "app/repository.py")

    def test_inherited_methods_are_found_through_bases(self):
        from tests.helpers import (
            make_architecture,
            make_class,
            make_file,
            make_method,
        )

        architecture = make_architecture(
            [
                make_file(
                    "shapes.py",
                    classes=[
                        make_class("Base", methods=[make_method("draw", 1)]),
                        make_class("Circle", bases=["Base"]),
                    ],
                )
            ]
        )
        table = SymbolTable(architecture)
        circle = class_id("shapes.py", "Circle")
        self.assertEqual(
            table.method_of(circle, "draw"), method_id("shapes.py", "Base", "draw")
        )


if __name__ == "__main__":
    unittest.main()
