"""Print every number the paper quotes from the live-model runs, as Markdown.

    python research/live_numbers.py --live results/live

Reads deviations-live.csv (live_deviations.py), deviations-live-repeat.csv
(the repeat run), the llm-cache records, and every runs-<project>.csv written
by live_llm.py. Nothing is typed by hand.
"""
import argparse
import csv
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from stats.core import wilson_interval  # noqa: E402

GATES = ("always", "content", "structural", "isomorphism")


def quartiles(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    if len(values) == 1:
        return values[0], values[0], values[0]
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], statistics.median(values), q[2]


def fmt_q(q, unit="", places=0):
    if q is None:
        return "not measured"
    lo, med, hi = q
    return f"{med:,.{places}f}{unit} [{lo:,.{places}f}–{hi:,.{places}f}]"


def as_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def seeded(live):
    path = os.path.join(live, "deviations-live.csv")
    if not os.path.exists(path):
        return
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    print("## Seeded deviations, live model")
    print("| Gate | Real calls | Prompt tokens (Ollama) | Completion tokens | Model time, s | Changed-element coverage (10 changing) | Fully named | Ungrounded mentions |")
    print("|---|---|---|---|---|---|---|---|")
    base = None
    for gate in GATES:
        sub = [r for r in rows if r["strategy"] == gate]
        called = [r for r in sub if r["llm_status"] == "called"]
        tok = sum(int(r["ollama_prompt_tokens"] or 0) for r in called)
        comp = sum(int(r["ollama_completion_tokens"] or 0) for r in called)
        secs = sum(as_float(r["llm_wall_s"]) or 0 for r in called)
        if gate == "always":
            base = tok
        changing = [r for r in sub if r["findings_changed"] == "True" and r["changed_coverage"] not in ("", None)]
        cov = [float(r["changed_coverage"]) for r in changing]
        full = sum(1 for c in cov if c == 1.0)
        saved = f" (−{(1 - tok / base) * 100:.0f}%)" if base and gate != "always" else ""
        print(f"| {gate} | {len(called)} | {tok:,}{saved} | {comp:,} | {secs:,.0f} | "
              f"{(sum(cov) / len(cov)) if cov else float('nan'):.2f} (n={len(cov)}) | {full}/{len(cov)} | "
              f"{sum(int(r['ungrounded']) for r in sub)} |")
    print("\nPer mutation (coverage of the changed elements by the served explanation):")
    print("| Mutation | Changes findings | always | content | structural | isomorphism |")
    print("|---|---|---|---|---|---|")
    for m in dict.fromkeys(r["mutation"] for r in rows):
        cells = []
        for gate in GATES:
            r = next(x for x in rows if x["mutation"] == m and x["strategy"] == gate)
            mark = "" if r["gate_fired"] == "True" else " (reused)"
            cells.append(("—" if r["changed_coverage"] in ("", None) else f"{float(r['changed_coverage']):.2f}") + mark)
        changed = next(x for x in rows if x["mutation"] == m)["findings_changed"]
        print(f"| {m} | {changed} | " + " | ".join(cells) + " |")

    full_rows = [r for r in rows if r["strategy"] == "always" and r["llm_status"] == "called"]
    scoped_rows = [r for r in rows if r["strategy"] == "structural" and r["llm_status"] == "called"
                   and r["gate_fired"] == "True"]
    for label, group in (("full-project (always)", full_rows), ("scoped (structural)", scoped_rows)):
        print(f"- {label}: prompt tokens {fmt_q(quartiles([as_float(r['ollama_prompt_tokens']) for r in group]))}; "
              f"model time {fmt_q(quartiles([as_float(r['llm_wall_s']) for r in group]), ' s', 1)}; "
              f"prompt eval {fmt_q(quartiles([as_float(r['prompt_eval_s']) for r in group]), ' s', 1)}; "
              f"generation {fmt_q(quartiles([as_float(r['eval_s']) for r in group]), ' s', 1)}")


def repeat(live):
    cache = os.path.join(live, "llm-cache")
    pairs = []
    for rpath in glob.glob(os.path.join(cache, "*-r.json")):
        opath = rpath[: -len("-r.json")] + ".json"
        if not os.path.exists(opath):
            continue
        a, b = (json.load(open(p, encoding="utf-8")) for p in (opath, rpath))

        def gaps(x):
            try:
                return json.loads(x["content"]).get("gaps")
            except Exception:
                return None
        pairs.append((a.get("content") == b.get("content"), gaps(a) == gaps(b), a.get("wall_s"), b.get("wall_s")))
    if not pairs:
        return
    print("\n## Repeatability (same prompt sent twice, cache bypassed)")
    print(f"- pairs: {len(pairs)}; byte-identical answers: {sum(p[0] for p in pairs)}; identical gap lists: {sum(p[1] for p in pairs)}")
    ratio = [b / a for _, _, a, b in pairs if a and b]
    print(f"- second-call time / first-call time: median {statistics.median(ratio):.2f} (range {min(ratio):.2f}–{max(ratio):.2f})")
    path = os.path.join(live, "deviations-live-repeat.csv")
    if os.path.exists(path):
        original = {(r["mutation"], r["strategy"]): r for r in csv.DictReader(open(os.path.join(live, "deviations-live.csv"), encoding="utf-8"))}
        rep = list(csv.DictReader(open(path, encoding="utf-8")))
        same = sum(1 for r in rep if (r["changed_coverage"], r["ungrounded"]) ==
                   (original[(r["mutation"], r["strategy"])]["changed_coverage"], original[(r["mutation"], r["strategy"])]["ungrounded"]))
        print(f"- scored rows with identical coverage and ungrounded counts: {same}/{len(rep)}")


