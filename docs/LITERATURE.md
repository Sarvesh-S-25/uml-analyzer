# Literature, positioning, and a sample paper

*A survey of the field your tool sits in, what is already published, where the
genuine gap is, which datasets to evaluate on, which metrics to adopt, and a
writable draft of the paper's front half.*

---

## 1. What you have built, in the field's own vocabulary

Before the literature, a translation. Reviewers will not read "UML analyzer";
they will read your work as an entry in a 30-year-old line of research, and it
helps enormously to use its words.

| Your term | The field's term | Canonical source |
|---|---|---|
| Comparing the diagram to the code | **Architecture conformance checking** | Passos et al., IEEE Software 2010 |
| Class in the diagram, class in the code | **Convergence** | Murphy, Notkin & Sullivan, FSE 1995 |
| Class in code, not in the diagram | **Divergence** | *ibid.* |
| Class in the diagram, not in the code | **Absence** | *ibid.* |
| The design and code drifting apart over commits | **Architectural drift** / **erosion** / **degradation** | Perry & Wolf 1992; de Silva & Balasubramaniam 2012 |
| Your layering rules | **Dependency constraints** / design rules | Terra & Valente, DCL |
| Your gate | *(no established term — this is the new part)* | — |

Your tool is a **reflexion-model-style conformance checker with an LLM
augmentation and a change-gated incremental execution model.** Say it that way
in the abstract.

---

## 2. The single most important finding for your novelty claim

A 2025 systematic literature review of LLMs in software architecture — 18
peer-reviewed papers, ICSA/ECSA/journals, 2020–2025 — states plainly:

> "We found no articles regarding evaluating quality aspects of software
> architecture, such as evolvability, and **architecture conformance checking**."

and recommends conformance checking as a future direction, "e.g., by building on
works identifying architectural patterns and design rationales from code."

