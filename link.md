# Corpus links — repositories to upload into CompX

Every repository below was checked against the GitHub API on **5 September 2026**.
The dates, file counts and drift windows are measured, not estimated: for each
repository the whole file tree was listed, every `.mdj`/`.uml`/`.xmi` in it was
found, and the last commit touching that diagram was compared against the last
commit touching the repository.

**What you are looking for, and why.** If you draw a diagram from the code you
are about to analyse, conformance comes out at 100% and you have measured
nothing — a reviewer will say so and they will be right. The way out is to stop
drawing diagrams and start finding abandoned ones: a `.mdj` somebody committed
once and never touched again, while development carried on for years. That
diagram is a *genuine* statement of intended design, the drift away from it is
*genuine*, and nobody planted either.

That this happens is published, not assumed. Romeo et al. deep-cloned 13,152
GitHub repositories and found fewer than one third of the projects containing
UML saw any activity in their UML files during 2022
([PDF](https://www.inf.usi.ch/phd/raglianti/publications/Romeo2025a.pdf) ·
[IEEE Xplore](https://ieeexplore.ieee.org/document/11029930/)). Cite it when you
justify this corpus.

---

## How to read the table

| Column | Meaning |
|---|---|
| **Stale** | Days between the last edit to the diagram and the last edit to the code. Bigger is better — it is the window in which drift accumulated. |
| **Code files** | Source files in the default branch, counting only real languages (no docs, no config). |
| **Source** | Which of the three corpus justifications this repository serves. See below. |

**The three sources**, in order of how well they defend the paper:

1. **Abandoned diagram found in the wild** — the design and the drift are both
   genuine. Strongest, and what most of the corpus should be.
2. **Published ground-truth architecture** — validated by people with no stake
   in your result. Credible, but module-level rather than class-level, so it
   needs translating into a `.mdj` and you must say in the paper that you did.
3. **Recovered and frozen** — you reverse-engineer the diagram once and hold it
   fixed. Always available, but conformance is perfect at the recovery commit
   by construction, so it measures departure from a fixed reference rather than
   from a real intention.

Label every project in the paper with which source it came from. A reviewer
will look for exactly that.

---

## Tier 1 — Verified drifted StarUML diagrams (source 1)

These four are the find. Each one ships a real `.mdj` that stopped being
maintained while the code kept moving.

| Repository | Language | Code files | Diagram | Stale | Stars |
|---|---|---|---|---|---|
| [DaxiaK/MyDiary](https://github.com/DaxiaK/MyDiary) | Java | 125 | `UML/MyDiary.mdj` | **465 days** | 1,636 |
| [RenatusRS/FLUDJ-Net](https://github.com/RenatusRS/FLUDJ-Net) | PHP | 2,930 | 19 × `.mdj` in `faza6/` | **1,334 days** | 1 |
| [yusufkaraaslan/GameSpark](https://github.com/yusufkaraaslan/GameSpark) | C# | 63 | `UML/Game Spark UML.mdj` | **845 days** | 16 |
| [manoelcampos/sistema-bancario-java-junit](https://github.com/manoelcampos/sistema-bancario-java-junit) | Java | 10 | `sistema-bancario.staruml.mdj` | **1,777 days** | 17 |

### 1. DaxiaK/MyDiary — the best single candidate

Java, 125 source files, 1,636 stars. The diagram was last touched **4 November
2016**; the code carried on until **12 February 2018**.

- Diagram: [`UML/MyDiary.mdj`](https://github.com/DaxiaK/MyDiary/blob/master/UML/MyDiary.mdj) (359 KB)
- Freeze the diagram at commit `c3703a9d7803f1c0f71684f9a0a4ffe170611134`
- Default branch `master`, not archived, **no licence file** — check before redistributing anything derived from it

```bash
git clone https://github.com/DaxiaK/MyDiary.git
cd MyDiary
git log --oneline c3703a9..HEAD -- '*.java' | wc -l   # commits to replay
```

**Why it is the best of the four:** a real application rather than coursework, a
substantial Java codebase, and a drift window of well over a year. The only
caution is that the repository has been dormant since 2018, so the drift is
finite and bounded — which is fine, and arguably better, because the whole
window is available to replay.

### 2. RenatusRS/FLUDJ-Net — the largest

PHP, 2,930 source files. **19** `.mdj` files under `faza6/`, all last committed
**3 June 2022** (`7373cdfbe864fedbf8c207d33b9a3a4db59456cb`); the code ran on
until **27 January 2026**. That is a 1,334-day window.

- Example diagram: [`faza6/7.01. Registracija korisnika.mdj`](https://github.com/RenatusRS/FLUDJ-Net/blob/main/faza6/7.01.%20Registracija%20korisnika.mdj)
- Default branch `main`, **no licence file**

**Read this before using it.** The nineteen files are named per use case
("Registracija korisnika", "Pretraga proizvoda"), which strongly suggests they
are use-case and sequence diagrams rather than one class diagram. CompX compares
*class* structure. Open two or three in StarUML first and confirm there is a
class diagram in there; if there is not, this repository is not usable regardless
of how good the drift window looks. The 2,930-file count also includes vendored
dependencies — you will want `subdirectory` set narrowly.

### 3. yusufkaraaslan/GameSpark — the clean one

C#, 63 source files, CC0-1.0 licensed (the only one of the four with a clear
licence). Diagram last touched **24 February 2022**, code until **19 June 2024**.

- Diagram: [`UML/Game Spark UML.mdj`](https://github.com/yusufkaraaslan/GameSpark/blob/main/UML/Game%20Spark%20UML.mdj) (1.7 MB — a large model, likely a rich one)
- Freeze at `8902f401cf213796cea348fcabdb7f00dd3b8556`, default branch `main`

**Caveat:** C#, so verify the tree-sitter C# grammar is installed and that
`backend/parsers/polyglot_parser.py` handles it at the fidelity you need. If
your corpus is otherwise Java, one C# project is a *strength* — it supports the
"polyglot" claim — but only if it parses as well as the Java ones do.

### 4. manoelcampos/sistema-bancario-java-junit — a pilot, not a corpus entry

Java, but only **10 source files**. Ships both a StarUML `.mdj` and an
Eclipse `.uml` of the same model, both frozen since **13 August 2020** while the
code ran to June 2025 — a 1,777-day window, the longest here.

- Diagrams: [`sistema-bancario.staruml.mdj`](https://github.com/manoelcampos/sistema-bancario-java-junit/blob/master/sistema-bancario.staruml.mdj) · [`class-diagram-model.uml`](https://github.com/manoelcampos/sistema-bancario-java-junit/blob/master/class-diagram-model.uml)
- Freeze at `16508fe6aa217df6bafd1f8b445ddf1a6760ba72`

Ten files is too small to carry a result. Use it to prove the pipeline runs
end-to-end on a real abandoned diagram, and say in the paper that that is what it
is for. It is also the one repository here that gives you a free consistency
check: two formats of the same model should produce the same comparison.

---

## Tier 2 — Published ground-truth architectures (source 2)

The [**SAEroCon repository**](https://github.com/sebastianherold/SAEroConRepo)
exists for exactly this kind of evaluation: ground-truth intended architectures
for benchmarking architecture-degradation tools. Its
[wiki](https://github.com/sebastianherold/SAEroConRepo/wiki) documents three
systems.

| System | Version to check out | Repository |
|---|---|---|
| **JabRef** | `v3.7` | [JabRef/jabref](https://github.com/JabRef/jabref) |
| **Teammates** | `V5.110` | [TEAMMATES/teammates](https://github.com/TEAMMATES/teammates) |
| **ProM** | 6.9 | [promtools.org](https://promtools.org/) |

```bash
git clone https://github.com/JabRef/jabref.git && cd jabref && git checkout v3.7
```

**Two things I verified that you need to know.** I scanned `SAEroConRepo`
itself: it contains **2,844 source files and zero diagram files of any kind**.
The architectures are mappings and module descriptions, not `.mdj` — so the
translation work `docs/CORPUS-AND-SUBMISSION.md` warns about is real and
unavoidable. Budget for it, and describe the translation in the paper as a
methodological step.

And check out the tagged version. JabRef's current layout (`jabgui/`, `jablib/`,
`jabkit/`) bears no resemblance to 3.7's, so analysing `main` against a 3.7-era
architecture would produce nonsense.

---

## Tier 3 — Reference apps, diagram recovered by you (source 3)

I checked all of these: **none of them contains a diagram file of any kind.** If
you use them, you are reverse-engineering the diagram yourself and must label
them source 3 in the paper.

| Repository | Language | Code files | Why it is here |
|---|---|---|---|
| [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | Java | 50 | The canonical layered reference app — controllers, services, repositories, model. Small enough to recover a diagram by hand in an afternoon. |
| [mybatis/jpetstore-6](https://github.com/mybatis/jpetstore-6) | Java | 46 | Classic layered web app, deliberately simple. |
| [sqshq/piggymetrics](https://github.com/sqshq/piggymetrics) | Java | — | Spring Boot microservices; each service independently layered. |
| [thombergs/buckpal](https://github.com/thombergs/buckpal) | Java | — | Hexagonal architecture, textbook-clean boundaries. Only ~54 commits — pilot only. |

**Be honest about these in the paper.** They are reference applications and a
reviewer may fairly call them toys. The defensible position is that they are
*pilots* establishing the pipeline works, and that Tier 1 and Tier 2 carry the
generalisation claim. Do not build the whole corpus from reference apps.

---

## Checked and rejected

Recording these so nobody spends the afternoon I spent.

| Repository | Why not |
|---|---|
| [staruml/staruml-samples](https://github.com/staruml/staruml-samples) | 14 `.mdj` files and **zero source files**. Genuinely useful for testing that the `.mdj` reader survives real-world models — not usable as corpus. |
| [joaopauloaramuni/projeto-de-software](https://github.com/joaopauloaramuni/projeto-de-software) | 13 diagrams, but all PlantUML `.puml`, and only 29 source files. Coursework. |
| [carluscoooo/UPMArts](https://github.com/carluscoooo/UPMArts) | Has `.uml` files, but **stale = 0 days** — the diagram is maintained alongside the code. No drift to measure. |
| [bl00p1ng/Curso_POO](https://github.com/bl00p1ng/Curso_POO) | Two `.mdj`, but stale only 6 days, and it is a teaching repository. |
| SelimHorri/project-tracking-system-backend-app, NHViet03/Java_Project_RestaurantMS, Kishou76/Library-Management-System | Named in `staruml`-related searches and README text, but contain **no diagram files at all**. |

---

## Finding more yourself

I was working against the unauthenticated GitHub API, which allows 60 requests
per hour, so this list is roughly fifteen repositories deep rather than a
hundred. It is a starting corpus, not an exhaustive search.

**To go deeper, first get a token** — with one, GitHub's *code search* API opens
up, which searches file contents and paths and is far better at this than
repository search:

```bash
export GITHUB_TOKEN=ghp_...              # a classic token with public_repo scope
gh search code 'extension:mdj' --limit 100
gh search code 'path:docs extension:mdj'  # diagrams filed as documentation —
                                          # the most likely to be abandoned
```

**Queries that worked without a token** (repository search only):

- `topic:staruml` sorted by most recently updated
- `staruml in:readme language:java`
- `mdj uml in:readme`

**Other sources worth mining:**

- The [**Lindholmen dataset**](https://se.informatik.uni-rostock.de/en/research/datasets-and-tools/lindholmen-dataset/)
  — 93,000+ UML files across 24,000+ GitHub repositories
  ([Hebig et al., MODELS 2016](https://research.tue.nl/en/datasets/lindholmen-dataset-of-uml-models/) ·
  [Robles et al., MSR 2017](https://ieeexplore.ieee.org/document/7962411/)).
  The `models-db.com` portal has been redirect-looping; use the Rostock mirror.
  If you use it you **must** filter out reverse-engineered diagrams — there is
  [a published classifier for exactly that distinction](https://www.researchgate.net/publication/327690310_An_Automated_Approach_for_Classifying_Reverse-Engineered_and_Forward-Engineered_UML_Class_Diagrams).
- The [`staruml` GitHub topic](https://github.com/topics/staruml) — mostly
  student projects, but that is where three of the four Tier 1 finds came from.

**Then measure the drift** with the script this repository already ships:

```powershell
python research/find_stale_diagrams.py --clone https://github.com/owner/name.git --out results/
```

It reports, per diagram, when the diagram was last edited, when the code was
last edited, how many source-touching commits landed in between, and a verdict.
A large `stale_commits` is a candidate.

---

## Loading one into CompX

1. Clone the repository and check out the commit where the **diagram** was last
   touched — that is the design as its author left it.
2. In CompX: **Projects → New project → Start empty**, then **Code → Upload
   folder**. Point it at the source subdirectory only (`src/main/java`, not the
   repository root) — otherwise you analyse tests and build output and the
   numbers become noise.
3. **Diagram → Upload .mdj**, using the frozen diagram.
4. **Check now.** The first check is version 1 and re-analyses by definition.
5. For the replay study, add the project to `research/corpus.json` and run
   `python research/replay.py` rather than driving the interface by hand:

```json
{
  "name": "mydiary",
  "source": "https://github.com/DaxiaK/MyDiary.git",
  "uml": "research/models/mydiary.mdj",
  "commits": 40,
  "branch": "master",
  "notes": "Abandoned diagram found in the wild (source 1). Diagram frozen at c3703a9, last touched 2016-11-04; code ran to 2018-02-12, a 465-day drift window."
}
```

---

## Honest limits of this file

- **Fifteen repositories were scanned, not the whole of GitHub.** Without a
  token I could not use code search, which is the only good way to find files by
  extension. Expect a token-backed search to find considerably more.
- **I did not open any `.mdj` in StarUML.** I confirmed each file exists, its
  size, and when it was last committed. Whether a given file contains a *class*
  diagram — as opposed to a use-case or sequence diagram, which CompX does not
  compare — is unverified, and is flagged above where I think it is a real risk.
- **Licences are mostly absent.** Only GameSpark has an explicit one (CC0-1.0).
  Check before you redistribute any derived artefact in a replication package.
- **Drift windows are measured in days between commits, not in commits.** For
  the commit counts, run `find_stale_diagrams.py`, which clones and counts
  properly.
