"""Which gate re-analyses would fit a local model's context window (RQ4).

The offline replay records, for every run where a gate fired, the size of the
prompt it would have sent (cl100k tokens). The live runs measured how those
counts relate to what the local model's tokenizer evaluates (the median
Ollama/cl100k ratio, passed as --ratio). This script applies that ratio and
reports, per gate, the share of fired prompts that fit the sending threshold
(--fit-margin x --num-ctx), pooled and per project.

    python research/fit_numbers.py --runs results/corpus-v2-merged/runs.csv --ratio 1.051
"""
import argparse
import csv
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from stats.core import wilson_interval  # noqa: E402

GATES = ("always", "content", "structural", "isomorphism")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", required=True)
    p.add_argument("--ratio", type=float, required=True)
    p.add_argument("--num-ctx", type=int, default=32768)
    p.add_argument("--fit-margin", type=float, default=0.85)
    args = p.parse_args(argv)
    limit = args.num_ctx * args.fit_margin
    rows = [r for r in csv.DictReader(open(args.runs, encoding="utf-8")) if r["gate_allowed_llm"] == "True"]

    print(f"## Fit to a {args.num_ctx:,}-token window (send threshold {limit:,.0f} model tokens, ratio {args.ratio})")
    print("| Gate | Fired prompts | Fit | Share [95% CI] | Median size (model tokens) | 90th percentile |")
    print("|---|---|---|---|---|---|")
    for gate in GATES:
        sizes = [int(r["counterfactual_prompt_tokens"] or 0) * args.ratio for r in rows if r["gate_strategy"] == gate]
        if not sizes:
            continue
        fit = sum(1 for s in sizes if s <= limit)
        lo, hi = wilson_interval(fit, len(sizes))
        q = statistics.quantiles(sizes, n=10) if len(sizes) > 1 else [sizes[0]] * 9
        print(f"| {gate} | {len(sizes)} | {fit} | {fit / len(sizes) * 100:.0f}% [{lo * 100:.0f}–{hi * 100:.0f}] | "
              f"{statistics.median(sizes):,.0f} | {q[8]:,.0f} |")

    per = defaultdict(lambda: defaultdict(list))
    for r in rows:
        per[r["project"]][r["gate_strategy"]].append(int(r["counterfactual_prompt_tokens"] or 0) * args.ratio)
    always_never = [p for p, g in per.items() if g["always"] and all(s > limit for s in g["always"])]
    always_all = [p for p, g in per.items() if g["always"] and all(s <= limit for s in g["always"])]
    struct_all = [p for p, g in per.items() if g["structural"] and all(s <= limit for s in g["structural"])]
    print(f"\n- projects: {len(per)}")
    print(f"- projects whose full-project prompt never fits: {len(always_never)}")
    print(f"- projects whose full-project prompt always fits: {len(always_all)}")
    print(f"- projects where every structural re-analysis fits: {len(struct_all)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