def calibration(live):
    """Counterfactual (cl100k) estimate against what Ollama actually evaluated."""
    records = [json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(live, "llm-cache", "*.json"))
               if not p.endswith("-r.json")]
    pairs = [(r["est_prompt_tokens"], r["prompt_eval_count"]) for r in records
             if r.get("ok") and r.get("est_prompt_tokens") and r.get("prompt_eval_count")]
    if not pairs:
        return
    ratios = [o / e for e, o in pairs]
    print("\n## Counterfactual estimate vs measured prompt tokens")
    print(f"- calls: {len(pairs)}; Ollama tokens / cl100k estimate: median {statistics.median(ratios):.3f} "
          f"(IQR {statistics.quantiles(ratios, n=4)[0]:.3f}–{statistics.quantiles(ratios, n=4)[2]:.3f}; range {min(ratios):.3f}–{max(ratios):.3f})")
    print(f"- truncated by Ollama: {sum(1 for r in records if r.get('truncated'))}; bad JSON answers: see runs")
    tps = [r["prompt_eval_count"] / r["prompt_eval_s"] for r in records if r.get("ok") and r.get("prompt_eval_s")]
    gps = [r["eval_count"] / r["eval_s"] for r in records if r.get("ok") and r.get("eval_s")]
    print(f"- throughput: prompt {statistics.median(tps):,.0f} tok/s, generation {statistics.median(gps):,.1f} tok/s (medians)")


def corpus(live):
    paths = sorted(glob.glob(os.path.join(live, "runs-*.csv")))
    if not paths:
        return
    print("\n## Live corpus replay")
    print("| Project | Gate | Runs | Gate fired | Sent | Fits? no_fit | Not sampled | Bad JSON | Prompt tokens (Ollama) | Model time, s | Counterfactual tokens |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    totals = {g: dict(runs=0, fired=0, sent=0, nofit=0, ns=0, bad=0, tok=0, secs=0.0, cf=0) for g in GATES}
    allrows = []
    for path in paths:
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        allrows += rows
        project = rows[0]["project"] if rows else os.path.basename(path)
        for gate in GATES:
            sub = [r for r in rows if r["gate_strategy"] == gate]
            if not sub:
                continue
            fired = [r for r in sub if r["gate_allowed_llm"] == "True"]
            sent = [r for r in fired if r["llm_status"] in ("called", "bad_json")]
            t = dict(runs=len(sub), fired=len(fired), sent=len(sent),
                     nofit=sum(r["llm_status"] == "no_fit" for r in fired),
                     ns=sum(r["llm_status"] == "not_sampled" for r in fired),
                     bad=sum(r["llm_status"] == "bad_json" for r in fired),
                     tok=sum(int(r["ollama_prompt_tokens"] or 0) for r in sent),
                     secs=sum(as_float(r["llm_wall_s"]) or 0 for r in sent),
                     cf=sum(int(r["counterfactual_prompt_tokens"] or 0) for r in sub))
            for k, v in t.items():
                totals[gate][k] += v
            print(f"| {project} | {gate} | {t['runs']} | {t['fired']} | {t['sent']} | {t['nofit']} | {t['ns']} | {t['bad']} | "
                  f"{t['tok']:,} | {t['secs']:,.0f} | {t['cf']:,} |")
    for gate in GATES:
        t = totals[gate]
        print(f"| **all** | {gate} | {t['runs']} | {t['fired']} | {t['sent']} | {t['nofit']} | {t['ns']} | {t['bad']} | "
              f"{t['tok']:,} | {t['secs']:,.0f} | {t['cf']:,} |")
    # Fit: of all gate-fired prompts, how many fit the window, by scoping.
    fired = [r for r in allrows if r["gate_allowed_llm"] == "True" and r["llm_status"] in ("called", "bad_json", "no_fit")]
    for gate in GATES:
        sub = [r for r in fired if r["gate_strategy"] == gate]
        if sub:
            ok = sum(r["llm_status"] != "no_fit" for r in sub)
            lo, hi = wilson_interval(ok, len(sub))
            print(f"- {gate}: {ok}/{len(sub)} fired prompts fit the window ({ok / len(sub) * 100:.0f}%, CI {lo * 100:.0f}–{hi * 100:.0f}%)")
    # Explanation coverage at commits whose findings changed.
    print("\nServed-explanation coverage at commits where the deterministic findings changed:")
    for gate in GATES:
        sub = [r for r in allrows if r["gate_strategy"] == gate and r["conformance_changed"] == "True" and r["changed_coverage"] not in ("", None)]
        cov = [float(r["changed_coverage"]) for r in sub]
        print(f"- {gate}: n={len(cov)}; mean {sum(cov) / len(cov):.2f}" if cov else f"- {gate}: not measured")
    for gate in GATES:
        sub = [r for r in allrows if r["gate_strategy"] == gate and r["llm_status"] in ("called",)]
        print(f"- {gate}: ungrounded mentions per sent call: "
              f"{(sum(int(r['ungrounded_mentions']) for r in sub) / len(sub)) if sub else float('nan'):.2f} (n={len(sub)})")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--live", default="results/live")
    args = p.parse_args(argv)
    seeded(args.live)
    repeat(args.live)
    calibration(args.live)
    corpus(args.live)


if __name__ == "__main__":
    main()
