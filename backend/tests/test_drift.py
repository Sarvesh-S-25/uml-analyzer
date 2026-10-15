"""Conformance drift measures, and the replay semantics they rest on."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from stats.drift import (
    build_drift_report,
    direction,
    element_survival,
    kaplan_meier,
    km_quantile,
)
from stats.report import _recovery_horizon, normalise_rows

RESEARCH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "research"))


def point(index, divergences, absences, touched=True):
    return {"commit_index": index, "divergences": divergences, "absences": absences,
            "similarity": None, "source_touched": touched, "conformance_changed": None}


class KaplanMeierTests(unittest.TestCase):
    def test_censoring_leaves_the_risk_set_after_events(self):
        # 4 at risk; one event at 3 (S=3/4), one event and one censor at 5
        # (S=3/4*2/3=1/2), one censored at 10.
        curve = kaplan_meier([(3, True), (5, False), (5, True), (10, False)])
        self.assertEqual([(t, round(s, 4)) for t, s, _ in curve], [(3, 0.75), (5, 0.5)])
        self.assertEqual(km_quantile(curve, 0.5), 5)

    def test_all_censored_has_no_median(self):
        curve = kaplan_meier([(4, False), (4, False)])
        self.assertEqual(curve, [])
        self.assertIsNone(km_quantile(curve, 0.5))


class DirectionTests(unittest.TestCase):
    def test_divergence_led(self):
        d = direction([point(0, 2, 1), point(1, 4, 1), point(2, 5, 1)])
        self.assertEqual(d["direction"], "divergence-led")
        self.assertEqual(d["net_divergence"], 3)
        self.assertEqual(d["eroding_commits"], 2)
        self.assertEqual(d["drift_per_commit"], 1.5)

    def test_absence_led(self):
        d = direction([point(0, 0, 0), point(1, 0, 3)])
        self.assertEqual(d["direction"], "absence-led")

    def test_stable_and_repair_are_distinguished(self):
        self.assertEqual(direction([point(0, 1, 1), point(1, 1, 1)])["direction"], "stable")
        d = direction([point(0, 3, 3), point(1, 1, 3)])
        self.assertEqual(d["direction"], "converging")
        self.assertEqual(d["repairing_commits"], 1)

    def test_one_commit_is_not_a_span(self):
        self.assertFalse(direction([point(0, 1, 1)])["measured"])


class ElementSurvivalTests(unittest.TestCase):
    def rows(self):
        statuses = {
            "A": ["conforming", "conforming", "divergent", "divergent"],
            "B": ["conforming", "absent", "absent", "absent"],
            "C": ["conforming"] * 4,
            "D": ["partial"] * 4,  # deviating at freeze: not at risk
        }
        return [
            {"project": "p", "commit_index": i, "element": name, "status": status}
            for name, history in statuses.items()
            for i, status in enumerate(history)
        ]

    def test_time_to_first_deviation(self):
        report = element_survival(self.rows())["p"]
        self.assertEqual(report["conforming_at_freeze"], 3)
        self.assertEqual(report["deviating_at_freeze"], 1)
        self.assertEqual(report["deviated_during_window"], 2)
        self.assertEqual(report["first_deviations"], {"B": 1, "A": 2})
        # S(1)=2/3, S(2)=1/3 -> half-life at commit 2.
        self.assertEqual(report["half_life_commits"], 2)

    def test_half_life_not_reached_is_reported_as_censored(self):
        rows = [r for r in self.rows() if r["element"] in ("A", "C")]
        rows += [dict(r, element=r["element"] + "2") for r in rows if r["element"] == "C"]
        report = element_survival(rows)["p"]
        self.assertIsNone(report["half_life_commits"])
        self.assertEqual(report["half_life_censored_beyond"], 3)

    def test_report_has_a_sentence_per_project(self):
        runs = [
            {"project": "p", "gate_strategy": "always", "commit_index": i, "gate_allowed_llm": True,
             "divergences": d, "absences": 0, "source_touched": True}
            for i, d in enumerate([0, 1, 2])
        ]
        report = build_drift_report(normalise_rows(runs), self.rows())
        self.assertTrue(report["measured"])
        self.assertIn("divergence-led", report["projects"][0]["reading"])
        self.assertEqual(report["pooled_survival"]["at_risk"], 3)


class RecoveryOnsetTests(unittest.TestCase):
    def test_a_stale_stretch_counts_once(self):
        rows = normalise_rows([
            {"project": "p", "gate_strategy": "isomorphism", "commit_index": i,
             "gate_allowed_llm": fired, "missed_change": missed, "diverges_from_oracle": diverges}
            for i, (fired, missed, diverges) in enumerate([
                (True, False, False),
                (False, True, True),   # onset
                (False, True, True),   # same stale analysis, not a new miss
                (True, False, False),  # corrected two commits after onset
            ])
        ])
        horizon = _recovery_horizon(rows)
        self.assertEqual(horizon["misses_tracked"], 1)
        self.assertEqual(horizon["median_commits"], 2.0)


def _git_available():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


try:
    if RESEARCH not in sys.path:
        sys.path.insert(0, RESEARCH)
        sys.path.insert(0, os.path.join(RESEARCH, "deviations"))
    import evaluate_deviations  # noqa: E402
    import harness  # noqa: E402
    import replay  # noqa: E402
    from mutations import MUTATIONS  # noqa: E402

    harness.preflight()  # raises nothing; returns a reason string if unusable
    REPLAY_READY = _git_available() and harness.preflight() is None
except Exception:  # pragma: no cover - depends on the install
    REPLAY_READY = False


@unittest.skipUnless(REPLAY_READY, "git or the tree-sitter grammars are unavailable")
class ReplayMissSemanticsTests(unittest.TestCase):
    """A real four-commit history through the real replay.

    0  the reference project, matching its diagram
    1  OrderRepository renamed to OrderStore everywhere: isomorphic, so the
       isomorphism gate reuses an analysis written for the old findings
    2  a comment: no gate but `content` re-analyses; isomorphism is still
       serving the stale analysis
    3  a new undocumented class: every structural gate re-analyses, and the
       isomorphism gate's served analysis is current again
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="replay-semantics-")
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(self.repo)

        def git(*args):
            subprocess.run(["git", "-C", self.repo, *args], capture_output=True, check=True)

        git("init", "--quiet")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        by_id = {m.id: m for m in MUTATIONS}
        evaluate_deviations.stage_base(self.repo)
        steps = [None, "rename-class-consistently", "comment-only", "add-undocumented-class"]
        for step in steps:
            if step:
                by_id[step].apply(self.repo)
            git("add", "-A")
            git("commit", "--quiet", "--allow-empty", "-m", step or "base")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_misses_are_stale_analyses_not_stale_findings(self):
        spec = harness.ProjectSpec(name="semantics", source=self.repo,
                                   uml=evaluate_deviations.UML_PATH, commits=10)
        sandbox = harness.Sandbox.create(os.path.join(self.root, "sandbox"))
        outcome = replay.replay_project(
            spec, ["structural", "isomorphism"], sandbox, os.path.join(self.root, "cache"),
            lambda *_: None,
        )
        by = {(r["gate_strategy"], r["commit_index"]): r for r in outcome["rows"]}

        # The structural gate re-analyses the rename and never serves stale.
        self.assertFalse(any(by[("structural", i)]["missed_change"] for i in range(4)))
        # The isomorphism gate's designed-in false negative, then its persistence.
        self.assertTrue(by[("isomorphism", 1)]["missed_change"])
        self.assertTrue(by[("isomorphism", 2)]["missed_change"])
        self.assertFalse(by[("isomorphism", 3)]["diverges_from_oracle"])
        # Commit-level facts are the same whichever gate's row is read.
        self.assertTrue(by[("structural", 1)]["conformance_changed"])
        self.assertFalse(by[("structural", 2)]["conformance_changed"])
        self.assertTrue(by[("structural", 2)]["source_touched"])
        # Counterfactual cost is recorded only when a gate would have called.
        self.assertGreater(by[("structural", 1)]["counterfactual_prompt_tokens"], 0)
        self.assertEqual(by[("isomorphism", 1)]["counterfactual_prompt_tokens"], 0)
        # Element-level drift: OrderRepository conforms at the freeze (its
        # undocumented __init__ is not a divergence) and is absent from commit 1.
        statuses = {(r["commit_index"], r["element"]): r["status"] for r in outcome["drift_rows"]}
        self.assertEqual(statuses[(0, "OrderRepository")], "conforming")
        self.assertEqual(statuses[(1, "OrderRepository")], "absent")


if __name__ == "__main__":
    unittest.main()
