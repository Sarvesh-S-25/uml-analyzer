"""The statistics must be correct, because the paper's numbers come from here.

Two kinds of assertion:

* **Arithmetic.** Where a closed form exists it is checked exactly -- McNemar
  against the binomial, the Wilson interval against its published value, and the
  per-project totals against the pooled totals they must sum to.
* **The sentences.** Every table generates a plain-English reading, and those
  sentences are what the user actually reads. A sentence that says "missed
  nothing" when something was missed would be worse than a wrong number, so the
  readings are asserted too.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from stats.core import (
    MIN_DISCORDANT_PAIRS,
    describe,
    mcnemar_exact,
    mean,
    median,
    p_value_text,
    percent,
    rate,
    wilson_interval,
)
from stats.exports import split_latex, to_csv_bundle, to_latex, to_zip
from stats.report import build_report, normalise_rows


# --- fixtures ----------------------------------------------------------------


def sample_rows(projects=3, commits=20, oracle=True):
    """A small synthetic study with a known change pattern.

    Every third commit changes conformance. `always` re-analyses everything,
    `structural` re-analyses exactly the changing commits (so it is perfect), and
    `isomorphism` skips one change in six (so it misses, on purpose -- a fixture
    where nothing is ever missed cannot test the column that matters).
    """
    rows = []
    for p in range(projects):
        for c in range(commits):
            changed = c % 3 == 0
            for gate, fires in (
                ("always", True),
                ("structural", changed),
                ("isomorphism", changed and c % 6 != 0),
            ):
                row = {
                    "project": f"proj-{p}",
                    "commit": f"c{c}",
                    "commit_index": c,
                    "gate_strategy": gate,
                    "gate_allowed_llm": fires,
                    "conformance_changed": changed,
                    "prompt_tokens": 1500 if fires else 0,
                    "completion_tokens": 300 if fires else 0,
                    "latency_ms": 900 if fires else 20,
                    "changed_nodes": 8 if changed else 0,
                    "similarity_score": 0.8 + (c % 5) / 100,
                    "divergences": c // 4,
                    "absences": 2,
                }
                if oracle:
                    row["missed_change"] = changed and not fires
                rows.append(row)
    return rows


# Shaped exactly like `research/evaluate_deviations.py`'s actual
# `deviations_summary.json` (an ordered `strategies` name list plus a
# `confusion` dict keyed by those names) -- not the flat list of
# self-labelled cells this fixture used to assume, which nothing in the
# codebase ever produced and which made `table_deviations()` crash on every
# real run (`AttributeError: 'str' object has no attribute 'get'`).
DEVIATION_SUMMARY = {
    "strategies": ["always", "structural", "isomorphism"],
    "confusion": {
        "always": {"true_positive": 9, "false_negative": 0,
                    "false_positive": 7, "true_negative": 0, "precision": 0.5625, "recall": 1.0},
        "structural": {"true_positive": 9, "false_negative": 0,
                       "false_positive": 2, "true_negative": 5, "precision": 0.8182, "recall": 1.0},
        "isomorphism": {"true_positive": 8, "false_negative": 1,
                         "false_positive": 2, "true_negative": 5, "precision": 0.8, "recall": 0.8889},
    },
}


# --- the small numeric core --------------------------------------------------


class DescriptiveTests(unittest.TestCase):
    def test_median_of_even_and_odd(self):
        self.assertEqual(median([1, 2, 3]), 2)
        self.assertEqual(median([1, 2, 3, 4]), 2.5)

    def test_empty_input_is_none_not_zero(self):
        # Zero would be read as a measurement. None is read as "no data".
        self.assertIsNone(median([]))
        self.assertIsNone(mean([]))
        self.assertEqual(describe([])["n"], 0)

    def test_none_and_nan_are_dropped(self):
        summary = describe([1, None, 2, float("nan"), 3])
        self.assertEqual(summary["n"], 3)
        self.assertEqual(summary["median"], 2)

    def test_rate_of_zero_total_is_none(self):
        self.assertIsNone(rate(0, 0))
        self.assertEqual(rate(1, 4), 0.25)


class WilsonTests(unittest.TestCase):
    def test_interval_contains_the_observed_rate(self):
        low, high = wilson_interval(7, 10)
        self.assertLess(low, 0.7)
        self.assertGreater(high, 0.7)

    def test_stays_inside_zero_and_one_at_the_boundary(self):
        """The reason Wilson is used at all: the normal approximation goes
        negative here, and a rate cannot be negative."""
        low, high = wilson_interval(0, 12)
        self.assertGreaterEqual(low, 0.0)
        self.assertLess(high, 1.0)

        low, high = wilson_interval(12, 12)
        self.assertGreater(low, 0.0)
        self.assertLessEqual(high, 1.0)

    def test_matches_the_formula_computed_independently(self):
        """Derived by hand rather than copied, so this test can catch a mistake
        in the implementation rather than repeating it.

            n = 200, x = 40, p = 0.2, z = 1.959964
            denominator = 1 + z^2/n                       = 1.019207
            centre      = (p + z^2/2n) / denominator      = 0.205654
            margin      = z*sqrt(p(1-p)/n + z^2/4n^2)/den = 0.055202
        """
        low, high = wilson_interval(40, 200)
        self.assertAlmostEqual(low, 0.205654 - 0.055202, places=5)
        self.assertAlmostEqual(high, 0.205654 + 0.055202, places=5)

    def test_interval_is_asymmetric_around_the_observed_rate(self):
        """Wilson's centre is pulled toward 0.5; that asymmetry is the whole
        reason it behaves at the boundaries where the normal approximation does
        not."""
        low, high = wilson_interval(40, 200)
        self.assertGreater((high - 0.2), (0.2 - low))

    def test_more_runs_give_a_tighter_interval(self):
        narrow = wilson_interval(40, 200)
        wide = wilson_interval(2, 10)
        self.assertLess(narrow[1] - narrow[0], wide[1] - wide[0])

    def test_no_observations_is_none(self):
        self.assertEqual(wilson_interval(0, 0), (None, None))


class McNemarTests(unittest.TestCase):
    def test_matches_the_exact_binomial(self):
        # 10 disagreements, all in one direction: p = 2 * 0.5^10.
        left = [True] * 10 + [True] * 5
        right = [False] * 10 + [True] * 5
        result = mcnemar_exact(left, right)
        self.assertTrue(result["usable"])
        self.assertAlmostEqual(result["p_value"], 2 * (0.5 ** 10), places=9)
        self.assertEqual(result["left_only"], 10)
        self.assertEqual(result["right_only"], 0)
        self.assertEqual(result["agreed"], 5)

    def test_an_even_split_is_not_significant(self):
        left = [True] * 10 + [False] * 10
        right = [False] * 10 + [True] * 10
        result = mcnemar_exact(left, right)
        self.assertTrue(result["usable"])
        self.assertAlmostEqual(result["p_value"], 1.0, places=9)

    def test_identical_decisions_refuse_rather_than_return_one(self):
        result = mcnemar_exact([True, False] * 10, [True, False] * 10)
        self.assertFalse(result["usable"])
        self.assertIsNone(result["p_value"])
        self.assertIn("same decision", result["reason"])

    def test_too_few_disagreements_refuses(self):
        left = [True] * 3 + [False] * 20
        right = [False] * 3 + [False] * 20
        result = mcnemar_exact(left, right)
        self.assertFalse(result["usable"])
        self.assertIn(str(MIN_DISCORDANT_PAIRS), result["reason"])

    def test_empty_input_refuses(self):
        self.assertFalse(mcnemar_exact([], [])["usable"])

    def test_p_value_never_prints_as_zero(self):
        """2^-50 is not zero, and printing it as 0.000 would be a false claim."""
        self.assertEqual(p_value_text(2 ** -50), "below 0.001")
        self.assertEqual(p_value_text(0.5), "0.500")
        self.assertEqual(p_value_text(None), "not computed")

    def test_percent_says_not_measured_rather_than_zero(self):
        self.assertEqual(percent(None), "not measured")
        self.assertEqual(percent(0.405), "40.5%")


# --- the four tables ---------------------------------------------------------


class ReportTests(unittest.TestCase):
    report = None

    @classmethod
    def setUpClass(cls):
        cls.report = build_report(sample_rows(), deviations=DEVIATION_SUMMARY)

    def test_empty_input_explains_itself(self):
        report = build_report([])
        self.assertFalse(report["usable"])
        self.assertIn("replay", report["reason"])

    def test_all_four_tables_present(self):
        for section in ("study", "gates", "projects", "deviations", "comparison", "charts"):
            self.assertIn(section, self.report)

    def test_every_table_carries_a_reading(self):
        """The whole point of the rebuild: no number without a sentence."""
        for section in ("study", "gates", "projects", "deviations"):
            reading = self.report[section].get("reading")
            self.assertTrue(reading, f"{section} has no plain-English reading")
            self.assertGreater(len(reading), 40)
        self.assertTrue(self.report["comparison"]["reading"])
        self.assertTrue(self.report["headline"])

    # -- Table 1
    def test_study_counts(self):
        study = self.report["study"]
        self.assertEqual(study["projects"], 3)
        # Commits are counted per project: the same commit id in two different
        # repositories is two commits, not one.
        self.assertEqual(study["commits"], 3 * 20)
        self.assertEqual(study["runs"], 3 * 20 * 3)
        self.assertTrue(study["has_oracle"])

    def test_missing_oracle_is_stated_not_hidden(self):
        report = build_report(sample_rows(oracle=False))
        self.assertFalse(report["study"]["has_oracle"])
        self.assertIn("not measured", report["study"]["reading"])
        for row in report["gates"]["rows"]:
            self.assertIsNone(row["miss_rate"])

    # -- Table 2
    def test_baseline_skips_nothing(self):
        always = self._gate("always")
        self.assertEqual(always["skipped"], 0)
        self.assertEqual(always["skip_rate"], 0.0)
        self.assertTrue(always["is_baseline"])
        self.assertIsNone(always["tokens_saved"])

    def test_counts_add_up(self):
        for row in self.report["gates"]["rows"]:
            self.assertEqual(row["skipped"] + row["reanalysed"], row["runs"])
            self.assertAlmostEqual(row["skip_rate"], row["skipped"] / row["runs"], places=4)

    def test_savings_are_measured_against_the_baseline(self):
        always = self._gate("always")
        for row in self.report["gates"]["rows"]:
            if row["is_baseline"]:
                continue
            self.assertEqual(row["tokens_saved"], always["tokens"] - row["tokens"])

    def test_a_perfect_gate_misses_nothing_and_says_so(self):
        structural = self._gate("structural")
        self.assertEqual(structural["missed"], 0)
        self.assertIn("missed nothing", structural["reading"])

    def test_a_leaky_gate_reports_its_misses_in_its_own_sentence(self):
        isomorphism = self._gate("isomorphism")
        self.assertGreater(isomorphism["missed"], 0)
        self.assertIn("missed", isomorphism["reading"])
        self.assertNotIn("missed nothing", isomorphism["reading"])

    def test_recommendation_prefers_the_gate_that_missed_nothing(self):
        recommended = self.report["gates"]["recommended"]
        self.assertEqual(recommended["gate"], "structural")
        self.assertTrue(recommended["safe"])
        self.assertEqual(recommended["missed"], 0)

    def test_no_recommendation_without_an_oracle(self):
        report = build_report(sample_rows(oracle=False))
        self.assertIsNone(report["gates"]["recommended"]["gate"])
        self.assertIn("replay", report["gates"]["recommended"]["reason"].lower())

    def test_thin_data_is_flagged_rather_than_quietly_printed(self):
        report = build_report(sample_rows(projects=1, commits=2))
        thin = [row for row in report["gates"]["rows"] if not row["enough_runs"]]
        self.assertTrue(thin)
        self.assertIn("Careful", report["gates"]["reading"])

    # -- Table 3
    def test_one_row_per_project(self):
        rows = self.report["projects"]["rows"]
        self.assertEqual([row["project"] for row in rows], ["proj-0", "proj-1", "proj-2"])

    def test_per_project_rows_use_the_recommended_gate(self):
        self.assertEqual(self.report["projects"]["gate"], "structural")
        for row in self.report["projects"]["rows"]:
            self.assertEqual(row["runs"], 20)

    def test_identical_projects_rank_consistently(self):
        self.assertTrue(self.report["projects"]["consistent_ranking"])
        self.assertIn("same order", self.report["projects"]["reading"])

    def test_single_project_declines_to_generalise(self):
        report = build_report(sample_rows(projects=1), deviations=DEVIATION_SUMMARY)
        self.assertIn("cannot say whether the result generalises",
                      report["projects"]["reading"])

    # -- Table 4
    def test_deviation_table_reads_the_summary(self):
        deviations = self.report["deviations"]
        self.assertTrue(deviations["available"])
        self.assertEqual(len(deviations["rows"]), 3)
        self.assertEqual(deviations["conformance_breaking"], 9)

    def test_deviation_reading_names_the_known_failure(self):
        self.assertIn("renamed consistently", self.report["deviations"]["reading"])

    def test_missing_deviation_run_says_how_to_produce_it(self):
        report = build_report(sample_rows())
        self.assertFalse(report["deviations"]["available"])
        self.assertIn("evaluate_deviations.py", report["deviations"]["reading"])

    # -- the comparison
    def test_comparison_pairs_the_two_non_baseline_gates(self):
        comparison = self.report["comparison"]
        self.assertEqual({comparison["left"], comparison["right"]},
                         {"structural", "isomorphism"})

    def test_comparison_counts_only_disagreements(self):
        comparison = self.report["comparison"]
        self.assertEqual(
            comparison["left_only"] + comparison["right_only"], comparison["discordant"]
        )
        self.assertEqual(
            comparison["discordant"] + comparison["agreed"], comparison["paired_observations"]
        )

    def test_comparison_reading_states_the_verdict_either_way(self):
        reading = self.report["comparison"]["reading"]
        self.assertTrue("chance" in reading)

    # -- charts
    def test_charts_plot_numbers_that_appear_in_a_table(self):
        skip = self.report["charts"]["skip_by_gate"]["data"]
        self.assertEqual(len(skip), len(self.report["gates"]["rows"]))
        for chart_row, table_row in zip(skip, self.report["gates"]["rows"]):
            self.assertEqual(chart_row["skip_rate"], table_row["skip_rate"])
            self.assertEqual(chart_row["missed"], table_row["missed"])

    def test_drift_series_are_ordered_and_deduplicated(self):
        for series in self.report["charts"]["drift"]["data"]:
            indices = [point["commit_index"] for point in series["points"]]
            self.assertEqual(indices, sorted(indices))
            self.assertEqual(len(indices), len(set(indices)))

    def test_labels_are_inferred_from_findings_hashes_when_absent(self):
        rows = [
            {"project": "p", "gate_strategy": "structural", "commit_index": index,
             "gate_allowed_llm": True, "findings_hash": "aaa" if index < 3 else "bbb"}
            for index in range(6)
        ]
        report = build_report(rows)
        self.assertEqual(report["inferred_labels"], 5)

    def _gate(self, name):
        return next(row for row in self.report["gates"]["rows"] if row["gate"] == name)


class RealDeviationSummaryIntegrationTests(unittest.TestCase):
    """`table_deviations()` must agree with what `evaluate_deviations.py`
    actually writes, not with a fixture that only encodes what the reading
    code *expects*.

    This is exactly the gap that let `/statistics` crash on every real run:
    `DEVIATION_SUMMARY` above was a hand-written stand-in shaped like a flat
    list of self-labelled cells, and it happened to match a bug in
    `table_deviations()` (iterating `summary["strategies"]`, a name list,
    instead of `summary["confusion"]`, the dict of matrices) rather than
    catching it. A fixture can only be as honest as the assumption it was
    written under. Running the real script and feeding its real output
    through `build_report()` has no such assumption to get wrong.
    """

    def test_build_report_accepts_real_evaluate_deviations_output(self):
        repo_root = Path(__file__).resolve().parents[2]
        script = repo_root / "research" / "evaluate_deviations.py"
        self.assertTrue(script.is_file(), f"expected {script} to exist")

        with tempfile.TemporaryDirectory() as out_dir:
            result = subprocess.run(
                [sys.executable, str(script), "--out", out_dir, "--quiet"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                result.returncode, 0,
                f"evaluate_deviations.py failed:\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
            summary_path = Path(out_dir) / "deviations_summary.json"
            self.assertTrue(summary_path.is_file())
            with open(summary_path, "r", encoding="utf-8") as handle:
                real_summary = json.load(handle)

        # The shape this test exists to pin down: an ordered name list plus a
        # matrix dict keyed by those names -- not a list of self-labelled cells.
        self.assertIsInstance(real_summary["strategies"], list)
        self.assertTrue(all(isinstance(name, str) for name in real_summary["strategies"]))
        self.assertIsInstance(real_summary["confusion"], dict)

        report = build_report(sample_rows(), deviations=real_summary)
        deviations = report["deviations"]
        self.assertTrue(deviations["available"])
        self.assertEqual(len(deviations["rows"]), len(real_summary["strategies"]))
        for row in deviations["rows"]:
            self.assertIn(row["gate"], real_summary["strategies"])


class ConsistencyTests(unittest.TestCase):
    """Cross-checks between tables. If two tables disagree, one is wrong and a
    reader cannot tell which."""

    @classmethod
    def setUpClass(cls):
        cls.rows = sample_rows()
        cls.report = build_report(cls.rows, deviations=DEVIATION_SUMMARY)

    def test_table1_run_count_equals_table2_run_counts(self):
        self.assertEqual(
            self.report["study"]["runs"],
            sum(row["runs"] for row in self.report["gates"]["rows"]),
        )

    def test_table3_runs_sum_to_the_recommended_gate_row_in_table2(self):
        gate = self.report["projects"]["gate"]
        table2 = next(r for r in self.report["gates"]["rows"] if r["gate"] == gate)
        self.assertEqual(
            table2["runs"], sum(row["runs"] for row in self.report["projects"]["rows"])
        )
        self.assertEqual(
            table2["skipped"], sum(row["skipped"] for row in self.report["projects"]["rows"])
        )

    def test_normalise_is_stable_under_repetition(self):
        first = normalise_rows(self.rows)
        second = normalise_rows(self.rows)
        self.assertEqual(first, second)


# --- exports -----------------------------------------------------------------


class ExportTests(unittest.TestCase):
    report = None

    @classmethod
    def setUpClass(cls):
        cls.report = build_report(sample_rows(), deviations=DEVIATION_SUMMARY)

    def test_bundle_has_one_csv_per_table(self):
        bundle = to_csv_bundle(self.report)
        for filename in (
            "table1-what-was-studied.csv",
            "table2-gate-performance.csv",
            "table3-per-project.csv",
            "table4-controlled-test.csv",
            "comparison-mcnemar.csv",
        ):
            self.assertIn(filename, bundle)

    def test_bundle_is_small_enough_to_read(self):
        """A reader who opens the export should not face sixteen files."""
        self.assertLessEqual(len(to_csv_bundle(self.report)), 7)

    def test_csv_parses_and_carries_the_reading(self):
        import csv
        import io

        bundle = to_csv_bundle(self.report)
        rows = list(csv.DictReader(io.StringIO(bundle["table2-gate-performance.csv"])))
        self.assertEqual(len(rows), 3)
        self.assertIn("skip_rate", rows[0])
        self.assertTrue(rows[0]["reading"])

    def test_zip_is_a_valid_archive(self):
        import io
        import zipfile

        payload = to_zip(to_csv_bundle(self.report))
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertTrue(archive.namelist())
            self.assertIsNone(archive.testzip())

    def test_latex_is_balanced(self):
        latex = to_latex(self.report)
        self.assertEqual(latex.count("\\begin{table}"), latex.count("\\end{table}"))
        self.assertEqual(latex.count("\\begin{tabular}"), latex.count("\\end{tabular}"))
        self.assertIn("tab:gates", latex)

    def test_one_latex_file_per_table(self):
        pieces = split_latex(self.report)
        for name in ("table1-study.tex", "table2-gates.tex", "table3-projects.tex",
                     "table4-deviations.tex"):
            self.assertIn(name, pieces)

    def test_latex_escapes_project_names_that_would_break_the_build(self):
        rows = sample_rows(projects=1)
        for row in rows:
            row["project"] = "my_project & co"
        pieces = split_latex(build_report(rows))
        table = pieces["table3-projects.tex"]
        self.assertIn(r"my\_project \& co", table)
        # A bare & would add a phantom column and fail the build.
        self.assertNotIn("my_project & co", table)


if __name__ == "__main__":
    unittest.main()


