"""Conformance drift: how a codebase moves away from a frozen design.

The gate tables answer "what does it cost to keep checking?". This module
answers the question that makes checking worth paying for: *how fast, and in
which direction, does real code leave its diagram?*

Everything here is computed from the oracle's findings only -- the forced full
analysis at every commit -- so no number depends on which gate was in use.

Four measures, each answering one question:

    trajectory      What did convergences, divergences and absences look like
                    at each commit?                         (Figure: drift curve)
    direction       Is the code growing away from the design (divergence-led),
                    or is the design going stale (absence-led)? The two have
                    different remedies: the first wants review, the second
                    wants the diagram updated.
    survival        For each designed element that conformed when the diagram
                    was frozen, how many commits until it first deviated?
                    Kaplan-Meier, because most elements never deviate inside a
                    finite window and dropping them would bias the estimate.
    half-life       After how many commits had half the originally-conforming
                    elements deviated at least once? "Not reached" is a valid
                    and common answer, reported as "more than N".

Pure Python, standard library only, like the rest of `stats/`.
"""
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from stats.core import round2

DEVIATING = ("absent", "partial", "divergent")


# --- trajectories ---------------------------------------------------------------


def trajectories(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """One point per commit per project, from normalised run rows.

    Every gate's row for a commit carries the same oracle counts, so the first
    row seen for each (project, commit) is used and the rest are ignored.
    """
    seen = set()
    by_project: Dict[str, List[Dict[str, Any]]] = {}
    for row in sorted(rows, key=lambda r: (r["project"], r["commit_index"])):
        key = (row["project"], row["commit_index"])
        if key in seen:
            continue
        if row.get("divergences") is None and row.get("absences") is None:
            continue
        seen.add(key)
        by_project.setdefault(row["project"], []).append(
            {
                "commit_index": row["commit_index"],
                "commit": row.get("commit"),
                # Counts arrive as floats from the normaliser; they are counts.
                "divergences": int(row.get("divergences") or 0),
                "absences": int(row.get("absences") or 0),
                "similarity": row.get("similarity"),
                "source_touched": row.get("source_touched"),
                "conformance_changed": row.get("conformance_changed"),
            }
        )
    return by_project


def direction(points: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Net drift over the window, split into its two directions."""
    if len(points) < 2:
        return {"measured": False, "reason": "Fewer than two commits; drift needs a span."}

    first, last = points[0], points[-1]
    span = max(1, last["commit_index"] - first["commit_index"])
    d_div = last["divergences"] - first["divergences"]
    d_abs = last["absences"] - first["absences"]

    eroding = repairing = 0
    for before, after in zip(points, points[1:]):
        total_before = before["divergences"] + before["absences"]
        total_after = after["divergences"] + after["absences"]
        if total_after > total_before:
            eroding += 1
        elif total_after < total_before:
            repairing += 1

    touched = sum(1 for p in points[1:] if p.get("source_touched"))
    changed = sum(1 for p in points[1:] if p.get("conformance_changed"))

    if d_div == 0 and d_abs == 0:
        label = "stable"
    elif d_div > 0 and d_div >= max(d_abs, 0):
        label = "divergence-led"
    elif d_abs > 0:
        label = "absence-led"
    else:
        label = "converging"

    sim_first, sim_last = first.get("similarity"), last.get("similarity")
    return {
        "measured": True,
        "commits": len(points),
        "span": span,
        "divergences_start": first["divergences"],
        "divergences_end": last["divergences"],
        "absences_start": first["absences"],
        "absences_end": last["absences"],
        "net_divergence": d_div,
        "net_absence": d_abs,
        "drift_per_commit": round2((d_div + d_abs) / span),
        "drift_per_touching_commit": round2((d_div + d_abs) / touched) if touched else None,
        "eroding_commits": eroding,
        "repairing_commits": repairing,
        "conformance_changing_commits": changed,
        "source_touching_commits": touched,
        "similarity_start": sim_first,
        "similarity_end": sim_last,
        "similarity_min": min(
            (p["similarity"] for p in points if p.get("similarity") is not None), default=None
        ),
        "direction": label,
    }


# --- element survival -------------------------------------------------------------


def kaplan_meier(observations: Sequence[Tuple[int, bool]]) -> List[Tuple[int, float, int]]:
    """Survival curve from (time, event) pairs; event False means censored.

    Returns (time, survival after that time, at-risk before it) at each event
    time. Censored observations leave the risk set *after* events at the same
    time, the usual convention.
    """
    curve: List[Tuple[int, float, int]] = []
    at_risk = len(observations)
    survival = 1.0
    for moment in sorted({t for t, _ in observations}):
        events = sum(1 for t, e in observations if t == moment and e)
        leaving = sum(1 for t, _ in observations if t == moment)
        if events and at_risk:
            survival *= 1 - events / at_risk
            curve.append((moment, survival, at_risk))
        at_risk -= leaving
    return curve


def km_quantile(curve: Sequence[Tuple[int, float, int]], level: float) -> Optional[int]:
    """First time the survival curve falls to `level` or below, or None."""
    for moment, survival, _ in curve:
        if survival <= level + 1e-12:
            return moment
    return None


def element_survival(
    element_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Time to first deviation for every element conforming at the freeze commit.

    `element_rows` are rows of `drift_elements.csv`: project, commit_index,
    element, status. Elements already deviating at the first commit are not at
    risk -- they are counted separately as "deviating at freeze", because the
    question here is how long a conforming element *stays* conforming.
    """
    by_project: Dict[str, Dict[str, List[Tuple[int, str]]]] = {}
    for row in element_rows:
        project = str(row["project"])
        by_project.setdefault(project, {}).setdefault(str(row["element"]), []).append(
            (int(row["commit_index"]), str(row["status"]))
        )

    report: Dict[str, Dict[str, Any]] = {}
    for project, elements in sorted(by_project.items()):
        observations: List[Tuple[int, bool]] = []
        deviating_at_freeze = 0
        first_deviation: Dict[str, int] = {}
        last_index = 0
        for name, history in elements.items():
            history.sort()
            last_index = max(last_index, history[-1][0])
            start_index, start_status = history[0]
            if start_status in DEVIATING:
                deviating_at_freeze += 1
                continue
            event_at = next(
                (index for index, status in history if status in DEVIATING), None
            )
            if event_at is None:
                observations.append((history[-1][0] - start_index, False))
            else:
                observations.append((event_at - start_index, True))
                first_deviation[name] = event_at

        curve = kaplan_meier(observations)
        at_risk = len(observations)
        events = sum(1 for _, e in observations if e)
        half_life = km_quantile(curve, 0.5)
        final_survival = curve[-1][1] if curve else (1.0 if at_risk else None)

        report[project] = {
            "designed_elements": len(elements),
            "conforming_at_freeze": at_risk,
            "deviating_at_freeze": deviating_at_freeze,
            "deviated_during_window": events,
            "window_commits": last_index + 1,
            "survival_at_end": round2(final_survival),
            "half_life_commits": half_life,
            "half_life_censored_beyond": None if half_life is not None else last_index,
            "first_deviations": dict(sorted(first_deviation.items(), key=lambda kv: kv[1])),
            "curve": [
                {"commit": moment, "survival": round2(survival), "at_risk": risk}
                for moment, survival, risk in curve
            ],
        }
    return report


def pooled_survival(element_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """One Kaplan-Meier curve over every project's at-risk elements."""
    per_project = element_survival(element_rows)
    observations: List[Tuple[int, bool]] = []
    by_project: Dict[str, Dict[str, List[Tuple[int, str]]]] = {}
    for row in element_rows:
        by_project.setdefault(str(row["project"]), {}).setdefault(str(row["element"]), []).append(
            (int(row["commit_index"]), str(row["status"]))
        )
    for elements in by_project.values():
        for history in elements.values():
            history.sort()
            if history[0][1] in DEVIATING:
                continue
            event_at = next((i for i, s in history if s in DEVIATING), None)
            if event_at is None:
                observations.append((history[-1][0] - history[0][0], False))
            else:
                observations.append((event_at - history[0][0], True))
    curve = kaplan_meier(observations)
    return {
        "projects": len(per_project),
        "at_risk": len(observations),
        "events": sum(1 for _, e in observations if e),
        "half_life_commits": km_quantile(curve, 0.5),
        "survival_at_end": round2(curve[-1][1]) if curve else (1.0 if observations else None),
    }


# --- report ---------------------------------------------------------------------


def _direction_sentence(project: str, d: Dict[str, Any]) -> str:
    if not d.get("measured"):
        return f"{project}: {d.get('reason', 'not measured')}"
    change = {
        "stable": "conformance did not move across the window",
        "divergence-led": "the code grew away from the design (divergence-led)",
        "absence-led": "the design went stale as designed elements disappeared (absence-led)",
        "converging": "the code moved back towards the design",
    }[d["direction"]]
    return (
        f"{project}: over {d['commits']} commits {change}; divergences "
        f"{d['divergences_start']}→{d['divergences_end']}, absences "
        f"{d['absences_start']}→{d['absences_end']}, "
        f"{d['eroding_commits']} eroding and {d['repairing_commits']} repairing commits."
    )


def build_drift_report(
    rows: Sequence[Dict[str, Any]],
    element_rows: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """The drift section of the report, with a sentence per project."""
    traj = trajectories(rows)
    provenance = {}
    for row in rows:
        if row.get("provenance"):
            provenance.setdefault(row["project"], row["provenance"])

    projects = []
    for project, points in sorted(traj.items()):
        d = direction(points)
        projects.append(
            {
                "project": project,
                "provenance": provenance.get(project, ""),
                **d,
                "reading": _direction_sentence(project, d),
            }
        )

    element_rows = list(element_rows or [])
    survival = element_survival(element_rows) if element_rows else {}
    pooled = pooled_survival(element_rows) if element_rows else None

    return {
        "title": "Conformance drift",
        "projects": projects,
        "trajectories": traj,
        "survival": survival,
        "pooled_survival": pooled,
        "measured": bool(projects),
    }


def drift_markdown(report: Dict[str, Any]) -> str:
    """Render the drift section for REPORT.md."""
    lines = ["## Conformance drift", ""]
    if not report.get("measured"):
        lines.append("Not measured: no run carried oracle reflexion counts.")
        return "\n".join(lines) + "\n"

    lines += [
        "| Project | Provenance | Commits | Div. start→end | Abs. start→end | Drift/commit | Eroding | Repairing | Direction |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in report["projects"]:
        if not p.get("measured"):
            continue
        lines.append(
            f"| {p['project']} | {p['provenance'] or '—'} | {p['commits']} | "
            f"{p['divergences_start']}→{p['divergences_end']} | "
            f"{p['absences_start']}→{p['absences_end']} | {p['drift_per_commit']} | "
            f"{p['eroding_commits']} | {p['repairing_commits']} | {p['direction']} |"
        )
    lines.append("")
    for p in report["projects"]:
        lines.append(f"- {p['reading']}")
    lines.append("")

    if report.get("survival"):
        lines += [
            "### Element survival (time to first deviation)",
            "",
            "| Project | Designed | Conforming at freeze | Deviated in window | Survival at end | Half-life (commits) |",
            "|---|---|---|---|---|---|",
        ]
        for project, s in report["survival"].items():
            half = (
                str(s["half_life_commits"])
                if s["half_life_commits"] is not None
                else f"> {s['half_life_censored_beyond']} (not reached)"
            )
            lines.append(
                f"| {project} | {s['designed_elements']} | {s['conforming_at_freeze']} | "
                f"{s['deviated_during_window']} | {s['survival_at_end']} | {half} |"
            )
        pooled = report.get("pooled_survival") or {}
        if pooled:
            half = pooled["half_life_commits"]
            lines += [
                "",
                f"Pooled over {pooled['projects']} project(s): {pooled['events']} of "
                f"{pooled['at_risk']} initially conforming elements deviated inside the window; "
                + (
                    f"half had deviated by commit {half}."
                    if half is not None
                    else "fewer than half deviated, so the half-life is not reached."
                ),
            ]
    return "\n".join(lines) + "\n"
