# How the code works

One analysis run, start to finish, and where every module fits. Read this before
changing anything.

---

## 1. The one-sentence version

Parse the code into a graph. Parse the UML into a graph. Compare them without a
model. Decide whether anything changed enough to be worth asking a model about.
If yes, ask it about only the part that changed. Save the result and a record of
what it cost.

---

## 2. One run, step by step

```
  source tree ──► PolyglotParser (tree-sitter) ──► architecture + fingerprints
  .mdj file   ──► StarUMLParser (two-pass)     ──► design model + relations
                            │
              build_implementation_graph  ◄── symbol-table call resolution
                            │
                   ComparisonEngine  (exact, no model)
                            │
                       decide_gate ──── reuse ──►  previous version, relabelled
                            │
                        re-analyse
                            │
              ai_service.evaluate_conformance  (scoped to the impact set)
                            │
              annotate + merge ──► version store (last 3) ──► run ledger
```

`backend/core/pipeline.py` is the orchestrator. Everything below is called from
there, in this order.

### Step 1 · Parse the code
`parsers/polyglot_parser.py` — tree-sitter grammars for Python, JavaScript,
TypeScript and Java. Produces modules, classes, interfaces, methods, functions,
and a **structural fingerprint** per file.

The fingerprint **includes** declarations, type annotations, base classes,
imports, and for each callable the *set* of names it calls. It **excludes** call
receivers, local variable names, statement order, comments, formatting, literals.

Why the callee set must be in: without it, a controller that quietly starts
calling the database directly is structurally identical to one that does not,
and the gate would never fire on the exact violation the tool exists to catch.

Why the exclusions are safe: none of them can change whether a class matches a
class diagram, because a class diagram does not describe them.

### Step 2 · Parse the diagram
`parsers/uml_parser.py` — reads StarUML `.mdj` in two passes: elements first,
then relationships, so a relationship can resolve both ends. A malformed file is
rejected outright rather than silently producing a score against an empty design.

### Step 3 · Build the graphs
`core/graph_builder.py` — turns parser output into NetworkX graphs.

Call edges are resolved through a project-wide symbol table: `self` calls, calls
through a typed field, through a local of known type, through a class name,
through an imported symbol, or to a unique global name. **A call site with
several equally plausible targets is left unlinked and counted, not linked to
all of them** — linking to all would invent edges and make every downstream
number optimistic. The resolution rate is reported with every run.

### Step 4 · Compare, deterministically
`comparison/engine.py` — no model involved. Produces the reflexion vocabulary:

- **convergence** — in both the design and the code
- **divergence** — in the code, not in the design
- **absence** — in the design, not in the code

Generalization and realization are recoverable exactly from an AST and are
scored. Associations are *evidenced* rather than proven — a typed field is
strong evidence, a name match is weak — and are excluded from the headline score
by default. Every result records which convention produced it.

### Step 5 · The gate
`core/graph_diff.py` — the decision this whole project is about. Four policies:

| Gate | Re-analyses when | Absorbs | Risk |
|---|---|---|---|
| `always` | every run | nothing | maximum cost; the baseline |
| `content` | any file's bytes changed | nothing | pays for comment edits |
| `structural` | the fingerprint changed | formatting, comments, literals, local names | a semantic change with identical structure is missed |
| `isomorphism` | fingerprint changed **and** the graph is not isomorphic to the previous one | also pure renames and reorderings | a rename that breaks a diagram naming that class is missed |

The isomorphism gate uses VF2 with a type-preserving node matcher. When an
isomorphism exists, **the mapping is the renaming**, so cached findings get
relabelled rather than regenerated — a project-wide rename produces a correct,
current report at zero model cost.

The `isomorphism` failure mode is designed in, not a defect. It is stated in the
paper next to the mechanism, and the seeded-deviation test measures how often it
costs anything.

### Step 6 · The model, if the gate allows
`ai_service.py` — the model receives the changed subgraph plus its *k*-hop
impact set (k=1 by default) and the deterministic findings as ground truth it
may not contradict. Scoping to the impact set is a second saving: cost then
scales with the size of the change rather than the size of the project.

