"""Run the seeded-deviation set through every gate and report a confusion matrix.

For each mutation and each gate strategy:

1. analyse the pristine reference project (establishing a baseline version),
2. apply the mutation,
3. analyse again and record whether the gate re-analysed,
4. independently force a full analysis and compare deterministic findings.

That yields two labelled outcomes per cell -- did the gate fire when it should,
and did the findings move when they should -- and therefore a confusion matrix
per gate over a set with known ground truth, which a naturalistic commit corpus
cannot provide.

Usage
-----
    python research/evaluate_deviations.py
    python research/evaluate_deviations.py --out results/ --strategies structural,isomorphism
    python research/evaluate_deviations.py --git-branches ./deviation-repo
"""
import argparse
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from harness import (  # noqa: E402
    GATE_STRATEGIES,
    Sandbox,
    copy_source,
    finding_signature,
    install_uml,
    preflight,
    signatures_differ,
    write_csv,
    write_json,
)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "deviations"))
from mutations import MUTATIONS, Mutation, branch_name  # noqa: E402

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deviations", "base")
UML_PATH = os.path.join(BASE_DIR, "design.mdj")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default="results", help="Output directory (default ./results).")
    parser.add_argument(
        "--strategies", default=",".join(GATE_STRATEGIES), help="Gates to evaluate."
    )
    parser.add_argument(
        "--git-branches",
        metavar="DIR",
        help="Also materialise the set as a git repository with one branch per mutation.",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


PRESERVE = {".git"}


def stage_base(destination: str) -> None:
    """Reset a tree to the pristine reference project.

    Entries in PRESERVE survive, so the same function can reset a plain scratch
    directory and a git working tree without destroying the repository.
    """
    os.makedirs(destination, exist_ok=True)
    for entry in os.listdir(destination):
        if entry in PRESERVE:
            continue
        target = os.path.join(destination, entry)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        else:
            os.remove(target)

    for entry in sorted(os.listdir(BASE_DIR)):
        if entry == "design.mdj":
            continue
        source = os.path.join(BASE_DIR, entry)
        target = os.path.join(destination, entry)
        if os.path.isdir(source):
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def evaluate(mutation: Mutation, strategies: List[str], sandbox: Sandbox, log) -> List[Dict[str, Any]]:
    from core.pipeline import run_analysis

    rows: List[Dict[str, Any]] = []
    tree = os.path.join(sandbox.root, f"__tree__{mutation.id}")

    # Ground truth: what a full analysis says before and after the mutation.
    oracle_project = sandbox.reset(f"oracle--{mutation.id}")
    install_uml(oracle_project, UML_PATH)

    stage_base(tree)
    copy_source(tree, oracle_project)
    before = finding_signature(run_analysis(oracle_project, gate_strategy="always", force=True))

    mutation.apply(tree)
    copy_source(tree, oracle_project)
    after_result = run_analysis(oracle_project, gate_strategy="always", force=True)
    after = finding_signature(after_result)

    findings_changed = bool(signatures_differ(before, after))
    changed_fields = signatures_differ(before, after)

    for strategy in strategies:
        project = sandbox.reset(f"{mutation.id}--{strategy}")
        install_uml(project, UML_PATH)

        stage_base(tree)
        copy_source(tree, project)
        run_analysis(project, gate_strategy=strategy)  # baseline version

        mutation.apply(tree)
        copy_source(tree, project)
        result = run_analysis(project, gate_strategy=strategy)

        gate_fired = bool(result["gate"]["should_invoke_llm"])

        rows.append(
            {
                "mutation": mutation.id,
                "category": mutation.category,
                "strategy": strategy,
                "expect_structural_change": mutation.expect_structural_change,
                "expect_conformance_change": mutation.expect_conformance_change,
                "gate_fired": gate_fired,
                "findings_changed": findings_changed,
                "changed_fields": ";".join(changed_fields),
                "gate_correct_on_structure": gate_fired == mutation.expect_structural_change,
                # The consequential error: the findings moved and the gate reused
                # the stale ones anyway.
                "missed_change": findings_changed and not gate_fired,
                # The wasteful error: nothing that matters moved, but we paid.
                "wasted_reanalysis": (not findings_changed) and gate_fired,
                "isomorphic": result["gate"]["isomorphic"],
                "reason": result["gate"]["reason"],
                "impact_nodes": result["gate"]["impact_node_count"],
                "similarity_before": before.get("similarity_score_rule_based"),
                "similarity_after": after.get("similarity_score_rule_based"),
            }
        )

    log(
        f"  {mutation.id:<28} findings_changed={str(findings_changed):<5} "
        + " ".join(
            f"{row['strategy'][:4]}={'fire' if row['gate_fired'] else 'reuse'}" for row in rows
        )
    )
    return rows


def confusion(rows: List[Dict[str, Any]], strategies: List[str]) -> Dict[str, Any]:
    """Per gate: does it fire exactly when the findings actually move?"""
    matrix: Dict[str, Any] = {}
    for strategy in strategies:
        subset = [row for row in rows if row["strategy"] == strategy]
        true_positive = sum(1 for r in subset if r["findings_changed"] and r["gate_fired"])
        false_negative = sum(1 for r in subset if r["findings_changed"] and not r["gate_fired"])
        false_positive = sum(1 for r in subset if not r["findings_changed"] and r["gate_fired"])
        true_negative = sum(1 for r in subset if not r["findings_changed"] and not r["gate_fired"])

        precision = (
            true_positive / (true_positive + false_positive)
            if (true_positive + false_positive)
            else None
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if (true_positive + false_negative)
            else None
        )
        matrix[strategy] = {
            "true_positive": true_positive,
            "false_negative": false_negative,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "missed": [r["mutation"] for r in subset if r["missed_change"]],
            "wasted": [r["mutation"] for r in subset if r["wasted_reanalysis"]],
        }
    return matrix


def make_git_branches(destination: str, log) -> Dict[str, Any]:
    """Materialise the set as a git repository: main plus one branch per mutation.

    Programmatic mutation is the reproducible source of truth; the branches are
    for inspecting a deviation by eye, or replaying it through any other tool.
    """
    os.makedirs(destination, exist_ok=True)

    def git(*args: str) -> None:
        result = subprocess.run(
            ["git", "-C", destination, *args], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")

    if not os.path.isdir(os.path.join(destination, ".git")):
        git("init", "--quiet", "--initial-branch=main")
        git("config", "user.email", "research@example.invalid")
        git("config", "user.name", "Deviation Harness")

    stage_base(destination)
    shutil.copy2(UML_PATH, os.path.join(destination, "design.mdj"))
    git("add", "-A")
    git("commit", "--quiet", "-m", "Reference project matching design.mdj", "--allow-empty")

    created = []
    for mutation in MUTATIONS:
        branch = branch_name(mutation)
        git("checkout", "--quiet", "main")
        git("checkout", "--quiet", "-B", branch)
        stage_base(destination)
        shutil.copy2(UML_PATH, os.path.join(destination, "design.mdj"))
        mutation.apply(destination)
        git("add", "-A")
        git("commit", "--quiet", "-m", f"{mutation.id}: {mutation.description}", "--allow-empty")
        created.append(branch)
        log(f"  branch {branch}")

    git("checkout", "--quiet", "main")
    return {"repository": os.path.abspath(destination), "branches": created}


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    def log(message: str):
        if not args.quiet:
            print(message, flush=True)

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = [s for s in strategies if s not in GATE_STRATEGIES]
    if unknown:
        print(f"Unknown strategies: {', '.join(unknown)}", file=sys.stderr)
        return 2

    if args.git_branches and not os.path.isdir(BASE_DIR):
        print(f"Reference project not found at {BASE_DIR}", file=sys.stderr)
        return 2

    blocker = preflight()
    if blocker:
        if args.git_branches:
            # Materialising branches needs no parser, so that half can still run.
            log(f"Note: {blocker.splitlines()[0]}")
            log("Skipping the evaluation; materialising git branches only.")
            report = make_git_branches(args.git_branches, log)
            write_json(os.path.join(args.out, "deviation_branches.json"), report)
            return 0
        print(blocker, file=sys.stderr)
        return 2

    log(f"Evaluating {len(MUTATIONS)} mutations across {len(strategies)} gate(s).")

    sandbox = Sandbox.create()
    rows: List[Dict[str, Any]] = []
    try:
        for mutation in MUTATIONS:
            try:
                rows.extend(evaluate(mutation, strategies, sandbox, log))
            except AssertionError as exc:
                log(f"  {mutation.id}: SKIPPED ({exc})")
    finally:
        sandbox.cleanup()

    matrix = confusion(rows, strategies)
    write_csv(os.path.join(args.out, "deviations.csv"), rows)
    write_json(
        os.path.join(args.out, "deviations_summary.json"),
        {
            "mutations": len(MUTATIONS),
            "strategies": strategies,
            "confusion": matrix,
            "rows": rows,
        },
    )

    log("")
    log(f"{'strategy':<14}{'TP':>5}{'FN':>5}{'FP':>5}{'TN':>5}{'precision':>11}{'recall':>9}")
    for strategy in strategies:
        cell = matrix[strategy]
        precision = "n/a" if cell["precision"] is None else f"{cell['precision']:.2f}"
        recall = "n/a" if cell["recall"] is None else f"{cell['recall']:.2f}"
        log(
            f"{strategy:<14}{cell['true_positive']:>5}{cell['false_negative']:>5}"
            f"{cell['false_positive']:>5}{cell['true_negative']:>5}{precision:>11}{recall:>9}"
        )

    for strategy in strategies:
        missed = matrix[strategy]["missed"]
        if missed:
            log(f"\n{strategy} missed: {', '.join(missed)}")

    if args.git_branches:
        log("")
        log(f"Materialising git branches in {args.git_branches}")
        report = make_git_branches(args.git_branches, log)
        write_json(os.path.join(args.out, "deviation_branches.json"), report)

    log("")
    log(f"Wrote {os.path.join(args.out, 'deviations.csv')} and deviations_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
