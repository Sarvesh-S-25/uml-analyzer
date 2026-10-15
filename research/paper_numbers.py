"""Print every corpus number the paper quotes, as Markdown, from results/.

    python research/paper_numbers.py --results results/

Reads statistics.json and drift.json (written by analyze_statistics.py) and
runs.csv, so the manuscript never carries a number typed by hand.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from stats.core import wilson_interval  # noqa: E402


def pct(x, places=1):
    return "—" if x is None else f"{x * 100:.{places}f}%"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results")
    args = parser.parse_args(argv)
    r = args.results
    stats = json.load(open(os.path.join(r, "statistics.json"), encoding="utf-8"))
    drift = json.load(open(os.path.join(r, "drift.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(r, "runs.csv"), encoding="utf-8")))

    commits = {(x["project"], x["commit_index"]) for x in rows}
    oracle = {}
    for x in rows:
        oracle.setdefault((x["project"], int(x["commit_index"])), x)
    print("## Corpus totals")
    print(f"- commits: {len(commits)}; runs: {len(rows)}")
    for project in sorted({p for p, _ in commits}):
        pts = [v for (p, _), v in oracle.items() if p == project]
        n = len(pts)
        touched = sum(1 for v in pts if v["source_touched"] == "True")
        changed = sum(1 for v in pts if v["conformance_changed"] == "True")
        print(f"- {project}: {n} commits; touched source {touched}/{n-1}; changed conformance {changed}/{n-1}")
    allp = list(oracle.values())
    judged = [v for v in allp if v["conformance_changed"] in ("True", "False")]
    ch = sum(1 for v in judged if v["conformance_changed"] == "True")
    tch = sum(1 for v in judged if v["source_touched"] == "True")
    lo, hi = wilson_interval(ch, len(judged))
    print(f"- pooled: {ch}/{len(judged)} commits changed conformance ({pct(ch/len(judged))}, CI {pct(lo)}–{pct(hi)}); "
          f"{tch}/{len(judged)} touched source; changed among touching: {ch}/{tch}")

    print("\n## Gate table (pooled)")
    print("| Gate | Runs | Re-analysed | Skip rate [95% CI] | Recall [95% CI] (n) | Specificity [95% CI] (n) | Stale runs | Counterfactual tokens | Saved vs always |")
    print("|---|---|---|---|---|---|---|---|---|")
    for g in stats["gates"]["rows"]:
        rec = "not measured" if g["recall"] is None else f"{pct(g['recall'])} [{pct(g['recall_low'])}–{pct(g['recall_high'])}] ({g['changed_checked']})"
        spe = "not measured" if g["specificity"] is None else f"{pct(g['specificity'])} [{pct(g['specificity_low'])}–{pct(g['specificity_high'])}] ({g['unchanged_checked']})"
        print(f"| {g['gate']} | {g['runs']} | {g['reanalysed']} | {pct(g['skip_rate'])} [{pct(g['skip_low'])}–{pct(g['skip_high'])}] | {rec} | {spe} | "
              f"{g['missed']} ({pct(g['miss_rate'])}) | {g['counterfactual_tokens']:,} | {pct(g['counterfactual_percent_saved']) if g['counterfactual_percent_saved'] is not None else '—'} |")
    for g in stats["gates"]["rows"]:
        h = g["recovery"]
        print(f"- recovery {g['gate']}: {json.dumps({k: h.get(k) for k in ('misses_tracked','resolved_count','censored_count','median_commits','censored_beyond','max_resolved')})}")
    print("\n- recommended:", stats["gates"]["recommended"].get("reading", stats["gates"]["recommended"]))
    print("- comparison:", json.dumps(stats.get("comparison"), default=str)[:900])

    print("\n## Per-project, per-gate")
    print("| Project | Gate | Commits | Skip rate | Re-analysed | Stale runs | Counterfactual tokens |")
    print("|---|---|---|---|---|---|---|")
    for project in sorted({x["project"] for x in rows}):
        base = sum(int(x["counterfactual_prompt_tokens"] or 0) for x in rows if x["project"] == project and x["gate_strategy"] == "always")
        for gate in ("always", "content", "structural", "isomorphism"):
            sub = [x for x in rows if x["project"] == project and x["gate_strategy"] == gate]
            if not sub:
                continue
            re = sum(1 for x in sub if x["gate_allowed_llm"] == "True")
            stale = sum(1 for x in sub if x["missed_change"] == "True")
            cf = sum(int(x["counterfactual_prompt_tokens"] or 0) for x in sub)
            saved = f" ({pct(1 - cf / base)} saved)" if base and gate != "always" else ""
            print(f"| {project} | {gate} | {len(sub)} | {pct(1 - re / len(sub))} | {re} | {stale} | {cf:,}{saved} |")

    print("\n## Drift")
    for p in drift["projects"]:
        print("-", json.dumps({k: p.get(k) for k in ("project", "commits", "divergences_start", "divergences_end", "absences_start", "absences_end", "net_divergence", "net_absence", "drift_per_commit", "drift_per_touching_commit", "eroding_commits", "repairing_commits", "conformance_changing_commits", "source_touching_commits", "similarity_start", "similarity_end", "similarity_min", "direction")}))
    print("\n## Survival")
    for project, s in drift["survival"].items():
        print("-", project, json.dumps({k: s[k] for k in ("designed_elements", "conforming_at_freeze", "deviating_at_freeze", "deviated_during_window", "survival_at_end", "half_life_commits", "half_life_censored_beyond", "first_deviations")}))
        print("  curve:", s["curve"][:12])
    print("- pooled:", drift["pooled_survival"])


if __name__ == "__main__":
    main()
