# START HERE — what to do, in order

Do these in order. Do not skip ahead: step 4 cannot work before step 3.

Every command runs from `C:\Users\sarve\uml-analyzer` in PowerShell.
Activate the environment first, once per terminal:

```powershell
cd C:\Users\sarve\uml-analyzer
backend\venv\Scripts\Activate.ps1
```

---

## Step 0 — Reinstall the frontend dependency list  ·  2 minutes

I removed `react-force-graph-2d` from `package.json`. Sync it:

```powershell
cd frontend
npm install
cd ..
```

**You should get:** `removed 1 package` or similar. No errors.

---

## Step 1 — Check it runs  ·  5 minutes

Two terminals.

**Terminal A:**
```powershell
cd C:\Users\sarve\uml-analyzer\backend
venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```
**You should get:** `Uvicorn running on http://127.0.0.1:8000`.

**Terminal B:**
```powershell
cd C:\Users\sarve\uml-analyzer\frontend
npm run dev
```
**You should get:** `Local: http://localhost:5173/`.

Open <http://localhost:5173>, sign in, open any project, click **Results**.

**You should see:** a graph drawn as boxes in fixed rows with arrows — not a
moving web of dots. A **Save as SVG** button above it.

If you still see dots that drift, the old build is cached: stop `npm run dev`,
delete `frontend/node_modules/.vite`, start it again.

---

## Step 2 — Get your first real result  ·  1 minute

```powershell
python research/evaluate_deviations.py --out results/
```

**You should get:** a table on screen with four rows (always, content,
structural, isomorphism) and columns TP / FN / FP / TN, and two new files:
`results/deviations.csv`, `results/deviations_summary.json`.

This is **Table 5 of your paper**, done. No internet, no API key, ~10 seconds.

---

## Step 3 — Build the diagrams  ·  THE REAL WORK, several days

This is the only step nobody can do for you, and nothing after it works without
it.

For each of 4–6 projects:

1. Clone it (list and links: `docs/CORPUS-AND-SUBMISSION.md`).
2. `git log --oneline | tail -50` — pick an **early** commit. Write down its SHA.
3. `git checkout <that SHA>`
4. Open StarUML. Draw the class diagram: the architecturally significant classes
   only — controllers, services, repositories, main domain classes. Not every
   class, not getters.
5. Save as `research/models/<project>.mdj`.
6. **Never open that .mdj again.**
7. `git checkout main` (put the repo back).

**Why freezing matters:** if the diagram changes as the code changes,
conformance is perfect by definition and there is nothing to measure. The whole
study depends on the diagram standing still while the code moves.

**You should end with:** 4–6 `.mdj` files in `research/models/`, and a note of
which commit each came from. You need those SHAs for the paper.

---

## Step 4 — Fill in the corpus file  ·  15 minutes

Open `research/corpus.recommended.json`. It already lists six real projects with
working clone URLs. For each one you actually built a diagram for:

- check `uml` points at your `.mdj`
- replace `<SHA>` in `notes` with the commit you used
- **delete any entry you did not build a diagram for**

Save it as `research/corpus.json` (overwrite the existing one).

---

## Step 5 — Run the replay  ·  30 minutes to several hours

```powershell
python research/replay.py --corpus research/corpus.json --out results/
```

**You should get:** progress lines per project and per commit, then
`results/runs.csv` and `results/summary.json`.

`runs.csv` should have roughly *projects x commits x 4* rows. Four projects at
40 commits = about 640 rows.

**If one project fails:** delete it from `corpus.json` and re-run. Five projects
that finished beat six that crashed.

---

## Step 6 — Produce every number and table  ·  10 seconds

```powershell
python research/analyze_statistics.py --runs results/runs.csv --out results/ --replication
```

**You should get** a summary on screen and these files:

| File | What it is |
|---|---|
| `results/REPORT.md` | **open this first** — every table with a plain-English sentence |
| `results/tables/*.csv` | one CSV per table |
| `results/tables-tex/*.tex` | one LaTeX file per table |
| `results/replication-package.zip` | the single file to upload to Zenodo |

