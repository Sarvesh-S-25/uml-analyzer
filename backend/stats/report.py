"""Four tables, one comparison, two charts -- and a plain-English sentence for
every one of them.

The rule this file is built around: **no number is shown without a sentence
saying what it means.** Those sentences are generated from the numbers
themselves, in `_reading()` functions, so they cannot go stale when the data
changes and cannot say something the data does not support.

What is here:

    Table 1  What was studied
    Table 2  How each gate performed        <- the paper's headline
    Table 3  Did it work on every project?
    Table 4  The controlled test (seeded deviations)
    +        One significance test (McNemar) on the comparison that matters
    +        Two charts: skip rate by gate, drift over commits

What is deliberately *not* here: regression models, machine learning, survival
analysis, rank correlations, multiple-comparison correction, bootstrap
resampling. They were here; they made the results harder to read than the data
they summarised.
"""
from typing import Any, Dict, List, Optional, Sequence

from stats.core import (
    MIN_RUNS_FOR_A_TRUSTWORTHY_RATE,
    count,
    describe,
    interval_text,
    km_median_horizon,
    mcnemar_exact,
    median,
    p_value_text,
    percent,
    rate,
    round2,
    wilson_interval,
)

# Cheapest first, so a table reads left-to-right as "how hard does this gate try
# to avoid work".
GATE_ORDER = ["always", "content", "structural", "isomorphism"]

GATE_DESCRIPTIONS = {
    "always": "Re-analyses every time. The baseline everything else is measured against.",
    "content": "Skips when no file's bytes changed.",
    "structural": "Skips when the code's structure is unchanged — ignores comments, formatting and renamed local variables.",
    "isomorphism": "Skips structural changes too, when the new design graph has the same shape as the old one (for example a class renamed everywhere).",
}


# --- input normalisation -----------------------------------------------------


def normalise_rows(rows: Sequence[Dict[str, Any]], default_project: str = "project") -> List[Dict[str, Any]]:
    """One shape for both inputs: live run ledgers and replay CSVs.

    Ledger rows come from real use and have no commit identifier; replay rows do.
    Where one is missing, the run's position within its project stands in, which
    is enough to line the same commit up across gates.
    """
    normalised: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}

    for row in rows:
        project = str(row.get("project") or default_project)
        seen[project] = seen.get(project, 0) + 1
        commit = row.get("commit") or row.get("commit_hash") or f"run-{seen[project]}"

        reanalysed = row.get("gate_allowed_llm")
        if reanalysed is None:
            reanalysed = row.get("llm_invoked")

        normalised.append(
            {
                "project": project,
                "commit": str(commit),
                "commit_index": _int(row.get("commit_index"), seen[project] - 1),
                "gate": str(row.get("gate_strategy") or "unknown"),
                "reanalysed": _bool(reanalysed),
                "missed_change": _optional_bool(row.get("missed_change")),
                "diverges_from_oracle": _optional_bool(row.get("diverges_from_oracle")),
                "conformance_changed": _optional_bool(row.get("conformance_changed")),
                "tokens": _num(row.get("prompt_tokens")) + _num(row.get("completion_tokens")),
                "latency_ms": _num(row.get("latency_ms")),
                "changed_nodes": _num(row.get("changed_nodes")),
                "similarity": _optional_num(row.get("similarity_score")),
                "divergences": _optional_num(row.get("divergences")),
                "absences": _optional_num(row.get("absences")),
                "findings_hash": row.get("findings_hash"),
                "model": row.get("model"),
                "provider": row.get("provider"),
                "llm_mode": row.get("llm_mode"),
                "temperature": _optional_num(row.get("temperature")),
                "seed": row.get("seed"),
                "association_scoring": row.get("association_scoring"),
                "impact_radius": row.get("impact_radius"),
                "degraded": row.get("degraded"),
            }
        )
    return normalised


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    return _bool(value)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _gates_in(rows: Sequence[Dict[str, Any]]) -> List[str]:
    present = {row["gate"] for row in rows}
    ordered = [gate for gate in GATE_ORDER if gate in present]
    return ordered + sorted(present - set(ordered))


def infer_missing_labels(rows: List[Dict[str, Any]]) -> int:
    """Work out where conformance changed, when no replay oracle is available.

    Every run records a hash of its deterministic findings. Two consecutive runs
    of the same project under the same gate with different hashes mean the
    findings moved. It is weaker than the replay oracle -- it cannot see a change
    the gate skipped -- and it is labelled as such wherever it is used.
    """
    filled = 0
    series: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        series.setdefault((row["project"], row["gate"]), []).append(row)

    for entries in series.values():
        entries.sort(key=lambda item: item["commit_index"])
        previous = None
        for entry in entries:
            current = entry.get("findings_hash")
            if entry["conformance_changed"] is None and current is not None and previous is not None:
                entry["conformance_changed"] = current != previous
                filled += 1
            if current is not None:
                previous = current
    return filled


# --- study configuration ------------------------------------------------------