`grounded_node_ratio` reports what share of model-proposed nodes correspond to
something the parser actually found. It is the number to check before believing
any model-authored claim.

With no API key the whole pipeline still runs; results are labelled
`deterministic-offline` so they can never be mistaken for a model's judgement.

### Step 7 · Persist
`core/graph_store.py` — a bounded ring of three versions.

**Two graphs are stored per version, and they must not be the same object:**

- the **presentation graph** the UI draws (implementation + design + model-proposed)
- the **gate graph**, implementation only, which the next run compares against

Comparing a merged presentation graph against a freshly parsed implementation
graph never matches, so the gate fires every time and the cache never hits. This
was a real bug; `test_cold_start_then_cache_hit` exists to stop it returning.

### Step 8 · Record
`core/run_ledger.py` — one append-only JSONL row per run: gate decision, whether
a model was actually reached, tokens, latency, change size, reflexion counts, a
findings hash, and the reproducibility settings (model, temperature, seed).

Two facts are recorded separately on purpose: **whether the gate permitted a
re-analysis** and **whether a model was actually called**. They differ in offline
mode, and conflating them once produced a reported 100% cache-hit rate for a
pipeline that had never cached anything.

The ledger is not logging. It is the evaluation dataset — every statistic in the
paper is computed from it.

---

## 3. Module map

### backend/

Every file except tests, so nothing is unaccounted for.

| Path | Does |
|---|---|
| `main.py` | Every HTTP endpoint. Thin — logic lives in `core/` |
| `config.py` | All configuration, read from the environment. Nothing hardcoded elsewhere |
| `auth.py` | JWT issue/verify, password hashing, per-user rate limiting |
| `database.py` | SQLAlchemy session and engine |
| `ai_service.py` | Model providers, determinism, retries, offline mode |
| `core/pipeline.py` | Orchestrates one run — the file to read first |
| `core/graph_builder.py` | Parser output → NetworkX; call resolution |
| `core/graph_diff.py` | **The gate.** Deltas, isomorphism, rename recovery, impact sets |
| `core/graph_store.py` | Versioned snapshots, bounded to three |
| `core/run_ledger.py` | Per-run metrics; the evaluation dataset |
| `core/workspace_fs.py` | The virtual directory — edit a project without git |
| `core/archive.py` | Hardened zip extraction |
| `core/paths.py` | Path containment. Every user-supplied path goes through it |
| `comparison/engine.py` | Deterministic conformance check + layering rules |
| `parsers/polyglot_parser.py` | tree-sitter extraction, fingerprints |
| `parsers/uml_parser.py` | StarUML `.mdj` reader |
| `models/user_model.py` | SQLAlchemy user row; Pydantic request/response schemas for auth |
| `models/design_model.py` | The intermediate design model both parsers produce, so code and UML become comparable |
| `stats/core.py` | median, mean, Wilson interval, McNemar. ~200 lines, the whole numeric core |
| `stats/report.py` | Builds the four tables and writes every plain-English sentence |
| `stats/exports.py` | CSV bundle, IEEE LaTeX, one file per table |
| `tools/check_imports.py` | Static cross-module import check |
| `tests/` | 210 tests, stdlib `unittest`, no pytest needed |

### frontend/src/

Every file, so nothing is unaccounted for.

