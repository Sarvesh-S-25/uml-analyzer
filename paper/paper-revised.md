# Measuring Conformance Drift Against Abandoned UML Designs with a Local Language Model in the Loop

*Revised manuscript, IEEE two-column format. Every number in this paper was
produced by the scripts in the replication package on 18 October 2026; Section
V-H gives the commands. This revision answers two review comments on the
previous version: that no language model was ever run, and that only one of
three projects drifted.*

**Sarvesh Sakthivel** (sarveshs2025@gmail.com)

---

## Abstract

⟦ABSTRACT⟧

**Index Terms —** architectural drift, architecture conformance checking,
reflexion models, UML, large language models, local models, incremental
analysis, mining software repositories.

---

## I. Introduction

The gap between a system's intended design and its code opens slowly and costs
a lot to close. Perry and Wolf gave the problem a name [1], and surveys cover
three decades of attempts to control it [2], [3]. Reflexion models [4], [5],
dependency-structure matrices [6] and dependency-constraint languages [7] can
all detect it, and Passos et al. [8] and Knodel and Popescu [9] compare them.
Drift is real and expensive in commercial development [10], and practitioners
say they value conformance checking yet seldom keep doing it [11].

**Drift needs a history.** Each of these techniques answers one question at one
moment: does this code conform to this design? Drift is how that answer
changes, and seeing it means repeating the check commit after commit. Evolution
studies usually compare architectures at a handful of releases [12], [13].
Where design documents have been followed commit by commit, researchers measured
how much of the code the diagram covers, not whether the code conforms to it in
the reflexion sense [14].

**What language models cost.** A model can relate a class diagram to code
without a hand-maintained mapping and explain each finding in prose. That eases
the maintenance burden that made earlier conformance tools fall out of use [11],
but it puts a price on every check, and running the check on every commit
multiplies the price by the length of the history. Most commits cannot change
conformance to a class diagram anyway: a reformatted file or a renamed local
variable leaves it as it was. A 2025 systematic review of language models in
software architecture found no study of architecture conformance checking [15].

**Where the design comes from.** A diagram recovered from the code under study
conforms by construction and measures nothing. Abandoned diagrams avoid that:
Romeo et al. found UML in 4.2% of 13,152 deep-cloned GitHub repositories, and
fewer than a third of those touched a UML file in 2022 [16]. An abandoned
diagram is a statement of intended design that nobody drew for a study, so the
drift away from it is real.

**What this revision changes.** An earlier version of this study had two
weaknesses. It never ran a language model: its cost evidence was the size of
prompts that were never sent. And its corpus held three projects, of which only
one drifted. Here we (i) put a real model in the loop, a 7.6-billion-parameter
open-weight code model served locally by Ollama, with no hosted API and no key,
and record what the model server itself measures; and (ii) replace hand-picked
subjects with a systematic search of GitHub for StarUML class models, screened
by a rule fixed before any replay, which yields ⟦N_PROJECTS⟧ projects.

We ask five research questions:

* **RQ1:** How does real code drift away from an abandoned class model?
* **RQ2:** How many model calls and tokens does each gate avoid, measured on a
  real model?
* **RQ3:** What does skipping cost in what the user is told?
* **RQ4:** Can a model that runs on a laptop serve this loop at all?
* **RQ5:** Can we trust the measuring instrument?

**Contributions.**

1. A design rule for conformance checking with language models: *gate the
   explanation, never the verdict* (Section III-A).
2. Drift measures built only from deterministic reflexion findings (Section
   III-E).
3. Four structural gate policies and a replay method that counts a miss as a
   stale served explanation, judged against a model-free oracle at every commit
   (Sections III-D and IV-C).
4. A reproducible corpus procedure: GitHub code search for StarUML class
   models, an automatic screen that runs the checker at the freeze and at HEAD,
   and an inclusion rule that never looks at whether a project drifted
   (Section IV-B).
5. A live-model protocol for local models: a prompt-addressed cache so gates
   that send the same prompt share one call, a context-fit guard that refuses
   to send a prompt the model would silently truncate, and deterministic scores
   for the explanation a user is served (Section IV-D).
6. Results on 16 seeded deviations and ⟦N_PROJECTS⟧ projects with abandoned
   StarUML models (⟦N_COMMITS⟧ first-parent commits), and a replication package.

---

## II. Background and Related Work

