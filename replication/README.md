# Replication material for the revised paper (18 October 2026)

`results-2026-10-18.zip` holds every raw result behind `paper/paper-revised.md`.
`results/` is gitignored, so this archive is the copy that travels with the
repository. Unzip it at the repository root to recreate `results/`, then run
`powershell -File paper\rebuild-revised.ps1` to regenerate every table, figure
and number, plus the Word file and the PDF.

| Path in the archive | What it is |
|---|---|
| `results/corpus-v2/<project>/` | Offline first-parent replay of each corpus project (`runs.csv`, `drift_elements.csv`, `summary.json`) |
| `results/v2/` | The merged corpus: `runs.csv`, `statistics.json`, `drift.json`, `corpus_table.json`, `paper_values.json` (every number filled into the paper), `paper_numbers.md`, `live_numbers.md`, tables |
| `results/live/llm-cache/` | Every answer the local model gave, keyed by a hash of model, context, generation cap, system prompt and prompt. Files ending `-r` are the repeatability re-sends |
| `results/live/calls.jsonl` | One line per model call or cache hit: tokens, timings, done reason |
| `results/live/deviations-live*.csv` | Seeded deviations with the live model (Table V), and the repeat run |
| `results/live/runs-<project>.csv` | Live corpus replays |
| `results/deviations*.{csv,json}` | Offline seeded-deviation run |
| `results/screen-candidates.json`, `results/corpus-decisions.csv` | Corpus screen output and every inclusion decision |

## Sources and links used

**Corpus search** (details in `research/corpus-search/README.md`):

* GitHub code search, used signed in through the web interface:
  `https://github.com/search?q=path%3A*.mdj+UMLClass+UMLOperation&type=code`,
  plus the same query with each of 49 extra terms appended. The results were
  read through the page's own JSON response (`Accept: application/json`).
* GitHub's `latest-commit` endpoint, used through the same session, gave the
  date each model and each repository was last changed:
  `https://github.com/<owner>/<repo>/latest-commit/HEAD/<path>`.
* Sourcegraph public code search API, unauthenticated:
  `https://sourcegraph.com/.api/search/stream?q=file:%5C.mdj%24+UMLClass+count:all`,
  plus six variants listed in `research/corpus-search/sg.py`.
* Every repository was then cloned over plain HTTPS from GitHub. No API token
  or key was used anywhere.

The Lindholmen UML dataset
(<https://se.informatik.uni-rostock.de/en/research/datasets-and-tools/lindholmen-dataset/>)
was considered but **not used**: its index predates most StarUML 3 `.mdj`
files and was not needed.

**Model and runtime:**

* Model: `qwen2.5-coder:7b` from the Ollama library (Qwen2.5-Coder-7B-Instruct,
  Q4_K_M, digest `dae161e27b0e`), <https://ollama.com/library/qwen2.5-coder>;
  technical report arXiv:2409.12186.
* Server: Ollama **0.40.6**, standalone Windows build
  `https://github.com/ollama/ollama/releases/download/v0.40.6/ollama-windows-amd64.zip`.
  The installed Ollama on the study machine had an empty `lib/` folder, which
  meant no optimised CPU kernels and no GPU backend (about 6 prompt tokens per
  second), so this standalone build was run instead, against the same model
  store.
* Environment variables for the Intel Arc 140T integrated GPU:
  `OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`, `OLLAMA_FLASH_ATTENTION=1`,
  `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_KEEP_ALIVE=60m`.
* Request settings (fixed in `research/live_llm.py`): `num_ctx` 32768,
  `num_predict` 2048, temperature 0, seed 20260815, `format: json`. Prompts
  above 85% of the window are not sent.
* Hardware: Intel Core Ultra 7 255H, 32 GB RAM shared with the GPU, Windows
  11. Throughput measured: about 378 prompt tokens/s and 12.9 generated
  tokens/s (medians).

**Software for the paper build:** Node `docx` 9.5.1 (`paper/package.json`),
Microsoft Word for the PDF export, and matplotlib for the figures.

## What is not reproducible exactly

* The GitHub search results change over time, and coursework repositories
  were removed partly by hand. The search snapshot is in
  `research/corpus-search/`.
* Model timings depend on the machine and on what else is running.
* The live corpus arm covered two projects (banquale, bankthread). The queue
  was stopped during artvance to finish the paper. To cover more projects,
  rerun `research/live_llm.py` for each remaining project, then run
  `rebuild-revised.ps1` to update the paper.
