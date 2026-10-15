"""Fig. 1 of the paper: one analysis, with the gate placed after the verdict.

    python research/make_pipeline_figure.py --out paper/figures/
"""
import argparse
import os

BLUE, ORANGE, INK, MUTED, FILL = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#f3f2ee"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join("paper", "figures"))
    args = parser.parse_args(argv)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    plt.rcParams.update({"font.family": "serif", "font.size": 7.5, "svg.fonttype": "none"})
    fig, ax = plt.subplots(figsize=(3.45, 3.9))
    ax.set_xlim(0, 102)
    ax.set_ylim(0, 112)
    ax.axis("off")

    def box(x, y, w, h, text, edge=MUTED, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.5",
                                    linewidth=1.0, edgecolor=edge, facecolor=FILL))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=INK,
                fontweight="bold" if bold else "normal", linespacing=1.25)

    def arrow(x0, y0, x1, y1, colour=MUTED, style="solid"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=7,
                                     linewidth=0.9, color=colour, linestyle=style))

    def label(x, y, text, colour=INK, italic=True, ha="left"):
        ax.text(x, y, text, color=colour, fontsize=6.4, ha=ha, va="center",
                style="italic" if italic else "normal")

    # Inputs. The strip at x < 10 is reserved for the gate's input channel.
    box(12, 98, 41, 11, "Source tree\n(Python, Java, JS/TS,\nC#, PHP)")
    box(59, 98, 41, 11, "StarUML class model\n(.mdj, frozen)")
    # Extraction
    box(12, 80, 41, 11, "tree-sitter extraction:\ngraph + fingerprint")
    box(59, 80, 41, 11, "Design model: classes,\nmembers, relations")
    arrow(32.5, 98, 32.5, 91.5)
    arrow(79.5, 98, 79.5, 91.5)
    # Verdict, computed on every commit
    box(16, 60, 80, 12, "Deterministic comparison = verdict\nconvergences, divergences, absences, score",
        edge=BLUE)
    arrow(32.5, 80, 44, 72.5)
    arrow(79.5, 80, 68, 72.5)
    label(56, 76.5, "every commit", colour=BLUE, italic=False, ha="center")
    # Gate: reads only code structure, through the left channel
    box(36, 40, 40, 10, "Gate\n(code structure only)", edge=ORANGE, bold=True)
    arrow(56, 60, 56, 50.5)
    ax.plot([12, 4, 4], [85.5, 85.5, 45], color=ORANGE, lw=0.9, ls=(0, (3, 2)))
    arrow(4, 45, 35.5, 45, colour=ORANGE, style=(0, (3, 2)))
    label(5.5, 51, "fingerprint\n+ graph", colour=ORANGE, italic=False)
    # Outcomes
    box(12, 19, 41, 12, "Reuse explanation\n(relabel on rename)")
    box(59, 19, 41, 12, "Re-analyse: model sees\nchanged subgraph\n+ 1-hop impact set")
    arrow(48, 40, 34, 31.5)
    arrow(64, 40, 78, 31.5)
    label(30, 37, "skip")
    label(75, 37, "fire")
    # Persist
    box(24, 1, 64, 10, "Version store (3) + per-run ledger")
    arrow(32.5, 19, 46, 11.5)
    arrow(79.5, 19, 66, 11.5)

    fig.tight_layout(pad=0.2)
    os.makedirs(args.out, exist_ok=True)
    fig.savefig(os.path.join(args.out, "fig-pipeline.svg"))
    fig.savefig(os.path.join(args.out, "fig-pipeline.png"), dpi=300)
    print("Wrote fig-pipeline.svg/.png")


if __name__ == "__main__":
    main()