Open `results/REPORT.md` and check three things:

1. The **Missed** column shows numbers, not "not measured".
2. **Table 4 (controlled test)** is filled in.
3. **"How these runs were produced"** shows one consistent configuration.

If any of those fail, see `docs/UNDERSTANDING.md` §7.

---

## Step 7 — Export the three figures  ·  2 minutes

In the app:

| Where | Button | Saves | Becomes |
|---|---|---|---|
| Results page, Figure 1 | Save as SVG | `figure1-skip-by-gate.svg` | Paper Figure 2 |
| Results page, Figure 2 | Save as SVG | `figure2-drift.svg` | Paper Figure 3 |
| Project → Results → graph | Save as SVG | `<project>-design-graph.svg` | Paper Figure 1 |

SVG, not screenshots. A screenshot goes blurry when IEEE scales it.

---

## Step 8 — Fill in the paper  ·  a few days of writing

Open `paper/IEEE-Access-draft.docx` in Word.

Use Find (Ctrl+F) for `<` — every placeholder is written `<like this>`. Work
through them with `results/REPORT.md` open beside you. `docs/UNDERSTANDING.md`
§8 maps each placeholder to the exact line it comes from.

Insert the three SVG figures where the italic notes say to, and delete the notes.

Write the author biographies at the end. **This is the item IEEE Access rejects
most often for being missing.**

---

## Step 9 — Submit  ·  1 hour

1. Upload `results/replication-package.zip` to <https://zenodo.org/>. Copy the
   DOI it gives you into the Data Availability section.
2. Save the Word file as PDF as well. **Both are required and must match.**
3. Go to <https://ieee.atyponrex.com/journal/ieee-access>.
4. Have ready: ORCID for every author, 3–10 keywords, article type
   (Research Article), and the AI-disclosure sentence in the acknowledgements.

---

## Where you are right now

You have finished **Step 0**. Steps 1 and 2 are the next thirty minutes.
Step 3 is the project.


---

## Appendix — every command and its options

```powershell
# The controlled test (16 seeded deviations, known answers)
python research/evaluate_deviations.py --out results/
    --strategies always,content,structural,isomorphism   # which gates
    --git-branches .\deviation-repo                      # also make a branch per mutation

# Find projects whose diagram was abandoned while the code moved on
python research/find_stale_diagrams.py --repo ..\some-project
    --clone https://github.com/owner/name.git   # clone and scan in one step, repeatable
    --out results/                              # write stale-diagrams.csv

# The corpus study
python research/replay.py --corpus research/corpus.json --out results/
    --repo ..\one-project --uml research\models\x.mdj   # a single project instead
    --commits 40            # how many commits per project
    --branch main
    --subdirectory src/main/java    # exclude tests and generated code
    --llm-mode offline      # default: free and exactly reproducible

# Turn runs into tables
python research/analyze_statistics.py --runs results/runs.csv --out results/
    --workspace backend/workspace   # use live app usage instead of a replay
    --replication                   # also build replication-package.zip

# Smoke-test the tables with fake data, before you have a corpus
python backend/tools/make_synthetic_runs.py --out results/fake.csv --projects 4 --commits 40
```

### If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `Activate.ps1 cannot be loaded` | PowerShell policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Analysis finds no classes | tree-sitter grammars missing | `pip install tree-sitter-python tree-sitter-javascript tree-sitter-typescript tree-sitter-java` |
| `git` not found in replay | not on PATH | Install Git for Windows, reopen the terminal |
| Port 8000 busy | something else bound | `uvicorn main:app --reload --port 8001`, then set `VITE_API_BASE` |
| Graph nodes drift | old build cached | Delete `frontend/node_modules/.vite`, restart `npm run dev` |
| Sessions drop on restart | `SECRET_KEY` blank | Set it in `backend/.env` |
