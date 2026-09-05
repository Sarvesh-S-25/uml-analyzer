# What to test on, and how to get from there to a submitted paper

*Links verified 26 August 2026.*

---

## Part 1 — Which projects to use

## The reverse-engineering problem, and the way out

If you draw a diagram from the code you are about to analyse, conformance is
100% and you have measured nothing. That is a real objection and it kills a
naive study.

**The way out is to stop drawing diagrams and start finding abandoned ones.**

Some repositories contain a `.mdj`, `.uml` or `.xmi` that somebody drew once and
then never touched again, while development carried on for hundreds of commits.
That diagram is a *genuine* statement of intended design — you did not make it —
and the code has *genuinely* drifted away from it. The violations are real and
nobody planted them.

This is common, not exceptional, and it is published: Romeo et al. deep-cloned
**13,152 GitHub repositories** and found that **fewer than one third of the
projects containing UML saw any activity in their UML files during 2022**
([paper](https://www.inf.usi.ch/phd/raglianti/publications/Romeo2025a.pdf) ·
[IEEE Xplore](https://ieeexplore.ieee.org/document/11029930/)). People draw the
diagram and then forget it. That is your corpus, and citing this paper is how
you justify it to a reviewer.

### Source 1 — find them automatically

```powershell
python research/find_stale_diagrams.py --clone https://github.com/owner/name.git --out results/
```

For every model file it reports when the diagram was last edited, when the code
was last edited, how many source-touching commits landed in between, and a
verdict:

```
  docs/design.mdj
    StarUML, last changed 2019-04-11, code at 2026-02-03
    412 commits and 2489 days behind; 168 source files changed since
    -> CANDIDATE - real design, real drift
```

Point it at ten repositories and keep the candidates. Start the analysis at the
commit where the diagram was last touched — that is the design as its author
last left it.

### Where to look

GitHub code search, one query at a time:

- `extension:mdj` — StarUML, what the tool reads natively
- `extension:uml` — Eclipse/Papyrus
- `extension:xmi` — interchange format
- `path:docs extension:mdj` — diagrams filed as documentation, the most likely
  to have been abandoned

Also the [`staruml` topic](https://github.com/topics/staruml) and the
[Lindholmen dataset](https://se.informatik.uni-rostock.de/en/research/datasets-and-tools/lindholmen-dataset/)
(93,000 UML files across 24,000 repositories; the models-db.com portal was
redirect-looping when I last checked — use the Rostock mirror).

### What this does and does not fix

It fixes the drift results, which are only meaningful if the design was really
intended.

It was never a problem for the cost results. **The gate never reads the
diagram.** It decides whether to re-analyse from changes in code structure
alone. Skip rates, miss rates, token savings and the gate comparison are
measurable against any diagram — even one you recovered yourself — because the
oracle is a forced full analysis against that *same* diagram, not against an
external notion of correctness.

So: provenance bounds Section V-E. It does not bound Sections V-A to V-D, which
are the contribution.

---

### The three sources, in priority order

| | Source | Strength | Weakness |
|---|---|---|---|
| **1** | **Abandoned diagrams found in the wild** (above) | The design is genuine and so is the drift; nobody planted either | You must find them, and some were abandoned because the component was |
| **2** | **Published ground-truth architectures** (SAEroCon) | Validated by people with no stake in your result | Only three systems, and module-level rather than class-level |
| **3** | **Recovered and frozen** | Always available | Conformance is perfect at the recovery commit by construction; measures departure from a fixed reference, not from a real intention |

Use source 1 for most of the corpus, source 2 for credibility, source 3 to fill
gaps — and label every project with which one it came from. That label goes in
the paper, and a reviewer will look for it.

---

### Source 2 — SAEroCon: three systems with validated intended architectures

The [**SAEroCon repository**](https://github.com/sebastianherold/SAEroConRepo)
exists for precisely your evaluation: "ground-truth intended software
architectures to form a base for benchmarking approaches and tools related to
software architecture degradation."

Its [wiki](https://github.com/sebastianherold/SAEroConRepo/wiki) documents three
systems:

| System | Version | Mappings provided | Source |
|---|---|---|---|
| **JabRef** | 3.7 | Generic, HUSACCT, JiTTaC | [github.com/JabRef/jabref](https://github.com/JabRef/jabref) — Java 92%, ~24,000 commits |
| **ProM** | 6.9 | JiTTaC | [promtools.org](https://promtools.org/) |
| **Teammates** | 5.110 | HUSACCT | [github.com/TEAMMATES/teammates](https://github.com/TEAMMATES/teammates) — Java 50% / TypeScript 39%, ~19,000 commits |

**The catch, and it matters:** these are *module-level* architectures, not UML
class diagrams. You must translate one into a `.mdj`. That translation is itself
describable work — say in the paper that you did it and how.

**Second catch:** JabRef's current layout (`jabgui/`, `jablib/`, `jabkit/`) is
nothing like 3.7's. Check out the tagged version the mapping refers to:

```powershell
git clone https://github.com/JabRef/jabref.git
cd jabref
git checkout v3.7
```

Same for Teammates at `V5.110`.

Also worth reading: [SAEroCon workshop page](https://saerocon.wordpress.com/the-saerocon-repository/)
and [Garcia et al., *Obtaining Ground-Truth Software Architectures*, ICSE 2013](https://dl.acm.org/doi/10.5555/2486788.2486911)
— the method behind these.

---

### Source 3 — projects where a class diagram is meaningful, if you must recover one

Pick these because their naming makes the layering explicit, which is what your
graph layout and your diagram both key on.

| Project | Why it fits | Link |
|---|---|---|
| **Spring PetClinic** | The canonical layered Java reference app: controllers, services, repositories, model. ~1,034 commits, 9.3k stars, Java 17. Small enough to reverse-engineer a diagram by hand in an afternoon. | [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) |
| **JPetStore 6** | Classic layered web app, deliberately simple, MyBatis-based. | [mybatis/jpetstore-6](https://github.com/mybatis/jpetstore-6) |
| **PiggyMetrics** | Spring Boot microservices; each service is independently layered. | [sqshq/piggymetrics](https://github.com/sqshq/piggymetrics) |
| **BuckPal** | Hexagonal architecture with textbook-clean boundaries. **Only ~54 commits** — use as a pilot, not a corpus entry. | [thombergs/buckpal](https://github.com/thombergs/buckpal) |

**Be honest about PetClinic and JPetStore in the paper.** They are reference
applications, and a reviewer may call them toys. The answer is that they are
*pilots* that establish the pipeline works, and JabRef/Teammates carry the
generalisation claim. Do not build the whole corpus from reference apps.

---

### Mining for real `.mdj` files

Two sources, with caveats:

**[Lindholmen dataset](http://models-db.com/)** — 93,000+ UML files across
24,000+ GitHub repositories, from [Hebig et al., MODELS 2016](https://research.tue.nl/en/datasets/lindholmen-dataset-of-uml-models/)
and [Robles et al., MSR 2017](https://ieeexplore.ieee.org/document/7962411/).
⚠️ **The models-db.com portal was redirect-looping when I checked it** — try the
[University of Rostock mirror](https://se.informatik.uni-rostock.de/en/research/datasets-and-tools/lindholmen-dataset/)
or email the Rostock SE chair. If you use it, you **must** filter out
reverse-engineered diagrams; there is
[a published classifier for exactly that distinction](https://www.researchgate.net/publication/327690310_An_Automated_Approach_for_Classifying_Reverse-Engineered_and_Forward-Engineered_UML_Class_Diagrams).

**GitHub code search** — `extension:mdj` and the
[`staruml` topic](https://github.com/topics/staruml). Note that
[staruml/staruml-samples](https://github.com/staruml/staruml-samples) has
`.mdj` files but **no paired source code** — useful only for testing that your
parser survives real-world diagrams, not as corpus.

---

### The corpus I would actually build

Six entries. Enough for Table 3 to say something, small enough to finish.

```json
{
  "projects": [
    {
      "name": "jabref",
      "source": "https://github.com/JabRef/jabref.git",
      "uml": "research/models/jabref.mdj",
      "commits": 40,
      "branch": "v3.7",
      "subdirectory": "src/main/java",
      "notes": "SAEroCon intended architecture, translated to .mdj, frozen at v3.7."
    },
    {
      "name": "teammates",
      "source": "https://github.com/TEAMMATES/teammates.git",
      "uml": "research/models/teammates.mdj",
      "commits": 40,
      "subdirectory": "src/main/java",
      "notes": "SAEroCon HUSACCT mapping, translated to .mdj, frozen at V5.110."
    },
    {
      "name": "spring-petclinic",
      "source": "https://github.com/spring-projects/spring-petclinic.git",
      "uml": "research/models/petclinic.mdj",
      "commits": 40,
      "subdirectory": "src/main/java",
      "notes": "Diagram reverse-engineered once at commit <SHA> and held fixed."
    },
    {
      "name": "jpetstore",
      "source": "https://github.com/mybatis/jpetstore-6.git",
      "uml": "research/models/jpetstore.mdj",
      "commits": 30,
      "subdirectory": "src/main/java",
      "notes": "Diagram reverse-engineered once at commit <SHA> and held fixed."
    },
    {
      "name": "piggymetrics",
      "source": "https://github.com/sqshq/piggymetrics.git",
      "uml": "research/models/piggymetrics.mdj",
      "commits": 30,
      "notes": "Diagram reverse-engineered once at commit <SHA> and held fixed."
    },
    {
      "name": "reference-orders",
      "source": "research/deviations/base",
      "uml": "research/deviations/base/design.mdj",
      "commits": 1,
      "notes": "The bundled seeded-deviation project."
    }
  ]
}
```

Replace every `<SHA>` with the real commit you recovered the diagram from, and
**record it** — a reviewer will ask.

---

## Part 2 — Step by step, from clone to submission

### Step 1 · The free result (today, one afternoon)

```powershell
cd C:\Users\sarve\uml-analyzer
backend\venv\Scripts\Activate.ps1
python research/evaluate_deviations.py --out results/
```

This produces `results/deviations_summary.json`, which **Table 4 reads
automatically** — both in the app and in the report. Sixteen deliberate changes
with known right answers, no network, no API key. It is the only table in your
study with unambiguous ground truth. Do it before anything else so you have a
result while the corpus is being built.

### Step 2 · Get the diagrams (the slow part — days, not hours)

For each project: open it in StarUML, build the class diagram for the classes
that matter (not every class — the architecturally significant ones), save as
`.mdj` under `research/models/`, then **do not touch it again**.

Write down, for each: which commit you recovered it from, and whether it came
from SAEroCon or from you. This goes in Section IV of the paper and it is the
first thing a sceptical reviewer checks.

### Step 3 · Fill in `research/corpus.json`

Use the block above. `subdirectory` matters for Java — without it you analyse
tests and generated code and your numbers become noise.

### Step 4 · Run the replay

```powershell
python research/replay.py --corpus research/corpus.json --out results/
```

Offline by default: free, and exactly reproducible. Expect this to take a while
— it clones each project and analyses every commit under all four gates.

**If it fails on one project, remove it and continue.** A five-project corpus
that finished beats a six-project corpus that didn't.

### Step 5 · Produce the tables

```powershell
python research/analyze_statistics.py --runs results/runs.csv --out results/ --replication
```

Open `results/REPORT.md` first. Check three things:

1. The **Missed** column has numbers, not "not measured". If it doesn't, the
   replay didn't finish.
2. **Table 4** is populated. If it isn't, go back to Step 1.
3. **"How these runs were produced"** shows one consistent configuration. If it
   flags a conflict, you ran part of the corpus under different settings — re-run
   the odd ones.

### Step 6 · Get the figures

In the app: **Results** tab → each figure has **Save as SVG**.

- `figure1-skip-by-gate.svg` — Figure 1
- `figure2-drift.svg` — Figure 2
- The design graph → **Save as SVG** — Figure 3, your architecture illustration

SVG, not screenshots. A screenshot goes soft the moment IEEE scales it into a
double column; a vector file doesn't.

### Step 7 · Build the paper

Open `paper/IEEE-Access-draft.docx` in Word and fill in the `<placeholders>`
from `results/REPORT.md`.

Get `ieeeaccess.cls` from [template-selector.ieee.org](https://template-selector.ieee.org/)
first.

Write in this order: **III → IV → V → II → VII → I → abstract.**

### Step 8 · Archive the replication package

`results/replication-package.zip` was built in Step 5. Upload it to
[**Zenodo**](https://zenodo.org/), which mints a DOI. Cite that DOI in the
paper's Data Availability section.

Not required by IEEE Access. Reviewers respond well to it and it costs nothing.

### Step 9 · Submit

**Portal:** <https://ieee.atyponrex.com/journal/ieee-access>

Have ready before you start:

- [ ] The `.docx` **and** a matching PDF — both are required, and the content must be identical
- [ ] Under 40 MB total, under 20 pages
- [ ] **ORCID for every author** — set this up beforehand, it holds people up
- [ ] **A biography for every author**, in the manuscript below the references
- [ ] 3–10 keywords
- [ ] Article type: **Research Article** or **Applied Research**
- [ ] Acknowledgements section **disclosing any AI-assisted text**, naming the system
- [ ] Supplementary material ready to upload if you're attaching the replication package directly

---

## Threats to validity — say these out loud in the paper, don't wait for a reviewer to ask

Three things a careful reviewer will check for. The code already defends
against the sharpest form of each one; what's missing is a sentence in the
paper saying so.

**Pooled McNemar across projects is pseudoreplication.** `compare_two_gates`
(`backend/stats/report.py`) pools every project's `(commit, gate)` pairs into
one paired test with no per-project clustering adjustment — standard practice
in software-engineering studies this size, but still worth naming rather than
presenting silently. Report the pooled comparison *and* the per-project
breakdown table (`table_projects`) together, and add one sentence in the
methodology section that the significance test treats commits, not projects,
as the unit of independence.

**4–6 projects is not enough to generalise across projects, only within
them.** The gate comparison for a single project is a real hypothesis test
over many commits; "which gate wins across the corpus" is a description of
4–6 data points, not a hypothesis test with power. Say so explicitly rather
than reporting only the pooled ranking — `MIN_DISCORDANT_PAIRS` in
`backend/stats/core.py` already refuses to report a McNemar result on too few
discordant pairs for exactly this reason; extend the same honesty to the
cross-project claim in prose.

**Not every replayed commit touches source.** `research/harness.py`'s
`commit_list` takes the last N non-merge commits with no filter on which
files they touch. A commit that only edits a README correctly registers as a
cache hit — that's not a bug — but if a project's history happens to be
padded with a lot of those, a high skip rate could be misread as gate
cleverness when it's partly commit-mix. Report what fraction of each
project's sampled commits actually touched a tracked source file, alongside
the skip rate, so the two aren't conflated.

---

## Part 3 — What I added for the paper

Three things the code did not have and the submission needs.

### 1. The reproducibility record

Every run now writes its model, provider, mode, temperature, seed, impact radius
and association-scoring setting to the ledger, and the report gains a **"How
these runs were produced"** section built from those values.

Read from the runs, not from your current environment — the config can change
between running a study and writing it up, and the paper has to state what was
actually used. If runs disagree, it says so rather than picking one:

> *These runs were not all produced under the same settings — Model, Temperature
> differ between runs. Report the split honestly, or re-run the corpus under one
> configuration.*

Model, temperature and seed are expected of any study involving a language
model. Their absence is a routine review comment.

### 2. Vector figure export

Figures 1 and 2 now have **Save as SVG**, sharing one implementation with the
design graph. It also pins an explicit background — without one the file renders
black in some viewers and white in others, and the text vanishes in one of them.

### 3. One-command replication package

```powershell
python research/analyze_statistics.py --runs results/runs.csv --out results/ --replication
```

Produces `results/replication-package.zip` (~50 KB): the report, the raw runs,
every table as CSV and LaTeX, `corpus.json`, the three scripts that produced
everything, and a README telling a reader how to reproduce the tables with
Python and nothing else. Only files that actually exist go in — a package that
claims a corpus it doesn't have is worse than no package.

---

## The three-line version

```powershell
python research/evaluate_deviations.py --out results/                              # today
python research/replay.py --corpus research/corpus.json --out results/             # after the diagrams
python research/analyze_statistics.py --runs results/runs.csv --out results/ --replication
```

Then: figures from the app, tables into `paper/tables`, zip to Zenodo,
manuscript to <https://ieee.atyponrex.com/journal/ieee-access>.

**Everything except Step 2 is automated. Step 2 — building and freezing the
diagrams — is the whole job, and only you can do it.**
