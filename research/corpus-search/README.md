# How the v2 corpus was found (18 October 2026)

The search had four stages. Stages 1–2 ran in a browser and on public search
services, so their raw output is only partly preserved; stages 3–4 are scripts
and are fully reproducible from the files here.

1. **Search.** Two sources, no API keys.
   * Sourcegraph public code search, query `file:\.mdj$ UMLClass` and six
     variants (`sg.py`): **102** repositories (`sourcegraph-repos.json`).
   * GitHub code search, signed in through the web interface, query
     `path:*.mdj UMLClass UMLOperation <term>`, sliced by 49 extra terms because
     each query returns at most about 100 results: **3,056** repositories.
     Only the per-repository paths of `.mdj` files were kept in the browser;
     the full result list was not exported.
2. **Staleness filter.** For each GitHub repository, the date of the last
   commit touching each `.mdj` file (up to four per repository) was compared
   with the repository's last commit, using GitHub's `latest-commit` endpoint
   (3,055 of 3,056 answered). Models last edited **at least 180 days** before
   the repository's last commit were kept and exported in two batches
   (`github-stale-batch1.tsv`, `github-stale-batch2.txt`). Batch 2 excluded by
   regular expression repositories and paths that name coursework (semester,
   lab, assignment, university course codes, design-pattern tutorials, notes)
   and non-class diagrams (use case, sequence, ER, …). Both batches were then
   pruned by hand of evident coursework, notes repositories and copies of
   vendored libraries; the Sourcegraph first pass (`screen.py`,
   `sourcegraph-first-pass.json`) contributed its real projects the same way.
   This manual step only removed candidates that stage 3 would have rejected
   for having no designed classes in code; it is a threat to exact
   replication, and is reported as one.
3. **Screen** (`screen_candidates.py`, paths inside are those of the original
   machine): for each of the **215** (repository, model) pairs in
   `screened-candidates.json`, clone, take the model at its last edit (the
   freeze), find which designed classes are declared in code at the freeze,
   take their common directory as the analysed directory, count first-parent
   commits after the freeze touching it, and run the deterministic checker at
   the freeze and at HEAD. Output: `screen-results.json`.
4. **Inclusion rule** (`../build_corpus.py`, fixed before any replay): see the
   docstring there. Every decision is in `decisions.csv`. 50 projects qualified;
   with the three projects of the first study, the corpus is
   `../corpus-v2.json`.

**Model files of rejected candidates.** `screen-results.json` records each
candidate's `model_file` as a path on the original machine. Those copies were
deleted after the study. The 50 included models are kept in `research/models/`.
Any other model can be recreated with `git show <freeze>:<mdj path>`, using the
repository, path and freeze commit recorded in the same row.
