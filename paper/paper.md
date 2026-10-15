# Measuring Conformance Drift Against Abandoned UML Designs: Continuous Checking Without Paying a Language Model Every Commit

*Conference paper, IEEE two-column format (target: MSR, ICSME, SANER or ICSA;
10 pages plus references). Every number in this paper was produced by the
scripts in the replication package on 5 October 2026; Section V-G gives the
commands.*

**Sarvesh Sakthivel** (sarveshs2025@gmail.com)

---

## Abstract

A UML class diagram is committed, and the code moves on without it. A one-off
conformance check can say how far apart the two are on a given day. Drift is a
different question, about how that gap changes over time, and answering it
means checking every commit. Language models make the check easier to build and
its findings easier to read, but they bill for each run, and most commits cannot
change whether code matches a class diagram.

We present CompX, a conformance checker for StarUML class models and code in
Python, Java, JavaScript, TypeScript, C# and PHP. It follows one rule: the
conformance verdict is computed deterministically on every commit, and only the
explanation written by the model is gated. The gate never reads the diagram. It
looks at the structure of the code and decides whether the explanation needs to
be regenerated. We define drift measures over the deterministic findings
(trajectory, direction and element-level survival) and compare four gate
policies.

We test the tool on 16 seeded deviations with known outcomes and on the full
first-parent histories of three open-source projects whose own authors committed
a StarUML model and then stopped maintaining it (142 commits in JavaScript, Java
and C#, with 845 to 1,777 days of drift). On the seeded set, the structural gate
caught all 10 deviations that changed conformance and wasted one call. The
isomorphism gate wasted none and missed only the consistent class rename it is
designed to let through. In the corpus, 12 of 139 commit transitions changed
conformance. Every gate re-analysed all 12, and the structural gate still
skipped 73% of commits and cut counterfactual prompt tokens by 93%. Drift was
rare and went one way. In the one project that drifted, divergences grew by 185
while absences grew by 4, over 11 eroding commits and no repairing ones, and 95%
of the new divergences came in six merge commits. We also learned something
about method: replaying non-merge commits in date order invented 22 of 95
apparent conformance changes by mixing branches, and four defects in our own instrument
showed up only through labelled cases and a check against the user interface.
We release the tool, the deviation set, the corpus and the scripts behind every
number.

**Index Terms —** architectural drift, architecture conformance checking,
reflexion models, UML, large language models, incremental analysis, mining
software repositories.

---

## I. Introduction

The gap between a system's intended design and its code opens slowly and costs
a lot to close. Perry and Wolf gave the problem a name [1], and surveys cover
three decades of attempts to control it [2], [3]. There are several mature ways
to detect it: reflexion models [4], [5], dependency-structure matrices [6] and
dependency-constraint languages [7], which Passos et al. [8] and Knodel and
Popescu [9] compare side by side. Case studies show that drift is real and
expensive in commercial development [10]. Practitioners say they value
conformance checking, yet few keep doing it [11].

**Drift needs a history.** Each of these techniques answers one question at one
moment: does this code conform to this design? Drift is how that answer
changes, and to see it you have to repeat the check commit after commit.
Evolution studies usually compare architectures at a handful of releases [12],
[13]. Where design documents have been followed commit by commit, researchers
measured how much of the code the diagram covers, not whether the code conforms
to it in the reflexion sense [14].

**What language models cost.** A model can relate a class diagram to code
without a hand-maintained mapping and can explain each finding in prose. That
helps with the maintenance burden that made earlier conformance tools fall out
of use [11]. It also puts a price on every check. A check that once cost almost
nothing is now paid per token, and running it on every commit multiplies the
bill by the length of the history. Most of those commits cannot change
conformance to a class diagram anyway. A reformatted file, a new comment or a
renamed local variable leaves it exactly as it was. A 2025 systematic review of
language models in software architecture looked at 18 studies and reports: *"We
found no articles regarding evaluating quality aspects of software
architecture, such as evolvability, and architecture conformance checking"*
[15].

**Where the design comes from.** If the diagram is recovered from the code being
studied, it conforms by construction and tells us nothing. Abandoned diagrams
avoid that problem, and there are plenty of them. Romeo et al. deep-cloned
13,152 GitHub repositories and found UML in 552 (4.2%). Fewer than a third of
the projects with UML touched a UML file at all in 2022 [16]. An abandoned
diagram is a real statement of intended design that nobody drew for a study, so
the drift away from it is real too.

We ask four research questions:

* **RQ1:** How does real code drift away from an abandoned class model?
* **RQ2:** How many model calls does each gate avoid?
* **RQ3:** What does skipping cost?
* **RQ4:** Can we trust the measuring instrument?

**Contributions.**

1. A design rule for conformance checking with language models: *gate the
   explanation, never the verdict*. If the gate gets a decision wrong, the
   explanation may go stale, but the score and the lists of divergences and
   absences stay correct (Section III-A).
2. Drift measures built only from deterministic reflexion findings: trajectory,
   direction (led by divergences or by absences), and element survival with
   Kaplan-Meier censoring (Section III-E).
3. Four structural gate policies behind one switch, and a replay method that
   counts a miss as a stale served analysis, judged against a forced oracle at
   every commit (Sections III-D and IV-B).
4. A study on 16 labelled deviations and the complete first-parent histories of
   three projects with StarUML models their authors abandoned, plus a
   sensitivity analysis on 678 non-merge commits (Section V).
5. Two lessons for anyone measuring drift: non-merge replay invents drift by
   mixing branches, and four defects in our instrument were caught only by
   labelled cases and a check against the interface (Sections V-E and V-F).
6. A replication package with the tool, the deviations, the frozen models, the
   raw runs and the scripts behind every table and figure.

---

## II. Background and Related Work

**Conformance checking.** Our vocabulary comes from reflexion models [4], [5].
A *convergence* appears in both the design and the code. A *divergence* appears
in the code but not the design, and an *absence* in the design but not the
code. ReflexML [17] uses UML as the high-level model in a reflexion analysis,
which makes it the classical work closest to our input. Passos et al. [8] and
Knodel and Popescu [9] compare the main approaches, and DSMs [6] and DCL [7]
swap the explicit model for dependency rules. All of them need the intended
architecture written in a tool-specific notation, plus a mapping from source to
model. We cut the mapping down to matching names, which is how people normally
read a class diagram anyway (Section VII).

**Drift and erosion.** De Silva and Balasubramaniam conclude that detection is
still the practical bottleneck [2]. Studies of architecture evolution compare
recovered architectures across releases [12], [13]. Li et al. look for signs of
erosion in code review [18], and Tekinerdogan builds drift analysis on reflexion
viewpoints [19]. The closest work to ours is by Romeo et al. [14]. They link
PlantUML diagrams to Java classes and track how much of the code the UML
*covers* across releases and commits, which captures drift between design,
implementation and documentation. We measure reflexion-style *conformance*
against a frozen StarUML model at every first-parent commit, keep its two
directions apart, and analyse how long designed elements survive, with
censoring.

**Incremental analysis.** Egyed's instant consistency checking [20], [21]
re-evaluates only the UML consistency rules a model change can affect, and IncA
[22] does the same for program analyses. Our gate borrows that idea, but the
economics differ. Those approaches save CPU time on cheap, deterministic checks,
where checking a bit too much costs almost nothing. We are saving money on an
expensive step that is not deterministic. So every skip needs a stated way it
can fail and a measured miss rate.

**Language models and cost.** The 2025 review [15] found no conformance work
based on language models. It also notes that about a third of the studies it
covers have no baseline; our deterministic mode is one by construction. Hybrid
designs ground a model in a static analyser [23]. Cost control through cascades
and response caching [24], or through semantic caches keyed on how similar
prompts are [25], makes its decision from the prompt. Our gate decides from a
checked structural property of the code itself. We follow the reporting
guidelines of Baltes et al. [26].

---

## III. Approach

### A. Gate the explanation, never the verdict

Fig. 1 shows what happens in one analysis. Tree-sitter parses the source into an
implementation graph, the StarUML model is parsed into a design model, and a
deterministic engine computes the reflexion findings. All of this runs on every
commit, whatever the gate says. The gate decides one thing: whether the model's
written analysis (gaps and recommendations in prose) is regenerated for the
changed part of the graph or carried over from the previous version.

![Fig. 1](figures/fig-pipeline.svg)
*Fig. 1. One analysis. The verdict is computed on every commit, and only the
explanation is gated. The gate's only input is code structure (dashed line). The
solid arrow into the gate shows order, not data flow, since the gate never reads
the diagram.*

Because the verdict is recomputed every time, a commit skipped by mistake leaves
behind an out-of-date explanation, but the score and the lists of divergences
and absences beside it are current. In Section VI-A we argue that any tool
putting a language model into a conformance loop should work this way.

### B. Extraction

We extract code structure from six languages. The extractor collects classes,
interfaces, methods, fields (declared ones, or those assigned through
`self.`/`this.` in languages without declarations), supertypes along with the
clause that declared them, imports and call sites. Calls are resolved through a
symbol table for the whole project. When a call has several plausible targets,
we count it as ambiguous instead of linking it to all of them, and every run
reports its resolution rate.

### C. Deterministic comparison

Design and code are matched by element name. Each designed class is a check, as
is each designed attribute and operation of a class that exists, and each
designed generalization and realization. The score is the share of checks that
pass. Associations cannot be proven from code. A typed field is good evidence
and a matching name is weak evidence, so we grade associations and leave them
out of the score. Three conventions affect the counts:

* **Supertype kind.** Where the language says whether a supertype is extended
  or implemented (Java, TypeScript, PHP), the kind must match the diagram.
  Where it does not (Python, JavaScript, and C# bases from outside the
  project), the declared supertype satisfies either UML relation.
* **Constructors.** A constructor missing from the diagram is not counted as a
  divergence, but a constructor the diagram specifies is still checked.
* **Counting.** Convergences are passed checks plus satisfied relations.
  Divergences are undocumented classes plus undocumented members of designed
  classes. Absences are missing classes, missing members and unsatisfied
  relations that count toward the score.

### D. Gates

Each gate is defined by the property it tests. That property sets what the gate
can safely ignore and what it can miss (Table I). None of the gates reads the
diagram.

**Table I. Gate policies.**

| Gate | Re-analyses when | Absorbs | Designed-in risk |
|---|---|---|---|
| `always` | every commit | nothing | none (baseline) |
| `content` | analysed bytes change | nothing structural | pays for comments, formatting |
| `structural` | the AST fingerprint changes | formatting, comments, literals, local names, statement order | a semantic change with identical structure |
| `isomorphism` | fingerprint changes **and** the graph is not isomorphic to the previous one | also pure renames and reorderings | a consistent rename of a class the diagram names |

The fingerprint covers declarations, types, supertypes, imports and, for each
callable, the *set* of names it calls. It ignores receivers, local names,
statement order, comments, formatting and literals. The set of called names has
to be in there. Without it, the gate would never notice a controller that starts
calling the persistence layer directly. The isomorphism gate runs VF2 [27], with
node matchers that preserve kind and edge matchers that preserve the relation.
If the graphs are isomorphic, the mapping between them is the renaming, so the
cached explanation is simply relabelled. We specify how this gate fails up
front. A consistent rename keeps the shape of the graph, so the gate reuses the
explanation, yet conformance has changed if the diagram names the renamed class.
When a gate does fire, the model only sees the changed part of the graph and
the nodes one step away from it, along with the deterministic findings as facts
it must not contradict. So the cost of a re-analysis depends on the size of the
change, not the size of the project.

### E. Drift measures

Every measure comes from the oracle's findings at each commit. No gate has any
influence on them.

1. **Trajectory.** The number of convergences, divergences and absences at
   every commit after the freeze.
2. **Direction.** The net change in divergences and in absences. We call a
   window *divergence-led* when divergences grew at least as much as absences,
   meaning the code grew away from the design. It is *absence-led* when
   designed structure disappeared faster. We also count *eroding* commits,
   where total deviations went up, and *repairing* commits, where they went
   down.
3. **Element survival.** At each commit, every designed element is
   *conforming*, *divergent* (all designed members present, plus undocumented
   ones), *partial* (a designed member missing) or *absent*. For elements that
   conformed at the freeze, we measure the time until their first deviation,
   censor it at the end of the window, and estimate it with Kaplan-Meier [28].
   The half-life is the first commit at which survival reaches 0.5; if it never
   does, we report "not reached". Elements that already deviated at the freeze
   are reported on their own instead of being given a time of zero.

---

## IV. Study Design

### A. Subjects

**Controlled set.** We built a four-layer Python reference project (controller,
service, domain, persistence) that matches its StarUML model exactly, and wrote
16 reproducible mutations of it. Each mutation states up front whether it should
change structure and whether it should change the deterministic findings. Nine
of them break conformance: a deleted designed method, a deleted designed class,
an undocumented class, a removed realization, an untyped association, a
controller that bypasses the service, an inverted dependency, and partial and
consistent class renames. Two change only structure. One adds an undocumented
private helper, which counts as a divergence, and the other adds an optional
parameter, which a comparison by name cannot see. The last five are negative
controls (a comment, whitespace, a local rename, reordered methods and a
docstring). Ten of the sixteen should change the findings.

**Corpus.** We looked for repositories where the project's own authors committed
a StarUML `.mdj` *class* model and then stopped editing it while work on the
code went on. For each model we counted how many commits touched source after
its last edit. Three projects qualified (Table II). All three designs were
*found* in the repositories, not recovered from code. The candidates we looked
at and rejected are listed, with reasons, in the tool's repository. Most were
turned down because the model had no classes (only use-case or sequence
diagrams), because the model was kept up to date with the code (so there was no
drift window), or because there was no source code to pair it with.

**Table II. Corpus. Figures at the freeze commit.**

| Project | Lang. | Model last edited | Code until | Days | Commits | Files | LOC | Classes / relations in model | Score at freeze |
|---|---|---|---|---|---|---|---|---|---|
| DiscordBotRPG-Server | JS | 2019-12-01 `f2ab878` | 2023-01-27 | 1,153 | 104 | 91 | 13,221 | 22 / 69 | 33.33% (29/87) |
| sistema-bancario-java-junit | Java | 2020-08-13 `16508fe` | 2025-06-26 | 1,777 | 25 | 8 | 659 | 8 / 9 | 90.00% (36/40) |
| GameSpark | C# | 2022-02-25 `8902f40` | 2024-06-19 | 845 | 13 | 52 | 3,629 | 53 / 88 | 91.72% (432/471) |

*Commits: the freeze commit and every first-parent commit after it. Files and
LOC: the analysed source directory (`bin/`, `src/main/java/`, `Assets/…/Script/`).*

The DiscordBotRPG model, as committed, was not valid JSON: four string literals
were missing their closing quote. We added exactly those four characters and
confirmed with a line diff that nothing else changed. The other two models are
semantically identical to the originals in their repositories.

### B. Procedure

We replay each project from the freeze commit along the **first-parent
mainline**, merges included, so every step is a real change from a parent to its
child (Section V-E shows why this matters). At every commit, we check out the
source and analyse it once with a forced full analysis, which we call the
**oracle**, and once with each gate. Each gate gets its own project directory,
so no gate can benefit from another gate's cache. A commit **changed
conformance** if the oracle's findings differ from its findings at the previous
commit. It **touched source** if any analysed file changed.

**What counts as a miss.** The deterministic findings are recomputed on every
run, so a gated run always produces the same findings as the oracle. Comparing
the two, as an early version of our harness did, will always report zero
misses. What a gate can leave stale is the explanation it hands to the user. So
each gate keeps a record of the findings its current explanation was written
for. A run counts as **missed** when the gate reused that explanation and those
findings no longer match the oracle's. We report *recall* (the share of
conformance-changing commits that were re-analysed), *specificity* (the share of
all other commits that were skipped) and stale runs as a share of all runs. We
also report a recovery horizon, the number of commits from the start of a stale
stretch until it is refreshed, estimated with Kaplan-Meier and censoring.

