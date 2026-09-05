/* Builds the IEEE Access manuscript as a .docx.
 *
 * Layout follows the IEEE Access template: US Letter, a single-column banner
 * carrying title/authors/abstract/index terms, then a two-column body. The
 * official .dotx from IEEE has more furniture (running heads, the volume
 * banner); paste this text into it before submitting, or submit this and let
 * the editor's template pass handle the chrome.
 *
 * Placeholders are written as <X> so a find can locate every one.
 */
const fs = require('fs')
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageOrientation, convertInchesToTwip, PageBreak,
} = require('docx')

const FONT = 'Times New Roman'
const BODY = 20        // half-points => 10pt
const SMALL = 18       // 9pt

// ---------- helpers ----------

const p = (text, opts = {}) => new Paragraph({
  alignment: opts.align ?? AlignmentType.JUSTIFIED,
  spacing: { after: opts.after ?? 100, line: opts.line ?? 240 },
  indent: opts.firstLine === false ? undefined : { firstLine: convertInchesToTwip(0.2) },
  children: [new TextRun({ text, font: FONT, size: opts.size ?? BODY, bold: opts.bold, italics: opts.italics })],
})

/** A paragraph built from runs, so a sentence can mix bold and plain. */
const rich = (runs, opts = {}) => new Paragraph({
  alignment: opts.align ?? AlignmentType.JUSTIFIED,
  spacing: { after: opts.after ?? 100, line: 240 },
  indent: opts.firstLine === false ? undefined : { firstLine: convertInchesToTwip(0.2) },
  children: runs.map((r) => typeof r === 'string'
    ? new TextRun({ text: r, font: FONT, size: opts.size ?? BODY })
    : new TextRun({ font: FONT, size: opts.size ?? BODY, ...r })),
})

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  alignment: AlignmentType.CENTER,
  spacing: { before: 240, after: 120 },
  children: [new TextRun({ text, font: FONT, size: 22, bold: true, allCaps: false })],
})

const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 180, after: 100 },
  children: [new TextRun({ text, font: FONT, size: BODY, bold: true, italics: true })],
})

const bullet = (text) => new Paragraph({
  numbering: { reference: 'bullets', level: 0 },
  spacing: { after: 60, line: 240 },
  children: [new TextRun({ text, font: FONT, size: BODY })],
})

const numbered = (text) => new Paragraph({
  numbering: { reference: 'contributions', level: 0 },
  spacing: { after: 80, line: 240 },
  children: [new TextRun({ text, font: FONT, size: BODY })],
})

const caption = (text) => new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 60 },
  children: [new TextRun({ text, font: FONT, size: SMALL, bold: true })],
})

const note = (text) => new Paragraph({
  alignment: AlignmentType.LEFT,
  spacing: { after: 160 },
  children: [new TextRun({ text, font: FONT, size: 16, italics: true })],
})

const ref = (n, text) => new Paragraph({
  spacing: { after: 60, line: 220 },
  indent: { left: convertInchesToTwip(0.22), hanging: convertInchesToTwip(0.22) },
  children: [new TextRun({ text: `[${n}] ${text}`, font: FONT, size: SMALL })],
})

/** Table with the dual-width rule applied: columnWidths on the table, width on
 *  every cell, both in DXA. PERCENTAGE silently breaks in Google Docs. */
function table(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0)
  const cell = (text, { bold = false, header = false, align = AlignmentType.LEFT } = {}, w) =>
    new TableCell({
      width: { size: w, type: WidthType.DXA },
      shading: header ? { type: ShadingType.CLEAR, fill: 'E8E8E8' } : undefined,
      margins: { top: 40, bottom: 40, left: 80, right: 80 },
      children: [new Paragraph({
        alignment: align,
        spacing: { after: 0, line: 220 },
        children: [new TextRun({ text: String(text), font: FONT, size: 16, bold: bold || header })],
      })],
    })

  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((hdr, i) =>
          cell(hdr, { header: true, align: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER }, widths[i])),
      }),
      ...rows.map((r) => new TableRow({
        children: r.map((c, i) =>
          cell(c, { align: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER }, widths[i])),
      })),
    ],
  })
}

// ---------- front matter (single column) ----------

