# The paper

`IEEE-Access-draft.docx` — the manuscript. **This is the only copy.** Edit it
directly in Word.

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