**Conformance checking.** Our vocabulary comes from reflexion models [4], [5].
A *convergence* appears in both the design and the code, a *divergence* in the
code but not the design, and an *absence* in the design but not the code.
ReflexML [17] uses UML as the high-level model of a reflexion analysis, which
makes it the classical work closest to our input. DSMs [6] and DCL [7] swap the
explicit model for dependency rules. All of these need the intended
architecture in a tool-specific notation plus a mapping from source to model;
we reduce the mapping to matching names, which is how people read a class
diagram anyway (Section VII).

**Drift and erosion.** De Silva and Balasubramaniam conclude that detection is
still the bottleneck [2]. Architecture-evolution studies compare recovered
architectures across releases [12], [13]; Li et al. look for erosion symptoms in
code review [18]; Tekinerdogan builds drift analysis on reflexion viewpoints
[19]. Closest to us, Romeo et al. [14] link PlantUML diagrams to Java classes and
track how much of the code the UML *covers* across commits. We measure
reflexion-style *conformance* against a frozen StarUML model at every
first-parent commit, keep its two directions apart, and analyse how long
designed elements survive.

**Incremental analysis.** Egyed's instant consistency checking [20], [21]
re-evaluates only the UML consistency rules a model change can affect, and IncA
[22] does the same for program analyses. Our gate borrows the idea, but those
approaches save CPU time on cheap deterministic checks, where checking a bit
too much costs almost nothing. We save calls to an expensive step that is not
deterministic, so every skip needs a stated failure mode and a measured miss
rate.

**Language models, cost and local deployment.** The 2025 review [15] found no
conformance work based on language models. Hybrid designs ground a model in a
static analyser [23]. Cost control by cascades and response caching [24], or by
semantic caches keyed on prompt similarity [25], decides from the prompt; our
gate decides from a checked structural property of the code. Open-weight code
models such as Qwen2.5-Coder [31] can be served on a workstation by Ollama [32],
which removes the per-token bill but replaces it with time and a bounded
context window, as Section V-D shows. We follow the reporting guidelines of
Baltes et al. [26]: we name the model, its version and quantisation, the
decoding settings and the hardware, and we measure run-to-run variation.

---

## III. Approach

### A. Gate the explanation, never the verdict

Fig. 1 shows one analysis. Tree-sitter parses the source into an implementation
graph, the StarUML model is parsed into a design model, and a deterministic
engine computes the reflexion findings. All of this runs on every commit,
whatever the gate says. The gate decides one thing: whether the model's written
analysis (gaps and recommendations in prose) is regenerated for the changed
part of the graph or carried over from the previous version.

![Fig. 1](figures/fig-pipeline.svg)
*Fig. 1. One analysis. The verdict is computed on every commit and only the
explanation is gated. The gate's only input is code structure (dashed line).*

Because the verdict is recomputed every time, a commit skipped by mistake
leaves an out-of-date explanation beside a current score and current lists of
divergences and absences. Section VI-A argues that any tool putting a language
model into a conformance loop should work this way.

### B. Extraction

We extract classes, interfaces, methods, fields (declared ones, or those
assigned through `self.`/`this.` where there are no declarations), supertypes
with the clause that declared them, imports and call sites from Python, Java,
JavaScript, TypeScript, C# and PHP. Calls are resolved through a project-wide
symbol table. A call with several plausible targets is counted as ambiguous
instead of being linked to all of them, and every run reports its resolution
rate.

### C. Deterministic comparison

Design and code are matched by element name. Each designed class is a check, as
is each designed attribute and operation of a class that exists, and each
designed generalization and realization. The score is the share of checks that
pass. Associations are graded (a typed field is good evidence, a matching name
weak evidence) and left out of the score. Where the language says whether a
supertype is extended or implemented (Java, TypeScript, PHP), the kind must
match the diagram; elsewhere the declared supertype satisfies either relation.
A constructor missing from the diagram is not a divergence. Convergences are
passed checks plus satisfied relations; divergences are undocumented classes
plus undocumented members of designed classes; absences are missing classes,
missing members and unsatisfied scored relations.

### D. Gates

Each gate is defined by the property it tests, which sets what it can safely
ignore and what it can miss (Table I). None of the gates reads the diagram.

**Table I. Gate policies.**

