# Structure-Gated Architecture Conformance Checking

Checks whether a codebase actually implements the design drawn in its StarUML
diagram — and re-checks it as the code changes, **spending a language-model call
only when the change is one that could plausibly affect the answer.**

That decision is called a **gate**, and measuring what each gate saves and what
it costs is the research contribution.

> **New here?** Read [`docs/START-HERE.md`](docs/START-HERE.md). It tells you
> what to run, in order, and what you should see each time.

---

## What problem this solves

Conformance checking is not a one-off. It has to be redone every time the code
changes. A language model makes the check easy to build and its output easy to
read, but it turns a cheap repeated check into one that is priced per token —
while most commits (a comment, a reformat, a renamed local) cannot possibly
change whether the code matches a class diagram.

So the tool works out what changed **structurally** before deciding whether to
ask a model anything. Four gates are implemented so the trade-off can be
measured rather than asserted:

| Gate | Re-analyses when | Absorbs | Risk |
|---|---|---|---|
| `always` | every run | nothing | maximum cost; the baseline |
| `content` | any file's bytes change | nothing | pays for comments and formatting |
| `structural` | the AST-derived fingerprint changes | formatting, comments, literals, local names | a semantic change with identical structure is missed |
| `isomorphism` | structural change **and** the graph is not isomorphic to the previous one | additionally pure renames and reorderings | a rename that breaks a diagram naming that class is missed |

Every run appends to a per-project ledger — gate decision, tokens, latency,
change size — so the saving is measured from real use, not simulated.

**Nothing here requires git or GitHub.** Upload a folder, a `.zip`, or write code
in the browser. GitHub import is one option among several.

**Nothing here requires an API key.** With no model configured the whole pipeline
runs deterministically. Only natural-language gap descriptions need one, and
results produced without it are labelled `deterministic-offline`.

---

## Quickstart

```powershell
# backend
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then set SECRET_KEY
uvicorn main:app --reload --port 8000

# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Then <http://localhost:5173>. Detailed steps, and what you should see at each
one, are in [`docs/START-HERE.md`](docs/START-HERE.md).

---

## Documentation

| Document | Answers |
|---|---|
| [docs/START-HERE.md](docs/START-HERE.md) | What do I do next? |
| [docs/UNDERSTANDING.md](docs/UNDERSTANDING.md) | What am I looking at? What should a good result look like? |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How does the code work? |
| [docs/CORPUS-AND-SUBMISSION.md](docs/CORPUS-AND-SUBMISSION.md) | Which projects do I evaluate on? How do I submit? |
| [docs/STATISTICS.md](docs/STATISTICS.md) | What are the four tables? |
| [docs/LITERATURE.md](docs/LITERATURE.md) | What do I cite? |
| [docs/API.md](docs/API.md) | How do I call the backend? |

Per-directory: [backend](backend/README.md) · [frontend](frontend/README.md) ·
[research](research/README.md) · [paper](paper/README.md)

---

## Repository layout

```
backend/          FastAPI service — parse, compare, gate, record
  core/           pipeline, the gate, graph store, run ledger
  parsers/        tree-sitter extraction; StarUML .mdj reader
  comparison/     deterministic conformance check
  stats/          the four paper tables, pure Python
frontend/         React + Vite. Three screens, static graph, two charts
research/         the experiments that produce the paper's numbers
  find_stale_diagrams.py   find projects whose UML model was abandoned
  evaluate_deviations.py   16 seeded deviations with known answers
  replay.py                commit replay across all four gates
  analyze_statistics.py    runs -> tables, CSV, LaTeX, replication package
  models/                  YOUR FROZEN .mdj FILES GO HERE
paper/            IEEE-Access-draft.docx and the script that builds it
docs/             seven documents, indexed above
workspace/        analysed projects (created at runtime)
results/          experiment output (created at runtime)
```

---

## How a run works

```
 source tree ──► PolyglotParser (tree-sitter) ──► architecture + fingerprints
 .mdj file   ──► StarUMLParser (two-pass)     ──► design model + relations
                          │
                          ├──► build_implementation_graph (symbol-table calls)
                          ├──► ComparisonEngine           (exact, no model)
                          ▼
                    decide_gate ── reuse ──►  previous version, relabelled
                          │
                       re-analyse
                          ▼
              ai_service.evaluate_conformance (scoped to the impact set)
                          ▼
        annotate + merge ──► version store (last 3) ──► run ledger
```

Two graphs are persisted per version: the presentation graph the UI draws, and
the pure implementation graph the gate compares against next time. They must not
be the same object — comparing a merged graph against a freshly parsed one never
matches, and the cache would never hit.

**Call resolution.** Calls are attributed through a project-wide symbol table. A
call with several equally plausible targets is left unlinked and *counted*
rather than linked to all of them, and the resolution rate is reported with every
analysis — so the remaining imprecision is a number, not an unknown.

**Relationships.** Generalization and realization are recoverable exactly from an
AST and are scored. Associations are not: a typed field is strong evidence, a
name match is weak, neither is proof. They are reported with their evidence level
and excluded from the headline score by default.

Full walkthrough: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Status

Built and tested: parser, UML reader, comparator, four gates, versioning,
statistics, static graph, exports, replication packaging. 210 backend tests
exist (207 passing as of this writing — `test_full_cycle`,
`test_versions_metrics_and_benchmark`, and `test_python_declarations` are
currently failing; see their tracebacks with `python -m unittest discover -s
tests -t .` from `backend/`); TypeScript compiles clean.

**Not done: the corpus.** Four to six projects with frozen diagrams and 30–40
commits each. That is the remaining work, and
[`docs/CORPUS-AND-SUBMISSION.md`](docs/CORPUS-AND-SUBMISSION.md) is how to get it.

---

## Security notes

Addressed, and worth knowing if you deploy this:

- The JWT signing key comes from `SECRET_KEY`. Unset, an ephemeral key is
  generated and the server warns; it never falls back to a constant.
- Project names and every path from a request are containment-checked, so `..`
  in a URL segment cannot escape the workspace.
- Archive extraction rejects absolute paths, `..` components and symlinks, and
  caps member count and uncompressed size.
- Token validation re-checks that the user still exists.
- Endpoints that can spend money are rate-limited per user.
- The GitHub webhook verifies its HMAC when `GITHUB_WEBHOOK_SECRET` is set.

Open, deliberately, for a local prototype: GitHub tokens are stored in plaintext
in SQLite, and the session token lives in `localStorage`. Both are recorded in
the paper's threats section.
