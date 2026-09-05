# Understanding docs — what each thing is, and what you should see

`START-HERE.md` tells you *what to do*. This tells you *what it means* and
*what a correct result looks like*, so you can tell working from broken.

---

## 1. What the project actually is, in four sentences

You have a UML class diagram and a codebase. The tool parses both, compares
them, and reports where they disagree. Because that check is expensive (it calls
a language model) and has to be repeated on every commit, the tool decides
**before calling the model** whether anything relevant actually changed.

**The paper's one claim:** that decision can skip most of the work without
missing real problems, and here is exactly what each version of the decision
costs.

Everything else in the repo exists to measure that one sentence.

---

## 2. The four gates — what they are

A "gate" is the decision *should we re-run the expensive analysis?*

| Gate | Re-runs when | Skips | The risk |
|---|---|---|---|
| `always` | every commit | nothing | costs the most; it is the yardstick |
| `content` | any file's bytes changed | nothing | pays for comment edits |
| `structural` | the code's *shape* changed | comments, formatting, renamed local variables | a change that keeps the shape is missed |
| `isomorphism` | shape changed **and** the graph isn't the same shape as before | also: whole-project renames | a rename that breaks a diagram naming that class is missed |

They go cheapest-risk to cheapest-cost, left to right. That trade is the paper.

---

## 3. The words you keep seeing

| Word | Means |
|---|---|
| **Skipped / skip rate** | The gate reused the previous answer and did not call the model. **The saving.** |
| **Missed / miss rate** | The gate skipped, but the answer had actually changed. It was wrong to skip. **The cost.** |
| **Oracle** | A forced full analysis run alongside every commit, so we can tell when a skip was wrong. Without it, miss rate cannot exist. |
| **Divergence** | The code does something the diagram does not describe. |
| **Absence** | The diagram describes something the code no longer does. |
| **Convergence** | Both agree. |
| **between X% and Y%** | A 95% interval. Wide = few runs, not a bad gate. |
| **Seeded deviation** | One of 16 deliberate changes we made on purpose, where we already know the right answer. |

**The one rule:** skip rate and miss rate are meaningless apart. A gate that
never skips has a perfect miss rate and saves nothing.

---

## 4. Every screen, and what you should see

### Dashboard
Your list of projects. A **Statistics/Results** button top right.

### Project → Setup
Upload code, upload the `.mdj`, pick a gate, press Run.
**You should see:** your files listed, and the diagram name once uploaded. If
the `.mdj` is rejected, the parser is telling you the file is malformed — it
refuses rather than scoring you against an empty design.

### Project → Results
The conformance report and the design graph.
**You should see:** boxes in fixed rows (Entry points → Application logic → Data
access → Model), arrows between them, and the same picture every time you open
it. Click a box to grey out everything it doesn't touch.
**You should not see:** dots floating or drifting. That is the old build.

### Project → History
The last three versions, cost per run, and the repeatability panel.

### Results (top-level)
Four tables and two charts. **Every table has a sentence underneath explaining
it.** If a table has no sentence, something is wrong.

---

## 5. The four tables, and what a good one looks like

**Table 1 — What was studied.** Counts. Sanity check only.
*Good:* Projects ≥ 4, runs ≥ 400, "Can we measure misses? **Yes**".
*Bad:* Projects 1, runs 3 — you have no study yet.

**Table 2 — How each gate performed.** The paper.
*Good:* `always` skips 0%. Each gate to the right skips more. At least one gate
missed 0. Tokens fall as skip rate rises.
*Bad:* every gate identical (your commits had no structural change), or Missed
reads "not measured" (no oracle — you skipped the replay).

**Table 3 — Did it work on every project?** One row per project.
*Good:* skip rates in a similar band, and the note says the gates rank the same
way everywhere.
*Bad:* one project at 90% and the rest at 10% — one repository is carrying your
average, and you must say so.

**Table 4 — The controlled test.** 16 changes with known right answers.
*Good:* `structural` catches all 9 conformance-breaking changes.
`isomorphism` misses exactly 1 — the rename. That is the designed failure and it
is a *good* sign it shows up.
*Bad:* not run. Run `evaluate_deviations.py`.

---

## 6. The two charts

**Figure 1 — skip rate per gate.** Bar = the saving. Tag on the right = the
cost, in words ("missed nothing" / "missed 3"). Both in one picture on purpose.

**Figure 2 — drift over commits.** A line going up means the code and the
diagram are drifting apart. Flat means they are keeping pace.

---

## 7. When something looks wrong

