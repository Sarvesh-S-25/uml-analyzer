"""Generate a synthetic run ledger, so the statistics pipeline can be exercised
before a real corpus exists.

This exists for smoke-testing the report, the exports and the page. **Numbers
produced from it are not results** — the generator knows the label it is drawing
from, so any model fitted to this data will look better than it can be. Real
figures come from `research/replay.py`.

    python backend/tools/make_synthetic_runs.py --out /tmp/runs.csv --projects 4
"""
import argparse
import csv
import hashlib
import os
import random
import sys

GATES = ["always", "content", "structural", "isomorphism"]
FIELDS = [
    "project", "commit", "commit_index", "gate_strategy", "gate_allowed_llm", "llm_invoked",
    "missed_change", "conformance_changed", "prompt_tokens", "completion_tokens", "latency_ms",
    "changed_nodes", "added_nodes", "removed_nodes", "impact_nodes", "files_scanned",
    "ambiguous_call_sites", "call_resolution_rate", "similarity_score", "findings_hash",
    "convergences", "divergences", "absences",
    "model", "provider", "llm_mode", "temperature", "seed", "association_scoring",
]


def build(projects: int, commits: int, seed: int):
    rng = random.Random(seed)
    rows = []
    for p in range(projects):
        project = f"project-{chr(ord('a') + p)}"
        # Projects differ deliberately: churn and size vary, so the per-project
        # tables and the heterogeneity test have something real to detect.
        churn = 0.8 + 0.9 * p
        files = 40 + 35 * p
        divergences, absences, convergences = 0, rng.randint(1, 3), 8 + 2 * p

        for c in range(commits):
            commit = hashlib.sha1(f"{project}-{c}".encode()).hexdigest()[:10]
            changed = max(0, int(rng.expovariate(1 / churn)))
            added = rng.randint(0, 1) if changed else 0
            removed = rng.randint(0, 1) if changed > 1 else 0
            # File count drifts across the history. A constant predictor makes
            # the OLS refuse, which would hide the cost model from anyone
            # smoke-testing with a single project.
            scanned = files + c // 4 + rng.randint(0, 2)
            impact = changed + added + removed + (rng.randint(0, 2) if changed else 0)
            structural = changed > 0 or added or removed
            renamed_only = structural and rng.random() < 0.18
            # A rename can still break conformance when the diagram names the
            # class -- rarely, but not never. Making it impossible would hand
            # the isomorphism gate a zero miss rate by construction, which is
            # exactly the flattering artefact this generator must not produce.
            truth = structural and rng.random() < (0.12 if renamed_only else 0.42)

            if truth:
                divergences += rng.randint(0, 1)
                if rng.random() < 0.2:
                    absences += 1
                convergences = max(0, convergences - (1 if rng.random() < 0.15 else 0))

            for gate in GATES:
                if gate == "always":
                    fired = True
                elif gate == "content":
                    fired = structural or rng.random() < 0.35
                elif gate == "structural":
                    fired = structural
                else:
                    fired = structural and not renamed_only

                tokens = int(900 + 130 * impact + rng.gauss(0, 90)) if fired else 0
                rows.append({
                    "project": project,
                    "commit": commit,
                    "commit_index": c,
                    "gate_strategy": gate,
                    "gate_allowed_llm": fired,
                    "llm_invoked": fired,
                    "missed_change": bool(truth and not fired),
                    "conformance_changed": truth,
                    "prompt_tokens": int(tokens * 0.82),
                    "completion_tokens": tokens - int(tokens * 0.82),
                    "latency_ms": int(160 + 22 * impact + rng.gauss(0, 40)) if fired else 12,
                    "changed_nodes": changed,
                    "added_nodes": added,
                    "removed_nodes": removed,
                    "impact_nodes": impact,
                    "files_scanned": scanned,
                    "ambiguous_call_sites": rng.randint(0, 6),
                    "call_resolution_rate": round(0.86 + rng.uniform(-0.06, 0.08), 3),
                    "similarity_score": round(
                        max(0.0, min(1.0, 0.88 - 0.012 * divergences + rng.gauss(0, 0.02))), 3
                    ),
                    "findings_hash": hashlib.sha1(
                        f"{project}{gate}{divergences}{absences}".encode()
                    ).hexdigest()[:16],
                    "convergences": convergences,
                    "divergences": divergences,
                    "absences": absences,
                    "model": "gpt-4o-2024-08-06",
                    "provider": "openai",
                    "llm_mode": "auto",
                    "temperature": 0,
                    "seed": 20260815,
                    "association_scoring": False,
                })
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="synthetic-runs.csv")
    parser.add_argument("--projects", type=int, default=4)
    parser.add_argument("--commits", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260819)
    args = parser.parse_args(argv)

    rows = build(args.projects, args.commits, args.seed)
    directory = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(directory, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} synthetic runs to {args.out}")
    print("These are NOT results. Use research/replay.py for anything you publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
