# The paper

> **Revised version (18 October 2026):** `paper-revised.md` / `.docx` / `.pdf`
> answer the faculty review: a real local model is now in the loop, and the
> corpus has 52 projects. Do not edit `paper-revised.md` directly. It is
> generated from `paper-revised.template.md` by `research/fill_paper.py`.
> Rebuild everything, numbers, figures (`figures-v2/`), Word and PDF, with
> `powershell -ExecutionPolicy Bypass -File paperebuild-revised.ps1`. The
> Word export closes only the document it opened, so your own open Word
> documents are safe. Sources, settings and raw results:
> `../replication/README.md`.

**`paper.md` is the current manuscript** — the conformance-drift framing, the
corpus study, verified references and every number filled from `results/`.

**`paper.docx`** is the same text laid out as an IEEE conference paper (US
Letter, two columns, Times New Roman 10 pt, figures and tables placed), and
**`paper.pdf`** is Word's export of it. Both are generated — edit `paper.md`,
then rebuild:

```
python research/make_pipeline_figure.py --out paper/figures/
python research/make_figures.py --results results/ --out paper/figures/
cd paper && npm install docx && node build-paper-docx.js
```

Before submitting, fill the one highlighted placeholder (archive link in Data
Availability) and move the text into the venue's own IEEE template if it
requires one. The author name and e-mail are set at the top of
`build-paper-docx.js`.

`IEEE-Access-draft.docx` is the earlier, gate-only draft with `<placeholders>`.
Several of its statements are superseded by `paper.md` (the controlled set has
ten findings-changing deviations, not nine; reference [14] is ICSE 2025, not
ICSME; ReflexML is by Adersberger and Philippsen). Port `paper.md` into the
IEEE Access template rather than filling the old draft.

The notes below describe the old draft.

Eight pages of finished prose with 21 numbered gaps. Everything else — abstract,
all eight sections, seven tables, threats, references — is written.

## Fill it in

1. Open the `.docx` in Word and `results/REPORT.md` beside it.
2. Ctrl+F for `<` — every placeholder is written `<like this>`.
3. [`../docs/UNDERSTANDING.md`](../docs/UNDERSTANDING.md) §8 maps each
   placeholder to the exact line of `REPORT.md` it comes from.
4. Insert the three SVG figures where the italic notes say to, then delete the
   notes.
5. **Write the author biographies at the end.** IEEE Access requires one per
   author below the references, and it is the item most often missed.

## Regenerating it

`build-docx.js` produced the file. Only use it if you want to change the
skeleton — once you start editing in Word, running it again overwrites your work.

```powershell
node build-docx.js
```

## Length

IEEE Access has **no minimum** and no hard maximum, but strongly recommends
staying **under 20 pages**; over 20 needs Editor-in-Chief approval before
submitting. The draft is 8 pages of text and lands near 10 with the figures and
biographies — a normal length.

## Before submitting

Both the `.docx` **and** a matching PDF are required, under 40 MB. You also need
an ORCID for every author, 3–10 keywords, the article type (Research Article),
and an AI-disclosure sentence in the acknowledgements if any text was
AI-assisted.

Full checklist and the portal link:
[`../docs/CORPUS-AND-SUBMISSION.md`](../docs/CORPUS-AND-SUBMISSION.md) Part 2.
