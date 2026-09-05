"""Produce the paper's four tables from a replay CSV or a project's run ledger.

The Statistics page in the app runs exactly this code, so a number on screen and
a number in the manuscript cannot disagree.

Usage
-----
    python research/analyze_statistics.py --runs results/runs.csv --out results/
    python research/analyze_statistics.py --workspace backend/workspace --out results/

Outputs, all into --out:
    REPORT.md                a readable summary -- start here
    statistics.json          the whole report, including every generated sentence
    tables/*.csv             one CSV per table
    tables-tex/*.tex         one LaTeX file per table, for \\input into the paper

Nothing here needs an API key or a network connection. The key is only for the
*analysis* step that produces runs in the first place.
"""
import argparse
import csv
import json
import os
import sys
import zipfile
from typing import Any, Dict, List, Optional

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

os.environ.setdefault("SECRET_KEY", "research-analysis-not-a-deployment")
os.environ.setdefault("LLM_MODE", "offline")

from stats.core import count, percent  # noqa: E402
from stats.exports import split_latex, to_csv_bundle  # noqa: E402
from stats.report import build_report, normalise_rows  # noqa: E402


def read_runs_csv(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_workspace(root: str) -> List[Dict[str, Any]]:
    """Every project's run ledger under a workspace directory.

    Layout is `<workspace>/<user>/<project>/reports/runs.jsonl`, which is what
    the application writes.
    """
    rows: List[Dict[str, Any]] = []
    for current, _dirs, files in os.walk(root):
        if os.path.basename(current) != "reports" or "runs.jsonl" not in files:
            continue
        project = os.path.basename(os.path.dirname(current))
        with open(os.path.join(current, "runs.jsonl"), "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row.setdefault("project", project)
                rows.append(row)
    return rows


def read_deviations(out_dir: str) -> Optional[Dict[str, Any]]:
    """The seeded-deviation confusion matrix, if it has been generated."""
    for candidate in (
        os.path.join(out_dir, "deviations_summary.json"),
        os.path.join("results", "deviations_summary.json"),
    ):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            except (OSError, ValueError):
                continue
    return None


def write_markdown(report: Dict[str, Any], path: str) -> None:
    """A readable summary: every table followed by the sentence that explains it.

    This is the file to open first. It is written so that a reader who knows no
    statistics can follow it, and so that the sentences can be lifted more or
    less directly into the paper.
    """
    lines: List[str] = ["# What the numbers say", "", f"**{report['headline']}**", ""]

    # Table 1
    study = report["study"]
    lines += [
        f"## Table {study['number']} — {study['title']}",
        "",
        "| | |",
        "|---|---|",
    ]
    lines += [f"| {row['label']} | {row['value']} |" for row in study["rows"]]
    lines += ["", f"*{study['reading']}*", ""]

    # Table 2
    gates = report["gates"]
    lines += [
        f"## Table {gates['number']} — {gates['title']}",
        "",
        "| Gate | Runs | Re-analysed | Skipped | Skip rate | Missed | Miss rate | Tokens | Saved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in gates["rows"]:
        skip = percent(row["skip_rate"])
        if row["skip_low"] is not None:
            skip += f" [{percent(row['skip_low'], 0)}–{percent(row['skip_high'], 0)}]"
        lines.append(
            f"| `{row['gate']}` | {row['runs']} | {row['reanalysed']} | {row['skipped']} | "
            f"{skip} | {'—' if row['missed'] is None else row['missed']} | "
            f"{percent(row['miss_rate'])} | {count(row['tokens'])} | "
            f"{'—' if row['tokens_saved'] is None else count(row['tokens_saved'])} |"
        )
    lines += ["", "Row by row:", ""]
    lines += [f"- **`{row['gate']}`** — {row['reading']}" for row in gates["rows"]]
    lines += ["", f"*{gates['reading']}*", ""]

    # Table 3
    projects = report["projects"]
    lines += [
        f"## Table {projects['number']} — {projects['title']}",
        "",
        f"Numbers below are for the `{projects['gate']}` gate.",
        "",
        "| Project | Commits | Runs | Skip rate | Missed | Tokens saved | Drift/commit |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in projects["rows"]:
        lines.append(
            f"| {row['project']} | {row['commits']} | {row['runs']} | "
            f"{percent(row['skip_rate'])} | {'—' if row['missed'] is None else row['missed']} | "
            f"{'—' if row['tokens_saved'] is None else count(row['tokens_saved'])} | "
            f"{'—' if row['drift_per_commit'] is None else row['drift_per_commit']} |"
        )
    lines += ["", f"*{projects['reading']}*", ""]

    # Every gate, per project. The pooled table cannot answer "what happened in
    # my repository", and that is the question someone with one project asks.
    if any(row.get("per_gate") for row in projects["rows"]):
        lines += [
            "### Every gate, project by project",
            "",
            "| Project | Gate | Runs | Skipped | Skip rate | Missed | Tokens | Saved |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in projects["rows"]:
            for i, gate in enumerate(row.get("per_gate", [])):
                lines.append(
                    f"| {row['project'] if i == 0 else ''} | `{gate['gate']}` | {gate['runs']} | "
                    f"{gate['skipped']} | {percent(gate['skip_rate'])} | "
                    f"{'—' if gate['missed'] is None else gate['missed']} | "
                    f"{count(gate['tokens'])} | "
                    f"{'—' if gate['tokens_saved'] is None else count(gate['tokens_saved'])} |"
                )
        lines.append("")

    # Table 4
    deviations = report["deviations"]
    lines += [f"## Table {deviations['number']} — {deviations['title']}", ""]
    if deviations["available"]:
        lines += [
            "| Gate | Caught | Missed | False alarms | Correctly ignored | Precision | Recall |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in deviations["rows"]:
            lines.append(
                f"| `{row['gate']}` | {row['caught']} | {row['missed']} | {row['false_alarms']} | "
                f"{row['correctly_ignored']} | {row['precision']} | {row['recall']} |"
            )
        lines.append("")
    lines += [f"*{deviations['reading']}*", ""]

    # The one significance test
    comparison = report["comparison"]
    lines += ["## Is the difference between the two gates real?", "",
              f"*{comparison['reading']}*", ""]

    # How the runs were produced -- the reproducibility block.
    configuration = report.get("configuration", {})
    if configuration.get("rows"):
        lines += [f"## {configuration['title']}", "", "| Setting | Value |", "|---|---|"]
        lines += [f"| {row['label']} | {row['value']} |" for row in configuration["rows"]]
        lines += ["", f"*{configuration['reading']}*", ""]

    # Glossary
    lines += ["## What the words mean", ""]
    lines += [f"- **{item['term']}** — {item['meaning']}" for item in report["how_to_read"]]
    lines += [""]

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def build_replication_package(out_dir: str, runs_csv: Optional[str]) -> str:
    """Everything a reader needs to reproduce the paper, in one file.

    IEEE Access does not require a replication package, but reviewers respond
    well to one and it costs nothing to produce. Archive it on Zenodo, cite the
    DOI in the paper, and the "is this reproducible?" question answers itself.

    Only files that already exist are included -- a package that claims to hold
    a corpus it does not have is worse than no package.
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target = os.path.join(out_dir, "replication-package.zip")

    wanted = [
        # The results.
        (os.path.join(out_dir, "REPORT.md"), "results/REPORT.md"),
        (os.path.join(out_dir, "statistics.json"), "results/statistics.json"),
        (runs_csv, "results/runs.csv") if runs_csv else None,
        (os.path.join(out_dir, "deviations.csv"), "results/deviations.csv"),
        (os.path.join(out_dir, "deviations_summary.json"), "results/deviations_summary.json"),
        (os.path.join(out_dir, "summary.json"), "results/summary.json"),
        # What produced them.
        (os.path.join(root, "research", "corpus.json"), "corpus.json"),
        (os.path.join(root, "research", "replay.py"), "scripts/replay.py"),
        (os.path.join(root, "research", "evaluate_deviations.py"), "scripts/evaluate_deviations.py"),
        (os.path.join(root, "research", "analyze_statistics.py"), "scripts/analyze_statistics.py"),
        (os.path.join(root, "docs", "STATISTICS.md"), "docs/STATISTICS.md"),
    ]

    readme = """# Replication package

Produced by `research/analyze_statistics.py --replication`.

## What is here

    results/REPORT.md          every table with a plain-English reading
    results/statistics.json    the full report
    results/runs.csv           one row per commit per gate -- the raw data
    results/deviations*.       the seeded-deviation controlled test
    tables/                    one CSV per table in the paper
    tables-tex/                one LaTeX file per table
    corpus.json                which projects were replayed, and at which commits
    scripts/                   the exact scripts that produced all of the above

## Reproducing the tables from the raw data

    python scripts/analyze_statistics.py --runs results/runs.csv --out .

This needs Python 3.9+ and nothing else -- no API key, no network, no
third-party packages. Every statistic is pure Python.

## Reproducing the raw data

    python scripts/evaluate_deviations.py --out results/
    python scripts/replay.py --corpus corpus.json --out results/

The replay clones the projects named in `corpus.json` and needs `git` on PATH.
It runs offline by default, so it costs nothing and is exactly reproducible.

## The settings these runs were produced under

See the "How these runs were produced" section of `results/REPORT.md`.
"""

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", readme)
        for entry in wanted:
            if not entry:
                continue
            source, name = entry
            if source and os.path.isfile(source):
                archive.write(source, name)
        for folder, prefix in (("tables", "tables"), ("tables-tex", "tables-tex")):
            directory = os.path.join(out_dir, folder)
            if not os.path.isdir(directory):
                continue
            for filename in sorted(os.listdir(directory)):
                archive.write(os.path.join(directory, filename), f"{prefix}/{filename}")
    return target


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--runs", help="runs.csv produced by research/replay.py")
    source.add_argument("--workspace", help="A workspace directory holding project run ledgers")
    parser.add_argument("--out", default="results", help="Output directory (default ./results)")
    parser.add_argument(
        "--replication",
        action="store_true",
        help="Also build replication-package.zip: the one file to upload to Zenodo.",
    )
    args = parser.parse_args(argv)

    rows = read_runs_csv(args.runs) if args.runs else read_workspace(args.workspace)
    if not rows:
        print("No runs found; nothing to analyse.", file=sys.stderr)
        return 1

    print(f"Analysing {len(rows)} run(s)…", flush=True)
    report = build_report(rows, deviations=read_deviations(args.out))

    os.makedirs(args.out, exist_ok=True)
    tables_dir = os.path.join(args.out, "tables")
    tex_dir = os.path.join(args.out, "tables-tex")
    os.makedirs(tables_dir, exist_ok=True)
    os.makedirs(tex_dir, exist_ok=True)

    with open(os.path.join(args.out, "statistics.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    bundle = to_csv_bundle(report, normalise_rows(rows))
    for filename, content in bundle.items():
        with open(os.path.join(tables_dir, filename), "w", encoding="utf-8", newline="") as handle:
            handle.write(content)

    pieces = split_latex(report)
    for filename, content in pieces.items():
        with open(os.path.join(tex_dir, filename), "w", encoding="utf-8") as handle:
            handle.write(content)

    write_markdown(report, os.path.join(args.out, "REPORT.md"))

    # A short version of the headline on the terminal, so a run that produced
    # nothing useful is obvious without opening a file.
    print()
    print(report["headline"])
    print()
    print(f"{'gate':<14}{'runs':>6}{'skipped':>9}{'missed':>8}{'tokens':>12}")
    for row in report["gates"]["rows"]:
        print(
            f"{row['gate']:<14}{row['runs']:>6}{percent(row['skip_rate']):>9}"
            f"{('—' if row['missed'] is None else str(row['missed'])):>8}"
            f"{row['tokens']:>12,}"
        )
    if not report["deviations"]["available"]:
        print("\nThe controlled test has not been run: python research/evaluate_deviations.py --out results/")

    print(f"\nWrote {args.out}/REPORT.md (start here), statistics.json, "
          f"{len(bundle)} CSV(s) and {len(pieces)} LaTeX table(s).")

    if args.replication:
        path = build_replication_package(args.out, args.runs)
        print(f"Replication package: {path} — upload this one file to Zenodo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
