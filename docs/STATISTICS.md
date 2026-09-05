# The statistics, in one page

Four tables, one significance test, three charts. That is all of it.

Every table on the Statistics page and in `results/REPORT.md` is followed by a
**sentence generated from its own numbers**. You should not have to interpret
anything — if a table needs explaining, the explanation is already under it.

---

## Getting the numbers

```bash
# 1. The controlled test — seconds, no network, no API key. Do this first.
python research/evaluate_deviations.py --out results/

# 2. The corpus study — needs git and a filled-in research/corpus.json.
python research/replay.py --corpus research/corpus.json --out results/

# 3. The tables.
python research/analyze_statistics.py --runs results/runs.csv --out results/
```

Or, from live use of the app with no replay at all:

```bash
python research/analyze_statistics.py --workspace backend/workspace --out results/
```

**Open `results/REPORT.md` first.** It is written to be read start to finish.

| Output | What it is |
|---|---|
| `REPORT.md` | Every table with its plain-English sentence |
| `statistics.json` | The whole report, sentences included |
| `tables/*.csv` | One CSV per table |
| `tables-tex/*.tex` | One LaTeX file per table — `\input` these into the paper |

---

## The four tables

**Table 1 — What was studied.** Projects, commits, runs, and whether miss rate is
measurable at all.

**Table 2 — How each gate performed.** *The paper.* Per gate: runs,
re-analysed, skipped, skip rate with a 95% interval, **missed** as a count,
miss rate, tokens, tokens saved. It also names a **recommended gate**: the most
economical one that missed nothing.

Two denominators appear here and they answer different questions. Both are
printed, and the column headings say which is which:

| Column | Denominator | Answers |
|---|---|---|
| **missed, all runs** | every run for that gate | How often, across the whole history, was this gate carrying a stale answer? |
| **caught, of real changes** (recall) | only commits where conformance actually changed | When there *was* something to find, did this gate go and look? |

The second is the one a reviewer will ask for. Most commits change nothing, so a
gate can post a near-zero miss rate simply by skipping a long quiet stretch —
the unconditional rate flatters exactly the gates that skip most. **Recall** is
the share of commits where conformance really changed that the gate re-analysed;
**specificity** is the share of unchanged commits it correctly skipped. Both
carry Wilson intervals and both are `null` — printed as "not measured" — when no
oracle established which commits changed.

Ground truth for "did conformance change" is the forced full analysis at a
commit compared against the forced full analysis at the *previous* commit. It is
never derived from a gated run: doing so would make the ground truth depend on
the thing being evaluated.

**Table 2b — Gate accuracy** (LaTeX export only). Recall, specificity and the
recovery horizon, split out because IEEE Access is double-column and Table 2 is
already nine columns wide.

**Recovery horizon.** How many commits pass between a gate missing a change and
the next check that agrees with the oracle again. It turns "this gate missed 2%
of changes" into a claim about how long the staleness lasted. A miss still
outstanding when a project's history ends is **censored** — known to be at least
that long, exact length unknown — so the median is Kaplan-Meier rather than a
plain median, and is reported as `null` when too many are outstanding for a
median to exist. In that case the table prints "more than N" rather than
inventing a midpoint. Censored misses are never counted as zero and never
dropped: dropping them would bias the median downwards, because the longest gaps
are precisely the ones most likely to outrun the end of the history.

**Table 3 — Did it work on every project?** The same numbers per project, for
the recommended gate, plus whether the ordering of gates is the same everywhere.

**Table 4 — The controlled test.** Sixteen deliberate design changes with known
right answers — nine that break conformance, seven that do not. The only table
with unambiguous ground truth. Produced by `evaluate_deviations.py`.

**The one test.** McNemar's exact test between the two candidate gates. The
design is paired — every commit goes through every gate — so only the commits
where the two *disagreed* carry information. One comparison, so no
multiple-comparison correction is needed.

**Three charts.** Figure 1: skip rate per gate with the miss count on each
bar. Figure 2: design violations accumulating over commits. Figure 3: the
Pareto frontier — skip rate against recall, one point per gate, with 95%
intervals on both axes.

Figure 3 is the tradeoff the paper is about, in one picture. A gate with another
gate both above it and to its right was beaten on both counts at once and there
is no reason to choose it. Dominance is reported twice: the plain empirical
version, and a stricter one that additionally requires the two intervals not to
overlap. Only the second is called clear, because a scatter plot invites
over-reading a difference smaller than its own uncertainty.

---

## Three rules the code enforces

1. **Skip rate and miss rate are never quoted apart.** A gate that never skips
   has a perfect miss rate and saves nothing. Figures 1 and 3 both draw them
   together for this reason.
2. **Miss rate, recall, specificity and the recovery horizon are "not
   measured", never zero,** when no forced full analysis exists to disagree
   with. A zero you did not measure is the most damaging thing you can put in a
   paper.
3. **A rate from fewer than ten runs is flagged.** 2/5 and 80/200 both print as
   40%; only one is worth quoting.
4. **Every rate says what it divided by.** Two miss rates with different
   denominators live in Table 2, so neither is labelled simply "miss rate".
5. **McNemar needs at least six disagreements.** At five, the most lopsided
   possible split gives p = 0.0625 — no outcome could reach the 0.05 the rest
   of the report uses, so quoting "not significant" there would invite the
   reader to treat it as evidence of no difference.

---

## What was removed, and what to do if a reviewer asks

Regression models, cross-validated classifiers, survival analysis, cluster
bootstrapping, rank correlations and six corrected pairwise tests were all
implemented here and have been deleted. They were correct and unreadable.

If a reviewer asks for a specific one, add back **that one test**, for the one
comparison it applies to. Do not restore the package.

The Kaplan-Meier median behind the recovery horizon is exactly such a targeted
addition: one twenty-line function handling censoring, not a reopening of the
deleted survival-analysis package.

---

## Words you will need

| Term | Meaning |
|---|---|
| **Skipped / skip rate** | The gate reused the previous result and did not call the model. The saving. |
| **Missed, all runs** | Misses divided by every run. Flattered by long quiet stretches — read it beside recall. |
| **Recall** | Of the commits where conformance really changed, the share the gate re-analysed. The cost of skipping, honestly denominated. |
| **Specificity** | Of the commits where nothing changed, the share the gate correctly skipped. |
| **Recovery horizon** | How many commits pass before a missed change is picked up again. |
| **Censored** | A miss still outstanding when the history ended. Counted, never treated as zero, never dropped. |
| **Dominated** | Another gate skipped at least as much *and* caught at least as many real changes. No reason to prefer this one. |
| **between X% and Y%** | 95% Wilson interval. Wide means few runs, not a bad gate. |
| **Divergence** | The code does something the diagram does not describe. |
| **Absence** | The diagram describes something the code no longer does. |
| **McNemar's test** | Whether two gates really differ, using only the commits where they disagreed. |

Use *divergence* and *absence* in the paper — they are the standard vocabulary
in this field, thirty years old, and every reviewer will know them.
