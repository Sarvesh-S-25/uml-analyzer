"""The measurement code itself has to be right, or the study reports fiction."""
import json
import os
import shutil
import sys
import tempfile
import unittest

RESEARCH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "research"))

if os.path.isdir(RESEARCH):
    sys.path.insert(0, RESEARCH)
    sys.path.insert(0, os.path.join(RESEARCH, "deviations"))

try:
    import evaluate_deviations
    import harness
    import replay

    AVAILABLE = True
    SKIP_REASON = ""
except Exception as exc:  # pragma: no cover - depends on layout
    AVAILABLE = False
    SKIP_REASON = f"research scripts unavailable: {exc}"


def result(missing_classes=(), violations=(), score=90.0):
    return {
        "difference": {
            "missing_classes": list(missing_classes),
            "extra_classes": [],
            "missing_relations": [],
            "unimplemented_associations": [],
            "element_differences": [],
        },
        "rule_violations": [{"rule": r, "file": "a.py"} for r in violations],
        "similarity_score_rule_based": score,
    }


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class SignatureTests(unittest.TestCase):
    def test_identical_results_have_identical_signatures(self):
        self.assertEqual(
            harness.finding_signature(result(["A"])),
            harness.finding_signature(result(["A"])),
        )

    def test_signature_ignores_ordering(self):
        self.assertEqual(
            harness.finding_signature(result(["A", "B"])),
            harness.finding_signature(result(["B", "A"])),
        )

    def test_differences_are_named(self):
        left = harness.finding_signature(result(["A"]))
        right = harness.finding_signature(result(["A", "B"]))
        self.assertEqual(harness.signatures_differ(left, right), ["missing_classes"])

    def test_score_change_alone_is_detected(self):
        left = harness.finding_signature(result(score=90.0))
        right = harness.finding_signature(result(score=80.0))
        self.assertIn("similarity_score_rule_based", harness.signatures_differ(left, right))

    def test_no_difference_returns_empty(self):
        left = harness.finding_signature(result(["A"], ["layering"]))
        self.assertEqual(harness.signatures_differ(left, dict(left)), [])


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class CorpusTests(unittest.TestCase):
    def test_bundled_corpus_parses(self):
        specs = harness.load_corpus(os.path.join(RESEARCH, "corpus.json"))
        self.assertTrue(specs)
        self.assertEqual(specs[0].name, "reference-orders")

    def test_spec_defaults(self):
        spec = harness.ProjectSpec.from_dict({"name": "x", "source": "/tmp/x"})
        self.assertEqual(spec.commits, 30)
        self.assertIsNone(spec.uml)

    def test_comment_keys_are_ignored(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "corpus.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {"$comment": "notes", "projects": [{"name": "a", "source": "."}]}, handle
            )
        specs = harness.load_corpus(path)
        self.assertEqual(len(specs), 1)


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class CopySourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tree_is_copied_and_vendored_dirs_skipped(self):
        tree = os.path.join(self.tmp, "tree")
        os.makedirs(os.path.join(tree, "app"))
        os.makedirs(os.path.join(tree, "node_modules", "pkg"))
        with open(os.path.join(tree, "app", "service.py"), "w") as handle:
            handle.write("class Service: pass")
        with open(os.path.join(tree, "node_modules", "pkg", "index.js"), "w") as handle:
            handle.write("module.exports = {}")

        project = os.path.join(self.tmp, "project")
        os.makedirs(os.path.join(project, "source"))
        copied = harness.copy_source(tree, project)

        self.assertEqual(copied, 1)
        self.assertTrue(os.path.exists(os.path.join(project, "source", "app", "service.py")))
        self.assertFalse(os.path.exists(os.path.join(project, "source", "node_modules")))

    def test_previous_contents_are_replaced_not_merged(self):
        """Each commit must produce the tree at that commit, not a union of all
        the trees seen so far -- otherwise deletions would never register."""
        tree = os.path.join(self.tmp, "tree")
        os.makedirs(tree)
        project = os.path.join(self.tmp, "project")
        os.makedirs(os.path.join(project, "source"))

        with open(os.path.join(tree, "old.py"), "w") as handle:
            handle.write("x = 1")
        harness.copy_source(tree, project)
        self.assertTrue(os.path.exists(os.path.join(project, "source", "old.py")))

        os.remove(os.path.join(tree, "old.py"))
        with open(os.path.join(tree, "new.py"), "w") as handle:
            handle.write("y = 2")
        harness.copy_source(tree, project)

        self.assertFalse(os.path.exists(os.path.join(project, "source", "old.py")))
        self.assertTrue(os.path.exists(os.path.join(project, "source", "new.py")))

    def test_subdirectory_narrows_the_copy(self):
        tree = os.path.join(self.tmp, "tree")
        os.makedirs(os.path.join(tree, "src", "main"))
        os.makedirs(os.path.join(tree, "docs"))
        with open(os.path.join(tree, "src", "main", "a.py"), "w") as handle:
            handle.write("a = 1")
        with open(os.path.join(tree, "docs", "readme.md"), "w") as handle:
            handle.write("# docs")

        project = os.path.join(self.tmp, "project")
        os.makedirs(os.path.join(project, "source"))
        harness.copy_source(tree, project, subdirectory="src")

        self.assertTrue(os.path.exists(os.path.join(project, "source", "main", "a.py")))
        self.assertFalse(os.path.exists(os.path.join(project, "source", "docs")))


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class SummaryTests(unittest.TestCase):
    def rows(self):
        # `gate_strategy`, not `strategy`: this is the column name
        # backend/stats/report.py::normalise_rows reads, and replay.py writes
        # it so a replayed study does not arrive with every row's gate
        # recorded as "unknown".
        return [
            {"gate_strategy": "always", "gate_allowed_llm": True, "missed_change": False,
             "prompt_tokens": 100, "completion_tokens": 20, "latency_ms": 50.0, "impact_nodes": 10},
            {"gate_strategy": "always", "gate_allowed_llm": True, "missed_change": False,
             "prompt_tokens": 100, "completion_tokens": 20, "latency_ms": 50.0, "impact_nodes": 10},
            {"gate_strategy": "structural", "gate_allowed_llm": True, "missed_change": False,
             "prompt_tokens": 100, "completion_tokens": 20, "latency_ms": 50.0, "impact_nodes": 4},
            {"gate_strategy": "structural", "gate_allowed_llm": False, "missed_change": False,
             "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 5.0, "impact_nodes": 0},
            {"gate_strategy": "isomorphism", "gate_allowed_llm": False, "missed_change": True,
             "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 5.0, "impact_nodes": 0},
            {"gate_strategy": "isomorphism", "gate_allowed_llm": False, "missed_change": False,
             "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 5.0, "impact_nodes": 0},
        ]

    def test_rates_are_computed_per_strategy(self):
        summary = replay.summarise(self.rows())
        self.assertEqual(summary["always"]["reuse_rate"], 0.0)
        self.assertEqual(summary["structural"]["reuse_rate"], 0.5)
        self.assertEqual(summary["isomorphism"]["reuse_rate"], 1.0)

    def test_miss_rate_is_reported(self):
        summary = replay.summarise(self.rows())
        self.assertEqual(summary["isomorphism"]["miss_rate"], 0.5)
        self.assertEqual(summary["structural"]["miss_rate"], 0.0)

    def test_relative_cost_uses_the_always_baseline(self):
        summary = replay.summarise(self.rows())
        # structural re-analysed once where always re-analysed twice
        self.assertEqual(summary["structural"]["reanalyses_vs_always"], 0.5)
        self.assertEqual(summary["isomorphism"]["reanalyses_vs_always"], 0.0)

    def test_token_totals_accumulate(self):
        summary = replay.summarise(self.rows())
        self.assertEqual(summary["always"]["prompt_tokens"], 200)
        self.assertEqual(summary["isomorphism"]["prompt_tokens"], 0)


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class ConfusionTests(unittest.TestCase):
    def rows(self):
        return [
            # findings moved and the gate fired: correct
            {"strategy": "structural", "findings_changed": True, "gate_fired": True,
             "missed_change": False, "wasted_reanalysis": False, "mutation": "delete-method"},
            # findings moved and the gate reused: the consequential error
            {"strategy": "structural", "findings_changed": True, "gate_fired": False,
             "missed_change": True, "wasted_reanalysis": False, "mutation": "rename-consistent"},
            # nothing moved and the gate reused: correct
            {"strategy": "structural", "findings_changed": False, "gate_fired": False,
             "missed_change": False, "wasted_reanalysis": False, "mutation": "comment-only"},
            # nothing moved but the gate fired: wasted spend
            {"strategy": "structural", "findings_changed": False, "gate_fired": True,
             "missed_change": False, "wasted_reanalysis": True, "mutation": "param-count"},
        ]

    def test_matrix_counts(self):
        matrix = evaluate_deviations.confusion(self.rows(), ["structural"])["structural"]
        self.assertEqual(matrix["true_positive"], 1)
        self.assertEqual(matrix["false_negative"], 1)
        self.assertEqual(matrix["false_positive"], 1)
        self.assertEqual(matrix["true_negative"], 1)

    def test_precision_and_recall(self):
        matrix = evaluate_deviations.confusion(self.rows(), ["structural"])["structural"]
        self.assertEqual(matrix["precision"], 0.5)
        self.assertEqual(matrix["recall"], 0.5)

    def test_missed_and_wasted_are_named(self):
        matrix = evaluate_deviations.confusion(self.rows(), ["structural"])["structural"]
        self.assertEqual(matrix["missed"], ["rename-consistent"])
        self.assertEqual(matrix["wasted"], ["param-count"])

    def test_empty_input_does_not_divide_by_zero(self):
        matrix = evaluate_deviations.confusion([], ["structural"])["structural"]
        self.assertIsNone(matrix["precision"])
        self.assertIsNone(matrix["recall"])


if __name__ == "__main__":
    unittest.main()