**Cost.** Every run used the deterministic offline mode. No model was ever
called, so the study can be reproduced exactly. Whenever a gate would have
called a model, we record the size of the prompt it would have sent, in
`cl100k_base` tokens, and record zero when the gate reused. These
*counterfactual prompt tokens* are an estimate of cost, not a measurement of
spend.

### C. Statistics

All proportions come with 95% Wilson intervals [29]. We compare the two
candidate gates with McNemar's exact test [30] on the commits where they
disagree. When there are fewer than six such commits we do not report the test,
because no result could then reach p < 0.05. Survival is estimated with
Kaplan-Meier [28]. If a rate has an empty denominator, we report it as *not
measured* and never as zero.

---

## V. Results

### A. RQ1: How the code drifted

**Table III. Drift over the post-freeze window (oracle findings, first-parent).**

| Project | Transitions | Touched source | Changed conformance | Divergences | Absences | Eroding / repairing | Direction | Score |
|---|---|---|---|---|---|---|---|---|
| DiscordBotRPG | 103 | 62 | 12 | 313 → 498 | 106 → 110 | 11 / 0 | divergence-led | 33.33% → 34.04% |
| sistema-bancario | 24 | 8 | 0 | 47 → 47 | 5 → 5 | 0 / 0 | stable | 90.00% → 90.00% |
| GameSpark | 12 | 1 | 0 | 45 → 45 | 64 → 64 | 0 / 0 | stable | 91.72% → 91.72% |
| **Pooled** | **139** | **71** | **12 (8.6%, CI 5.0–14.5%)** | | | | | |