def study_configuration(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What settings actually produced these runs.

    Read from the runs rather than from the current environment: the
    configuration can change between running a study and writing it up, and the
    paper has to state what was used, not what is set today. Where runs disagree
    the section says so instead of picking one -- a corpus assembled under two
    different models is a real problem, and silently reporting one of them would
    hide it.

    IEEE Access reviewers and the reporting guidelines for empirical studies
    involving language models both expect model, temperature, seed and mode to
    be stated. This is the block to copy into the methodology section.
    """
    def distinct(key: str) -> List[Any]:
        values = {row.get(key) for row in rows if row.get(key) not in (None, "")}
        return sorted(values, key=str)

    entries: List[Dict[str, Any]] = []
    conflicts: List[str] = []

    for key, label, note in (
        ("llm_mode", "Model mode", "offline means no model was ever called; the pipeline ran deterministically"),
        ("provider", "Provider", ""),
        ("model", "Model", "state the exact version string in the paper"),
        ("temperature", "Temperature", ""),
        ("seed", "Seed", ""),
        ("impact_radius", "Impact radius (hops)", "how far around a change the analysis looks"),
        ("association_scoring", "Associations scored", "off by default: an association cannot be proven from an AST, only evidenced"),
    ):
        values = distinct(key)
        if not values:
            continue
        if len(values) > 1:
            conflicts.append(label)
        entries.append({
            "label": label,
            "value": ", ".join(str(v) for v in values),
            "note": note,
            "consistent": len(values) == 1,
        })

    degraded = sum(1 for row in rows if row.get("degraded"))
    if degraded:
        entries.append({
            "label": "Runs that fell back to the deterministic path",
            "value": degraded,
            "note": "an API call failed and the deterministic result was used instead",
            "consistent": False,
        })

    if not entries:
        reading = (
            "No configuration was recorded with these runs. They predate the settings being "
            "written to the ledger — re-run the analysis to capture them. The paper needs the "
            "model, temperature and seed stated explicitly."
        )
    elif conflicts:
        reading = (
            "These runs were not all produced under the same settings — "
            + ", ".join(conflicts)
            + " differ between runs. Report the split honestly, or re-run the corpus under one "
            "configuration. A reviewer who finds two models in one corpus will discount the "
            "comparison."
        )
    else:
        reading = (
            "All runs share one configuration, which is what makes the comparison between gates "
            "fair. Copy these values into the paper's methodology section — model, temperature "
            "and seed are expected for any study involving a language model, and their absence "
            "is a routine review comment."
        )

    return {
        "title": "How these runs were produced",
        "rows": entries,
        "consistent": not conflicts,
        "reading": reading,
    }


# --- Table 1: what was studied -----------------------------------------------


def table_study(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    projects = sorted({row["project"] for row in rows})
    gates = _gates_in(rows)
    commits = {(row["project"], row["commit"]) for row in rows}
    has_oracle = any(row["missed_change"] is not None for row in rows)

    entries = [
        {"label": "Projects", "value": len(projects), "detail": ", ".join(projects[:6])},
        {"label": "Commits analysed", "value": len(commits), "detail": ""},
        {"label": "Total analysis runs", "value": len(rows), "detail": "each commit, once per gate"},
        {"label": "Gate policies compared", "value": len(gates), "detail": ", ".join(gates)},
        {
            "label": "Can we measure misses?",
            "value": "Yes" if has_oracle else "No",
            "detail": (
                "a forced full analysis ran alongside every commit"
                if has_oracle
                else "run research/replay.py to get the comparison that makes this measurable"
            ),
        },
    ]

    reading = (
        f"{len(projects)} project{'s' if len(projects) != 1 else ''} and {len(commits)} commits. "
        f"Each commit was analysed once per gate policy, giving {len(rows):,} runs in total."
    )
    if has_oracle:
        reading += (
            " A full analysis was forced alongside every commit, so whenever a gate skipped a "
            "commit we can check whether it should have."
        )
    else:
        reading += (
            " No forced comparison run is present, so the 'missed' column below cannot be filled "
            "in — the tool says 'not measured' rather than printing a zero it did not earn."
        )

    return {
        "number": 1,
        "title": "What was studied",
        "rows": entries,
        "projects": len(projects),
        "project_names": projects,
        "commits": len(commits),
        "runs": len(rows),
        "gates": gates,
        "has_oracle": has_oracle,
        "reading": reading,
    }


# --- Table 2: how each gate performed ----------------------------------------


def _recovery_horizon(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How long a missed change stays missed, for one gate.

    A miss is not a permanently wrong answer -- the next run that re-analyses
    picks the change up. This measures how many commits pass before that
    happens, which turns "this gate missed 2% of changes" into a claim a
    reviewer can weigh.

    "Corrected" means the gate's findings agree with the oracle again, not
    merely that the gate fired: a gate can re-analyse and still be looking at a
    different answer. That needs `diverges_from_oracle` on every row, not just
    the missed ones, which is why `research/replay.py` records it separately
    from `missed_change`.

    A miss still outstanding when its project's history ends is recorded as
    censored (`None`), never as zero and never dropped -- see invariant 4.
    """
    graded = [row for row in subset if row["diverges_from_oracle"] is not None]
    if not graded:
        return {
            "measured": False,
            "reason": "No oracle was recorded, so corrections cannot be detected.",
            "misses_tracked": 0,
            "resolved_count": 0,
            "censored_count": 0,
            "median_commits": None,
            "censored_beyond": None,
            "max_resolved": None,
        }

    durations: List[Optional[int]] = []
    for project in sorted({row["project"] for row in graded}):
        ordered = sorted(
            (row for row in graded if row["project"] == project),
            key=lambda row: row["commit_index"],
        )
        for position, row in enumerate(ordered):
            if not row["missed_change"]:
                continue
            gap: Optional[int] = None
            for later in ordered[position + 1 :]:
                if later["diverges_from_oracle"] is False:
                    gap = later["commit_index"] - row["commit_index"]
                    break
            durations.append(gap)

    summary = km_median_horizon(durations)
    summary["measured"] = True
    summary["reason"] = ""
    return summary


def table_gates(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The headline. Counts before rates, and misses beside savings, always."""
    gates = _gates_in(rows)
    by_gate = {gate: [row for row in rows if row["gate"] == gate] for gate in gates}

    # The baseline is the gate that never skips. Without it, the most expensive
    # gate present stands in, and the label says so -- savings have to be
    # measured against something, and silently changing what that something is
    # would be the worst possible failure here.
    baseline_gate = "always" if "always" in gates else max(
        gates, key=lambda gate: sum(row["tokens"] for row in by_gate[gate])
    )
    baseline_tokens = sum(row["tokens"] for row in by_gate[baseline_gate])

    entries = []
    for gate in gates:
        subset = by_gate[gate]
        runs = len(subset)
        reanalysed = sum(1 for row in subset if row["reanalysed"])
        skipped = runs - reanalysed
        skip_low, skip_high = wilson_interval(skipped, runs)

        checked = [row for row in subset if row["missed_change"] is not None]
        missed = sum(1 for row in checked if row["missed_change"])
        miss_low, miss_high = wilson_interval(missed, len(checked)) if checked else (None, None)

        # The miss rate above divides by *every* run, and most commits change
        # nothing, so a gate can post a near-zero miss rate simply by skipping a
        # long stretch of commits that had nothing to find. These two condition
        # on what actually happened at each commit instead:
        #   recall      -- of the commits where conformance really changed, how
        #                  many did this gate re-analyse?
        #   specificity -- of the commits where nothing changed, how many did it
        #                  correctly skip?
        # Both are framed on the gate's *decision*, which is the thing the gate
        # controls, rather than on the findings that follow from it.
        judged = [row for row in subset if row["conformance_changed"] is not None]
        changed = [row for row in judged if row["conformance_changed"]]
        unchanged = [row for row in judged if not row["conformance_changed"]]

        caught = sum(1 for row in changed if row["reanalysed"])
        skipped_quiet = sum(1 for row in unchanged if not row["reanalysed"])
        recall = rate(caught, len(changed)) if changed else None
        specificity = rate(skipped_quiet, len(unchanged)) if unchanged else None
        recall_low, recall_high = (
            wilson_interval(caught, len(changed)) if changed else (None, None)
        )
        specificity_low, specificity_high = (
            wilson_interval(skipped_quiet, len(unchanged)) if unchanged else (None, None)
        )

        horizon = _recovery_horizon(subset)

        tokens = sum(row["tokens"] for row in subset)
        saved = baseline_tokens - tokens

        entry = {
            "gate": gate,
            "description": GATE_DESCRIPTIONS.get(gate, ""),
            "runs": runs,
            "reanalysed": reanalysed,
            "skipped": skipped,
            "skip_rate": round2(rate(skipped, runs)),
            "skip_low": round2(skip_low),
            "skip_high": round2(skip_high),
            "checked_for_misses": len(checked),
            "missed": missed if checked else None,
            # Deliberately named "all runs": this denominator is every run, not
            # only the commits where something changed. `docs/STATISTICS.md`
            # describes both, and the caption must say which is which.
            "miss_rate": round2(rate(missed, len(checked))) if checked else None,
            "miss_low": round2(miss_low),
            "miss_high": round2(miss_high),
            "changed_checked": len(changed),
            "unchanged_checked": len(unchanged),
            "recall": round2(recall),
            "recall_low": round2(recall_low),
            "recall_high": round2(recall_high),
            "specificity": round2(specificity),
            "specificity_low": round2(specificity_low),
            "specificity_high": round2(specificity_high),
            "recovery": horizon,
            "tokens": int(tokens),
            "tokens_saved": int(saved) if gate != baseline_gate else None,
            "percent_saved": round2(saved / baseline_tokens) if baseline_tokens and gate != baseline_gate else None,
            "median_latency_ms": median([row["latency_ms"] for row in subset]),
            "is_baseline": gate == baseline_gate,
            "enough_runs": runs >= MIN_RUNS_FOR_A_TRUSTWORTHY_RATE,
        }
        entry["reading"] = _gate_reading(entry)
        entries.append(entry)

    recommended = _recommend(entries)

    return {
        "number": 2,
        "title": "How each gate performed",
        "rows": entries,
        "baseline_gate": baseline_gate,
        "baseline_is_always": baseline_gate == "always",
        "recommended": recommended,
        "reading": _gates_reading(entries, recommended, baseline_gate),
    }


def _gate_reading(entry: Dict[str, Any]) -> str:
    """One sentence about one gate, built from that gate's own numbers."""
    if entry["is_baseline"]:
        return (
            f"Re-analysed all {entry['runs']} runs and spent {count(entry['tokens'])} tokens. "
            "This is what the other gates are compared against."
        )

    sentence = (
        f"Skipped {entry['skipped']} of {entry['runs']} runs "
        f"({percent(entry['skip_rate'])}"
    )
    span = interval_text(entry["skip_low"], entry["skip_high"])
    if span:
        sentence += f", {span} if the study were repeated"
    sentence += ")"

    if entry["missed"] is None:
        sentence += ", but whether any of those skips were wrong was not measured."
    elif entry["missed"] == 0:
        sentence += " and missed nothing."
    else:
        sentence += (
            f" but missed {entry['missed']} real conformance change"
            f"{'s' if entry['missed'] != 1 else ''} "
            f"({percent(entry['miss_rate'])} of all runs)."
        )

    # The conditional figure, which is the one that survives a reviewer who
    # notices that most commits change nothing.
    if entry["recall"] is not None:
        sentence += (
            f" Of the {entry['changed_checked']} commit"
            f"{'s' if entry['changed_checked'] != 1 else ''} where conformance really changed, "
            f"it re-analysed {percent(entry['recall'])}"
        )
        span = interval_text(entry["recall_low"], entry["recall_high"])
        sentence += f" ({span})." if span else "."
    elif entry["changed_checked"] == 0 and entry["unchanged_checked"] == 0:
        sentence += " Recall was not measured: no commit had a known before-and-after."

    recovery = entry.get("recovery") or {}
    if recovery.get("measured") and recovery.get("misses_tracked"):
        if recovery.get("median_commits") is not None:
            sentence += (
                f" A miss was corrected after a median of "
                f"{recovery['median_commits']:.0f} commit(s)."
            )
        elif recovery.get("censored_count"):
            sentence += (
                f" {recovery['censored_count']} of {recovery['misses_tracked']} miss(es) were "
                "still uncorrected when the history ended, so the median is not identified."
            )

    if entry["tokens_saved"]:
        sentence += f" Saved {count(entry['tokens_saved'])} tokens ({percent(entry['percent_saved'], 0)})."
    return sentence


def _recommend(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The gate to actually use: the most economical one that missed nothing.

    Stated explicitly because it is the question a reader of Table 2 is trying to
    answer, and leaving them to work it out from six columns is how a table
    becomes unreadable.
    """
    measured = [e for e in entries if not e["is_baseline"] and e["missed"] is not None]
    if not measured:
        return {
            "gate": None,
            "reason": "Miss rates were not measured, so no gate can be recommended yet. Run the commit replay.",
        }

    safe = [e for e in measured if e["missed"] == 0]
    pool = safe or measured
    best = max(pool, key=lambda e: (e["skip_rate"] or 0))

    if safe:
        reason = (
            f"`{best['gate']}` is the most economical gate that missed nothing: it skipped "
            f"{percent(best['skip_rate'])} of runs and saved {count(best['tokens_saved'])} tokens."
        )
    else:
        reason = (
            f"Every gate missed at least one change. `{best['gate']}` skipped the most "
            f"({percent(best['skip_rate'])}) but missed {best['missed']} — decide whether that "
            "trade is acceptable for your use."
        )

    return {
        "gate": best["gate"],
        "skip_rate": best["skip_rate"],
        "missed": best["missed"],
        "tokens_saved": best["tokens_saved"],
        "safe": bool(safe),
        "reason": reason,
    }


def _gates_reading(entries, recommended, baseline_gate) -> str:
    parts = []
    if baseline_gate != "always":
        parts.append(
            f"No `always` runs are present, so savings are measured against `{baseline_gate}`, "
            "the most expensive gate here."
        )
    if recommended.get("gate"):
        parts.append(recommended["reason"])

    risky = [e for e in entries if e["missed"]]
    if risky:
        worst = max(risky, key=lambda e: e["missed"])
        parts.append(
            f"`{worst['gate']}` is the cheapest option but not a free one: it skipped "
            f"{percent(worst['skip_rate'])} of runs and missed {worst['missed']} real change"
            f"{'s' if worst['missed'] != 1 else ''}. That is the trade the paper is about — "
            "quote its skip rate and its miss rate in the same sentence, always."
        )

    thin = [e["gate"] for e in entries if not e["enough_runs"]]
    if thin:
        parts.append(
            f"Careful with {', '.join('`' + g + '`' for g in thin)}: fewer than "
            f"{MIN_RUNS_FOR_A_TRUSTWORTHY_RATE} runs, so the percentage moves a lot when a "
            "single run changes."
        )
    return " ".join(parts)


# --- Table 3: did it work on every project? ----------------------------------


def table_projects(rows: List[Dict[str, Any]], recommended_gate: Optional[str]) -> Dict[str, Any]:
    """The same headline numbers, one row per project, for the recommended gate.

    Answers the only question a pooled table cannot: does this hold everywhere,
    or is one repository carrying the average?
    """
    projects = sorted({row["project"] for row in rows})
    gates = _gates_in(rows)
    entries = []

    for project in projects:
        project_rows = [row for row in rows if row["project"] == project]
        focus = [row for row in project_rows if row["gate"] == recommended_gate] or project_rows

        runs = len(focus)
        skipped = sum(1 for row in focus if not row["reanalysed"])
        checked = [row for row in focus if row["missed_change"] is not None]
        missed = sum(1 for row in checked if row["missed_change"])

        baseline = [row for row in project_rows if row["gate"] == "always"]
        saved = sum(row["tokens"] for row in baseline) - sum(row["tokens"] for row in focus)

        # Which gate skips most in this project, so we can check the ranking is
        # the same everywhere.
        ranking = sorted(
            gates,
            key=lambda gate: -_skip_rate([r for r in project_rows if r["gate"] == gate]),
        )

        entries.append(
            {
                "project": project,
                "commits": len({row["commit"] for row in project_rows}),
                "runs": runs,
                "skipped": skipped,
                "skip_rate": round2(rate(skipped, runs)),
                "missed": missed if checked else None,
                "tokens_saved": int(saved) if baseline else None,
                "drift_per_commit": _drift_rate(project_rows),
                "median_similarity": median(
                    [row["similarity"] for row in project_rows if row["similarity"] is not None]
                ),
                "best_gate": ranking[0] if ranking else None,
                "ranking": ranking,
                "enough_runs": runs >= MIN_RUNS_FOR_A_TRUSTWORTHY_RATE,
                # Every gate's numbers for THIS project. Without it the table
                # can only answer "did the recommended gate work here", which is
                # not the same question as "what happened in this project".
                "per_gate": [_project_gate_row(project_rows, project, gate) for gate in gates],
            }
        )

    consistent = len({tuple(e["ranking"]) for e in entries}) <= 1 if entries else False
    skip_rates = [e["skip_rate"] for e in entries if e["skip_rate"] is not None]

    return {
        "number": 3,
        "title": "Did it work on every project?",
        "gate": recommended_gate,
        "rows": entries,
        "consistent_ranking": consistent,
        "lowest_skip_rate": round2(min(skip_rates)) if skip_rates else None,
        "highest_skip_rate": round2(max(skip_rates)) if skip_rates else None,
        "reading": _projects_reading(entries, consistent, recommended_gate, skip_rates),
    }


def _project_gate_row(project_rows, project: str, gate: str) -> Dict[str, Any]:
    """One project under one gate — the cell a reader actually wants to inspect."""
    subset = [row for row in project_rows if row["gate"] == gate]
    if not subset:
        return {"gate": gate, "runs": 0, "skipped": 0, "skip_rate": None,
                "missed": None, "tokens": 0, "tokens_saved": None, "enough_runs": False}

    skipped = sum(1 for row in subset if not row["reanalysed"])
    checked = [row for row in subset if row["missed_change"] is not None]
    baseline = [row for row in project_rows if row["gate"] == "always"]
    tokens = sum(row["tokens"] for row in subset)

    return {
        "gate": gate,
        "runs": len(subset),
        "reanalysed": len(subset) - skipped,
        "skipped": skipped,
        "skip_rate": round2(rate(skipped, len(subset))),
        "missed": sum(1 for row in checked if row["missed_change"]) if checked else None,
        "miss_rate": round2(rate(sum(1 for r in checked if r["missed_change"]), len(checked))) if checked else None,
        "tokens": int(tokens),
        "tokens_saved": int(sum(r["tokens"] for r in baseline) - tokens) if baseline and gate != "always" else None,
        "median_latency_ms": median([row["latency_ms"] for row in subset]),
        "enough_runs": len(subset) >= MIN_RUNS_FOR_A_TRUSTWORTHY_RATE,
    }


def _skip_rate(rows: Sequence[Dict[str, Any]]) -> float:
    if not rows:
        return -1.0
    return sum(1 for row in rows if not row["reanalysed"]) / len(rows)


def _drift_rate(rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    points = sorted(
        (r for r in rows if r["divergences"] is not None or r["absences"] is not None),
        key=lambda r: r["commit_index"],
    )
    if len(points) < 2:
        return None
    span = max(1, points[-1]["commit_index"] - points[0]["commit_index"])
    start = (points[0]["divergences"] or 0) + (points[0]["absences"] or 0)
    end = (points[-1]["divergences"] or 0) + (points[-1]["absences"] or 0)
    return round2((end - start) / span)


def _projects_reading(entries, consistent, gate, skip_rates) -> str:
    if not entries:
        return "No projects recorded yet."
    if len(entries) == 1:
        return (
            "Only one project, so this table cannot say whether the result generalises. "
            "Add projects and re-run the replay — with three or more you can say something "
            "about generality, and with one you cannot."
        )

    parts = [
        f"With the `{gate}` gate, skip rates ranged from {percent(min(skip_rates))} to "
        f"{percent(max(skip_rates))} across {len(entries)} projects."
    ]

    misses = [e for e in entries if e["missed"]]
    if any(e["missed"] is None for e in entries):
        parts.append("Misses were not measured for every project.")
    elif not misses:
        parts.append("It missed nothing in any project.")
    else:
        worst = max(misses, key=lambda e: e["missed"])
        parts.append(
            f"It missed changes in {len(misses)} of {len(entries)} projects, at worst "
            f"{worst['missed']} in {worst['project']}."
        )

    if consistent:
        parts.append(
            "The gates rank in the same order in every project, so the result is not being "
            "driven by one repository — that sentence belongs in your threats-to-validity "
            "section."
        )
    else:
        differing = sorted({e["best_gate"] for e in entries if e["best_gate"]})
        parts.append(
            f"The gates do not rank the same way in every project (best gate is "
            f"{', '.join('`' + g + '`' for g in differing)} depending on the project). Say so "
            "explicitly rather than reporting only the pooled numbers."
        )

    thin = [e["project"] for e in entries if not e["enough_runs"]]
    if thin:
        parts.append(f"Too few runs to trust the rate in: {', '.join(thin)}.")
    return " ".join(parts)


# --- Table 4: the controlled test --------------------------------------------


def table_deviations(summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The seeded-deviation set: 16 deliberate changes with known right answers.

    The only part of the study with unambiguous ground truth, and until now it
    never reached the screen at all. Produced by
    `python research/evaluate_deviations.py --out results/`.
    """
    if not summary or not summary.get("strategies") or not summary.get("confusion"):
        return {
            "number": 4,
            "title": "The controlled test",
            "available": False,
            "rows": [],
            "reading": (
                "Not run yet. `python research/evaluate_deviations.py --out results/` takes "
                "seconds, needs no network and no API key, and gives you the only table in the "
                "study with unambiguous right answers. Run it first."
            ),
        }

    # `strategies` is the ordered list of gate names; the per-gate confusion
    # matrix lives in `confusion`, keyed by that same name. The two used to be
    # conflated here -- iterating `strategies` directly and calling `.get()` on
    # each name -- which raised on every real run this script has ever
    # produced, because a gate name is a string, not the matrix.
    confusion = summary["confusion"]
    entries = []
    for name in summary["strategies"]:
        cell = confusion.get(name)
        if not isinstance(cell, dict):
            continue
        caught = _int(cell.get("true_positive"))
        missed = _int(cell.get("false_negative"))
        false_alarms = _int(cell.get("false_positive"))
        ignored = _int(cell.get("true_negative"))
        entries.append(
            {
                "gate": name,
                "caught": caught,
                "missed": missed,
                "false_alarms": false_alarms,
                "correctly_ignored": ignored,
                "precision": round2(cell.get("precision")),
                "recall": round2(cell.get("recall")),
                "reading": (
                    f"Caught {caught} of {caught + missed} conformance-breaking changes"
                    + (f", missed {missed}" if missed else ", missed none")
                    + f". Re-analysed unnecessarily {false_alarms} time"
                    f"{'s' if false_alarms != 1 else ''}, and correctly ignored {ignored} "
                    "harmless change" + ("s" if ignored != 1 else "") + "."
                ),
            }
        )

    real = entries[0]["caught"] + entries[0]["missed"] if entries else 0
    perfect = [e["gate"] for e in entries if e["missed"] == 0]
    imperfect = [e for e in entries if e["missed"]]

    reading = (
        f"Of {real} deliberate changes that break conformance, "
        + (
            f"{', '.join('`' + g + '`' for g in perfect)} caught every one. "
            if perfect
            else "no gate caught all of them. "
        )
    )
    for entry in imperfect:
        reading += (
            f"`{entry['gate']}` missed {entry['missed']} — the known failure mode: a class "
            "renamed consistently everywhere leaves the code's shape unchanged, but still "
            "breaks a diagram that names that class. It is by design, and reporting it is "
            "stronger than hiding it. "
        )

    return {
        "number": 4,
        "title": "The controlled test",
        "available": True,
        "rows": entries,
        "conformance_breaking": real,
        "reading": reading.strip(),
    }


# --- the one significance test -----------------------------------------------


def compare_two_gates(
    rows: List[Dict[str, Any]], left: Optional[str] = None, right: Optional[str] = None
) -> Dict[str, Any]:
    """McNemar on the pair that matters: the recommended gate against the cheaper,
    riskier one. One test, not a family of six, so no correction is needed."""
    gates = _gates_in(rows)
    candidates = [gate for gate in gates if gate != "always"]

    if left is None or right is None:
        if len(candidates) < 2:
            return {
                "usable": False,
                "left": None,
                "right": None,
                "reason": "Fewer than two gates besides the baseline; nothing to compare.",
                "reading": "Run at least two gate policies to compare them.",
            }
        left, right = candidates[-2], candidates[-1]

    index = {(row["gate"], row["project"], row["commit"]): row for row in rows}
    shared = [
        (project, commit)
        for (gate, project, commit) in index
        if gate == left and (right, project, commit) in index
    ]
    shared.sort()

    result = mcnemar_exact(
        [index[(left, p, c)]["reanalysed"] for p, c in shared],
        [index[(right, p, c)]["reanalysed"] for p, c in shared],
    )
    result["left"] = left
    result["right"] = right
    result["p_text"] = p_value_text(result["p_value"])
    result["reading"] = _comparison_reading(result)
    return result


def _comparison_reading(result: Dict[str, Any]) -> str:
    left, right = result["left"], result["right"]
    if not result["usable"]:
        return (
            f"Cannot test `{left}` against `{right}` yet: {result['reason']} "
            "This test needs commits where the two gates actually disagreed."
        )

    lead = (
        f"On the {result['paired_observations']} commits both gates saw, they disagreed "
        f"{result['discordant']} times: `{left}` re-analysed and `{right}` skipped on "
        f"{result['left_only']}, the reverse on {result['right_only']}."
    )

    if result["p_value"] < 0.05:
        verdict = (
            f" That split is too lopsided to be chance (McNemar's exact test, "
            f"p {result['p_text']}), so the difference between these two gates is real "
            "rather than an accident of which commits happened to be in the corpus."
        )
    else:
        verdict = (
            f" That split is within what chance would produce (p {result['p_text']}), so this "
            "corpus does not show the two gates behaving differently. That is not proof they "
            "are the same — it usually means more commits are needed."
        )

    return lead + verdict


# --- charts ------------------------------------------------------------------


def chart_data(rows: List[Dict[str, Any]], gate_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Exactly two. Both plot numbers that already appear in a table above, so a
    reader can check the picture against the figures."""
    skip_by_gate = [
        {
            "gate": entry["gate"],
            "skip_rate": entry["skip_rate"],
            "low": entry["skip_low"],
            "high": entry["skip_high"],
            "miss_rate": entry["miss_rate"],
            "missed": entry["missed"],
            "runs": entry["runs"],
        }
        for entry in gate_rows
    ]

    drift = []
    for project in sorted({row["project"] for row in rows}):
        points = sorted(
            (
                row
                for row in rows
                if row["project"] == project
                and (row["divergences"] is not None or row["absences"] is not None)
            ),
            key=lambda row: row["commit_index"],
        )
        seen = set()
        series = []
        for point in points:
            if point["commit_index"] in seen:
                continue
            seen.add(point["commit_index"])
            series.append(
                {
                    "commit_index": point["commit_index"],
                    "divergences": point["divergences"] or 0,
                    "absences": point["absences"] or 0,
                    "violations": (point["divergences"] or 0) + (point["absences"] or 0),
                }
            )
        if len(series) >= 2:
            drift.append({"project": project, "points": series})

    # Figure 3: the tradeoff the whole paper is about, in one picture. A gate
    # is *dominated* when another gate skipped at least as much and caught at
    # least as many real changes -- there is then no reason to prefer it.
    #
    # Point estimates alone would let a gate be declared dominated on a
    # difference far smaller than the uncertainty in the estimate, so dominance
    # is reported twice: the plain empirical version, and a `robust` version
    # that additionally requires the two Wilson intervals not to overlap on the
    # axis where the winner is strictly ahead.
    plottable = [entry for entry in gate_rows if entry.get("recall") is not None]
    if len(plottable) < 2:
        pareto: Dict[str, Any] = {
            "available": False,
            "reason": (
                "Needs at least two gates with a measured recall. Recall is only defined "
                "once an oracle has established which commits actually changed."
            ),
            "data": [],
        }
    else:
        def _beats(win: Dict[str, Any], lose: Dict[str, Any]) -> bool:
            return (
                win["skip_rate"] >= lose["skip_rate"]
                and win["recall"] >= lose["recall"]
                and (win["skip_rate"] > lose["skip_rate"] or win["recall"] > lose["recall"])
            )

        def _separated(win: Dict[str, Any], lose: Dict[str, Any]) -> bool:
            """True when the intervals do not overlap on at least one axis."""
            skip_clear = (
                win["skip_low"] is not None
                and lose["skip_high"] is not None
                and win["skip_low"] > lose["skip_high"]
            )
            recall_clear = (
                win["recall_low"] is not None
                and lose["recall_high"] is not None
                and win["recall_low"] > lose["recall_high"]
            )
            return bool(skip_clear or recall_clear)

        points = []
        for entry in plottable:
            beaten_by = [other["gate"] for other in plottable if _beats(other, entry)]
            robust = [
                other["gate"]
                for other in plottable
                if _beats(other, entry) and _separated(other, entry)
            ]
            points.append(
                {
                    "gate": entry["gate"],
                    "skip_rate": entry["skip_rate"],
                    "skip_low": entry["skip_low"],
                    "skip_high": entry["skip_high"],
                    "recall": entry["recall"],
                    "recall_low": entry["recall_low"],
                    "recall_high": entry["recall_high"],
                    "changed_checked": entry["changed_checked"],
                    "dominated_by": beaten_by,
                    "robustly_dominated_by": robust,
                    "on_frontier": not beaten_by,
                }
            )
        pareto = {"available": True, "reason": "", "data": points}

    return {
        "pareto": {
            "title": "Figure 3 — What each gate saves, against what it catches",
            "caption": (
                "Each gate is one point: how often it skipped, against how often it "
                "re-analysed when conformance had really changed. Bars are 95% intervals. "
                "A gate on the frontier is a defensible choice; a gate inside it was beaten "
                "on both axes at once. Dominance is only called \"clear\" when the intervals "
                "do not overlap."
            ),
            **pareto,
        },
        "skip_by_gate": {
            "title": "Figure 1 — How much each gate skipped",
            "caption": (
                "Bar length is the share of runs skipped; the label on each bar is how many "
                "real changes that gate missed. Both numbers are shown together because "
                "neither means anything alone."
            ),
            "data": skip_by_gate,
        },
        "drift": {
            "title": "Figure 2 — Design violations building up over commits",
            "caption": (
                "Divergences (code does something the diagram does not describe) plus absences "
                "(the diagram describes something the code no longer does), accumulating as "
                "each project's history advances."
            ),
            "data": drift,
        },
    }


# --- entry point -------------------------------------------------------------


def build_report(
    rows: Sequence[Dict[str, Any]],
    *,
    default_project: str = "project",
    deviations: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalised = normalise_rows(rows, default_project=default_project)

    if not normalised:
        return {
            "usable": False,
            "reason": (
                "No analysis runs recorded yet. Analyse a project a few times, or run "
                "`python research/replay.py --corpus research/corpus.json` to generate a full "
                "dataset."
            ),
            "deviations": table_deviations(deviations),
        }

    inferred = infer_missing_labels(normalised)
    study = table_study(normalised)
    gates = table_gates(normalised)
    projects = table_projects(normalised, gates["recommended"].get("gate"))
    deviation_table = table_deviations(deviations)
    comparison = compare_two_gates(normalised)

    return {
        "usable": True,
        "inferred_labels": inferred,
        "study": study,
        "gates": gates,
        "projects": projects,
        "deviations": deviation_table,
        "comparison": comparison,
        "configuration": study_configuration(normalised),
        "charts": chart_data(normalised, gates["rows"]),
        "headline": _headline(study, gates, projects),
        "how_to_read": HOW_TO_READ,
        "tokens": describe([row["tokens"] for row in normalised]),
    }


def _headline(study, gates, projects) -> str:
    """The one paragraph to read if you read nothing else on the page."""
    recommended = gates["recommended"]
    if not recommended.get("gate"):
        return (
            f"{study['runs']:,} runs across {study['projects']} project(s). "
            + recommended.get("reason", "")
        )

    sentence = recommended["reason"]
    if projects["rows"] and len(projects["rows"]) > 1:
        sentence += (
            f" Across projects its skip rate ranged from {percent(projects['lowest_skip_rate'])} "
            f"to {percent(projects['highest_skip_rate'])}."
        )
    return sentence


HOW_TO_READ = [
    {
        "term": "Skipped / skip rate",
        "meaning": (
            "The gate decided nothing important had changed, reused the previous result, and "
            "did not call the language model. This is the saving."
        ),
    },
    {
        "term": "Missed / miss rate",
        "meaning": (
            "The gate skipped a commit where the findings actually did change — so it was "
            "wrong to skip. This is the cost of the saving. Never quote one without the other."
        ),
    },
    {
        "term": "between X% and Y%",
        "meaning": (
            "A 95% interval. If the study were repeated, the true rate would very likely land "
            "in this range. A wide range means few runs, not a bad gate."
        ),
    },
    {
        "term": "Tokens saved",
        "meaning": (
            "How many fewer tokens this gate spent than re-analysing every commit."
        ),
    },
    {
        "term": "Divergence / absence",
        "meaning": (
            "Divergence: the code does something the diagram does not describe. Absence: the "
            "diagram describes something the code no longer does. Standard vocabulary in this "
            "field — use these words in the paper."
        ),
    },
    {
        "term": "McNemar's test",
        "meaning": (
            "Asks whether two gates really behave differently, or whether the difference could "
            "be chance. It looks only at commits where the two disagreed, because the same "
            "commits go through both gates."
        ),
    },
]