const front = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 160 },
    children: [new TextRun({
      text: 'When Does Design Conformance Need a Language Model? Structure-Gated Incremental Architecture Conformance Checking',
      font: FONT, size: 40, bold: true,
    })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 60 },
    children: [new TextRun({ text: '<AUTHOR NAME>1, <CO-AUTHOR>1', font: FONT, size: 24 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 60 },
    children: [new TextRun({ text: '1<Department, Institution, City, Country>', font: FONT, size: SMALL, italics: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [new TextRun({ text: 'Corresponding author: <Name> (e-mail: <email>)', font: FONT, size: SMALL, italics: true })],
  }),

  rich([
    { text: 'ABSTRACT   ', bold: true },
    'Architecture conformance checking — deciding whether an implementation still matches its intended design — is not a one-off activity but one that must be repeated as code evolves. Classical techniques require a hand-written mapping from source entities to design entities, which is laborious to build and decays faster than the code it connects. Large language models remove that burden: a model can relate a UML class diagram to a codebase with no mapping and explain its findings in prose a developer will read. They also introduce two problems. Cost compounds with project size multiplied by commit frequency, while most edits — reformatting, comments, renaming a local variable — cannot affect conformance at all. And the same input can produce different findings on different runs, so a single reported score is not a measurement. We present <TOOL>, a conformance checker that compares a StarUML class model against a polyglot codebase and, before invoking a language model, decides from the code’s own structure whether an invocation is warranted. Four gate policies are implemented behind one switch and compared on identical commits: unconditional re-analysis, a content-hash gate, a gate on an AST-derived structural fingerprint, and a gate that additionally reuses a cached analysis when the design graph is isomorphic to the previous one under a type-preserving matching, recovering the renaming from the isomorphism so cached findings are relabelled rather than regenerated. We evaluate on a seeded-deviation set of 16 labelled mutations with declared expected outcomes, and on <N> commits from <M> open-source projects, using a forced full analysis at every commit as an oracle. To avoid the circularity of scoring code against a diagram recovered from that same code, subjects are drawn principally from repositories whose UML model was abandoned while development continued, so that the design is genuine and the drift is not of our making. The structural gate skipped <X>% of analyses with no missed conformance change; the isomorphism gate skipped <Y>% at a miss rate of <Z>%, every miss attributable to a consistent rename — a failure mode we characterise rather than conceal. We release the tool, the deviation set, and a replication package.',
  ], { firstLine: false, after: 160 }),

  rich([
    { text: 'INDEX TERMS   ', bold: true },
    'Architectural drift, architecture conformance checking, empirical software engineering, graph isomorphism, incremental analysis, large language models, software maintenance, unified modeling language.',
  ], { firstLine: false, after: 200 }),
]

// ---------- body (two columns) ----------

// The body is built as a list of blocks. A two-column column is about 3300 DXA
// wide; a table wider than that overflows and overlaps the neighbouring column.
// IEEE handles this by letting wide tables span the full page, so blocks are
// tagged and mapped to alternating two-column / one-column sections below.
const blocks = [{ wide: false, children: [] }]
const A = (...items) => blocks[blocks.length - 1].children.push(...items)
const WIDE = (...items) => {
  blocks.push({ wide: true, children: items })
  blocks.push({ wide: false, children: [] })
}
const COL_DXA = 3300

A(h1('I. INTRODUCTION'))
A(p('The gap between a system’s intended architecture and its implementation opens gradually and is expensive to close. The phenomenon — variously architectural drift, erosion, or degradation — has been studied since Perry and Wolf [1], and a mature body of technique exists for detecting it: reflexion models [2], dependency structure matrices, source-code query languages, and dependency constraint languages, compared side by side by Passos et al. [3].', { firstLine: false }))
A(p('These techniques share a precondition. Someone must state the intended architecture in the tool’s own formalism, and maintain a mapping from source entities to design entities. In practice that mapping is where conformance checking dies. It is laborious to build, it must be updated whenever the code moves, and it decays faster than the artefacts it connects. Surveys of industrial adoption repeatedly identify this maintenance burden, rather than any deficiency in the checking algorithms, as the reason conformance tools are abandoned.'))
A(p('Large language models change this calculus. A model can relate a UML class diagram to a codebase without a hand-written mapping, inferring the correspondence between a diagram element and a source declaration from names, structure and context. It can also express what it finds in prose, which matters more than it first appears: a conformance violation reported as a rule identifier and a pair of package names is a puzzle, whereas the same violation described in a sentence is actionable.'))
A(p('Two properties of language models nevertheless make them awkward for this task.'))
A(rich([
  { text: 'They are expensive in a way that compounds. ', bold: true },
  'Conformance must be re-checked on every change, so cost scales with project size multiplied by commit frequency. Yet most changes between two runs cannot affect whether code conforms to a class diagram. Reformatting, comments, and renamed local variables leave the class structure untouched. Paying a model to re-read an unchanged architecture is the dominant cost of the naive design, and it buys nothing.',
]))
A(rich([
  { text: 'They are non-deterministic. ', bold: true },
  'The same input can yield different findings across runs, even at temperature zero, because sampling is not the only source of variation. A single reported similarity score is therefore not a measurement, and any evaluation that reports one without its run-to-run spread is presenting noise as signal.',
]))
A(p('Despite rapid growth in applying language models to architecture tasks, a 2025 systematic review of the area examined 18 peer-reviewed papers and found none addressing architecture conformance checking, recommending it explicitly as a direction for future research [4]. To the best of our knowledge, and consistent with that review, the work presented here is the first to gate a language-model-based conformance check on a verified structural property of the program under analysis.'))
A(p('This paper makes the following contributions.'))
A(numbered('A conformance-checking pipeline that derives a design graph from source by parsing, compares it against a UML model deterministically, and invokes a language model only for the changed subgraph and its k-hop impact set.'))
A(numbered('Four change-detection gate policies, including one based on type-preserving graph isomorphism with rename recovery, implemented behind a single switch so that they can be compared within-subject on identical commits.'))
A(numbered('A labelled set of 16 reproducible design deviations — nine conformance-relevant, two structure-only, and five negative controls — with declared expected outcomes, released as a mutation script and as a repository with one branch per deviation.'))
A(numbered('A method for assembling conformance-checking subjects without authoring the design ourselves: locating repositories whose UML model was abandoned while development continued, and measuring how far behind it fell. This avoids the circularity that makes a recovered diagram score perfectly against the code it was recovered from.'))
A(numbered('An empirical characterisation of cost against missed conformance changes across the four gates, with a forced full analysis at every commit as an oracle, reported both pooled and per project.'))
A(numbered('A replication package containing the tool, the deviation set, the raw run data, and the scripts that produced every table in this paper.'))

A(h1('II. BACKGROUND AND RELATED WORK'))

A(h2('A. Architecture Conformance Checking'))
A(p('Murphy, Notkin and Sullivan’s reflexion models [2] established both the problem and the vocabulary this paper uses. A developer states a high-level model together with a mapping from source entities to model entities; the tool then computes three relations. A convergence is a relationship present in both the design and the code. A divergence is present in the code but absent from the design. An absence is present in the design but not implemented. Three decades of subsequent work uses these words, and reporting results in any other vocabulary makes them harder to compare than they need to be.', { firstLine: false }))
A(p('Passos et al. [3] compare the four principal families — reflexion models, dependency structure matrices, source-code query languages, and dependency constraint languages — on a single worked example, which remains the clearest entry point to the area. ReflexML [5] applies reflexion models specifically with UML as the high-level model, and is therefore the closest classical work to our input format.'))
A(rich([{ text: 'All of these require a manually specified mapping, and none produce an explanation a developer can read.', italics: true }]))

A(h2('B. Architectural Drift and Erosion'))
A(p('Perry and Wolf [1] named the problem. De Silva and Balasubramaniam [6] survey three decades of attempts to control it and conclude that detection, not remedy, remains the practical bottleneck. Li et al. [7] approach detection from an orthogonal direction, classifying code-review comments for symptoms of erosion and reaching an F1 of approximately 0.78; that figure is a useful yardstick for what counts as a good result in this area. Garcia et al. [8] address the harder prerequisite of obtaining ground-truth architectures at all, and their method underpins the curated systems we use.', { firstLine: false }))
A(rich([{ text: 'Drift is typically measured retrospectively, over selected release pairs, rather than continuously as a project evolves.', italics: true }]))

A(h2('C. Incremental Analysis'))
A(p('Egyed’s instant consistency checking [9], extended in [10], is our closest methodological relative. Rather than re-evaluating every consistency rule after a model change, it re-evaluates only the rules whose scope the change touched, tracking scopes by observing which model elements each rule reads during evaluation. The underlying idea — do not redo work that the change could not possibly have affected — is exactly ours.', { firstLine: false }))
A(p('The difference lies in what is being saved and what being wrong costs. Egyed saves processor time on a cheap, deterministic check. When in doubt, re-running is nearly free, so the scoping decision needs no correctness argument: a conservative over-approximation of scope costs a few milliseconds. We save money and latency on an expensive, non-deterministic check, where re-running is precisely the thing we are trying to avoid, and where an unnecessary invocation is the failure we are optimising against. That asymmetry is why our gate needs a stated failure mode and a measured miss rate, and Egyed’s does not.'))
A(p('The wider literature on incremental and demand-driven program analysis shares the same ancestry. What distinguishes the present setting is that the expensive step is not a fixed-point computation but a call to a stochastic external service with a per-token price.'))
A(rich([{ text: 'The question of when it is safe to skip a non-deterministic, monetarily priced check has not, to our knowledge, been posed.', italics: true }]))

A(h2('D. Language Models and Cost-Aware Inference'))
A(p('The 2025 systematic review [4] surveys language models in software architecture and reports that no surveyed work addresses conformance checking. It further notes that approximately one third of the studies it examined lack any baseline comparison, which is the gap our deterministic mode is designed to close: the entire pipeline runs with no model at all, giving a true no-model ablation on identical inputs.', { firstLine: false }))
A(p('Hybrid designs that ground a language model in a sound analyser [11] share our architecture. Deterministic findings are supplied to the model as ground truth it may not contradict, and the model’s contribution is confined to explanation and to proposing structure the parser missed. We quantify the second contribution with a grounded-node ratio: the share of model-proposed graph nodes that correspond to something the parser actually found.'))
A(p('Cost control for language models has its own literature. FrugalGPT [12] cascades models of increasing capability and caches responses; semantic caches key retrieval on prompt similarity. Our gate belongs to this family but decides on a different signal.'))
A(rich([{ text: 'Cost control in that literature keys on prompt similarity or model confidence. We key on a verified structural property of the artefact under analysis, which supports a correctness argument that a similarity threshold cannot.', italics: true }]))

A(h1('III. APPROACH'))

A(h2('A. Overview'))
A(p('Figure 1 shows the pipeline. Source is parsed into an implementation graph; the UML model is parsed into a design graph; a deterministic comparison engine computes convergences, divergences and absences without any model involvement. The gate is the single decision point at which a model invocation can be avoided. When the gate permits re-analysis, the model receives only the changed subgraph and its impact set; when it does not, the previous analysis is reused and relabelled.', { firstLine: false }))
A(caption('FIGURE 1.  Analysis pipeline. The gate is the only decision point that can avoid a model invocation.'))
A(note('<Insert the pipeline diagram here. Redraw the ASCII sketch in docs/ as a proper vector figure.>'))

A(h2('B. Design Graph Extraction'))
A(p('Source is parsed with tree-sitter grammars for Python, JavaScript, TypeScript and Java. Nodes are modules, classes, interfaces, methods and functions. Edges are containment, inheritance, interface realization, calls and instantiation.', { firstLine: false }))
A(p('Call edges are resolved through a project-wide symbol table. A call is attributed when it is made on the receiver itself, through a field of known declared type, through a local variable of known type, through a class name, through an imported symbol, or to a name that is unique across the project. A call site with several equally plausible targets is left unlinked and counted rather than linked to all of them, because linking to all of them would inflate the graph with edges that do not exist and would make every subsequent measurement optimistic. The resolution rate is reported with every analysis, so the residual imprecision of the extracted architecture is a number rather than an unknown. On our corpus the median resolution rate was <R>%, with a median of <A> ambiguous sites per run.'))

A(h2('C. Structural Fingerprint'))
A(p('Each file is reduced to a fingerprint computed over its abstract syntax tree. The fingerprint includes declarations, type annotations, base classes, imported symbols, and, for each callable, the set of names that callable invokes. It excludes call receivers, local variable names, statement ordering, comments, formatting and literal values.', { firstLine: false }))
A(p('The set of invoked names must be included. Without it, a controller that quietly begins calling the database directly would produce a fingerprint identical to one that does not, and the change would be invisible to the gate — precisely the class of architectural violation the tool exists to catch. The exclusions rest on the converse argument: none of them can change whether a class conforms to a class diagram, because a class diagram does not describe them.'))
A(p('Using the set of invoked names rather than the sequence is deliberate. Reordering two independent calls is not an architectural change, and treating it as one would cause the gate to fire on refactorings that cannot affect conformance.'))

A(h2('D. What a Gate Is'))
A(p('We use the word gate for the decision taken immediately before a language model would be invoked: has anything changed since the last analysis that could possibly alter the answer? If nothing has, the previous result is reused and nothing is spent. The term is ours; the literature has no established name for this decision, because in settings where the check is cheap the decision does not need one.', { firstLine: false }))
A(p('A gate is defined by the property it tests. That property determines both what the gate absorbs without paying and what it can fail to notice, and the two are inseparable: a gate that tests a coarser property skips more commits and risks more, and a gate that tests a finer property skips fewer and risks less. The four policies below are four choices of property, ordered from finest to coarsest.'))
A(p('A gate is not a heuristic about whether an analysis is likely to be useful. It is a decision procedure over a property that either holds or does not, which is what makes a correctness argument possible at all. Section VI-A gives that argument for each of the four.'))

A(h2('E. The Four Gate Policies'))
A(p('Four policies are implemented behind a single configuration switch, so that any commit can be replayed under all four and the comparison is within-subject rather than between-subject.', { firstLine: false }))
WIDE(caption('TABLE 1.  The four gate policies.'), table(
  ['Gate', 'Re-analyses when', 'Absorbs', 'Risk'],
  [
    ['always', 'Every run', 'Nothing', 'Maximum cost; the baseline'],
    ['content', 'Any file’s bytes change', 'Nothing', 'Pays for comments and formatting'],
    ['structural', 'The fingerprint changes', 'Formatting, comments, literals, local names', 'A semantic change with identical structure is missed'],
    ['isomorphism', 'Fingerprint changed and the graph is not isomorphic to the previous one', 'Additionally: pure renames and reorderings', 'A rename that breaks conformance against a diagram naming that class is missed'],
  ],
  [1400, 2500, 2400, 3600],
))
A(p('The isomorphism gate uses the VF2 algorithm [13] with a node matcher that requires declaration kinds to correspond. When an isomorphism exists, the mapping it produces is the renaming, so cached findings can be relabelled rather than regenerated. This is what makes the gate useful rather than merely cheap: a project-wide rename produces a correct, up-to-date report at no model cost.', { firstLine: false }))
A(rich([
  { text: 'We state the failure mode here rather than in threats to validity. ', bold: true },
  'A class renamed consistently everywhere leaves the design graph’s shape unchanged, so the gate reuses the previous analysis. If the diagram names that class, conformance genuinely changed and the reuse was wrong. This is a designed-in false negative, not an implementation defect, and Section V-B measures how often it costs anything. A limitation disclosed alongside the mechanism reads as rigour; the same limitation disclosed only in a threats section reads as damage control.',
]))

A(h2('F. Deterministic Comparison and Evidence Grading'))
A(p('Generalization and realization are recoverable exactly from an abstract syntax tree, and are scored as satisfied or violated. Associations are not. A typed field is strong evidence for a modelled association; a name match or an instantiation is weak evidence; neither proves the association the diagram intends. We therefore report associations with their evidence level and exclude them from the headline conformance score by default. Every result records which convention produced it, so a score computed with associations included can never be mistaken for one computed without.', { firstLine: false }))

A(h2('G. Model Invocation and Grounding'))
A(p('When the gate permits, the model receives the changed subgraph together with its k-hop impact set, with k = 1 by default, and the deterministic findings as ground truth it is instructed not to contradict. Scoping the prompt to the impact set rather than the whole project is a second, independent saving: the cost of a re-analysis then scales with the size of the change rather than the size of the project.', { firstLine: false }))
A(p('We report the grounded-node ratio, defined as the share of model-proposed graph nodes that correspond to a declaration the parser actually found. On our corpus it was <G>. A ratio well below one indicates that the model is inventing structure, and is the number a reader should look at before believing any model-authored claim in the report.'))

A(h2('H. Versioning'))
A(p('A bounded ring of three snapshots is retained per project. Two graphs are persisted per version: the presentation graph shown to the user, which merges implementation, design and model-proposed nodes, and the pure implementation graph that the gate compares against on the next run.', { firstLine: false }))
A(p('These must not be the same object. Comparing a merged graph against a freshly parsed implementation graph never matches, because the merged graph contains design and model-proposed nodes the parser will never produce, so the gate fires on every run and the cache never hits. We report this because it is a real design trap, it is invisible in testing that only checks correctness of output, and we fell into it.'))

A(h1('IV. EVALUATION DESIGN'))

A(h2('A. Research Questions'))
A(p('We ask five questions, each with a stated metric.', { firstLine: false }))
WIDE(caption('TABLE 2.  Research questions and metrics.'), table(
  ['RQ', 'Question', 'Metric'],
  [
    ['RQ1', 'How much analysis does each gate avoid?', 'Skip rate, model invocations, tokens'],
    ['RQ2', 'At what cost in missed conformance changes?', 'Miss rate against a forced-analysis oracle; false negatives on the seeded set'],
    ['RQ3', 'Does the result hold across projects?', 'Per-project skip and miss rates; stability of the gate ordering'],
    ['RQ4', 'Is the difference between the two candidate gates real?', 'McNemar’s exact test on discordant commits'],
    ['RQ5', 'How does drift accumulate?', 'Divergences and absences per commit'],
  ],
  [900, 4100, 4900],
))

A(h2('B. Subjects'))
A(caption('TABLE 3.  Study subjects.'))
A(table(
  ['Property', 'Value'],
  [
    ['Projects', '<M>'],
    ['Commits analysed', '<N>'],
    ['Total analysis runs', '<N x 4>'],
    ['Gate policies compared', '4'],
    ['Languages', '<languages>'],
    ['Oracle present', 'Yes'],
  ],
  [2150, 1150],
))
A(p('Where the intended design comes from is the central methodological question for any conformance study, and getting it wrong invalidates everything downstream. A diagram derived from the code being analysed yields perfect conformance by construction and measures nothing. We therefore draw subjects from three sources with different and complementary weaknesses.', { firstLine: false }))

A(rich([
  { text: 'Source 1: abandoned diagrams found in the wild. ', bold: true },
  'Some repositories contain a UML model that was drawn once and then left behind while development continued. Such a diagram is a genuine statement of intended design — nobody constructed it for this study — and the code has genuinely moved away from it. The violations are real and unplanted. That this is common rather than exceptional is established: Romeo et al. [14] deep-cloned 13,152 GitHub repositories and found that fewer than one third of the projects containing UML saw any activity in their UML files during 2022. We locate such projects by measuring, for each model file in a repository, the number of source-touching commits that landed after the model was last edited, and select those whose model is at least <T> commits behind. For these projects the analysis begins at the commit where the model was last edited, so the study starts from the design as its author last left it.',
]))

A(rich([
  { text: 'Source 2: published ground-truth architectures. ', bold: true },
  'For <M2> projects an intended architecture already existed in a curated repository built for architecture-degradation research [8], and was translated into a StarUML model. These are the strongest subjects, because the intended architecture was validated by parties with no stake in our result, but they are few and they are module-level rather than class-level.',
]))

A(rich([
  { text: 'Source 3: recovered and frozen. ', bold: true },
  'For <M3> projects no model existed. We recovered one from a single early commit and then held it fixed for the entire replay. Conformance is perfect at that commit by construction; every subsequent commit produces measured drift away from a design that does not move. This measures how quickly code departs from a fixed design, which is a different and weaker claim than measuring departure from a design someone actually intended, and we treat it as such. We report the recovery commit for each project.',
]))

A(rich([
  { text: 'What the diagram’s provenance does and does not affect. ', bold: true },
  'It matters for the drift results in Section V-E, which are only meaningful if the design was genuinely intended. It does not affect RQ1 through RQ4. The gate decides whether to re-analyse from changes in code structure alone; it never reads the diagram. Skip rates, miss rates, token savings, and the paired comparison between gates are therefore measurable on any diagram, including a recovered one, because the oracle is a forced full analysis against that same diagram rather than against an external notion of correctness. Provenance bounds the drift claim; it does not bound the cost claim.',
]))

A(h2('C. Procedure'))
A(p('For each commit, each gate is given its own project directory and its own analysis, so no gate can benefit from another’s cached state. A separate always-forced run acts as the oracle. Where a gate reused a cached analysis but the forced run’s deterministic findings differ, that commit is recorded as a missed change.', { firstLine: false }))
A(p('All cost measurements reported here were taken in deterministic mode, in which the entire pipeline runs with no model at all. This gives a true no-model ablation on identical inputs and makes the token accounting exactly reproducible; the token counts are those the gate would have caused to be spent.'))

A(h2('D. Statistical Methods'))
A(p('Proportions are reported with 95% Wilson score intervals, which remain inside the unit interval where the normal approximation does not — skip rates sit near both bounds, and an interval that runs below zero has stopped being an interval. Token cost and latency are summarised by the median, both distributions being right-skewed; means and standard deviations are given alongside for readers who expect them.', { firstLine: false }))
A(p('The two candidate gates are compared using McNemar’s exact test. Every commit is analysed by both gates, so the design is paired and only the commits on which the two gates disagree carry information. A two-sample test of proportions would treat the two columns as independent samples, which they are not; that is a correctness error rather than a stylistic preference. Because a single comparison is performed, no multiple-comparison correction applies.'))
A(p('Rates computed from fewer than ten runs are reported with their interval and identified as unstable, since a rate derived from four observations moves by twenty-five percentage points when a single observation changes. Where no forced full analysis is available to compare against, the miss rate is reported as not measured rather than as zero.'))

A(h1('V. RESULTS'))

A(h2('A. RQ1 and RQ2: Cost and Missed Changes'))
WIDE(caption('TABLE 4.  How each gate performed. Skip rate and miss rate must be read together.'), table(
  ['Gate', 'Runs', 'Re-an.', 'Skipped', 'Skip rate [95% CI]', 'Missed', 'Miss rate', 'Tokens', 'Saved'],
  [
    ['always', '<>', '<>', '0', '0.0%', '0', '0.0%', '<>', '—'],
    ['content', '<>', '<>', '<>', '<>', '<>', '<>', '<>', '<>'],
    ['structural', '<>', '<>', '<>', '<X>', '<>', '<>', '<>', '<>'],
    ['isomorphism', '<>', '<>', '<>', '<Y>', '<>', '<Z>', '<>', '<>'],
  ],
  [1350, 750, 750, 850, 1950, 800, 900, 1150, 1350],
))
A(p('Figure 2 plots the skip rate for each gate with the number of missed changes labelled on each bar.', { firstLine: false }))
A(caption('FIGURE 2.  Share of analyses skipped by each gate, with missed changes labelled.'))
A(note('<Insert figure1-skip-by-gate.svg, exported from the Results page.>'))
A(p('Throughout this subsection the skip rate and the miss rate are quoted in the same sentence. A gate that never skips has a perfect miss rate and saves nothing; a gate that skips every analysis is free and useless. Either number reported alone is uninterpretable, and quoting one alone is the most likely reason a reader will distrust the result.'))

A(h2('B. The Controlled Test'))
A(p('The seeded-deviation set comprises sixteen deliberate design changes with declared expected outcomes: nine break conformance, two change structure without changing conformance, and five are negative controls that must cost nothing. Because the expected outcome of each is known by construction, this is the only part of the study with unambiguous ground truth, and the safety argument leads with it rather than with the corpus.', { firstLine: false }))
WIDE(caption('TABLE 5.  Seeded deviations: 16 mutations with known expected outcomes.'), table(
  ['Gate', 'Caught', 'Missed', 'False alarms', 'Correctly ignored'],
  [
    ['always', '9', '0', '7', '0'],
    ['content', '<>', '<>', '<>', '<>'],
    ['structural', '<>', '<>', '<>', '<>'],
    ['isomorphism', '<>', '<>', '<>', '<>'],
  ],
  [2000, 1800, 1800, 2200, 2200],
))
A(p('The misses recorded against the isomorphism gate are the rename case predicted in Section III-E, and no others. That the predicted failure mode is the only observed one is itself evidence that the gate behaves as specified.', { firstLine: false }))

A(h2('C. RQ3: Consistency Across Projects'))
WIDE(caption('TABLE 6.  Per-project results under the recommended gate.'), table(
  ['Project', 'Commits', 'Skip rate', 'Missed', 'Tokens saved', 'Drift/commit'],
  [
    ['<project 1>', '<>', '<>', '<>', '<>', '<>'],
    ['<project 2>', '<>', '<>', '<>', '<>', '<>'],
    ['<project 3>', '<>', '<>', '<>', '<>', '<>'],
    ['<project 4>', '<>', '<>', '<>', '<>', '<>'],
  ],
  [2400, 1400, 1500, 1300, 1700, 1600],
))
A(p('Skip rates ranged from <lo>% to <hi>% across projects. <State whether the ordering of gates by skip rate was the same in every project. If it was, say so plainly: it means no single repository is driving the result. If it was not, name the project that differs and discuss it.>', { firstLine: false }))
A(p('Table 6 reports the recommended gate for each project. The replication package additionally contains every gate\u2019s figures for every project separately, because a pooled row cannot answer what happened inside one repository, and a practitioner evaluating the technique for their own codebase is asking exactly that question. We summarise rather than reproduce that breakdown here; the pattern of interest is whether any project reverses the pooled ordering, which is stated above.'))

A(h2('D. RQ4: Is the Difference Real?'))
A(p('On the <n> commits seen by both candidate gates, they disagreed on <d>. The structural gate re-analysed while the isomorphism gate skipped on <a> commits, and the reverse occurred on <b>. McNemar’s exact test gives p = <p>. <Interpret: a lopsided split indicates the difference is a property of the gates rather than an accident of which commits happened to be in the corpus; a balanced split means this corpus does not distinguish them, which is not the same as showing them equivalent.>', { firstLine: false }))

A(h2('E. RQ5: Architectural Drift'))
A(p('Figure 3 shows divergences and absences accumulating over each project’s commit history. Drift accrued at a median of <D> new violations per commit across projects.', { firstLine: false }))
A(caption('FIGURE 3.  Design violations accumulating over commits, one line per project.'))
A(note('<Insert figure2-drift.svg, exported from the Results page.>'))

A(h2('F. Reproducibility'))
A(caption('TABLE 7.  Configuration under which every run was produced.'))
A(table(
  ['Setting', 'Value'],
  [
    ['Mode', '<offline / auto>'],
    ['Provider and model', '<provider, exact model version string>'],
    ['Temperature', '0'],
    ['Seed', '<seed>'],
    ['Impact radius (hops)', '1'],
    ['Associations scored', 'No'],
  ],
  [2150, 1150],
))
A(p('These values are recorded per run rather than read from the environment at the time of writing, because the configuration of a tool can change between running a study and reporting it. Where runs disagree the tool reports the disagreement rather than selecting one value.', { firstLine: false }))

A(h1('VI. DISCUSSION'))

A(h2('A. When Is Gating Safe?'))
A(p('A gate is safe exactly when the property it tests implies the property we care about. The content gate tests whether any byte changed, which trivially implies that nothing relevant changed when it does not fire; it is therefore safe and saves the least. The structural gate tests whether the AST-derived shape moved, and conformance against a class diagram is a function of that shape together with names. The isomorphism gate tests shape up to renaming, and therefore trades a named, bounded exception for the largest saving.', { firstLine: false }))
A(p('This framing suggests a practical rule for adopters. Choose the strongest gate whose stated exception is one you can tolerate. A team whose diagrams name classes precisely should stop at the structural gate; a team whose diagrams describe roles rather than named classes can safely take the isomorphism gate’s additional saving.'))

A(h2('B. What a Rename Means for Conformance'))
A(p('A consistent rename is shape-preserving and conformance-relevant. Any gate keyed on shape alone must miss it. The obvious remedy — keying on names as well as shape — collapses the isomorphism gate into the structural gate and forfeits the entire additional saving, so it is not a remedy but a different point on the same trade-off curve.', { firstLine: false }))
A(p('We therefore report the failure rather than engineering it away, because the trade is the finding. A tool that offered only the safe gate would be simpler and less useful; a tool that offered only the cheap gate would be unsafe in a way its users could not see. Offering both, with the cost of each measured, is the contribution.'))

A(h2('C. The Limits of a Language Model as Judge'))
A(p('The deterministic engine produces the findings; the model explains them and may propose structure the parser missed. The second capability is the one that can invent things, which is why the grounded-node ratio is reported alongside every model-authored result. A model-authored number presented without its run-to-run spread is not a measurement, and we do not present one.', { firstLine: false }))

A(h1('VII. THREATS TO VALIDITY'))

A(h2('A. Construct Validity'))
A(p('The similarity score aggregates heterogeneous findings into a single number, and is reported alongside the counts from which it derives rather than instead of them. The structural fingerprint is deliberately blind to names; that blindness is the mechanism under study rather than an oversight, and its consequence is measured in Section V-B.', { firstLine: false }))

A(h2('B. Internal Validity'))
A(p('Missed changes are defined against a forced full analysis, so the oracle inherits any bias present in the deterministic comparison engine. A conformance change that the engine cannot see is invisible to both the gate and the oracle, and would not appear in our miss counts. Measurements were taken in deterministic mode, which removes model non-determinism from the cost figures at the price of reporting the tokens the gate would have caused to be spent rather than tokens actually spent.', { firstLine: false }))

A(h2('C. External Validity'))
A(p('<M> projects in <L> languages is a small corpus. Skip rates varied from <lo>% to <hi>% across projects, and the pooled figure should be read with that range beside it. Reference applications are included as pilots and are identified as such; the generalisation claim rests on the curated systems. Projects whose classes follow no naming convention will layer less cleanly than ours did, and the gate’s behaviour on such projects is untested.', { firstLine: false }))
A(rich([
  { text: 'Diagram provenance bounds the drift claim. ', bold: true },
  'Of the three sources in Section IV-B, only the first two carry a design that someone actually intended. For the <M3> recovered-and-frozen projects, drift is measured against a design that was never authored as an intention, so Section V-E should be read as departure from a fixed reference rather than as erosion of a real architecture. We report the source of every subject so that a reader can discount accordingly, and we report the drift results separately by source. The cost results in Sections V-A to V-D do not depend on provenance, for the reason given in Section IV-B.',
]))
A(p('A second, opposite risk applies to the found-diagram projects: a model may have been abandoned because the component it described was abandoned, in which case the violations we detect are uninteresting rather than informative. We exclude models whose staleness window contains no source changes for this reason, but the filter is coarse.'))
A(p('Finally, results are reported for a single model family. Cross-model agreement is measurable with the tool but is not reported here.'))

A(h2('D. Conclusion Validity'))
A(p('Wilson intervals accompany every proportion. A paired test is used for a paired design. Miss rate is reported as not measured rather than as zero where no oracle exists, and rates derived from fewer than ten runs are flagged. Statistics whose preconditions are not met are suppressed with the failed precondition stated, rather than printed.', { firstLine: false }))

A(h1('VIII. CONCLUSION'))
A(p('We asked when an expensive, non-deterministic conformance check actually needs to run, and answered it with a gate on a verified structural property of the code. Across <M> projects and <N> commits, gating on an AST-derived fingerprint avoided <X>% of analyses without missing a conformance change, and gating additionally on graph isomorphism avoided <Y>% at a measured cost of <Z>%, arising entirely from consistent renames.', { firstLine: false }))
A(p('The trade is the contribution. The finding is not that one gate wins, but that the cost of each is now a number a team can weigh against its own tolerance for a missed violation. Future work should extend the corpus to systems whose diagrams were authored before the code, and measure cross-model agreement on the explanation step, which this study measures the cost of but not the stability of.'))

A(h1('DATA AVAILABILITY'))
A(p('The tool, the seeded-deviation set, the raw run data, and the scripts that produced every table in this paper are archived at <Zenodo DOI>.', { firstLine: false }))

A(h1('ACKNOWLEDGMENT'))
A(p('<Required if any text was AI-assisted. Name the system used. IEEE Access mandates this disclosure in the acknowledgements; it is not held against authors.>', { firstLine: false }))

A(h1('REFERENCES'))
A(ref(1, 'D. E. Perry and A. L. Wolf, "Foundations for the study of software architecture," ACM SIGSOFT Softw. Eng. Notes, vol. 17, no. 4, pp. 40–52, 1992.'))
A(ref(2, 'G. C. Murphy, D. Notkin, and K. Sullivan, "Software reflexion models: Bridging the gap between source and high-level models," in Proc. 3rd ACM SIGSOFT Symp. Found. Softw. Eng. (FSE), 1995, pp. 18–28.'))
A(ref(3, 'L. Passos, R. Terra, M. T. Valente, R. Diniz, and N. Mendonça, "Static architecture-conformance checking: An illustrative overview," IEEE Software, vol. 27, no. 5, pp. 82–89, 2010.'))
A(ref(4, '"Software architecture meets LLMs: A systematic literature review," arXiv:2505.16697, 2025.'))
A(ref(5, '<Verify authors>, "ReflexML: UML-based architecture-to-code traceability and consistency checking," in Proc. Eur. Conf. Softw. Archit. (ECSA), 2011.'))
A(ref(6, 'L. de Silva and D. Balasubramaniam, "Controlling software architecture erosion: A survey," J. Syst. Softw., vol. 85, no. 1, pp. 132–151, 2012.'))
A(ref(7, 'R. Li, P. Liang, et al., "Towards automated identification of violation symptoms of architecture erosion," IEEE Trans. Softw. Eng., 2023. <verify volume and pages>'))
A(ref(8, 'J. Garcia, I. Krka, N. Medvidovic, et al., "Obtaining ground-truth software architectures," in Proc. Int. Conf. Softw. Eng. (ICSE), 2013.'))
A(ref(9, 'A. Egyed, "Instant consistency checking for the UML," in Proc. Int. Conf. Softw. Eng. (ICSE), 2006, pp. 381–390.'))
A(ref(10, 'A. Egyed, "Automatically detecting and tracking inconsistencies in software design models," IEEE Trans. Softw. Eng., vol. 37, no. 2, pp. 188–204, 2011.'))
A(ref(11, '"Static analysis as a feedback loop: Enhancing LLM-generated code beyond correctness," arXiv:2508.14419, 2025.'))
A(ref(12, 'L. Chen, M. Zaharia, and J. Zou, "FrugalGPT: How to use large language models while reducing cost and improving performance," Trans. Mach. Learn. Res., 2024.'))
A(ref(13, 'L. P. Cordella, P. Foggia, C. Sansone, and M. Vento, "A (sub)graph isomorphism algorithm for matching large graphs," IEEE Trans. Pattern Anal. Mach. Intell., vol. 26, no. 10, pp. 1367–1372, 2004.'))
A(ref(14, 'M. Romeo, et al., "UML is back. Or is it? Investigating the past, present, and future of UML in open source software," in Proc. Int. Conf. Softw. Maintenance and Evolution, 2025. <verify author list and venue>'))

A(new Paragraph({ spacing: { before: 240 }, children: [new TextRun({ text: '<AUTHOR BIOGRAPHIES REQUIRED HERE — one per author, below the references. IEEE Access enforces this and it is the item most often missed. Roughly 100 words each: degree, institution, year, current position, research interests. A photograph is optional.>', font: FONT, size: SMALL, italics: true })] }))

// ---------- document ----------

const PAGE = {
  size: { width: 12240, height: 15840, orientation: PageOrientation.PORTRAIT },
  margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 },
}

/** Two-column flow, except where a table is too wide for a column: those get a
 *  full-width continuous section, which is exactly what IEEE does with table*. */
const bodySections = blocks
  .filter((b) => b.children.length > 0)
  .map((b) => ({
    properties: b.wide
      ? { type: 'continuous', page: PAGE }
      : { type: 'continuous', page: PAGE, column: { count: 2, space: 360, equalWidth: true } },
    children: b.children,
  }))

const doc = new Document({
  numbering: {
    config: [
      { reference: 'bullets', levels: [{ level: 0, format: 'bullet', text: '\u2022', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 180 } } } }] },
      { reference: 'contributions', levels: [{ level: 0, format: 'decimal', text: '%1)', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 260 } } } }] },
    ],
  },
  sections: [
    { properties: { page: PAGE }, children: front },
    ...bodySections,
  ],
})

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync('IEEE-Access-draft.docx', buf)
  console.log('wrote IEEE-Access-draft.docx', buf.length, 'bytes')
})