| Gate | Re-analyses when | Absorbs | Designed-in risk |
|---|---|---|---|
| `always` | every commit | nothing | none (baseline) |
| `content` | analysed bytes change | nothing structural | pays for comments, formatting |
| `structural` | the AST fingerprint changes | formatting, comments, literals, local names, statement order | a semantic change with identical structure |
| `isomorphism` | fingerprint changes **and** the graph is not isomorphic to the previous one | also pure renames and reorderings | a consistent rename of a class the diagram names |

The fingerprint covers declarations, types, supertypes, imports and, for each
callable, the *set* of names it calls; it ignores receivers, local names,
statement order, comments, formatting and literals. The isomorphism gate runs
VF2 [27] with kind-preserving node matchers and relation-preserving edge
matchers; if the graphs are isomorphic, the mapping is the renaming and the
cached explanation is relabelled. When a gate fires on a project with history,
the model sees only the changed part of the graph and its one-hop neighbours,
together with the deterministic findings as facts it must not contradict, so
the prompt grows with the change rather than the project. A gate firing with an
empty change set (bytes changed, structure did not) has nothing to scope to and
sends the whole project.

### E. Drift measures

Every measure comes from the oracle's deterministic findings; no gate and no
model influences them. *Trajectory* is the number of convergences, divergences
and absences at every commit after the freeze. *Direction* is the net change in
divergences and in absences: a window is *divergence-led* when divergences grew
at least as much as absences (the code grew away from the design) and
*absence-led* otherwise (designed structure disappeared faster); a commit is
*eroding* when total deviations rose and *repairing* when they fell. *Element
survival* classifies each designed element at each commit as conforming,
divergent, partial or absent and estimates the time to first deviation of the
elements that conformed at the freeze with Kaplan–Meier [28], censored at the
end of the window.

---

## IV. Study Design

### A. Controlled set

A four-layer Python reference project (controller, service, domain,
persistence) matches its StarUML model exactly, and 16 reproducible mutations
state in advance whether they should change structure and whether they should
change the deterministic findings. Ten change the findings (a deleted designed
method or class, an undocumented class, a removed realization, an untyped
association, a controller bypassing the service, an inverted dependency, a
partial and a consistent class rename, an undocumented private helper). One
changes structure only (an optional parameter). Five are negative controls (a
comment, whitespace, a local rename, reordered methods, a docstring).

### B. Corpus: a systematic search

⟦CORPUS_SEARCH⟧

### C. Replay procedure

We replay each project from its freeze along the **first-parent mainline**,
merges included, so every step is a real change from a parent to its child; a
date-ordered replay of non-merge commits mixes branches and invents drift
(Section V-G). Windows are capped at 150 first-parent commits. At every commit
the source is analysed once by a forced, model-free full analysis, the
**oracle**, and once by each gate in its own project directory, so no gate
benefits from another's cache. A commit **changed conformance** if the oracle's
findings differ from its findings at the previous commit.

**What counts as a miss.** Gated and forced runs compute identical findings by
construction, so comparing them always reports zero misses (an early version of
our harness did exactly that). What a gate can make stale is the explanation it
serves. Each gate therefore records the findings its current explanation was
written for, and a run is **missed** when the gate reused that explanation and
those findings no longer match the oracle's. We report *recall* (the share of
conformance-changing commits re-analysed), *specificity* (the share of other
commits skipped) and stale runs.

### D. The live model

**Model and serving.** Every gate re-analysis is sent to
`qwen2.5-coder:7b` (Qwen2.5-Coder-7B-Instruct [31], Q4_K_M quantisation,
7.6 B parameters) served by Ollama 0.40.6 [32] on the integrated GPU of a
laptop (Intel Core Ultra 7 255H, Intel Arc 140T via Vulkan, 32 GB shared RAM),
with temperature 0, a fixed seed, a 32,768-token context, JSON output mode and
at most 2,048 generated tokens. No hosted model and no API key are involved.
The prompt is exactly the one the tool builds; we did not tune it for this
model.

**What is sent.** The oracle never reaches a model. A prompt whose size exceeds
85% of the context window is **not sent**, because Ollama truncates an
over-long prompt silently and the answer would describe part of the project;
such a run is recorded as *no fit*. Responses are cached on disk by a hash of
model, context, generation cap, system prompt and prompt, so gates that send
byte-identical prompts share one call; every gate is still charged the
measured tokens and time of the call it needed. In the corpus, the `always`
baseline is called at commit 0, at every commit whose findings changed, and at
every tenth commit; other `always` runs are recorded as *not sampled*.

