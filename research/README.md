# Research harness

Everything needed to run the experiments behind the paper (see
`docs/CORPUS-AND-SUBMISSION.md` for corpus selection and `docs/START-HERE.md`
for the full run order). All three
scripts drive the real pipeline in-process, so what is measured is the code the
application runs.

## Prerequisites

```bash
cd backend
pip install -r requirements.txt      # tree-sitter grammars are required here
```

`git` must be on PATH for the commit replay. The scripts default to
`LLM_MODE=offline`, so nothing calls a paid API and the deterministic findings
are exactly reproducible; pass `--llm-mode auto` when you want a real model in
the loop.

## 0. Find projects worth testing on

```bash
python research/find_stale_diagrams.py --clone https://github.com/owner/name.git --out results/
```

Reports, for every UML model in a repository, how many source-touching commits
landed after the model was last edited. A model far behind is a corpus
candidate: the design is genuine and so is the drift. See
`docs/CORPUS-AND-SUBMISSION.md`.

## 1. Seeded deviations — labelled ground truth

Sixteen reproducible mutations of a reference project whose code matches its
diagram exactly: nine conformance-breaking deviations, two structure-only edits
(one adds an undocumented member, which is a divergence; one changes an arity,
which the name-based comparison does not see), and five negative controls that
must cost nothing. Ten change the deterministic findings and six do not, and
the oracle agrees with every one of the sixteen declared labels.

```bash
python research/evaluate_deviations.py --out results/
python research/evaluate_deviations.py --out results/ --git-branches ./deviation-repo
```

Produces `deviations.csv` and `deviations_summary.json` with a confusion matrix
per gate. `--git-branches` additionally materialises the set as a git repository
with one branch per deviation, for inspecting a case by eye or replaying it
through another tool. The programmatic mutations are the source of truth; the
branches are generated from them.

Start here. It runs in seconds, needs no network, and it is the only part of the
study with unambiguous labels.

## 2. Commit replay — the cost measurement

```bash
python research/replay.py --repo ../some-project --uml models/some-project.mdj --commits 40
python research/replay.py --corpus research/corpus.json --out results/
```

For each commit, each gate gets its own project and its own analysis, and a
separate always-forced run acts as the oracle.

**What a miss is.** The deterministic findings are recomputed on every run,
gated or not, so they can never be stale. What a gate can leave stale is the
*model-authored analysis* it reuses. Each gate therefore tracks which findings
its served analysis was produced for; a commit is a **missed change** when the
gate reused and those findings no longer equal the oracle's. A stale analysis
stays stale until the gate next re-analyses, and every commit in between is
counted (the "missed, all runs" denominator); the recovery horizon counts each
stale stretch once, from its onset.

Give `start` (the diagram-freeze commit) to replay forward from the design as
its author left it; `commits: 0` means every commit after it. `provenance`
labels where the design came from.

Produces `runs.csv` (one row per commit per gate), `drift_elements.csv` (one
row per designed element per commit) and `summary.json`. Feed
`runs.csv` to `research/analyze_statistics.py` to turn it into the paper's
tables, CSV/LaTeX exports, and the replication package.

## Building the corpus

`corpus.json` ships with the reference project only. Add real projects to it.
What makes a good one:

- **A class diagram is meaningful for it.** Layered applications with named
  services, repositories and controllers. Not scripts, not config-heavy repos.
- **A design model exists, or can be reverse-engineered once and then frozen.**
  Freezing it is the point: if the diagram moves with the code there is no drift
  to detect. Reverse-engineer from an early commit, then leave it alone.
- **30–50 consecutive commits with real churn.** Merge commits are excluded
  automatically. Avoid a window that is entirely dependency bumps.
- **`subdirectory`** narrows analysis to application code, excluding tests,
  generated code and build output — worth setting for most Java projects.

Aim for 5–10 projects. Fewer than five and per-project idiosyncrasy dominates;
the variance across projects is itself a result worth reporting.

## What each output column means

| Column | Meaning |
|---|---|
| `gate_allowed_llm` | The gate decided this commit needed a fresh analysis |
| `reused` | The gate served the previous version instead |
| `missed_change` | It reused, **and** the analysis it served was written for findings the oracle no longer reports |
| `diverges_from_oracle` | The served analysis disagrees with the oracle, reused or not |
| `conformance_changed` | The oracle's findings differ from the previous commit's (a property of the commit) |
| `source_touched` | Any analysed source file changed since the previous commit |
| `counterfactual_prompt_tokens` | Offline only: the prompt the gate *would* have sent; 0 when it reused |
| `convergences` / `divergences` / `absences` | The oracle's reflexion counts at this commit — the drift trajectory |
| `impact_nodes` | Size of the subgraph sent to the model when it did run |
| `call_resolution_rate` | Share of call sites attributed to exactly one target |
| `ambiguous_calls` | Call sites left unlinked because several targets matched |

The pairing that matters is `reuse rate` with `miss rate`. Either alone is
misleading: a gate that never fires has a perfect reuse rate and is useless.
