"""Replay a commit sequence through every gate strategy, and measure the result.

This is the experiment the cost claim rests on. For each project and each gate:

1. materialise each commit's tree into a fresh project's virtual directory,
2. run one analysis,
3. record what the gate decided, what it cost, and how long it took.

In parallel, every commit is also analysed with the gate disabled (`force`), in
its own project. That forced run is the oracle: wherever a gate chose to reuse
but the forced run's deterministic findings differ, the gate missed a real
change. Those are counted per strategy and listed in the output, because the
miss rate -- not the saving alone -- is what decides whether a gate is usable.

Usage
-----
    python research/replay.py --corpus research/corpus.json --out results/
    python research/replay.py --repo ../some-project --uml design.mdj --commits 40
    python research/replay.py --corpus research/corpus.json --strategies structural,isomorphism

Runs offline (no model calls) by default so the deterministic findings are
exactly reproducible. Pass --llm-mode auto to include a real model.
"""
import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional

from harness import (  # noqa: E402  (path set up inside harness)
    GATE_STRATEGIES,
    GitError,
    ProjectSpec,
    Sandbox,
    checkout_worktree,
    clone_or_reuse,
    commit_list,
    copy_source,
    finding_signature,
    git_available,
    install_uml,
    load_corpus,
    preflight,
    signatures_differ,
    write_csv,
    write_json,
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--corpus", help="JSON manifest of projects to replay.")
    source.add_argument("--repo", help="A single local path or clone URL.")

    parser.add_argument("--uml", help="Path to a .mdj model, when using --repo.")
    parser.add_argument("--commits", type=int, default=30, help="Commits per project (default 30).")
    parser.add_argument("--branch", help="Branch to read history from.")
    parser.add_argument("--subdirectory", help="Analyse only this subdirectory of the repo.")
    parser.add_argument(
        "--strategies",
        default=",".join(GATE_STRATEGIES),
        help="Comma-separated gate strategies to compare.",
    )
    parser.add_argument("--out", default="results", help="Output directory (default ./results).")
    parser.add_argument("--cache", default=".corpus-cache", help="Where clones are kept.")
    parser.add_argument(
        "--llm-mode",
        default="offline",
        choices=("offline", "auto", "api"),
        help="offline (default) keeps the run free and exactly reproducible.",
    )
    parser.add_argument("--keep-sandbox", action="store_true", help="Do not delete scratch projects.")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def resolve_projects(args: argparse.Namespace) -> List[ProjectSpec]:
    if args.corpus:
        return load_corpus(args.corpus)
    return [
        ProjectSpec(
            name=os.path.basename(str(args.repo).rstrip("/")) or "project",
            source=args.repo,
            uml=args.uml,
            commits=args.commits,
            branch=args.branch,
            subdirectory=args.subdirectory,
        )
    ]


def replay_project(
    spec: ProjectSpec,
    strategies: List[str],
    sandbox: Sandbox,
    cache_dir: str,
    log,
) -> Dict[str, Any]:
    from core.pipeline import run_analysis  # imported after harness sets sys.path

    repo = clone_or_reuse(spec.source, cache_dir)
    commits = commit_list(repo, spec.commits, spec.branch)
    if not commits:
        raise GitError(f"No commits found for {spec.name}.")

    log(f"  {spec.name}: {len(commits)} commits x {len(strategies)} strategies (+ oracle)")

    tree_dir = os.path.join(sandbox.root, f"__tree__{spec.name}")
    projects = {strategy: sandbox.reset(f"{spec.name}--{strategy}") for strategy in strategies}
    oracle_project = sandbox.reset(f"{spec.name}--oracle")

    for path in list(projects.values()) + [oracle_project]:
        install_uml(path, spec.uml)

    rows: List[Dict[str, Any]] = []
    misses: List[Dict[str, Any]] = []

    # The oracle's own previous signature. Whether conformance *changed* at a
    # commit is a fact about the code and the diagram, not about any gate, so it
    # is measured by comparing the forced full analysis against the forced full
    # analysis of the commit before it -- never against a gated run, which would
    # make the answer depend on the thing being evaluated.
    previous_truth: Optional[Dict[str, Any]] = None

    for index, commit in enumerate(commits):
        checkout_worktree(repo, commit, tree_dir)

        # The oracle: the same commit, always fully re-analysed.
        copy_source(tree_dir, oracle_project, spec.subdirectory)
        oracle_started = time.perf_counter()
        oracle = run_analysis(oracle_project, gate_strategy="always", force=True)
        oracle_elapsed = (time.perf_counter() - oracle_started) * 1000
        truth = finding_signature(oracle)

        # None at the first commit of a project: there is no earlier commit to
        # compare against, so the answer is "not measured", never False.
        conformance_changed = (
            bool(signatures_differ(previous_truth, truth))
            if previous_truth is not None
            else None
        )

        for strategy in strategies:
            project_path = projects[strategy]
            file_count = copy_source(tree_dir, project_path, spec.subdirectory)

            started = time.perf_counter()
            result = run_analysis(project_path, gate_strategy=strategy)
            elapsed = (time.perf_counter() - started) * 1000

            observed = finding_signature(result)
            differing = signatures_differ(truth, observed)
            reused = not result["gate"]["should_invoke_llm"]
            missed = bool(differing) and reused

            if missed:
                misses.append(
                    {
                        "project": spec.name,
                        "strategy": strategy,
                        "commit": commit,
                        "commit_index": index,
                        "differing_fields": differing,
                        "reason": result["gate"]["reason"],
                    }
                )

            rows.append(
                {
                    "project": spec.name,
                    # These column names are the contract with
                    # backend/stats/report.py::normalise_rows. Renaming either
                    # of them silently degrades every downstream table.
                    "gate_strategy": strategy,
                    "commit_index": index,
                    "commit": commit[:12],
                    "files": file_count,
                    "gate_allowed_llm": result["gate"]["should_invoke_llm"],
                    "reused": reused,
                    "reason": result["gate"]["reason"],
                    "changed_nodes": result["gate"]["delta"]["changed_nodes"],
                    "added_nodes": result["gate"]["delta"]["added_nodes"],
                    "removed_nodes": result["gate"]["delta"]["removed_nodes"],
                    "impact_nodes": result["gate"]["impact_node_count"],
                    "isomorphic": result["gate"]["isomorphic"],
                    "prompt_tokens": result["llm"]["prompt_tokens"],
                    "completion_tokens": result["llm"]["completion_tokens"],
                    "latency_ms": round(elapsed, 1),
                    "graph_nodes": result["networkx_nodes"],
                    "graph_edges": result["networkx_edges"],
                    "similarity_score": result["similarity_score_rule_based"],
                    "call_resolution_rate": (result.get("call_resolution") or {}).get(
                        "resolution_rate"
                    ),
                    "ambiguous_calls": (result.get("call_resolution") or {}).get("ambiguous", 0),
                    "missed_change": missed,
                    # Did this run's findings differ from the oracle's, whether
                    # or not the gate reused? `missed_change` folds this
                    # together with "and the gate reused", which loses the
                    # information needed to tell when a miss is corrected.
                    "diverges_from_oracle": bool(differing),
                    # A property of the commit, identical for every strategy.
                    "conformance_changed": conformance_changed,
                    "oracle_latency_ms": round(oracle_elapsed, 1),
                }
            )

        previous_truth = truth

        if not index % 10:
            log(f"    commit {index + 1}/{len(commits)}")

    return {"project": spec.name, "commits": len(commits), "rows": rows, "misses": misses}


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_strategy: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        bucket = by_strategy.setdefault(
            row["gate_strategy"],
            {
                "runs": 0,
                "reanalyses": 0,
                "reused": 0,
                "missed_changes": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms": 0.0,
                "impact_nodes": 0,
            },
        )
        bucket["runs"] += 1
        bucket["reanalyses"] += 1 if row["gate_allowed_llm"] else 0
        bucket["reused"] += 0 if row["gate_allowed_llm"] else 1
        bucket["missed_changes"] += 1 if row["missed_change"] else 0
        bucket["prompt_tokens"] += row["prompt_tokens"] or 0
        bucket["completion_tokens"] += row["completion_tokens"] or 0
        bucket["latency_ms"] += row["latency_ms"] or 0.0
        bucket["impact_nodes"] += row["impact_nodes"] or 0

    baseline = by_strategy.get("always", {}).get("reanalyses")
    for strategy, bucket in by_strategy.items():
        runs = bucket["runs"] or 1
        bucket["reuse_rate"] = round(bucket["reused"] / runs, 4)
        bucket["miss_rate"] = round(bucket["missed_changes"] / runs, 4)
        bucket["mean_latency_ms"] = round(bucket["latency_ms"] / runs, 1)
        bucket["mean_impact_nodes"] = round(bucket["impact_nodes"] / runs, 2)
        if baseline:
            bucket["reanalyses_vs_always"] = round(bucket["reanalyses"] / baseline, 4)
    return by_strategy


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    os.environ["LLM_MODE"] = args.llm_mode

    def log(message: str):
        if not args.quiet:
            print(message, flush=True)

    if not git_available():
        print("git is required to replay commit history.", file=sys.stderr)
        return 2

    blocker = preflight()
    if blocker:
        print(blocker, file=sys.stderr)
        return 2

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = [s for s in strategies if s not in GATE_STRATEGIES]
    if unknown:
        print(f"Unknown strategies: {', '.join(unknown)}", file=sys.stderr)
        return 2

    projects = resolve_projects(args)
    sandbox = Sandbox.create(keep=args.keep_sandbox)
    all_rows: List[Dict[str, Any]] = []
    all_misses: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []

    log(f"Replaying {len(projects)} project(s) under {len(strategies)} gate(s), LLM {args.llm_mode}.")

    try:
        for spec in projects:
            try:
                outcome = replay_project(spec, strategies, sandbox, args.cache, log)
            except (GitError, OSError) as exc:
                log(f"  {spec.name}: SKIPPED ({exc})")
                failures.append({"project": spec.name, "error": str(exc)})
                continue
            all_rows.extend(outcome["rows"])
            all_misses.extend(outcome["misses"])
    finally:
        sandbox.cleanup()

    if not all_rows:
        print("No runs completed; nothing to report.", file=sys.stderr)
        return 1

    summary = summarise(all_rows)
    write_csv(os.path.join(args.out, "runs.csv"), all_rows)
    write_json(
        os.path.join(args.out, "summary.json"),
        {
            "projects": [spec.name for spec in projects],
            "strategies": strategies,
            "llm_mode": args.llm_mode,
            "total_runs": len(all_rows),
            "by_strategy": summary,
            "missed_changes": all_misses,
            "failures": failures,
        },
    )

    log("")
    log(f"{'strategy':<14}{'runs':>6}{'reanalysed':>12}{'reused':>9}{'reuse%':>9}{'missed':>8}{'miss%':>8}")
    for strategy in strategies:
        bucket = summary.get(strategy)
        if not bucket:
            continue
        log(
            f"{strategy:<14}{bucket['runs']:>6}{bucket['reanalyses']:>12}{bucket['reused']:>9}"
            f"{bucket['reuse_rate'] * 100:>8.1f}%{bucket['missed_changes']:>8}"
            f"{bucket['miss_rate'] * 100:>7.1f}%"
        )
    log("")
    log(f"Wrote {os.path.join(args.out, 'runs.csv')} and summary.json")
    if all_misses:
        log(f"{len(all_misses)} missed change(s) recorded -- see summary.json for the commits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
