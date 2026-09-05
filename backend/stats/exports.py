"""The four tables as CSV and as IEEE-ready LaTeX.

Values are formatted once, in `stats.core`, so the number on screen, the number
in the CSV and the number in the manuscript are the same string. Retyping a
figure from a screen into a paper is how a table and its prose end up
disagreeing, and nobody notices until a reviewer does.
"""
import csv
import io
import zipfile
from typing import Any, Dict, Optional, Sequence


def _csv(rows: Sequence[Dict[str, Any]], columns: Optional[Sequence[str]] = None) -> str:
    if not rows:
        return ""
    fieldnames = list(columns) if columns else list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _n(value: Any) -> str:
    """A count, with thousands separators."""
    if value is None:
        return "--"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any, places: int = 1) -> str:
    if value is None:
        return "--"
    try:
        return f"{float(value) * 100:.{places}f}\\%"
    except (TypeError, ValueError):
        return "--"


def _tex(text: Any) -> str:
    """Escape the characters that break a LaTeX build."""
    if text is None:
        return "--"
    out = str(text)
    for char, replacement in (
        ("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
        ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ):
        out = out.replace(char, replacement)
    return out


# --- CSV ---------------------------------------------------------------------


def to_csv_bundle(report: Dict[str, Any], raw_rows: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, str]:
    """Four tables, four files, plus the raw runs for the replication package."""
    bundle: Dict[str, str] = {}

    study = report.get("study", {})
    if study.get("rows"):
        bundle["table1-what-was-studied.csv"] = _csv(
            [{"item": row["label"], "value": row["value"], "detail": row["detail"]} for row in study["rows"]]
            + [{"item": "Reading", "value": "", "detail": study.get("reading", "")}],
            ["item", "value", "detail"],
        )

    gates = report.get("gates", {})
    if gates.get("rows"):
        bundle["table2-gate-performance.csv"] = _csv(
            [
                {
                    "gate": row["gate"],
                    "runs": row["runs"],
                    "reanalysed": row["reanalysed"],
                    "skipped": row["skipped"],
                    "skip_rate": row["skip_rate"],
                    "skip_rate_low": row["skip_low"],
                    "skip_rate_high": row["skip_high"],
                    "checked_for_misses": row["checked_for_misses"],
                    "missed": row["missed"],
                    "miss_rate": row["miss_rate"],
                    "miss_rate_low": row["miss_low"],
                    "miss_rate_high": row["miss_high"],
                    "tokens": row["tokens"],
                    "tokens_saved": row["tokens_saved"],
                    "percent_saved": row["percent_saved"],
                    "median_latency_ms": row["median_latency_ms"],
                    "reading": row["reading"],
                }
                for row in gates["rows"]
            ]
        )

    projects = report.get("projects", {})
    if projects.get("rows"):
        bundle["table3-per-project.csv"] = _csv(
            [
                {
                    "project": row["project"],
                    "gate": projects.get("gate"),
                    "commits": row["commits"],
                    "runs": row["runs"],
                    "skipped": row["skipped"],
                    "skip_rate": row["skip_rate"],
                    "missed": row["missed"],
                    "tokens_saved": row["tokens_saved"],
                    "drift_per_commit": row["drift_per_commit"],
                    "median_similarity": row["median_similarity"],
                    "best_gate": row["best_gate"],
                    "gate_ranking": " > ".join(row["ranking"]),
                }
                for row in projects["rows"]
            ]
        )

    # One row per project *per gate* — the breakdown the page shows when a
    # project row is expanded, so what is on screen can be checked in a
    # spreadsheet.
    if projects.get("rows"):
        bundle["table3b-per-project-per-gate.csv"] = _csv(
            [
                {
                    "project": row["project"],
                    "gate": gate["gate"],
                    "runs": gate["runs"],
                    "skipped": gate["skipped"],
                    "skip_rate": gate["skip_rate"],
                    "missed": gate["missed"],
                    "miss_rate": gate.get("miss_rate"),
                    "tokens": gate["tokens"],
                    "tokens_saved": gate["tokens_saved"],
                    "median_latency_ms": gate.get("median_latency_ms"),
                    "enough_runs": gate["enough_runs"],
                }
                for row in projects["rows"]
                for gate in row.get("per_gate", [])
            ]
        )

    deviations = report.get("deviations", {})
    if deviations.get("rows"):
        bundle["table4-controlled-test.csv"] = _csv(
            [
                {
                    "gate": row["gate"],
                    "caught": row["caught"],
                    "missed": row["missed"],
                    "false_alarms": row["false_alarms"],
                    "correctly_ignored": row["correctly_ignored"],
                    "precision": row["precision"],
                    "recall": row["recall"],
                    "reading": row["reading"],
                }
                for row in deviations["rows"]
            ]
        )

    configuration = report.get("configuration", {})
    if configuration.get("rows"):
        bundle["study-configuration.csv"] = _csv(
            [{"setting": row["label"], "value": row["value"], "note": row["note"]}
             for row in configuration["rows"]]
            + [{"setting": "Reading", "value": "", "note": configuration.get("reading", "")}],
            ["setting", "value", "note"],
        )

    comparison = report.get("comparison", {})
    if comparison.get("left"):
        bundle["comparison-mcnemar.csv"] = _csv(
            [
                {
                    "left_gate": comparison["left"],
                    "right_gate": comparison["right"],
                    "paired_commits": comparison.get("paired_observations"),
                    "left_only_reanalysed": comparison.get("left_only"),
                    "right_only_reanalysed": comparison.get("right_only"),
                    "discordant": comparison.get("discordant"),
                    "p_value": comparison.get("p_value"),
                    "usable": comparison.get("usable"),
                    "reading": comparison.get("reading"),
                }
            ]
        )

    charts = report.get("charts", {})
    drift = charts.get("drift", {}).get("data", [])
    if drift:
        bundle["figure2-drift.csv"] = _csv(
            [
                {
                    "project": series["project"],
                    "commit_index": point["commit_index"],
                    "divergences": point["divergences"],
                    "absences": point["absences"],
                    "violations": point["violations"],
                }
                for series in drift
                for point in series["points"]
            ]
        )

    if raw_rows:
        bundle["raw-runs.csv"] = _csv(list(raw_rows))

    return bundle


def to_zip(bundle: Dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in sorted(bundle.items()):
            archive.writestr(filename, content)
    return buffer.getvalue()


# --- LaTeX -------------------------------------------------------------------


def _table(caption: str, label: str, columns: Sequence[str], alignment: str,
           rows: Sequence[Sequence[str]]) -> str:
    lines = [
        "\\begin{table}[!t]",
        "\\caption{" + caption + "}",
        "\\label{" + label + "}",
        "\\centering",
        "\\begin{tabular}{" + alignment + "}",
        "\\toprule",
        " & ".join(columns) + " \\\\",
        "\\midrule",
    ]
    lines.extend(" & ".join(row) + " \\\\" for row in rows)
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    return "\n".join(lines)


def to_latex(report: Dict[str, Any]) -> str:
    """The four tables, IEEE booktabs style. Requires \\usepackage{booktabs}."""
    return "\n".join(
        ["% Generated by the conformance platform. Requires \\usepackage{booktabs}.",
         "% Regenerate rather than edit by hand, so paper and data stay in step.", ""]
        + [block for block in split_latex(report).values() if block.startswith("\\begin{table}")]
    )


def split_latex(report: Dict[str, Any]) -> Dict[str, str]:
    """One file per table, so the manuscript can \\input each where the text
    discusses it and regenerate without touching a word of prose."""
    pieces: Dict[str, str] = {}

    study = report.get("study", {})
    if study.get("rows"):
        pieces["table1-study.tex"] = _table(
            "What was studied.",
            "tab:study",
            ["Property", "Value"],
            "lr",
            [[_tex(row["label"]), _tex(row["value"])] for row in study["rows"]],
        )

    gates = report.get("gates", {})
    if gates.get("rows"):
        body = []
        for row in gates["rows"]:
            skip = _pct(row["skip_rate"])
            if row["skip_low"] is not None:
                skip += f" [{_pct(row['skip_low'], 0)}, {_pct(row['skip_high'], 0)}]"
            missed = "--" if row["missed"] is None else str(row["missed"])
            body.append([
                "\\texttt{" + _tex(row["gate"]) + "}",
                _n(row["runs"]),
                _n(row["reanalysed"]),
                _n(row["skipped"]),
                skip,
                missed,
                "--" if row["miss_rate"] is None else _pct(row["miss_rate"]),
                _n(row["tokens"]),
                "--" if row["tokens_saved"] is None else _n(row["tokens_saved"]),
            ])
        pieces["table2-gates.tex"] = _table(
            "How each gate performed. Skip rate and miss rate must be read together: a gate "
            "that never skips has a perfect miss rate and saves nothing.",
            "tab:gates",
            ["Gate", "Runs", "Re-an.", "Skipped", "Skip rate [95\\% CI]", "Missed", "Miss rate",
             "Tokens", "Saved"],
            "lrrrlrrrr",
            body,
        )

    projects = report.get("projects", {})
    if projects.get("rows"):
        pieces["table3-projects.tex"] = _table(
            f"Per-project results under the \\texttt{{{_tex(projects.get('gate'))}}} gate. "
            + ("The ordering of gates by skip rate is the same in every project."
               if projects.get("consistent_ranking")
               else "The ordering of gates differs between projects; see the text."),
            "tab:projects",
            ["Project", "Commits", "Runs", "Skip rate", "Missed", "Tokens saved", "Drift/commit"],
            "lrrrrrr",
            [
                [
                    _tex(row["project"]),
                    _n(row["commits"]),
                    _n(row["runs"]),
                    _pct(row["skip_rate"]),
                    "--" if row["missed"] is None else str(row["missed"]),
                    _n(row["tokens_saved"]),
                    "--" if row["drift_per_commit"] is None else f"{row['drift_per_commit']:.2f}",
                ]
                for row in projects["rows"]
            ],
        )

    deviations = report.get("deviations", {})
    if deviations.get("rows"):
        pieces["table4-deviations.tex"] = _table(
            "The seeded-deviation set: 16 reproducible design changes with known expected "
            "outcomes. The only part of the study with unambiguous ground truth.",
            "tab:deviations",
            ["Gate", "Caught", "Missed", "False alarms", "Correctly ignored", "Precision", "Recall"],
            "lrrrrrr",
            [
                [
                    "\\texttt{" + _tex(row["gate"]) + "}",
                    str(row["caught"]),
                    str(row["missed"]),
                    str(row["false_alarms"]),
                    str(row["correctly_ignored"]),
                    "--" if row["precision"] is None else f"{row['precision']:.2f}",
                    "--" if row["recall"] is None else f"{row['recall']:.2f}",
                ]
                for row in deviations["rows"]
            ],
        )

    configuration = report.get("configuration", {})
    if configuration.get("rows"):
        pieces["configuration.tex"] = _table(
            "Configuration under which every run was produced. Stating the model, temperature "
            "and seed is expected of any study involving a language model.",
            "tab:configuration",
            ["Setting", "Value"],
            "ll",
            [[_tex(row["label"]), _tex(row["value"])] for row in configuration["rows"]],
        )

    comparison = report.get("comparison", {})
    if comparison.get("usable"):
        pieces["comparison.tex"] = (
            "% Drop this sentence into the results section.\n"
            + comparison.get("reading", "").replace("`", "").replace("%", "\\%")
            + "\n"
        )

    for key, name in (("headline", "headline.tex"),):
        if report.get(key):
            pieces[name] = (
                "% The one-sentence summary of the study.\n"
                + str(report[key]).replace("`", "").replace("%", "\\%")
                + "\n"
            )

    return pieces