**Source:** [Software Architecture Meets LLMs: A Systematic Literature Review,
arXiv:2505.16697](https://arxiv.org/abs/2505.16697) ([PDF](https://arxiv.org/pdf/2505.16697))

This is the strongest sentence you will find for your introduction. It is a
recent, peer-reviewed-venue SLR saying your exact topic is empty. Quote it,
cite it, and build the motivation paragraph around it.

Two caveats to be honest about, because a reviewer will raise them:

1. The SLR's scope was ICSA/ECSA and adjacent venues. Work may exist in
   MODELS/SoSyM (the modelling community) that it did not sweep. Do your own
   check of SoSyM and MODELS 2024–2026 before claiming "none exists", and
   phrase your claim as "to the best of our knowledge, and consistent with the
   findings of [SLR]".
2. "Nobody has done X" is a weak contribution on its own. Absence of prior work
   is *permission* to publish, not a contribution. Your contribution is the
   gating mechanism and its measured frontier — see §5.

---

## 3. The papers to read and cite

### 3.1 Foundational — you cannot omit these

| Paper | Why it matters to you | Link |
|---|---|---|
| **Murphy, Notkin & Sullivan, "Software Reflexion Models: Bridging the Gap between Source and High-Level Models"**, FSE 1995 (TSE 2001 extended). ACM SIGSOFT Retrospective Impact Paper Award 2011. | *The* origin of your problem. A developer states a high-level model plus a mapping from source to model entities; the tool computes convergences, divergences, absences. Your `ComparisonEngine` recomputes this. You must position against it explicitly. | [ACM](https://dl.acm.org/doi/10.1145/222124.222136) · [author page](https://www.cs.ubc.ca/~murphy/papers/rm/fse95.html) · [Semantic Scholar](https://www.semanticscholar.org/paper/Software-reflexion-models:-bridging-the-gap-between-Murphy-Notkin/c7f7013ccc33d67a0aa5ff03a9a52eb525b4f821) |
| **Passos, Terra, Valente, Diniz & Mendonça, "Static Architecture-Conformance Checking: An Illustrative Overview"**, IEEE Software 2010 | Compares the four families — reflexion models, dependency structure matrices, source-code query languages, dependency constraint languages — on one example. Your related-work section's spine. | [IEEE](https://ieeexplore.ieee.org/document/5204070/) · [free PDF](https://homepages.dcc.ufmg.br/~mtov/pub/2010_ieeesw.pdf) |
| **Egyed, "Instant Consistency Checking for the UML"**, ICSE 2006 | **Your closest methodological relative.** Egyed re-evaluates only the consistency rules whose *scope* was touched by a model change, instead of all rules — the same idea as your gate, applied to model-to-model consistency without an LLM. Reviewers who know this work will ask how you differ; answer it before they ask. | [PDF](https://www.irisa.fr/lande/lande/icse-proceedings/icse/p381.pdf) · [UML/Analyzer tool paper](https://www.researchgate.net/publication/4251313_UMLAnalyzer_A_Tool_for_the_Instant_Consistency_Checking_of_UML_Models) |
| **Egyed, "Automatically Detecting and Tracking Inconsistencies in Software Design Models"**, TSE 2011 | The journal extension: incremental consistency at scale, with performance numbers. Cite for the "incremental checking is a known and valuable idea" framing. | [ResearchGate](https://www.researchgate.net/publication/224124964_Egyed_A_Automatically_Detecting_and_Tracking_Inconsistencies_in_Software_Design_Models_IEEE_Transactions_on_Software_Engineering_372_188-204) |
| **Reussner et al. / Reimer, "ReflexML: UML-Based Architecture-to-Code Traceability and Consistency Checking"**, ECSA 2011 | Reflexion models specifically with UML as the high-level model — the closest classical work to your input format. | [Springer](https://link.springer.com/chapter/10.1007/978-3-642-23798-0_37) |

### 3.2 Architectural drift and erosion — the framing you asked about

| Paper | Why | Link |
|---|---|---|
| **Li, Liang et al., "Towards Automated Identification of Violation Symptoms of Architecture Erosion"**, TSE (arXiv 2306.08616) | 606 labelled code-review comments from OpenStack and Qt; SVM+word2vec reaches F1 0.779. Shows the field cares about *detecting erosion symptoms automatically*, and gives you a precision/recall bar to compare against. Also a source of labelled violation text. | [arXiv](https://arxiv.org/abs/2306.08616) · [HTML](https://arxiv.org/html/2306.08616) |
| **Tekinerdogan & Ozkose Erdogan, "Architectural Drift Analysis using Architecture Reflexion Viewpoint and Design Structure Reflexion Matrices"** | Drift analysis built directly on reflexion models — the bridge between your two framings. | [PDF](https://www.researchgate.net/profile/Bedir-Tekinerdogan/publication/301257152_Architectural_drift_analysis_using_architecture_reflexion_viewpoint_and_design_structure_reflexion_matrices/links/5a57e342a6fdccf0ad1a3ae9/Architectural-drift-analysis-using-architecture-reflexion-viewpoint-and-design-structure-reflexion-matrices.pdf) |
| **Le, Behnamghader, Garcia, Medvidovic et al., ARCADE workbench** and the a2a/c2c metric family | How the community *measures* architectural change and decay across versions. Directly relevant to §6. | [ARCADE](https://www.researchgate.net/publication/347697245_ARCADE_an_extensible_workbench_for_architecture_recovery_change_and_decay_evaluation) · [ICSE'15 architecture-decay paper](https://jgarcia.ics.uci.edu//wp-content/uploads/archdeps_icse_seip_2015.pdf) |
| **Baerbak Christensen et al., "A literature study of architectural erosion and comparison to an industrial case"** | Good, readable framing of erosion vs drift for your introduction. | [PDF](https://baerbak.cs.au.dk/c/saip-arxiv/resource/le2017.pdf) |
| **de Silva & Balasubramaniam, "Controlling software architecture erosion: A survey"**, JSS 2012 | The standard survey citation for "erosion is a real, expensive problem". | search JSS; widely cited |

### 3.3 LLMs in software architecture and engineering

| Paper | Why | Link |
|---|---|---|
| **"Software Architecture Meets LLMs: A Systematic Literature Review"** (2025) | The gap statement. See §2. | [arXiv:2505.16697](https://arxiv.org/abs/2505.16697) |
| **"An Empirical Evaluation of Large Language Models Applying Software Architectural Patterns"** (AI, 2025) | LLMs reasoning about architectural patterns — adjacent, not conformance. | [DOI](https://doi.org/10.3390/ai7060195) |
| **"Improving LLM-assisted code generation through the use of architectural documents and implementation plans"**, ICSE 2026 Designing workshop | The inverse direction: architecture → code generation. Cite to show you know the neighbourhood. | [ICSE 2026](https://conf.researchr.org/details/icse-2026/designing-2026-papers/2/Improving-LLM-assisted-code-generation-through-the-use-of-architectural-documents-and-implementation-plans) |
| **"Guidelines for Empirical Studies in Software Engineering involving Large Language Models"** (arXiv 2508.15503) | **Read this before writing your evaluation.** Reviewers increasingly hold LLM-SE papers to it: report model version, temperature, seed, prompt, repetitions, and variance. Your `/repeatability` endpoint exists to satisfy exactly this — say so. | [arXiv](https://arxiv.org/abs/2508.15503) |
| **"Static Analysis as a Feedback Loop: Enhancing LLM-Generated Code Beyond Correctness"** (arXiv 2508.14419) | Hybrid static-analysis + LLM, the same architecture as your deterministic-engine-grounds-the-LLM design. | [arXiv](https://arxiv.org/abs/2508.14419) |
| **"IRIS: LLM-Assisted Static Analysis for Detecting Security Vulnerabilities"** | The strongest template for "combine a sound analyser with an LLM and measure what each contributes". Structure your ablation like theirs. | [OpenReview](https://openreview.net/forum?id=9LdJDU7E91) |

### 3.4 The cost/efficiency angle — your actual contribution's neighbours

| Paper | Why | Link |
|---|---|---|
| **Chen, Zaharia & Zou, "FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance"**, TMLR | Cascades, caching, and routing to cut LLM cost. **Your gate is a domain-specific admission-control policy in the same family** — cite it as the general technique and position yours as the software-engineering-aware instance that uses program structure rather than prompt similarity. | [arXiv:2305.05176](https://arxiv.org/abs/2305.05176) · [TMLR PDF](https://lingjiaochen.com/papers/2024_FrugalGPT_TMLR.pdf) |
| **Semantic caching for LLM serving** (several 2025–26 papers) | Generic prompt-similarity caches. Useful contrast: they cache on *text* similarity; you gate on *verified structural equivalence*, which gives a correctness argument a similarity threshold cannot. | [arXiv:2508.07675](https://arxiv.org/html/2508.07675v1) |
| **Incremental / demand-driven static analysis** (Saha & Ramakrishnan, PPDP 2005; incremental points-to with CFL-reachability) | Long tradition of "only re-analyse what changed" in program analysis. Cite one or two to show your gate has classical ancestry. | [ACM](https://dl.acm.org/doi/10.1145/1069774.1069785) · [Springer](https://link.springer.com/chapter/10.1007/978-3-642-37051-9_4) |

---

## 4. What is *similar* to your work (be honest about this)

Grouped by how much they overlap, most-overlapping first.

**(a) Reflexion models and UML conformance — same problem, no LLM, no gate.**
Murphy et al., ReflexML, HUSACCT, JITTAC, Sonargraph, Structure101, DV8,
ArchUnit, Terra & Valente's DCL. These already do design-vs-code conformance,
often better than you do on precision for the rules they cover. **Do not claim
conformance checking as your novelty.** Claim that these require a manually
maintained mapping and a rule language, and produce no natural-language
explanation — which is where the LLM earns its place.

**(b) Incremental consistency checking — same idea, different artefacts.**
Egyed's instant consistency checking scopes rule re-evaluation to what changed.
Your gate does the same for LLM invocation. The difference is what is being
saved: Egyed saves CPU on a cheap deterministic check; you save money and
latency on an expensive non-deterministic one, and therefore need a
*correctness* argument for skipping that Egyed did not (his rules are cheap
enough to re-run when in doubt). Make that argument explicitly.

**(c) LLM cost reduction — same goal, different signal.** FrugalGPT-style
cascades and semantic caches decide using prompt similarity, confidence
scores, or model tiers. You decide using a verified property of the artefact:
graph isomorphism under a type-preserving matching. That is a stronger
guarantee than a similarity threshold, and it is domain-specific in a way the
ML literature cannot be.

**(d) Architecture erosion detection — same motivation, different method.**
Li et al. classify code-review comments; you analyse code against a diagram.
Complementary, not competing. Their F1 ≈ 0.78 is a useful yardstick for "what
counts as good" in this area.

---

## 5. Where your novelty actually is

Three defensible claims, in descending order of strength. Claim the first;
support it with the second and third.

### Claim 1 (primary) — Structure-gated LLM invocation for conformance checking

> We introduce a change-detection gate that decides, from a verified property of
> the program's design graph, whether an LLM-based conformance analysis needs to
> run at all; and we characterise the cost/miss frontier of four gate policies
> on a labelled deviation set and a commit corpus.

Why it holds up:

- The *mechanism* is new: gating an LLM on **type-preserving graph isomorphism**
  of a parser-derived design graph, with rename recovery via the VF2 mapping so
  a cached analysis can be relabelled rather than regenerated. Nobody in the
  conformance literature does this because nobody there had an expensive
  non-deterministic step to protect.
- The *result shape* is new and honest: not "our gate is best" but a frontier —
  reuse rate against miss rate — including the case where your own best gate is
  provably wrong (a consistent rename leaves the graph isomorphic while the
  diagram still names the old class). Reporting a designed-in false negative and
  measuring how often it costs anything is exactly the kind of result reviewers
  trust.
- It is *falsifiable* and you have the harness to falsify it.

### Claim 2 (supporting) — A deterministic control for LLM-based architecture analysis

Your `deterministic-offline` mode runs the entire pipeline with no model.
That gives you a true no-LLM ablation on identical inputs — which the SLR notes
roughly a third of LLM-architecture studies lack entirely ("approximately
one-third of studies lack baseline comparisons"). Combined with
`grounded_node_ratio` (the share of LLM-proposed graph nodes that correspond to
something the parser actually found), you can answer "what did the LLM add, and
how much of it was real?" — a question the field is currently bad at answering.

### Claim 3 (supporting) — Evidence-graded relationship conformance

Treating UML associations as *evidenced* rather than *satisfied/violated* —
strong (typed field or signature), weak (name match or instantiation), none —
and excluding them from the headline score by default with the convention
recorded in every result. Small, but it is a methodological honesty that
classical binary conformance checkers do not offer, and it is easy to defend.

### What is *not* novel — do not claim these

- LLM reads code and produces findings. Ubiquitous.
- UML-to-code comparison. 30 years old.
- Token reduction by sending an AST summary instead of raw code. Widely known,
  and your `/benchmark` measures a representation saving that any structured-
  extraction paper already claims.
- Versioning graphs. Standard engineering.

---

## 6. Metrics to add — the highest-value change you can make

Your current outputs are a similarity percentage plus counts. That is the
weakest part of the paper as it stands, because no reviewer knows what
"similarity 84%" means or how to compare it to anything. Replace it, or augment
it, with metrics the field already recognises.

### 6.1 Adopt reflexion-model terminology as primary output *(do this first)*

Report, per analysis:

- **Convergences** — relations/elements present in both design and code
- **Divergences** — present in code, absent from design
- **Absences** — present in design, absent from code

You already compute all three (`extra_classes`, `missing_classes`,
`missing_relations`, `element_differences`). Renaming your output fields to this
vocabulary costs an afternoon and instantly makes your results legible and
comparable to three decades of work. **Highest value-per-effort change in the
whole project.**

### 6.2 Architectural drift over time — what you asked about

You have version history; you are not yet using it to say anything about drift.
Define and report:

- **Drift rate** = new divergences + new absences per commit (or per KLOC
  changed), tracked across your version ring and the replay corpus.
- **Drift direction** — is the code moving away from the design (divergence
  growth) or the design becoming stale (absence growth)? These have different
  remedies and no existing tool distinguishes them well.
- **Time-to-first-divergence** for a given design element — a survival-analysis
  framing that would be genuinely novel and is directly computable from your
  replay output.
- **Conformance half-life** — commits until 50% of the originally-conforming
  elements have diverged. A memorable, quotable number.

This is where the paper becomes interesting rather than merely correct. "We
gate LLM calls efficiently" is a systems result; "here is how fast real projects
drift from their diagrams, and what it costs to keep checking" is a *finding*.

### 6.3 Established comparison metrics

| Metric | What it measures | Where from |
|---|---|---|
| **a2a** (architecture-to-architecture) | Distance between two architectures; use it between consecutive versions to quantify structural change independently of your gate | Garcia et al., ARCADE |
| **c2c** (cluster-to-cluster) | Coverage between two decompositions | *ibid.* |
| **MoJoFM** | Normalised move/join distance between clusterings — the standard in architecture recovery | Wen & Tzerpos |
| **Precision / recall / F1** vs the seeded set | You already produce the confusion matrix | your `evaluate_deviations.py` |

Adding a2a between consecutive versions is maybe 60 lines given you already
store both graphs, and it lets you say "the gate reused on all changes below
a2a = 0.03, and the one miss occurred at a2a = 0.11" — a much stronger sentence
than any count.

### 6.4 Cost metrics you already have

Tokens, USD, latency, cache-hit rate, LLM calls avoided, resolution rate. Keep
these; they are the systems half of the paper. Always report them with the miss
rate beside them.

---

## 7. Where to get projects to evaluate on

Your corpus is the last thing blocking the paper. Ranked by usefulness.

### 7.1 The Lindholmen dataset — projects that actually contain UML *(start here)*

> "more than 93 000 UML files (spread across more than 24 000 GitHub repositories)"

This is precisely the problem you have: finding real projects with real
diagrams. It was built by mining GitHub for UML.

- Portal: [models-db.com](http://models-db.com/)
- Mirror + description: [University of Rostock](https://se.informatik.uni-rostock.de/en/research/datasets-and-tools/lindholmen-dataset/)
- Record: [TU Eindhoven research portal](https://research.tue.nl/en/datasets/lindholmen-dataset-of-uml-models/)
- Cite: Hebig et al., *The Quest for Open Source Projects that Use UML: Mining
  GitHub*, MODELS 2016 · Ho-Quang et al., *Practices and perceptions of UML use
  in open source projects*, ICSE-SEIP 2017 · Robles et al.,
  [*An Extensive Dataset of UML Models in GitHub*](https://www.researchgate.net/publication/318123548_An_Extensive_Dataset_of_UML_Models_in_GitHub), MSR 2017
- Reflection on its impact: [JSS 2023](https://www.sciencedirect.com/science/article/pii/S0950584923001726)

**Caveat you must handle:** many mined diagrams are *reverse-engineered* from
code (so conformance is trivially perfect) rather than *forward-engineered*
(designed first). There is a published classifier for exactly this distinction —
[An Automated Approach for Classifying Reverse-Engineered and Forward-Engineered
UML Class Diagrams](https://www.researchgate.net/publication/327690310_An_Automated_Approach_for_Classifying_Reverse-Engineered_and_Forward-Engineered_UML_Class_Diagrams).
Use it, or filter by hand, and **say in the paper that you did**. A reviewer who
spots reverse-engineered diagrams in your corpus will reject the results.

### 7.2 SAEroCon repository — ground-truth intended architectures

Purpose-built for exactly your evaluation: "ground-truth intended software
architectures to form a base for benchmarking approaches and tools related to
software architecture degradation".

- Workshop page: [The SAEroCon Repository](https://saerocon.wordpress.com/the-saerocon-repository/)
- Repository: [github.com/sebastianherold/SAEroConRepo](https://github.com/sebastianherold/SAEroConRepo) ([wiki](https://github.com/sebastianherold/SAEroConRepo/wiki))
- Known systems: **JabRef 3.7** (mappings for generic, HUSACCT, JiTTaC),
  **ProM 6.9** (JiTTaC mapping), **Teammates 5.110** (HUSACCT mapping)
- Foundational method: Garcia et al., [*Obtaining Ground-Truth Software
  Architectures*](https://dl.acm.org/doi/10.5555/2486788.2486911), ICSE 2013

These are module-level architectures rather than UML class diagrams, so you will
need to translate one into a `.mdj` (or extend your parser to read their format —
a defensible contribution in itself). The payoff is a *validated* intended
architecture, which no amount of mining gives you.

The [SAEroCon workshop](https://saerocon.wordpress.com/) itself (co-located with
ICSA) is also a natural venue for an early version of your work.

### 7.3 ModelSet — 5 000+ labelled models

[ModelSet](https://modelset.github.io/) — a labelled dataset of Ecore and UML
models for ML research. Less directly usable (models are often not paired with
their code) but useful for testing your `.mdj`/model parser's robustness across
many real diagrams.

- Paper: [SoSyM 2021](https://link.springer.com/article/10.1007/s10270-021-00929-3) · [GitHub](https://github.com/modelset/modelset-dataset)

### 7.4 Qualitas Corpus — curated Java, no diagrams

[Qualitas Corpus](https://zenodo.org/records/268432) ([paper](https://qualitascorpus.com/pubs/QualitasCorpusAPSEC2010.pdf)) —
111 curated Java systems with multiple versions. No diagrams, so you would have
to author the intended architecture yourself, but it is the standard corpus for
Java empirical work and its multi-version structure suits drift analysis.

### 7.5 Direct GitHub mining — the pragmatic fallback

Your tool eats StarUML `.mdj`. GitHub code search for `extension:mdj`,
`extension:uml`, `extension:xmi`, plus `path:docs` filters, will find candidates
quickly. The [staruml GitHub topic](https://github.com/topics/staruml) and
[staruml-samples](https://github.com/staruml/staruml-samples) are starting
points. This is lower-quality than Lindholmen but immediate, and fine for the
first 2–3 pilot projects while you set up the real corpus.

### 7.6 Recommended corpus composition

| Source | Projects | Role |
|---|---|---|
| Your seeded-deviation set | 1 (16 variants) | Labelled ground truth, exact precision/recall |
| SAEroCon | 2–3 | Validated intended architectures |
| Lindholmen, forward-engineered only | 4–6 | Realistic diagram/code pairs at scale |
| Direct mining | 1–2 | Pilot / sanity check |

Ten projects total, 30–50 commits each, is a defensible evaluation for a
conference paper.

---

## 8. Venues

*Checked 17 August 2026. Conference deadlines move every year — verify on
[se-deadlines.github.io](https://se-deadlines.github.io/) before committing.*

### 8.1 Conferences still open

| Venue | Fit | Deadline | Conference | Link |
|---|---|---|---|---|
| **SANER 2027** | **Best open fit.** Analysis/evolution/reengineering; the 2027 CFP names "AI for Software Engineering" as a strategic theme. 10 + 2 pages, double-anonymous. | Abstract **21 Sep 2026**, paper **25 Sep 2026** | 9–12 Mar 2027, Richmond, VA | [Research track](https://conf.researchr.org/track/saner-2027/saner-2027-papers) |
| **FSE 2027** | Top tier. Only with the full corpus and a strong result. | **2 Oct 2026** | 12–16 Jul 2027, Shenzhen | [FSE 2027](https://conf.researchr.org/home/fse-2027) |
| **MSR 2027** | If the commit-replay corpus becomes the centre of the paper. Also has a Data & Tool Showcase (10 Nov 2026) that suits the deviation set. | **23 Oct 2026** | 26–27 Apr 2027, Dublin | [MSR 2027](https://conf.researchr.org/home/msr-2027) |
| **ICSE 2027 NIER** | Research track closed 30 Jun 2026; NIER is the way in. Good home for the seeded-deviation result alone. | **23 Oct 2026** | 25 Apr – 1 May 2027, Dublin | [ICSE 2027](https://conf.researchr.org/track/icse-2027/icse-2027-research-track) |
| **ICSME 2027** | Still the best *topical* fit (maintenance and evolution = drift over commits). CFP not yet out; expect a deadline around March 2027. | ~Mar 2027 | Sep 2027 | [ICSME series](https://conf.researchr.org/series/icsme) |
| **SAEroCon** (at ICSA) | Erosion and architectural consistency — near-perfect topical match, friendly first audience. | see workshop CFP | with ICSA | [SAEroCon](https://saerocon.wordpress.com/) |
| **ICSA / ECSA 2027** | Architecture community's home venues. | TBA | 2027 | [ICSA](https://conf.researchr.org/series/icsa) · [ECSA](https://conf.researchr.org/home/ecsa-2026) |

**Closed for 2026:** ICSA 2026 (Dec 2025), SANER 2026 (Oct 2025), ICSME 2026
(6 Mar 2026), ASE 2026 (26 Mar 2026), ICSE 2027 research (30 Jun 2026).

### 8.2 Journals (rolling submission — no deadline to miss)

| Journal | Fit | APC | Link |
|---|---|---|---|
| **IEEE Access** | Fast, indexed, no page limit, explicitly welcomes applications-oriented and tool papers. See §8.3. | **$2,160** (−25% for India → $1,620 + tax) | [About](https://ieeeaccess.ieee.org/about/) · [Submission guidelines](https://ieeeaccess.ieee.org/authors/submission-guidelines/) |
| **Software and Systems Modeling (SoSyM)**, Springer | Best fit if the centre is UML/model conformance — the community most likely to care about `.mdj` handling | free (hybrid) | [Aims & scope](https://link.springer.com/journal/10270/aims-and-scope) |
| **Empirical Software Engineering (EMSE)**, Springer | Best fit if the centre is the measurement study | free (hybrid) | [Aims & scope](https://link.springer.com/journal/10664/aims-and-scope) · [Guidelines](https://link.springer.com/journal/10664/submission-guidelines) |
| **Journal of Systems and Software (JSS)**, Elsevier | Broad; home of the erosion survey literature | free (hybrid) | [JSS](https://www.sciencedirect.com/journal/journal-of-systems-and-software) |
| **Information and Software Technology (IST)**, Elsevier | Broad, tool-and-method friendly | free (hybrid) | [IST](https://www.sciencedirect.com/journal/information-and-software-technology) |
| **IEEE TSE** | Highest bar; only with the full corpus and a strong result | $2,800 if OA, free if not | [TSE](https://www.computer.org/csdl/journal/ts) |

### 8.3 IEEE Access — the practical facts

| | |
|---|---|
| **Scope fit** | Good. Multidisciplinary gold OA; explicitly seeks "applications-oriented articles" and work that "would be considered out of scope for most of the IEEE journals". A tool-plus-evaluation paper is squarely in range. Submit as **Research Article** or **Applied Research**. |
| **Impact factor / indexing** | IF ≈ 4.2, Q2, SCIE + Scopus indexed. Satisfies most university "indexed journal publication" requirements. |
| **Speed** | Submission to publication **4–6 weeks**; peer review ≈ 4 weeks. Minimum two reviewers, **single-anonymised** (your names are visible — unlike SANER/ICSME). |
| **Decision model** | **Binary: accept or reject.** A reject may come "with resubmission permitted", which grants **exactly one** revision attempt with a point-to-point response. Fail to address everything and it becomes a permanent reject. There is no iterative major/minor revision cycle. |
| **Acceptance rate** | IEEE states ≈ 20%. |
| **Length** | No hard limit; **under 20 pages strongly recommended**, over 20 needs Editor-in-Chief approval. Double-column IEEE Access template, Word or LaTeX **plus** matching PDF, ≤ 40 MB. |
| **Required extras** | Author biographies below the references, 3–10 keywords, all acronyms defined at first use, and an Acknowledgements section **disclosing any AI-generated text**. |
| **Cost** | **$2,160** + local tax. India is Group C in IEEE's geographic programme → **25% discount ≈ $1,620**, plus ~18% GST ≈ **$1,910 (≈ ₹1.6–1.7 lakh)**. IEEE member discounts (5%/20%) **do not apply to students** and cannot be combined with the geographic discount. Check whether your institution has an IEEE open-access agreement — some cover the APC entirely. |

Links: [Article processing charges](https://ieeeaccess.ieee.org/about/article-processing-charges/) ·
[Stages of peer review](https://ieeeaccess.ieee.org/authors/stages-of-peer-review/) ·
[Rapid peer review](https://ieeeaccess.ieee.org/about/rapid-peer-review/) ·
[Low/lower-middle income discount programme](https://open.ieee.org/for-authors/ieee-low-and-lower-middle-income-country-open-access-discount-program/) ·
[2026 country groups PDF](https://open.ieee.org/wp-content/uploads/2026-GEO-Countries.pdf) ·
[2026 IEEE APC list](https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE-Article-Processing-Charges-List.pdf) ·
[Special sections](https://ieeeaccess.ieee.org/sections/special-sections/)

**Where IEEE Access helps you specifically**

- No page limit means the full pipeline, the four gates, the deviation set, the
  frontier tables, and the threats table all fit — a 10-page conference format
  forces you to cut either the system or the evaluation.
- Reviewers judge "originality and technical correctness", not conceptual
  novelty against a top-tier bar. Your contribution is real but incremental
  relative to reflexion models; that lands better here than at FSE.
- Rolling submission. Every SE conference deadline for 2026 has passed; the next
  is SANER 2027 on 25 September 2026.
- Indexed and citable immediately, which matters if a degree requirement or a
  scholarship depends on a publication this year.

**Where it costs you**

- The money is real, and it is not refunded if a later reader thinks less of the
  venue.
- Software-engineering academics rank ICSE/FSE/ASE/TSE/EMSE well above mega-
  journals. If you intend to apply for SE PhD programmes or research posts, one
  SANER/ICSME paper is worth more than one IEEE Access paper.
- One resubmission only. Do not submit until the corpus study is finished —
  a half-evaluated paper burns the venue permanently for that manuscript.

**Recommended play:** submit the 10-page version to **SANER 2027 (25 Sep 2026)**
first — it is free, double-anonymous, thematically on point, and five weeks out.
If it is rejected, extend it to the full 18–20 page treatment and send it to
IEEE Access, which welcomes extended work provided the conference version is
cited and the extension is substantial. That sequence costs nothing to try and
keeps the expensive option open. If you need a publication *this calendar year*
and cannot wait for a December notification, go straight to IEEE Access.

---

## 9. Sample paper — a writable draft

Below is a draft of the front half in the field's idiom. It is written to be
edited, not admired: replace every `X`, and delete any claim your data does not
support. Target length for ICSME: 10 pages + 2 of references.

---

### Title (pick one)

- **"When Does Design Conformance Need an LLM? Structure-Gated Incremental Conformance Checking"**
- "Cheap Conformance: Gating LLM-Based Architecture Analysis on Graph Isomorphism"
- "Measuring Architectural Drift Without Paying for It Every Commit"

The first is best: it poses a question, names the mechanism, and signals both
halves of the contribution.

---

### Abstract

> Architecture conformance checking — deciding whether an implementation still
> matches its intended design — is not a one-off activity but one that must be
> repeated as the code evolves. Large language models make the checking step
> easier to build and its output easier to read, but they turn a cheap repeated
> check into one whose cost scales with project size times commit frequency, and
> whose answers vary between runs on identical input. We present ⟨TOOL⟩, a
> conformance checker that compares a StarUML class model against a polyglot
> codebase and, before invoking a language model, decides from the code's own
> structure whether an invocation is warranted at all. Four gate policies are
> implemented and compared: unconditional re-analysis, a content-hash gate, a
> gate on an AST-derived structural fingerprint, and a gate that additionally
> reuses a cached analysis when the design graph is isomorphic to the previous
> one under a type-preserving matching, recovering the renaming from the
> isomorphism so cached findings can be relabelled rather than regenerated.
> We evaluate on a seeded-deviation set of 16 labelled mutations with known
> expected outcomes, and on N commits drawn from M open-source projects that
> ship UML models, using a forced full analysis at every commit as an oracle.
> The structural gate avoids X% of invocations relative to the content-hash
> baseline with no missed conformance change; the isomorphism gate avoids a
> further Y% at a measured miss rate of Z%, all attributable to consistent
> renames — a limitation we characterise rather than conceal. We further report
> run-to-run variance of the model's judgements at temperature zero, and the
> proportion of model-proposed structure corroborated by parsing, and we release
> the tool, the deviation set, and the replication package.

*(Fill X, Y, Z from `results/REPORT.md`. If the isomorphism gate's miss rate
turns out to be 0 on your corpus, say so and note that the deviation set shows
the failure mode exists even where the corpus does not exercise it — that is a
stronger, more careful claim than pretending the risk is absent.)*

---

### 1. Introduction *(≈1 page)*

Paragraph 1 — the problem is old and real.

> The gap between a system's intended architecture and its implementation opens
> gradually and is expensive to close. This phenomenon — variously architectural
> drift, erosion, or degradation — has been studied since Perry and Wolf, and a
> mature body of work exists for detecting it: reflexion models [Murphy et al.],
> dependency structure matrices, source-code query languages, and dependency
> constraint languages, surveyed comparatively by Passos et al.

Paragraph 2 — what changed.

> These techniques share a precondition: someone must state the intended
> architecture in the tool's own formalism and maintain a mapping from source
> entities to design entities. In practice this mapping is where conformance
> checking dies — it is laborious to build and it decays faster than the code.
> Large language models change that calculus: a model can relate a UML class
> diagram to a codebase with no hand-written mapping, and can express findings
> in prose a developer will read.

Paragraph 3 — but it introduces two new problems, and this is your hook.

> Two properties of language models make them awkward for this task. First, they
> are expensive in a way that compounds: conformance must be re-checked on every
> change, so cost scales with project size times commit frequency, while most
> changes — reformatting, comments, renaming a local variable — cannot affect
> conformance at all. Second, they are non-deterministic: the same input can
> yield different findings across runs, so a single reported score is not a
> measurement.

Paragraph 4 — the gap, with the SLR citation.

> Despite rapid growth in applying language models to architecture tasks, a 2025
> systematic review of the area found no published work on architecture
> conformance checking, and recommends it as a direction for future research.

Paragraph 5 — contributions, as a numbered list.

> 1. A conformance-checking pipeline that derives a design graph from source by
>    parsing, compares it against a UML model deterministically, and invokes a
>    language model only for the changed subgraph and its k-hop impact set.
> 2. Four change-detection gate policies, including one based on type-preserving
>    graph isomorphism with rename recovery, implemented behind a single switch
>    so they can be compared within-subject.
> 3. A labelled set of 16 reproducible design deviations — nine conformance-
>    relevant, two structure-only, five negative controls — with declared
>    expected outcomes, released as both a mutation script and a git repository
>    with one branch per deviation.
> 4. An empirical characterisation of the cost/miss frontier across the four
>    gates on ⟨corpus⟩, with a forced full analysis as oracle.
> 5. Measurements of run-to-run variance at temperature zero and of the share of
>    model-proposed structure corroborated by parsing.

---

### 2. Background and related work *(≈1.5 pages)*

Four subsections; two paragraphs each is plenty.

**2.1 Architecture conformance checking.** Reflexion models and the
convergence/divergence/absence vocabulary. The four families per Passos et al.
End with: *all require a manually specified mapping; none produce explanations.*

**2.2 Architectural drift and erosion.** Perry & Wolf; de Silva &
Balasubramaniam; Li et al. on violation symptoms; ARCADE's a2a/c2c for measuring
change across versions. End with: *drift is measured retrospectively, rarely
continuously.*

**2.3 Incremental analysis.** Egyed's instant consistency checking — scope-based
rule re-evaluation; incremental and demand-driven program analysis. End with the
key distinction: *these save computation on deterministic checks; the question of
when it is safe to skip a non-deterministic, monetarily-priced check has not
been posed.*

**2.4 Language models in architecture and cost-aware inference.** The SLR and
its gap; hybrid static-analysis-plus-LLM designs; FrugalGPT-style cascades and
semantic caches. End with: *cost control in that literature keys on prompt
similarity or model confidence; we key on a verified structural property of the
artefact under analysis.*

---

### 3. Approach *(≈2.5 pages)*

3.1 Overview + the pipeline figure (adapt the ASCII diagram from your README).

3.2 **Design graph extraction.** tree-sitter; nodes = modules/classes/
interfaces/methods/functions; edges = contains/extends/implements/calls/
instantiates. Say plainly that call resolution goes through a project-wide
symbol table (self, typed field, local of known type, static, imported symbol,
same file, unique global) and that ambiguous sites are left unlinked and
counted. Report the resolution rate as a threat-bounding number.

3.3 **Structural fingerprint.** Define exactly what is in and out. In:
declarations, types, bases, imports, and each callable's *set of callee names*.
Out: receivers, local variable names, call ordering, comments, formatting.
Justify the call set in one sentence — *without it, a controller that quietly
begins calling the database directly would be invisible to the gate* — and
justify the exclusions in another.

3.4 **The four gates.** A table, then a paragraph on the isomorphism gate and
VF2 rename recovery, with the honest note that a consistent rename is
shape-preserving but conformance-relevant.

3.5 **Deterministic comparison and evidence grading.** Convergence/divergence/
absence. Inheritance is exact; associations are evidenced (strong/weak/none) and
excluded from the score by default, with the convention recorded per result.

3.6 **Model invocation and grounding.** Scoped prompt; the deterministic
findings passed as ground truth the model must not contradict;
`grounded_node_ratio` as the check on invented structure.

3.7 **Versioning.** Bounded ring of three; two graphs per version and *why they
must differ* — this is a real design lesson and worth two sentences.

---

### 4. Evaluation design *(≈1 page)*

State RQs as questions with a stated method and metric each:

- **RQ1** How much re-analysis does each gate avoid?  → reuse rate, LLM calls,
  tokens, latency; replay corpus.
- **RQ2** At what cost in missed conformance changes? → miss rate against the
  forced-analysis oracle; false negatives on the seeded set.
- **RQ3** How stable are the model's judgements on identical input? → mean/sd/
  range of score and gap set over n≥5 repetitions at temperature 0.
- **RQ4** How much of the model's output is corroborated by parsing? →
  `grounded_node_ratio`.
- **RQ5** How does drift accumulate over a project's history? → divergences and
  absences per commit; time-to-first-divergence.

Then: subjects (corpus table with LOC, commits, diagram provenance —
forward-engineered vs reverse-engineered, and how you classified them),
procedure, and the deterministic control condition.

---

### 5–7. Results, discussion, threats

Results: the frontier table, the confusion matrix, variance, drift curves.
Lead with the frontier.

Discussion: when gating is safe, what a rename means for conformance, and the
limits of LLM-as-judge here.

Threats: use the table already in `docs/RESEARCH.md` §5 — it is written and it
is honest. Add corpus-selection bias (forward- vs reverse-engineered diagrams)
and single-model dependence.

---

## 10. Two-week plan to a submittable draft

| Days | Work |
|---|---|
| 1 | Rename outputs to convergence / divergence / absence throughout. Cheap, and it changes how every reader parses your results. |
| 4–5 | Run `evaluate_deviations.py`; write §5 results for the seeded set. It is complete, labelled, and needs no corpus. |
| 6–8 | Build the corpus: 2 SAEroCon systems + 4 forward-engineered Lindholmen projects. Classify and record diagram provenance. |
| 9–11 | Run the replay, offline first, then once with a model. Generate the report. |
| 12–14 | Write §1–4 from the draft above; fill results; internal review. |

The seeded-deviation results alone would carry a NIER or workshop paper. Do not
wait for the full corpus to start writing.

---

## Sources

**Foundational conformance**
- [Murphy, Notkin & Sullivan, Software Reflexion Models, FSE 1995](https://dl.acm.org/doi/10.1145/222124.222136) · [author page](https://www.cs.ubc.ca/~murphy/papers/rm/fse95.html)
- [Passos et al., Static Architecture-Conformance Checking, IEEE Software 2010](https://ieeexplore.ieee.org/document/5204070/) · [PDF](https://homepages.dcc.ufmg.br/~mtov/pub/2010_ieeesw.pdf)
- [ReflexML: UML-Based Architecture-to-Code Traceability and Consistency Checking, ECSA 2011](https://link.springer.com/chapter/10.1007/978-3-642-23798-0_37)
- [Architecture Conformance overview, ScienceDirect Topics](https://www.sciencedirect.com/topics/computer-science/architecture-conformance)

**Incremental consistency**
- [Egyed, Instant Consistency Checking for the UML, ICSE 2006](https://www.irisa.fr/lande/lande/icse-proceedings/icse/p381.pdf)
- [UML/Analyzer tool paper](https://www.researchgate.net/publication/4251313_UMLAnalyzer_A_Tool_for_the_Instant_Consistency_Checking_of_UML_Models)
- [Incremental Consistency Checking for Complex Design Rules and Larger Model Changes, MODELS 2012](https://link.springer.com/chapter/10.1007/978-3-642-33666-9_14)
- [Incremental and demand-driven points-to analysis, PPDP 2005](https://dl.acm.org/doi/10.1145/1069774.1069785)

**Drift and erosion**
- [Towards Automated Identification of Violation Symptoms of Architecture Erosion, arXiv:2306.08616](https://arxiv.org/abs/2306.08616)
- [Architectural drift analysis using architecture reflexion viewpoint and DSRMs](https://www.researchgate.net/profile/Bedir-Tekinerdogan/publication/301257152_Architectural_drift_analysis_using_architecture_reflexion_viewpoint_and_design_structure_reflexion_matrices/links/5a57e342a6fdccf0ad1a3ae9/Architectural-drift-analysis-using-architecture-reflexion-viewpoint-and-design-structure-reflexion-matrices.pdf)
- [A literature study of architectural erosion and comparison to an industrial case](https://baerbak.cs.au.dk/c/saip-arxiv/resource/le2017.pdf)
- [ARCADE: workbench for architecture recovery, change and decay evaluation](https://www.researchgate.net/publication/347697245_ARCADE_an_extensible_workbench_for_architecture_recovery_change_and_decay_evaluation)
- [Garcia et al., Obtaining Ground-Truth Software Architectures, ICSE 2013](https://dl.acm.org/doi/10.5555/2486788.2486911)

**LLMs**
- [Software Architecture Meets LLMs: A Systematic Literature Review, arXiv:2505.16697](https://arxiv.org/abs/2505.16697) · [PDF](https://arxiv.org/pdf/2505.16697)
- [Guidelines for Empirical Studies in SE involving LLMs, arXiv:2508.15503](https://arxiv.org/abs/2508.15503)
- [FrugalGPT, arXiv:2305.05176](https://arxiv.org/abs/2305.05176) · [TMLR PDF](https://lingjiaochen.com/papers/2024_FrugalGPT_TMLR.pdf)
- [Static Analysis as a Feedback Loop, arXiv:2508.14419](https://arxiv.org/abs/2508.14419)
- [IRIS: LLM-Assisted Static Analysis for Detecting Security Vulnerabilities](https://openreview.net/forum?id=9LdJDU7E91)
- [An Empirical Evaluation of LLMs Applying Software Architectural Patterns](https://doi.org/10.3390/ai7060195)
- [Semantic Caching for Low-Cost LLM Serving, arXiv:2508.07675](https://arxiv.org/html/2508.07675v1)

**Datasets**
- [Lindholmen Dataset portal](http://models-db.com/) · [Rostock mirror](https://se.informatik.uni-rostock.de/en/research/datasets-and-tools/lindholmen-dataset/) · [TU/e record](https://research.tue.nl/en/datasets/lindholmen-dataset-of-uml-models/)
- [Robles et al., An Extensive Dataset of UML Models in GitHub, MSR 2017](https://www.researchgate.net/publication/318123548_An_Extensive_Dataset_of_UML_Models_in_GitHub)
- [A reflection on the impact of model mining from GitHub, JSS 2023](https://www.sciencedirect.com/science/article/pii/S0950584923001726)
- [Classifying Reverse- vs Forward-Engineered UML Class Diagrams](https://www.researchgate.net/publication/327690310_An_Automated_Approach_for_Classifying_Reverse-Engineered_and_Forward-Engineered_UML_Class_Diagrams)
- [SAEroCon Repository](https://saerocon.wordpress.com/the-saerocon-repository/) · [GitHub](https://github.com/sebastianherold/SAEroConRepo)
- [ModelSet](https://modelset.github.io/) · [SoSyM paper](https://link.springer.com/article/10.1007/s10270-021-00929-3) · [GitHub](https://github.com/modelset/modelset-dataset)
- [Qualitas Corpus](https://zenodo.org/records/268432) · [paper PDF](https://qualitascorpus.com/pubs/QualitasCorpusAPSEC2010.pdf)

**Venues**
- [ICSME 2026 research track](https://conf.researchr.org/track/icsme-2026/icsme-2026-papers) · [CFP](https://easychair.org/cfp/ICSME26) · [tool demo](https://conf.researchr.org/track/icsme-2026/icsme-2026-tool-demonstration) · [NIER](https://conf.researchr.org/track/icsme-2026/icsme-2026-nier)
- [ICSA 2026](https://conf.researchr.org/home/icsa-2026) · [dates](https://conf.researchr.org/dates/icsa-2026) · [research track](https://conf.researchr.org/track/icsa-2026/icsa-2026-papers)
- [SANER 2026 dates](https://conf.researchr.org/dates/saner-2026)
- [ECSA 2026](https://conf.researchr.org/home/ecsa-2026)
- [SAEroCon workshop](https://saerocon.wordpress.com/)
- [EMSE aims & scope](https://link.springer.com/journal/10664/aims-and-scope) · [submission guidelines](https://link.springer.com/journal/10664/submission-guidelines)
- [SoSyM aims & scope](https://link.springer.com/journal/10270/aims-and-scope)