| What you see | What it means | Fix |
|---|---|---|
| "Missed: not measured" | No oracle in the data | Run `research/replay.py` |
| Table 4 empty | Controlled test not run | `python research/evaluate_deviations.py --out results/` |
| "few runs" warning | Fewer than 10 runs behind that rate | Analyse more commits. The rate is unstable, not wrong |
| Every gate has the same skip rate | Your commits contain no structural change | Use a project with real churn, not dependency bumps |
| Skip rate 100% | The gate never fired at all | Almost always: the diagram or the code never changed. Check the replay ran over real commits |
| Config panel says settings differ | Part of your corpus ran under different settings | Re-run the odd projects under one configuration |
| Graph nodes drift | Old build cached | Delete `frontend/node_modules/.vite`, restart `npm run dev` |
| Analysis finds no classes | tree-sitter grammars missing | `pip install tree-sitter-python tree-sitter-javascript tree-sitter-typescript tree-sitter-java` |

---

## 8. Every placeholder in the paper, and where it comes from

Open `paper/IEEE-Access-draft.docx` and `results/REPORT.md` side by side.

| In the paper | Comes from |
|---|---|
| `<TOOL>` | Pick a name. Use the same one everywhere |
| `<M>` projects, `<N>` commits | REPORT.md → Table 1 |
| `<M1>` / `<M2>` | How many diagrams came from a ground-truth repo vs you |
| `<languages>`, `<L>` | Which languages your corpus uses |
| `<X>`, `<Y>`, `<Z>` | REPORT.md → Table 2, the structural and isomorphism rows |
| Table 4 in the paper | REPORT.md → Table 2, copied across |
| Table 5 in the paper | REPORT.md → Table 4 (controlled test) |
| Table 6 in the paper | REPORT.md → Table 3 (per project) |
| Table 7 in the paper | REPORT.md → "How these runs were produced" |
| `<lo>`, `<hi>` | REPORT.md → Table 3, lowest and highest skip rate |
| `<n>`, `<d>`, `<a>`, `<b>`, `<p>` | REPORT.md → "Is the difference real?" |
| `<D>` drift | REPORT.md → Table 3, drift/commit column |
| `<R>`, `<A>` call resolution | The Results page, or any analysis result |
| `<G>` grounded ratio | Any analysis result, `grounded_node_ratio` |
| `<Zenodo DOI>` | After you upload the replication package |
| Figures 1, 2, 3 | Save as SVG buttons — see START-HERE §7 |
| Biographies | Write them. Required |

---

## 9. IEEE Access page rules

- **No minimum.** No hard maximum.
- **Under 20 pages strongly recommended.** Over 20 needs Editor-in-Chief
  approval *before* you submit.
- The draft is currently **7 pages** of text. With the three figures and the
  author biographies it lands around **10**, which is a normal length.
- Both a Word/LaTeX file **and** a matching PDF are required.
- Under 40 MB.
- Biographies below the references, one per author. **Most commonly missed item.**
- 3–10 keywords.
- AI-disclosure sentence in the acknowledgements if any text was AI-assisted.
- Review is **single-anonymised** (reviewers see your name) and the decision is
  **accept or reject** — at most one resubmission. Do not submit before the
  corpus study is finished.

---

## 10. What is in the repo

```
backend/          the analysis engine
  stats/          4 tables + McNemar, ~700 lines, pure Python
  core/pipeline.py   orchestrates one analysis run
  core/graph_diff.py the four gates live here
frontend/src/
  lib/layout.ts   the fixed graph layout (no physics)
  components/StatisticsPage.tsx   the Results page
research/
  evaluate_deviations.py   the controlled test  -> Table 4
  find_stale_diagrams.py   finds projects whose diagram was abandoned
  replay.py                the corpus study     -> Tables 1,2,3
  analyze_statistics.py    turns runs into tables
  corpus.recommended.json  six real projects, ready to edit
  models/                  YOUR FROZEN .mdj FILES GO HERE
paper/
  IEEE-Access-draft.docx   the manuscript — the only copy, edit this one
  build-docx.js            regenerates it if you ever need to
docs/
  START-HERE.md            what to do, in order
  UNDERSTANDING.md         this file
  CORPUS-AND-SUBMISSION.md which projects, and how to submit
  STATISTICS.md            the four tables in one page
results/                   created when you run things
```

---

## 11. The honest summary

Built and working: parser, UML reader, comparator, four gates, versioning,
statistics, graph, exports, replication packaging. 210 backend tests pass and
TypeScript compiles clean.

Not done: **the corpus**. You have 1 project and 3 runs. You need 4–6 projects
with frozen diagrams and 30–40 commits each.

That is the whole remaining project. Everything else is one afternoon.
