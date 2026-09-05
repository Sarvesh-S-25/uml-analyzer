# Structure-gated conformance checker — project instructions

@../docs/README.md

The import above is the six-document index; each row says which doc answers
which question. Open the specific doc a task needs — most tasks need exactly
one — rather than reading all of them up front.

## What this repo is

A tool that checks whether a codebase still implements the design drawn in its
StarUML class diagram, and re-checks it as the code changes **without calling a
language model on every commit.** A deterministic **gate** decides, from code
structure alone, whether a commit could plausibly have changed the answer;
measuring what each of the four gates saves and costs is the research
contribution and the subject of an IEEE Access submission (`paper/`).

Two halves, no monorepo tooling tying them together — `cd` into the one you're
touching:

| Dir | Stack | Run |
|---|---|---|
| `backend/` | FastAPI, SQLAlchemy, tree-sitter, NetworkX | `uvicorn main:app --reload --port 8000` |
| `frontend/` | React 19, Vite, Tailwind v4, no chart library | `npm run dev` |
| `research/` | Plain Python scripts, no framework | run individually, see `docs/START-HERE.md` |
| `paper/` | `IEEE-Access-draft.docx` + a build script | edited directly in Word |

**This directory is not a git repository.** Do not assume `git status`/`git
diff` work here — they will error. If a task needs a diff, ask what changed or
work from the files named in the request. (The *analysed projects* under
`workspace/` and the corpus repos under `research/` are separate git checkouts
and behave normally.)

## The six invariants — read `docs/ARCHITECTURE.md` §4 for the reasoning

Most real defects in this codebase are one of these, not style problems:

1. **The gate graph and the presentation graph are different objects.**
   Comparing a merged presentation graph against a freshly parsed one never
   matches, so the cache never hits — this was a real, shipped bug.
2. **`gate_allowed_llm` and `llm_invoked` are separate run-ledger fields.** The
   gate permitting a re-analysis and a model actually being reached are
   different facts; they diverge in offline mode.
3. **An ambiguous call site is counted, never linked to every candidate.**
   Linking to all plausible targets invents edges and makes every downstream
   number optimistic.
4. **A rate with no oracle is reported as "not measured", never as zero.**
5. **The gate never reads the UML diagram.** It decides from code structure
   alone — that's what makes the cost measurement valid even on a
   reverse-engineered diagram.
6. **Every user-supplied path goes through `backend/core/paths.py`.** Project
   names reject `/`, `\` and `..` outright.

## Before finishing any change

1. **Backend touched** → `python -m unittest discover -s tests -t .` from
   `backend/` (211 tests, stdlib `unittest`, no pytest). Also run
   `python tools/check_imports.py`.
   As of this writing the suite is fully green on a clean checkout — the three
   tests once documented here as known-failing (`test_full_cycle`,
   `test_versions_metrics_and_benchmark` in `tests/test_api.py`, and
   `test_python_declarations` in `tests/test_parser.py`) were real bugs, not
   environment noise: `ManualWorkflowTests.setUp` wasn't fully isolating the
   shared "Manual Flow" project between test methods, the parser wasn't
   propagating a constructor parameter's type annotation to `self.x = param`
   fields, and the parser test's own assertion compared a bare string against
   a list of dicts. All three are fixed. If the suite is red again, it is a
   real regression — check the *set* of failures against this note before
   assuming it's a known baseline.
2. **Frontend touched** → from `frontend/`: `npx tsc -p tsconfig.app.json
   --noEmit`. It must compile clean; there is no separate lint step gating
   commits.
3. **The gate, the parsers, or the comparison engine touched** → re-run the
   controlled test: `python research/evaluate_deviations.py --out results/`.
   It has known answers (16 seeded deviations) and runs in seconds — the
   fastest way to know whether a "fix" broke the thing it was fixing.
4. Never report work as done without having run the relevant one of these.

## Consult Gemini before a design decision

Gemini is the second opinion on this project, reached through the **Antigravity
CLI** (`agy`) via a wrapper script — the standalone `gemini` CLI can no longer
sign in with an individual Google account. **Any task with a design decision in
it gets a Gemini pass before implementation begins** — a feature, a schema or
API change, a bug whose cause isn't known yet, or anything touching more than
one file.

Two ways, depending on size:

- **A whole task** → the `gemini-planner` subagent. It gathers context, asks
  Gemini for a plan, checks the answer against this repo's invariants and
  layout, and returns a plan with the disagreements marked.
- **A single question** → the `gemini-call` skill, or directly:

  ```powershell
  node .claude/scripts/gemini.mjs --dirs backend/core "your question"
  ```

**Prefer `--dirs` over reading files into context.** The wrapper reads those
files itself and sends them to Gemini — Gemini's context is large and cheap;
mine is scarce. See `.claude/README.md` for how the wrapper works and why it's
built the way it is.

**Report what it said, then judge it.** Say what Gemini recommended, where you
agree, and where you don't and why. Never relay its answer as settled. It has
not read this conversation and does not know this repo as well as
`docs/ARCHITECTURE.md` does — **where the two conflict, this repo's invariants
win.**

**Skip it, and say so, for:** single-line edits, typos, renames, running a
command, reading a file, anything already specified precisely enough to just
do, and follow-ups inside a task Gemini already reviewed.

**Exit code 2 is a setup problem** — nothing installed, or authentication
failed. Stop and say so rather than proceeding as though the review happened;
retrying will not fix it. A quota error is exit 1: say so in one line and carry
on alone.

## When a task touches the frontend UI

Use the `frontend-design` skill before hand-writing layout or styling — it
routes new screens through Stitch first and keeps the result on this project's
actual tokens (Tailwind v4, `frontend/src/lib/theme.ts`, `frontend/src/index.css`).

## Status, in one line

Parser, UML reader, comparator, four gates, versioning, statistics, static
graph and exports are built and tested. The corpus — 4–6 real projects with a
frozen diagram and 30–40 replayed commits each — is the only thing not done.
`docs/README.md` and `docs/START-HERE.md` say what that involves.