![Fig. 2](figures/fig-drift.svg)
*Fig. 2. Divergences and absences at every first-parent commit after the
diagram was frozen.*

**Frequency and direction.** Only 12 of 139 commit transitions changed
conformance, and all 12 were in DiscordBotRPG. Even there, 51 of the 62 commits
that touched source changed nothing. In the two smaller projects, nine commits
touched source after the freeze, and none of them changed anything a class
diagram describes. When DiscordBotRPG did drift, it drifted one way. The code
grew away from its design, adding 185 divergences while absences rose by only
4. There were 11 eroding commits and no repairing ones, so the drift never
reversed. The first change in conformance came at mainline commit 38, in April
2020, four months after the freeze.

**Where the divergence came from.** Between the freeze and the last commit,
undocumented classes went from 80 to 131 (+51) and undocumented members of
designed classes from 233 to 367 (+134). Together that is exactly the 185 new
divergences. Missing designed members went from 33 to 38. Missing designed
classes fell from 13 to 12, because `Monster` came back. Most of the divergence
arrived with releases. Six merge commits from release branches brought in 175 of
the 185 new divergences (95%). A single merge, pull request #30 for release 1.10
in January 2021, brought in 103 (56%), and the three largest merges brought in
160 (86%).

**Element survival.** Table IV explains why survival analysis has little to say
about this corpus. In DiscordBotRPG, not one of the 22 designed elements
conformed at the freeze: 13 were already absent, 7 were partial and 2 were
divergent. The design had drifted before the authors stopped updating the
diagram. The drift we saw afterwards took the form of undocumented code built up
around the designed elements. In the two smaller projects, 33 elements conformed
at the freeze and none of them deviated during the window. Survival stayed at
1.0, and the half-life was never reached (it is beyond 24 and 12 commits,
respectively).

