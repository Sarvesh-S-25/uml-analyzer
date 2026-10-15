"""Merge replay outputs produced by several processes into one results directory.

A long replay can be split across processes -- one per gate, say -- because
every gate's run carries its own copy of the oracle. Merging is a concatenation,
but only after checking that the copies agree: the oracle is deterministic, so
two processes that disagree about whether conformance changed at a commit mean
something is wrong with the run, not with the gates.

    python research/merge_results.py --out results/ results/corpus-a/always \
        results/corpus-a/content results/corpus-a/structural results/corpus-a/isomorphism \
        results/corpus-b
"""
import argparse
import csv
import os
import sys
from typing import Dict, List, Tuple

ORACLE_COLUMNS = ("conformance_changed", "source_touched", "convergences", "divergences",
                  "absences", "findings_hash", "similarity_score")


def read(path: str) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write(path: str, rows: List[Dict[str, str]]) -> None:
    if not rows:
        return
    columns: List[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("parts", nargs="+", help="Directories each holding a runs.csv")
    args = parser.parse_args(argv)

    runs: List[Dict[str, str]] = []
    elements: List[Dict[str, str]] = []
    seen_elements = set()
    oracle: Dict[Tuple[str, str], Dict[str, str]] = {}
    seen_runs = set()
    disagreements = 0

    for part in args.parts:
        for row in read(os.path.join(part, "runs.csv")):
            key = (row["project"], row["gate_strategy"], row["commit_index"])
            if key in seen_runs:
                print(f"duplicate run {key} in {part}", file=sys.stderr)
                return 1
            seen_runs.add(key)
            commit_key = (row["project"], row["commit_index"])
            facts = {column: row.get(column, "") for column in ORACLE_COLUMNS}
            if commit_key in oracle and oracle[commit_key] != facts:
                disagreements += 1
                if disagreements <= 5:
                    print(f"oracle copies disagree at {commit_key}: {oracle[commit_key]} vs {facts}",
                          file=sys.stderr)
            oracle.setdefault(commit_key, facts)
            runs.append(row)

        element_path = os.path.join(part, "drift_elements.csv")
        if os.path.isfile(element_path):
            for row in read(element_path):
                key = (row["project"], row["commit_index"], row["element"])
                if key not in seen_elements:
                    seen_elements.add(key)
                    elements.append(row)

    if disagreements:
        print(f"{disagreements} commit(s) where oracle copies disagree; not merging.", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)
    runs.sort(key=lambda r: (r["project"], int(r["commit_index"]), r["gate_strategy"]))
    write(os.path.join(args.out, "runs.csv"), runs)
    write(os.path.join(args.out, "drift_elements.csv"), elements)
    projects = sorted({r["project"] for r in runs})
    print(f"Merged {len(runs)} runs over {len(oracle)} commits in {len(projects)} project(s); "
          f"every oracle copy agreed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