**What is measured.** For each call Ollama reports the prompt tokens it
evaluated, the tokens it generated and the time spent on each; we also record
wall-clock time. For the explanation a user is *served* at each run (fresh or
reused), we compute two deterministic scores against the oracle: **coverage**,
the share of elements whose findings changed at that step that the explanation
names, and **ungrounded mentions**, identifiers it names that exist in neither
the design nor the code. To measure run-to-run variation, 13 prompts were sent
a second time with the cache bypassed.

### E. Statistics

Proportions carry 95% Wilson intervals [29]. Gates are compared with McNemar's
exact test [30] on the commits where they disagree, and the test is not
reported with fewer than six discordant commits. Latencies are reported as
medians with interquartile ranges, because inference time on shared hardware is
skewed. A rate with an empty denominator is reported as *not measured*, never
as zero.

---

## V. Results

### A. RQ1: How the code drifted

⟦RQ1⟧

### B. RQ2: What each gate avoids

⟦RQ2⟧

### C. RQ3: What skipping costs in what the user is told

**Stale explanations in the corpus.** ⟦RQ3_CORPUS⟧

**Seeded deviations with a real model.** Table VII repeats the controlled
experiment with every gate re-analysis sent to the local model. The gate
decisions are those of the offline run, since a gate never sees model output:
the structural gate fired on all ten findings-changing mutations and on one
structure-only change, and the isomorphism gate let through only the
consistent rename it is designed to absorb.

**Table VII. Seeded deviations with the live model (16 mutations; 10 change the findings).**

| Gate | Real calls | Prompt tokens (measured) | Model time | Mean coverage of changed elements | Explanations naming every changed element | Invented identifiers |
|---|---|---|---|---|---|---|
| always | 16 | 63,109 | 772 s | 0.65 | 5/10 | 0 |
| content | 16 | 40,584 (−36%) | 645 s | 0.56 | 3/10 | 0 |
| structural | 11 | 22,353 (−65%) | 448 s | 0.56 | 3/10 | 0 |
| isomorphism | 9 | 17,758 (−72%) | 334 s | 0.48 | 3/10 | 0 |

*Prompt tokens are those Ollama reports evaluating. Coverage is the share of
elements whose deterministic findings the mutation changed that the served
explanation names. An identifier is invented if it occurs nowhere in the
analysed source or the design model.*

Three things stand out. First, the cost saving survives contact with a real
model: the structural gate sent 11 of 16 calls and 35% of the `always`
baseline's prompt tokens. Second, the designed-in failure is visible in what
the user reads: after the consistent rename, the isomorphism gate served the
pre-rename explanation, which names none of the renamed elements (coverage 0),
while the structural gate's fresh call named three of four. The score and the
divergence list served beside it were current, as Section III-A requires.
Third, scoping changes *what* the model writes, not only what it costs. A
scoped prompt carries only the changed subgraph, and the model named the
changed elements less often from it (mean 0.56 against 0.65). The full-project
prompt named an undocumented private helper that every scoped prompt missed;
on the undocumented class it was the other way round. Neither prompt shape
named the controller that bypasses its service, a finding that exists only as
a layer-rule violation. No answer, scoped or full, named an identifier that
does not exist.

*Answer to RQ3.* ⟦RQ3_ANSWER⟧

### D. RQ4: Can a laptop model serve the loop?

⟦RQ4⟧

### E. RQ5: Can the instrument be trusted?

*Labels.* For all 16 mutations the oracle's findings changed exactly when the
label said they should, before and after the fixes in Section V-F.

*Oracle determinism.* ⟦ORACLE_AGREE⟧

*Model repeatability.* We sent 13 prompts a second time with the cache
bypassed. Eleven answers were byte-identical, twelve had identical lists of
gaps, and all twelve scored rows had identical coverage and invented-identifier
counts. Only time varied: the second call took a median 0.80 of the first
(range 0.71–0.90). At temperature 0 with a fixed seed this model is close to
deterministic on this hardware, but not exactly, which is one more reason the
design keeps the model out of the verdict.

*Counterfactual against measured tokens.* The previous version of this study
reported prompt sizes in `cl100k_base` tokens without sending them. Over the
⟦N_CALIBRATION⟧ distinct prompts sent here, Ollama evaluated a median of
⟦CAL_RATIO⟧ times the `cl100k` estimate (range ⟦CAL_RANGE⟧). The
counterfactual was a slight and nearly uniform underestimate, so every saving
reported as a percentage is unaffected.

### F. Defects found in the instrument