**Table IV. Designed-element status at the freeze and at the end of the window.**

| Project | Designed | Conforming | Divergent | Partial | Absent | Changed status |
|---|---|---|---|---|---|---|
| DiscordBotRPG | 22 | 0 → 0 | 2 → 2 | 7 → 8 | 13 → 12 | `Monster`: absent → partial |
| sistema-bancario | 8 | 1 → 1 | 4 → 4 | 1 → 1 | 2 → 2 | none |
| GameSpark | 53 | 32 → 32 | 5 → 5 | 16 → 16 | 0 → 0 | none |

*Answer to RQ1.* In the one project that drifted, most of the design was gone by
the time the diagram was abandoned. The drift that followed added code around
the design instead of removing it, never reversed, and arrived through release
merges. In the other two projects, the abandoned diagrams stayed exactly as
accurate as on the day they were last edited.

### B. RQ2: What each gate avoids

**Table V. Gates over the corpus (142 commits, 139 judged transitions).**

| Gate | Re-analysed | Skip rate [95% CI] | Recall (n = 12) | Specificity (n = 127) | Counterfactual tokens | Saved |
|---|---|---|---|---|---|---|
| always | 142 | 0.0% [0–3] | 100% [76–100] | 0.0% [0–3] | 19,770,303 | — |
| content | 74 | 48% [40–56] | 100% [76–100] | 54% [45–62] | 6,872,366 | 65% |
| structural | 39 | 73% [65–79] | 100% [76–100] | 81% [73–87] | 1,392,753 | 93% |
| isomorphism | 37 | 74% [66–80] | 100% [76–100] | 83% [75–88] | 1,386,369 | 93% |

