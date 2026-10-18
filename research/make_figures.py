"""Vector figures for the paper, from the replay and the statistics report.

    python research/make_figures.py --results results/ --out paper/figures/

Writes SVG (scales cleanly into a two-column layout):

    fig-drift.svg      divergences and absences at every commit, one panel per project
    fig-survival.svg   Kaplan-Meier survival of initially conforming design elements
    fig-gates.svg      skip rate against recall per gate, 95% Wilson intervals

Colours are the first slots of a categorical palette validated for colour-vision
deficiency (all pairs); every series is also directly labelled, so identity
never rests on colour alone. Requires matplotlib (optional dependency).
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from stats.drift import element_survival, trajectories  # noqa: E402
from stats.report import normalise_rows  # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SERIES = [BLUE, ORANGE, AQUA]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def _style(plt):
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 8,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "axes.titlesize": 8.5,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "svg.fonttype": "none",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fig_drift(plt, rows, out):
    traj = trajectories(rows)
    projects = sorted(traj, key=lambda p: -len(traj[p]))
    fig, axes = plt.subplots(1, len(projects), figsize=(7.0, 2.1), squeeze=False)
    for ax, project in zip(axes[0], projects):
        pts = traj[project]
        x = [p["commit_index"] for p in pts]
        ax.plot(x, [p["divergences"] for p in pts], color=BLUE, lw=1.6, drawstyle="steps-post")
        ax.plot(x, [p["absences"] for p in pts], color=ORANGE, lw=1.6, drawstyle="steps-post")
        ax.set_title(project, loc="left", color=INK)
        ax.set_xlabel("commits after diagram freeze")
        ax.set_ylim(bottom=0)
        # The higher line is labelled above itself and the lower one below,
        # unless the lower one sits so close to the axis that "below" would
        # put the label on it.
        top = max(pts[-1]["divergences"], pts[-1]["absences"], 1)
        for name in ("divergences", "absences"):
            value = pts[-1][name]
            other = pts[-1]["absences" if name == "divergences" else "divergences"]
            above = value >= other or value < 0.15 * top
            ax.annotate(name, (x[-1], value), textcoords="offset points",
                        xytext=(-2, 4 if above else -9), ha="right", color=INK, fontsize=7)
    axes[0][0].set_ylabel("count (oracle)")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig-drift.svg"))
    fig.savefig(os.path.join(out, "fig-drift.png"), dpi=300)
    plt.close(fig)


def fig_drift_corpus(plt, drift, out):
    """One dot per project: net change in divergences against net change in absences.

    Per-project panels stop being readable past a handful of projects; this
    keeps the direction claim visible at corpus scale. Points below the y = x
    line are divergence-led, above it absence-led. Symmetric-log axes, because
    a few projects drift by hundreds and most by a handful.
    """
    projects = [p for p in drift["projects"] if p.get("measured", True)]
    xs = [p["net_divergence"] for p in projects]
    ys = [p["net_absence"] for p in projects]
    fig, ax = plt.subplots(figsize=(3.4, 2.7))
    ax.set_xscale("symlog", linthresh=5)
    ax.set_yscale("symlog", linthresh=5)
    lim = max(max(map(abs, xs + ys)), 10) * 1.6
    ax.plot([-lim, lim], [-lim, lim], color=MUTED, lw=0.8, ls=(0, (3, 3)), zorder=1)
    ax.scatter(xs, ys, s=22, color=BLUE, edgecolors="white", linewidths=1.0, zorder=3)
    # Label only the projects that drifted most, so the labels stay legible.
    offsets = [((6, -3), "left"), ((-7, 7), "right")]
    top = sorted(projects, key=lambda p: -(abs(p["net_divergence"]) + abs(p["net_absence"])))[:1]
    for (offset, ha), p in zip(offsets, sorted(top, key=lambda p: -p["net_divergence"])):
        ax.annotate(p["project"], (p["net_divergence"], p["net_absence"]), textcoords="offset points",
                    xytext=offset, ha=ha, va="center", color=INK, fontsize=6.5)
    ticks = [t for t in (-100, -10, 0, 10, 100, 1000) if abs(t) <= lim]
    ax.set_xticks(ticks); ax.set_yticks(ticks)
    ax.set_xticklabels([f"{t:+d}" if t else "0" for t in ticks])
    ax.set_yticklabels([f"{t:+d}" if t else "0" for t in ticks])
    ax.minorticks_off()
    ax.annotate("absence-led", (-lim * 0.6, lim * 0.5), color=MUTED, fontsize=7, ha="left")
    ax.annotate("divergence-led", (lim * 0.6, -lim * 0.5), color=MUTED, fontsize=7, ha="right")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("net change in divergences")
    ax.set_ylabel("net change in absences")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig-drift.svg"))
    fig.savefig(os.path.join(out, "fig-drift.png"), dpi=300)
    plt.close(fig)


def fig_survival_pooled(plt, element_rows, out):
    """Kaplan-Meier over every initially conforming element of every project."""
    pooled = [dict(row, project="all", element=f"{row['project']}::{row['element']}") for row in element_rows]
    s = element_survival(pooled)["all"]
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    xs, ys = [0], [1.0]
    for point in s["curve"]:
        xs.append(point["commit"]); ys.append(point["survival"])
    xs.append(s["window_commits"] - 1); ys.append(ys[-1])
    ax.step(xs, ys, where="post", color=BLUE, lw=1.6)
    ax.annotate(f"{s['conforming_at_freeze']} elements conforming at the freeze", (xs[-1], 1.0),
                textcoords="offset points", xytext=(-2, -2), ha="right", va="top", color=INK, fontsize=7)
    ax.axhline(0.5, color=MUTED, lw=0.8, ls=(0, (3, 3)))
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("commits after diagram freeze")
    ax.set_ylabel("share still conforming")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig-survival.svg"))
    fig.savefig(os.path.join(out, "fig-survival.png"), dpi=300)
    plt.close(fig)


def fig_survival(plt, element_rows, out):
    survival = element_survival(element_rows)
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    for colour, (project, s) in zip(SERIES, sorted(survival.items())):
        if not s["conforming_at_freeze"]:
            continue
        xs, ys = [0], [1.0]
        for point in s["curve"]:
            xs.append(point["commit"]); ys.append(point["survival"])
        xs.append(s["window_commits"] - 1); ys.append(ys[-1])
        ax.step(xs, ys, where="post", color=colour, lw=1.6)
        ax.annotate(f"{project} (n={s['conforming_at_freeze']})", (xs[-1], ys[-1]),
                    textcoords="offset points", xytext=(-2, 4), ha="right", color=INK, fontsize=7)
    ax.axhline(0.5, color=MUTED, lw=0.8, ls=(0, (3, 3)))
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("commits after diagram freeze")
    ax.set_ylabel("share still conforming")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig-survival.svg"))
    fig.savefig(os.path.join(out, "fig-survival.png"), dpi=300)
    plt.close(fig)


def fig_gates(plt, statistics, out):
    rows = statistics["gates"]["rows"]
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    markers = {"always": "o", "content": "s", "structural": "D", "isomorphism": "^"}
    for row in rows:
        if row.get("recall") is None:
            continue
        x, y = row["skip_rate"], row["recall"]
        xerr = [[x - (row["skip_low"] or x)], [(row["skip_high"] or x) - x]]
        yerr = [[y - (row["recall_low"] or y)], [(row["recall_high"] or y) - y]]
        ax.errorbar(x, y, xerr=xerr, yerr=yerr, fmt=markers.get(row["gate"], "o"),
                    color=BLUE, ms=6, mec="white", mew=1.2, elinewidth=0.9, capsize=2)
        # The gated policies cluster near the top; each label sits at its own
        # marker (above, below, right) so no name is read against a neighbour.
        offset, ha = {
            "always": ((7, -11), "left"),
            "content": ((0, 9), "center"),
            "structural": ((0, -15), "center"),
            "isomorphism": ((9, -14), "left"),
        }.get(row["gate"], ((6, -10), "left"))
        ax.annotate(row["gate"], (x, y), textcoords="offset points", xytext=offset,
                    ha=ha, color=INK, fontsize=7)
    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(min(0.0, ax.get_ylim()[0]), 1.12)
    ax.set_xlabel("skip rate (share of commits with no model call)")
    ax.set_ylabel("recall of conformance changes")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig-gates.svg"))
    fig.savefig(os.path.join(out, "fig-gates.png"), dpi=300)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", default="results")
    parser.add_argument("--out", default=os.path.join("paper", "figures"))
    args = parser.parse_args(argv)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is needed for figures: pip install matplotlib", file=sys.stderr)
        return 2
    _style(plt)
    os.makedirs(args.out, exist_ok=True)

    rows = normalise_rows(read_csv(os.path.join(args.results, "runs.csv")))
    corpus = len({row["project"] for row in rows}) > 3
    drift_path = os.path.join(args.results, "drift.json")
    if corpus and os.path.isfile(drift_path):
        with open(drift_path, encoding="utf-8") as handle:
            fig_drift_corpus(plt, json.load(handle), args.out)
    else:
        fig_drift(plt, rows, args.out)
    elements = os.path.join(args.results, "drift_elements.csv")
    if os.path.isfile(elements):
        (fig_survival_pooled if corpus else fig_survival)(plt, read_csv(elements), args.out)
    stats_path = os.path.join(args.results, "statistics.json")
    if os.path.isfile(stats_path):
        with open(stats_path, encoding="utf-8") as handle:
            fig_gates(plt, json.load(handle), args.out)
    print(f"Wrote figures to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