Each of these would have skewed a headline number, and none was caught by
tests that only checked that the pipeline ran. Items 1–4 and 6 are defects in
the tool, item 5 is a flaw in replay method, and item 7 is a flaw in our own
explanation score.

1. **Supertype order.** Supertype names were sorted to build the fingerprint
   and the comparator then took the first as the superclass, so a Python
   realization could never be satisfied and sistema-bancario scored 80%
   instead of 90%.
2. **JavaScript fields.** Fields assigned as `this.x = …` were not extracted;
   DiscordBotRPG scored 19.54% instead of 33.33% at its freeze.
3. **An oracle blind to extra members** could not see the seeded
   undocumented-helper divergence.
4. **Misses that could never happen.** Comparing freshly computed findings
   with the oracle's, which are equal by construction, made the miss rate zero
   whatever a gate did.
5. **Branch interleaving** (Section V-G).
6. **An isomorphism check without a time bound.** VF2 is exponential in the
   worst case, and the tool guarded it only by graph size. On two corpus
   projects (MSChartExtension in C#, AndRouter in Java) with a few hundred
   nodes, many of them alike, a single gate decision ran for more than half an
   hour. The gate now applies a Weisfeiler–Lehman shape signature first, which
   rejects most non-isomorphic pairs without search, and bounds VF2 to five
   seconds; an exhausted search is *undecided* and, like a graph too large to
   test, makes the gate re-analyse. The seeded results are unchanged.
7. **An explanation score that counted real names as invented.** The first
   version of our invented-identifier score compared the model's mentions with
   the implementation graph, which has no nodes for parameters or for fields
   of undocumented classes, and reported 3 to 9 "invented" names per gate on
   the seeded set. All of them (`self`, `weight`, `order_id`, …) occur in the
   source. Checked against the source text and the design model, the count is
   zero.

Items 1–4 and 6 have regression tests (281 tests in total).

### G. Sensitivity: replaying non-merge commits instead

Replaying every non-merge commit of DiscordBotRPG in date order (678 commits)
gives the same endpoints as the first-parent replay but 95 apparent
conformance changes instead of 12, 15 of them "repairs". Of its 677
transitions, 64 connect commits that are not parent and child; they account
for 22 of the 95 apparent changes. The gate conclusions barely move (recall
95/95, structural skip rate 53%, 94% counterfactual saving), but the drift
conclusions do not survive, which is why the corpus is replayed first-parent.

### H. Reproducing the results

```
python research/evaluate_deviations.py --out results/                  # Table VI
python research/live_deviations.py --out results/live                  # Table VII
python research/build_corpus.py --screen research/corpus-search/screen-results.json --out research/corpus-v2.json
python research/replay_each.py --corpus research/corpus-v2.json --out results/corpus-v2
python research/merge_results.py --out results/v2 results/corpus-v2/*/
python research/analyze_statistics.py --runs results/v2/runs.csv --out results/v2 --replication
python research/live_llm.py --corpus research/corpus-v2.json --only <project> --out results/live --model qwen2.5-coder:7b --num-ctx 32768 --always-sample 10
python research/paper_numbers.py --results results/v2                  # Tables III-V
python research/live_numbers.py --live results/live                    # live tables
python research/fit_numbers.py --runs results/v2/runs.csv --ratio <median ratio>
```

The live arm needs Ollama with `qwen2.5-coder:7b` pulled; it never needs a key.

---

## VI. Discussion

⟦DISCUSSION⟧

---

## VII. Threats to Validity

⟦THREATS⟧

---

## VIII. Conclusion

⟦CONCLUSION⟧

---

## Data Availability

The tool, the seeded deviations, the corpus search artifacts and inclusion
rule (`research/corpus-search/`, `research/build_corpus.py`), the corpus
manifest and frozen models, the raw per-run data of the offline and live
replays, the model-response cache and the scripts that produce every table and
figure are in the replication package (`<archive link or Zenodo DOI>`).

---

## References

All entries were checked against Crossref, arXiv or the publisher's record;
[31] and [32] were added on 18 October 2026.

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

[31] B. Hui, J. Yang, Z. Cui, J. Yang, D. Liu, L. Zhang, *et al.*, "Qwen2.5-Coder technical report," arXiv:2409.12186, 2024.

[32] Ollama, "Ollama: Get up and running with large language models locally," version 0.40.6, 2026. [Online]. Available: https://github.com/ollama/ollama