![Fig. 3](figures/fig-gates.svg)
*Fig. 3. Skip rate against recall of conformance changes, with 95% Wilson
intervals.*

The two structural gates skipped roughly three commits out of four. They saved
even more tokens (93%) than that skip rate suggests, because each re-analysis
was scoped to the change. Under the structural gate, a re-analysis prompt
averaged 35,712 tokens (median 16,101). A full-project prompt under `always`
averaged 139,227 (median 146,320). The content gate skipped fewer than half the
commits. In DiscordBotRPG it skipped only the 41 of 103 transitions that touched
no analysed file, and its re-analyses averaged 92,870 tokens. In 35 of its 71
re-analyses after each project's first commit, bytes had changed but structure
had not. That left an empty change set and nothing to scope the prompt to, so
the whole project was sent.

Looking at each project on its own, the structural gate skipped 67% of
DiscordBotRPG's commits, 88% of sistema-bancario's and 85% of GameSpark's, and
saved 93.0%, 93.6% and 90.6% of their counterfactual tokens. One full-project
prompt for DiscordBotRPG came to 140,452 tokens at the freeze and 225,324 at the
end of its history. That is more than the 128k-token context window of many
deployable models.

*Answer to RQ2.* Gating on structure avoided three quarters of the model calls.
With scoping on top, it avoided more than 90% of the prompt tokens.

### C. RQ3: What skipping costs

**Corpus.** No gate ever served a stale explanation. Every gate re-analysed all
12 commits that changed conformance (recall 12/12, 95% CI 76 to 100%). With nothing
to recover from, the recovery horizon could not be measured. The structural and
isomorphism gates disagreed on just two commits, both in sistema-bancario,
where the isomorphism gate let through a change that altered no finding. Two
disagreements are too few for McNemar's test, which needs at least six. The
structural gate paid for its safety with 24 re-analyses of commits whose
findings had not changed (specificity 81%). The content gate paid for 59
(specificity 54%).

**Controlled set.** Table VI is the only result where the ground truth is beyond
dispute.

**Table VI. Seeded deviations (16 mutations; 10 change the findings).**

| Gate | TP | FN | FP | TN | Precision | Recall |
|---|---|---|---|---|---|---|
| always | 10 | 0 | 6 | 0 | 0.63 | 1.00 |
| content | 10 | 0 | 6 | 0 | 0.63 | 1.00 |
| structural | 10 | 0 | 1 | 5 | 0.91 | 1.00 |
| isomorphism | 9 | 1 | 0 | 6 | 1.00 | 0.90 |

The structural gate's one false positive was the added optional parameter. The
fingerprint notices the extra argument, but a comparison by name has no use for
it, and the isomorphism gate lets it through. The isomorphism gate's one miss
was the consistent rename of `OrderRepository` described in Section III-D, the
failure we had designed in and the only one we saw. Both structural
gates skipped all five negative controls, and both baselines paid for all five.

*Answer to RQ3.* On the corpus, skipping cost nothing. On the labelled set, the
only cost was the rename case we had already specified, and with our design
that case can make only the explanation stale, never the verdict.

### D. RQ4: Can the instrument be trusted?

*Labels.* For all 16 mutations, the oracle's findings changed exactly when the
label said they should.

*Oracle determinism.* Each project's replay ran as four separate processes, one
per gate, each with its own oracle. Before merging the results, we compared the
four copies of the oracle at every commit on conformance change, source change,
reflexion counts, score and a hash of the findings. They agreed at all 142
commits, and at all 716 commits of the non-merge sensitivity replay.

