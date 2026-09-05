# The statistics, in one page

Four tables, one significance test, two charts. That is all of it.

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

**Table 3 — Did it work on every project?** The same numbers per project, for
the recommended gate, plus whether the ordering of gates is the same everywhere.

**Table 4 — The controlled test.** Sixteen deliberate design changes with known
right answers — nine that break conformance, seven that do not. The only table
with unambiguous ground truth. Produced by `evaluate_deviations.py`.

**The one test.** McNemar's exact test between the two candidate gates. The
design is paired — every commit goes through every gate — so only the commits
where the two *disagreed* carry information. One comparison, so no
multiple-comparison correction is needed.

**Two charts.** Skip rate per gate with the miss count on each bar; design
violations accumulating over commits.

---

## Three rules the code enforces

1. **Skip rate and miss rate are never quoted apart.** A gate that never skips
   has a perfect miss rate and saves nothing. The chart draws them in one
   figure for this reason.
2. **Miss rate is "not measured", never zero,** when no forced full analysis
   exists to disagree with. A zero you did not measure is the most damaging
   thing you can put in a paper.
3. **A rate from fewer than ten runs is flagged.** 2/5 and 80/200 both print as
   40%; only one is worth quoting.

---

## What was removed, and what to do if a reviewer asks

Regression models, cross-validated classifiers, survival analysis, cluster
bootstrapping, rank correlations and six corrected pairwise tests were all
implemented here and have been deleted. They were correct and unreadable.

If a reviewer asks for a specific one, add back **that one test**, for the one
comparison it applies to. Do not restore the package.

---

## Words you will need

| Term | Meaning |
|---|---|
| **Skipped / skip rate** | The gate reused the previous result and did not call the model. The saving. |
| **Missed / miss rate** | The gate skipped a commit whose findings had actually changed. The cost. |
| **between X% and Y%** | 95% Wilson interval. Wide means few runs, not a bad gate. |
| **Divergence** | The code does something the diagram does not describe. |
| **Absence** | The diagram describes something the code no longer does. |
| **McNemar's test** | Whether two gates really differ, using only the commits where they disagreed. |

Use *divergence* and *absence* in the paper — they are the standard vocabulary
in this field, thirty years old, and every reviewer will know them.