| Path | Does |
|---|---|
| `main.tsx` | Vite entry point |
| `App.tsx` | Auth gate, theme, and top-level routing |
| `components/AppShell.tsx` | The sidebar: destinations, the open project's sections, theme toggle |
| `lib/api.ts` | Every backend call, typed |
| `lib/layout.ts` | **Deterministic graph layout.** Sugiyama-style, no physics |
| `lib/statsTypes.ts` | Mirrors `backend/stats/report.py` exactly |
| `lib/theme.ts` | Conformance status colours, glyphs, labels; the light/dark controller |
| `lib/tree.ts` | Rebuilds a folder hierarchy from the backend's flat path list |
| `lib/highlight.ts` | Small dependency-free syntax highlighter for the code viewer |
| `components/ProjectsPage.tsx` | Project list, GitHub import, create |
| `components/ProjectWorkspace.tsx` | The four sections: Code, Diagram, Results, History |
| `components/CodePanel.tsx` | The three-pane code screen: tree, viewer, what the diagram says |
| `components/FileTree.tsx` | The collapsible folder tree, keyboard-navigable |
| `components/CodeViewer.tsx` | Line numbers, highlighting, gutter status marks |
| `components/DesignMap.tsx` | The static layered graph, with SVG export |
| `components/StatisticsPage.tsx` | Four tables, three charts, gate explainer |
| `components/charts/ParetoChart.tsx` | Figure 3: skip rate against recall |
| `components/AuthView.tsx` | Sign in and register |
| `components/UmlPanel.tsx` | Upload and validate the `.mdj` |
| `components/ConformanceReport.tsx` | The findings for one analysis: score, divergences, absences |
| `components/VersionTimeline.tsx` | The three retained versions, and switching between them |
| `components/MetricsPanel.tsx` | Per run: model invocations avoided, latency, cache behaviour |
| `components/ResearchPanel.tsx` | Repeatability and cross-model agreement |
| `components/ui.tsx` | Card, Button, Badge, Banner, EmptyState, Spinner — every shared primitive |
| `components/Toast.tsx` | Transient notifications |
| `components/charts/primitives.tsx` | Chart chrome: palette, `Figure`, `Legend`, axis ticks, SVG export |
| `components/charts/BarChart.tsx` | Figure 1 — skip rate per gate, miss count on each bar |
| `components/charts/DriftChart.tsx` | Figure 2 — violations accumulating over commits |
| `lib/types.ts` | Shapes returned by every non-statistics endpoint |
| `lib/csv.ts` | RFC 4180 CSV generation and browser download |

### research/

| Path | Does |
|---|---|
| `find_stale_diagrams.py` | Finds projects whose UML model was abandoned |
| `evaluate_deviations.py` | The 16 seeded deviations → Table 4 |
| `replay.py` | Commit replay across all four gates, with the oracle |
| `analyze_statistics.py` | Runs → tables, CSV, LaTeX, replication package |
| `harness.py` | Shared machinery for the two experiment scripts |
| `deviations/` | The reference project and its 16 mutations |
| `models/` | **Your frozen `.mdj` files go here** |

---

## 4. Invariants — break these and the results become wrong

1. **The gate graph and the presentation graph are different objects.** See §2
   step 7.
2. **`gate_allowed_llm` and `llm_invoked` are separate ledger fields.** See §2
   step 8.
3. **Ambiguous call sites are counted, never linked to every candidate.**
4. **A rate with no oracle is reported as "not measured", never as zero.**
5. **The gate never reads the UML diagram.** It decides from code structure
   alone. This is what makes the cost results valid even on a recovered
   diagram — the oracle is a forced analysis against the *same* diagram.
6. **Every user-supplied path goes through `core/paths.py`.** Project names
   reject `/`, `\` and `..` outright rather than sanitising them.

---

## 5. Where the data lives

```
workspace/<user>/<project>/
  source/                  the code under analysis
  uml/                     the .mdj
  reports/
    runs.jsonl             the ledger — every statistic comes from here
    semantic_graph.json    latest presentation graph
    versions/
      index.json
      v1.graph.json        presentation graph
      v1.gate.json         implementation-only graph
      ...                  bounded to three
```

`backend/conformance_app.db` holds users, projects and GitHub tokens. Deleting
the workspace but keeping the database leaves the UI listing projects whose files
are gone — delete both together.

---

## 6. Reading order for a newcomer

1. `docs/UNDERSTANDING.md` — what the words mean
2. This file, §2 — one run end to end
3. `backend/core/pipeline.py` — the same thing in code
4. `backend/core/graph_diff.py` — the gate, which is the contribution
5. `backend/stats/report.py` — how the numbers become tables