*Interface agreement.* We also checked the tool through its web interface,
driving it with browser automation. We created projects from the
freeze-commit source of sistema-bancario and DiscordBotRPG, uploaded the frozen
models and ran a check. The interface reported 90% (36 of 40 checks) and 33.33%
(29 of 87), the same as the research pipeline. When we checked the unchanged
DiscordBotRPG project again, the structural gate skipped it ("fingerprint
unchanged"), and the interface still showed the current 33.33%, as Section
III-A requires.

### E. Sensitivity: replaying non-merge commits instead

A common alternative is to replay every non-merge commit after the freeze in
date order. For DiscordBotRPG that gives 678 commits. The start and end points
are the same (divergences 313 → 498, absences 106 → 110), but the path between
them is not. This replay shows 95 apparent changes in conformance, 77 eroding
commits and 15 "repairing" ones. Of its 677 transitions, 64 connect commits that
are not parent and child. They are neighbouring commits from parallel branches.
On one branch a class was still called `Monstre`, and on the other it had been
renamed `Monster`. Those 64 transitions account for 22 of the 95 apparent
changes. The gate results barely move (recall 95/95 for every gate, a structural
skip rate of 53%, and a 94% counterfactual saving). So the conclusions about
cost hold whichever history model we use, but the conclusions about drift do
not.

### F. Defects found in the instrument

Each of these would have skewed a headline number, and none was caught by tests
that only checked whether the pipeline ran. Items 1 to 4 are defects in the
instrument. Item 5 is a flaw in how we replayed history.

1. **Supertype order.** Supertype names were sorted to build the fingerprint,
   and the comparator then took the first name as the superclass. So
   `class A extends Zeta implements Alpha` turned into `extends Alpha`, and a
   Python realization could never be satisfied. The seeded
   *remove-realization* deviation went unnoticed, and sistema-bancario scored
   80% instead of 90% because four `implements Cadastro` realizations were
   scored as generalizations.
2. **JavaScript fields.** Fields assigned as `this.x = …` were never extracted,
   so every designed attribute of a JavaScript class looked absent.
   DiscordBotRPG scored 19.54% instead of 33.33% at its freeze.
3. **An oracle blind to extra members.** The oracle left out undocumented
   members, so it could not see the seeded *add-private-helper* divergence.
4. **Misses that could never happen.** The replay compared freshly computed
   findings with the oracle's, which are equal by construction. The corpus
   miss rate came out as zero no matter what a gate did.
5. **Branch interleaving** (Section V-E). The order of the commits alone
   produced 23% of the apparent changes in conformance.

All of these are fixed, and each has a regression test (279 tests in total).

### G. Reproducing the results

```
python research/evaluate_deviations.py --out results/                       # Table VI
python research/replay.py --corpus research/corpus.json --out results/      # raw runs
python research/analyze_statistics.py --runs results/runs.csv --out results/ --replication
python research/make_figures.py --results results/ --out paper/figures/     # Figs. 2-3
python research/paper_numbers.py --results results/                         # Tables III-V
```

---

## VI. Discussion

### A. Gate the explanation, never the verdict

People usually treat cost control for language models as a trade-off: save
money, lose some correctness. We accept that trade-off for the explanation and
refuse it for the verdict, because the deterministic comparison is cheap. A full
analysis of DiscordBotRPG, which grew from 13,221 to 21,975 lines over its
window, took a median of 470 ms and never more than 720 ms. There is no reason
to gate it, so the gate only decides whether to pay for new prose. The worst a
gate can do is leave a developer reading an explanation written for an earlier
version of the code, *with a current score and current findings right next to
it.* If a tool lets a cost optimisation change its verdict, the correctness of
that verdict now depends on a heuristic. We think keeping the two apart should
be a requirement.

This separation also answers a fair question: why not call the model exactly
when the deterministic findings change? That policy costs nothing to run and has perfect
recall *against this oracle*, and that is precisely why this oracle cannot
evaluate it: the policy and the ground truth would be the same function. It
would also throw away changes that the structural gates notice and the findings
do not. A new call between two designed classes, for example, changes no
reflexion count, but it may be exactly what a reviewer wants explained. Weighing
that trade-off means judging the explanations themselves.

### B. Choosing a gate

A gate is safe exactly when the property it tests implies the property you care
about. The content gate is safe in a trivial way, and on real histories it
wastes a lot: it re-analysed 59 commits that changed nothing a diagram
describes. The structural gate missed nothing in either evaluation, at the cost
of 24 unnecessary re-analyses over 139 transitions. The isomorphism gate saved
only a little more in practice (two commits), and its one miss was the rename
we specified. Our advice is to use the structural gate when your diagram names
concrete classes. If your diagram describes roles, the isomorphism gate's small
extra saving is worth having.

### C. What the drift says about abandoned diagrams

Two of the three abandoned diagrams were as accurate at the end of their windows
as on the day they were last edited. Development went on for 845 and 1,777 days
without touching anything they describe. The third had lost most of its design
before it was abandoned, with 13 of its 22 designed classes already absent at
the freeze. After that, the code grew *around* what was left of the design
instead of wearing it down further: 51 new undocumented classes, 134 new
undocumented members, 4 new absences and no repairs. Since this growth came in
with release merges, it points to a practical schedule. A conformance check
gated on structure is cheap enough to run on every commit. The drift worth a
person's attention, though, piles up where release branches are merged.

### D. Methodological lessons

Replaying a repository's non-merge commits in date order is convenient, and for
drift it gives the wrong answer. Neighbouring commits can come from different
branches, so the replay sees changes nobody actually made. In our data it
invented about a quarter of the apparent drift events and all 15
"repairs", while hardly changing the cost results. Drift studies should replay
the first-parent history, or walk the full commit graph and compare each commit
with its own parent. Instruments for drift studies also need labelled cases.
Two of the defects in Section V-F would have produced believable, wrong numbers
while every unlabelled test passed.

---

## VII. Threats to Validity

**Construct.** We compare by name. If a class is renamed in the code but not in
the diagram, we count an absence and a divergence. That is how reflexion models
read it, but it may overstate drift when the change is only a rename. We grade
associations instead of scoring them, and by convention we do not count
constructors as divergences; either choice changes the counts. Call resolution
was 25% to 37% at the freeze commits, with no ambiguous call sites. Most of the
unresolved calls go to library code that a class diagram does not describe, but
resolution still limits how much call structure the fingerprint can capture.
Our costs are counterfactual prompt sizes, not measured spend, and they leave
out completion tokens.

**Internal.** The oracle is the same deterministic engine the gates rely on. A
change in conformance that the engine cannot see is invisible to the oracle as
well, and the labelled set only protects against the kinds of deviation it
contains. We found and fixed four defects in the instrument and one flaw in the
replay method (Section V-F). There may be others like them, which is why we
release every raw run.

**External.** Three projects make a small corpus, and the one that drifted
dominates every rate across the corpus. Two of the windows are short (13 and 25
commits). The results describe these histories, not open-source software in
general. The way we selected projects is itself a filter: it keeps only projects
whose authors drew a StarUML class diagram and committed it. A diagram may have
been abandoned because the part of the system it described was abandoned, so
Table IV lists elements one by one to let readers judge. Because no language
model was called, we did not measure how model output varies from run to run
[26]. Our design limits that variation to the explanation.

**Conclusion.** Every proportion has a Wilson interval. Recall rests on 12
commits that changed conformance (CI 76% to 100%). That is enough to say no gate
failed often, but not enough to say gates never fail. McNemar's test could not
be computed. Pooled rates treat commits as independent, which is why we also
report figures per project.

---

## VIII. Conclusion

We wanted to measure conformance drift at every commit after a design was
frozen, without paying a language model to re-read an unchanged architecture
each time. Separating the deterministic verdict from the model's explanation
made that possible, and safe. Drift is measured from a verdict that is never
gated, and the gate only controls what is spent on prose. On three projects
whose authors abandoned their StarUML models, a structural gate skipped 73% of
commits and cut counterfactual prompt tokens by 93%, and it still re-analysed
all 12 commits that changed conformance. On 16 labelled deviations, it caught
all 10 that mattered. The drift itself was rare. It added code around the
design, never reversed, and arrived through release merges. To measure it
correctly we had to replay the first-parent history, because replaying
non-merge commits in date order invented about a quarter of the apparent drift
events.

The corpus should grow, through a systematic search
of public repositories for abandoned class models. The explanations themselves
need evaluating, including how stable they are across runs and what they add
beyond the findings. And gating policies that combine code structure with
changes in the deterministic findings are worth testing.

---

## Data Availability

The tool, the seeded deviations, the corpus manifest and frozen models, the raw
per-run data (`runs.csv`, `drift_elements.csv`) and the scripts that produce
every table and figure are available in the replication package
(`<archive link or Zenodo DOI>`).

---

## References

All entries were checked against Crossref, arXiv or the publisher's record on
5 October 2026.

[1] D. E. Perry and A. L. Wolf, "Foundations for the study of software architecture," *ACM SIGSOFT Softw. Eng. Notes*, vol. 17, no. 4, pp. 40–52, 1992, doi: 10.1145/141874.141884.

[2] L. de Silva and D. Balasubramaniam, "Controlling software architecture erosion: A survey," *J. Syst. Softw.*, vol. 85, no. 1, pp. 132–151, 2012, doi: 10.1016/j.jss.2011.07.036.

[3] L. Hochstein and M. Lindvall, "Combating architectural degeneration: A survey," *Inf. Softw. Technol.*, vol. 47, no. 10, pp. 643–656, 2005, doi: 10.1016/j.infsof.2004.11.005.

[4] G. C. Murphy, D. Notkin, and K. Sullivan, "Software reflexion models: Bridging the gap between source and high-level models," in *Proc. 3rd ACM SIGSOFT Symp. Found. Softw. Eng.*, 1995, pp. 18–28, doi: 10.1145/222124.222136.

[5] G. C. Murphy, D. Notkin, and K. J. Sullivan, "Software reflexion models: Bridging the gap between design and implementation," *IEEE Trans. Softw. Eng.*, vol. 27, no. 4, pp. 364–380, 2001, doi: 10.1109/32.917525.

[6] N. Sangal, E. Jordan, V. Sinha, and D. Jackson, "Using dependency models to manage complex software architecture," in *Proc. OOPSLA*, 2005, pp. 167–176, doi: 10.1145/1094811.1094824.

[7] R. Terra and M. T. Valente, "A dependency constraint language to manage object-oriented software architectures," *Softw. Pract. Exper.*, vol. 39, no. 12, pp. 1073–1094, 2009, doi: 10.1002/spe.931.

[8] L. Passos, R. Terra, M. T. Valente, R. Diniz, and N. das Chagas Mendonça, "Static architecture-conformance checking: An illustrative overview," *IEEE Softw.*, vol. 27, no. 5, pp. 82–89, 2010, doi: 10.1109/MS.2009.117.

[9] J. Knodel and D. Popescu, "A comparison of static architecture compliance checking approaches," in *Proc. WICSA*, 2007, doi: 10.1109/WICSA.2007.1.

[10] J. Rosik, A. Le Gear, J. Buckley, M. A. Babar, and D. Connolly, "Assessing architectural drift in commercial software development: A case study," *Softw. Pract. Exper.*, vol. 41, no. 1, pp. 63–86, 2011, doi: 10.1002/spe.999.

[11] N. Ali, S. Baker, R. O'Crowley, S. Herold, and J. Buckley, "Architecture consistency: State of the practice, challenges and requirements," *Empir. Softw. Eng.*, vol. 23, no. 1, pp. 224–258, 2018, doi: 10.1007/s10664-017-9515-3.

[12] D. M. Le, P. Behnamghader, J. Garcia, D. Link, A. Shahbazian, and N. Medvidovic, "An empirical study of architectural change in open-source software systems," in *Proc. MSR*, 2015, pp. 235–245, doi: 10.1109/MSR.2015.29.

[13] P. Behnamghader, D. M. Le, J. Garcia, D. Link, A. Shahbazian, and N. Medvidovic, "A large-scale study of architectural evolution in open-source software systems," *Empir. Softw. Eng.*, vol. 22, no. 3, pp. 1146–1193, 2017, doi: 10.1007/s10664-016-9466-0.

[14] J. Romeo, M. Raglianti, C. Nagy, and M. Lanza, "Capturing and understanding the drift between design, implementation, and documentation," in *Proc. 32nd IEEE/ACM Int. Conf. Program Comprehension (ICPC)*, 2024, pp. 382–386, doi: 10.1145/3643916.3644399.

[15] L. Schmid, T. Hey, M. Armbruster, S. Corallo, D. Fuchß, J. Keim, H. Liu, and A. Koziolek, "Software architecture meets LLMs: A systematic literature review," arXiv:2505.16697, 2025.

[16] J. Romeo, M. Raglianti, C. Nagy, and M. Lanza, "UML is back. Or is it? Investigating the past, present, and future of UML in open source software," in *Proc. 47th IEEE/ACM Int. Conf. Softw. Eng. (ICSE)*, 2025, pp. 2342–2354, doi: 10.1109/ICSE55347.2025.00155.

[17] J. Adersberger and M. Philippsen, "ReflexML: UML-based architecture-to-code traceability and consistency checking," in *Proc. ECSA*, LNCS, 2011, pp. 344–359, doi: 10.1007/978-3-642-23798-0_37.

[18] R. Li, P. Liang, P. Avgeriou, and Y. Wang, "Towards automated identification of violation symptoms of architecture erosion," arXiv:2306.08616, 2023.

[19] B. Tekinerdogan, "Architectural drift analysis using architecture reflexion viewpoint and design structure reflexion matrices," in *Software Quality Assurance*. Morgan Kaufmann, 2016, pp. 221–236, doi: 10.1016/B978-0-12-802301-3.00010-7.

[20] A. Egyed, "Instant consistency checking for the UML," in *Proc. 28th Int. Conf. Softw. Eng. (ICSE)*, 2006, pp. 381–390, doi: 10.1145/1134285.1134339.

[21] A. Egyed, "Automatically detecting and tracking inconsistencies in software design models," *IEEE Trans. Softw. Eng.*, vol. 37, no. 2, pp. 188–204, 2011, doi: 10.1109/TSE.2010.38.

[22] T. Szabó, S. Erdweg, and M. Voelter, "IncA: A DSL for the definition of incremental program analyses," in *Proc. 31st IEEE/ACM Int. Conf. Automated Softw. Eng. (ASE)*, 2016, pp. 320–331, doi: 10.1145/2970276.2970298.

[23] S. Blyth, S. A. Licorish, C. Treude, and M. Wagner, "Static analysis as a feedback loop: Enhancing LLM-generated code beyond correctness," arXiv:2508.14419, 2025.

[24] L. Chen, M. Zaharia, and J. Zou, "FrugalGPT: How to use large language models while reducing cost and improving performance," arXiv:2305.05176, 2023.

[25] X. Liu, B. Atalar, X. Dai, J. Zuo, S. Wang, and J. C. S. Lui, "Semantic caching for low-cost LLM serving: From offline learning to online adaptation," arXiv:2508.07675, 2025.

[26] S. Baltes *et al.*, "Guidelines for empirical studies in software engineering involving large language models," arXiv:2508.15503, 2025.

[27] L. P. Cordella, P. Foggia, C. Sansone, and M. Vento, "A (sub)graph isomorphism algorithm for matching large graphs," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 26, no. 10, pp. 1367–1372, 2004, doi: 10.1109/TPAMI.2004.75.

[28] E. L. Kaplan and P. Meier, "Nonparametric estimation from incomplete observations," *J. Amer. Statist. Assoc.*, vol. 53, no. 282, pp. 457–481, 1958, doi: 10.1080/01621459.1958.10501452.

[29] E. B. Wilson, "Probable inference, the law of succession, and statistical inference," *J. Amer. Statist. Assoc.*, vol. 22, no. 158, pp. 209–212, 1927, doi: 10.1080/01621459.1927.10502953.

[30] Q. McNemar, "Note on the sampling error of the difference between correlated proportions or percentages," *Psychometrika*, vol. 12, no. 2, pp. 153–157, 1947, doi: 10.1007/BF02295996.
