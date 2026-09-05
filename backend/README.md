# Backend

FastAPI service: parses code and UML, compares them, decides whether to spend a
model call, and records what every run cost.

## Run it

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1          # source venv/bin/activate elsewhere
pip install -r requirements.txt
copy .env.example .env             # then set SECRET_KEY
uvicorn main:app --reload --port 8000
```

API on <http://localhost:8000>, interactive docs at `/docs`, reference in
[`../docs/API.md`](../docs/API.md).

**No API key is needed.** With `OPENAI_API_KEY` blank the whole pipeline runs
deterministically — parsing, graphs, the gate, versioning, the conformance check
and every statistic. A model only adds natural-language gap descriptions, and
results produced without one are labelled `deterministic-offline`.

## Tests

```powershell
python -m unittest discover -s tests -t .   # 210 tests, under a second
python tools/check_imports.py               # every local import resolves
```

Tests needing the native tree-sitter grammars or FastAPI skip themselves and say
why. Skips are expected; failures are not.

## Layout

| Path | Does |
|---|---|
| `main.py` | Every HTTP endpoint. Thin — logic lives in `core/` |
| `config.py` | All configuration, read from the environment |
| `auth.py` | JWT, password hashing, per-user rate limiting |
| `ai_service.py` | Model providers, determinism, retries, offline mode |
| `core/pipeline.py` | Orchestrates one analysis run — **read this first** |
| `core/graph_diff.py` | **The gate.** The project's actual contribution |
| `core/graph_builder.py` | Parser output → NetworkX; call resolution |
| `core/graph_store.py` | Three-version ring, two graphs per version |
| `core/run_ledger.py` | Per-run metrics — the evaluation dataset |
| `core/workspace_fs.py` | The virtual directory (no git required) |
| `core/paths.py`, `core/archive.py` | Containment and hardened extraction |
| `comparison/engine.py` | Deterministic conformance check |
| `parsers/` | tree-sitter extraction; StarUML `.mdj` reader |
| `stats/` | The four paper tables, pure Python |

Full walkthrough: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Configuration

Everything is in `.env`; `.env.example` documents each key. The ones that matter:

| Key | Effect |
|---|---|
| `SECRET_KEY` | Signs session tokens. Unset means sessions die on restart |
| `LLM_MODE` | `auto` uses a model when a key exists; `offline` never calls out |
| `GATE_STRATEGY` | Default gate: `always`, `content`, `structural`, `isomorphism` |
| `MAX_GRAPH_VERSIONS` | Snapshots retained (3) |
| `IMPACT_RADIUS` | How far around a change the model is shown (1) |
| `ASSOCIATION_SCORING` | Whether associations count toward the score (off) |

## Two things not to break

**The gate graph and the presentation graph are different objects.** Comparing a
merged graph against a freshly parsed one never matches, so the cache never hits.
`test_cold_start_then_cache_hit` guards this.

**`gate_allowed_llm` and `llm_invoked` are separate ledger fields.** The gate
permitting a re-analysis and a model actually being reached are different facts;
they differ in offline mode.
