# API reference

Base URL `http://localhost:8000`. Interactive docs at `/docs`, machine-readable
schema at `/openapi.json`.

**Conventions.** All routes except `/health`, `/config`, `/register`, `/login`,
and `/github/webhook` require `Authorization: Bearer <token>`. Errors return the
appropriate status with a `{"detail": "..."}` body; validation failures return
422 with FastAPI's field-level detail. Every path segment or body field that
names a file is containment-checked, so `..` anywhere returns 400 rather than
escaping the project.

**GitHub is optional.** Nothing under *Projects*, *Virtual directory*, *UML*, or
*Analysis* touches it.

---

## Meta

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness probe. |
| GET | `/config` | Client configuration: GitHub client ID, whether a model is configured, available models, gate strategies, retention count. Never includes secrets. |

## Authentication

| Method | Path | Purpose |
|---|---|---|
| POST | `/register` | `{username, email, password}`. Username 3–20 alphanumerics; password 8–72 bytes. |
| POST | `/login` | Form-encoded `username`/`password`; returns a bearer token. |
| GET | `/me` | The current user. |

## Projects

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects` | All projects with file counts, diagram presence, and latest version. |
| POST | `/projects` | `{name, github_repo_full_name?}`. Omit the repo field for a manual project. |
| GET | `/projects/{name}` | Detail: source stats, UML models, version count. |
| DELETE | `/projects/{name}` | Remove the project and its history. |

## Virtual directory

The complete no-git workflow.

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects/{name}/tree` | Files and folders with sizes and an `editable` flag, plus aggregate stats. |
| GET | `/projects/{name}/files?path=` | File contents. 400 if binary or over 1 MB. |
| POST | `/projects/{name}/files` | `{path, content}` — create; 400 if it exists. |
| PUT | `/projects/{name}/files` | `{path, content}` — create or overwrite. This is what the editor saves with. |
| DELETE | `/projects/{name}/files?path=` | Delete a file or a folder and its contents. |
| POST | `/projects/{name}/files/move` | `{source, destination}` — rename or move. |
| POST | `/projects/{name}/files/batch` | `{files: [{path, content}]}` — many text files at once; reports per-item outcomes. |
| POST | `/projects/{name}/folders` | `{path}` — create a folder. |
| POST | `/projects/{name}/upload/source` | Multipart single file, or a `.zip` whose structure is preserved. |
| POST | `/projects/{name}/upload/source-batch` | Multipart `files[]` plus `paths` (JSON array). Used by whole-folder upload. |
| DELETE | `/projects/{name}/source` | Empty the directory, keeping the project and its history. |
| GET | `/projects/{name}/export` | The source tree as a zip download. |

Archive extraction rejects absolute paths, `..` components, and symlinks, and
caps member count and uncompressed size. Rejected members are listed in the
response rather than silently dropped.

## UML models

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects/{name}/uml` | Models present; the one in use is flagged `active`. |
| POST | `/projects/{name}/upload/uml` | Multipart `.mdj`. Invalid JSON is rejected here, not at analysis time. |
| DELETE | `/projects/{name}/uml/{filename}` | Remove a model. |

Analysis uses the alphabetically first model. With several present the API says
which one that is.

## Analysis

| Method | Path | Purpose |
|---|---|---|
| POST | `/projects/{name}/analyze` | `{gate_strategy?, force?}`. Runs the gated pipeline. |
| POST | `/projects/{name}/webhook/delta` | `{modified_files, commit_hash?, gate_strategy?}`. The file list is informational; the gate recomputes the real delta. |
| GET | `/projects/{name}/versions` | Retained versions with their gate decisions and model usage. |
| GET | `/projects/{name}/versions/{v}/graph` | One version's graph as `{nodes, links}`. 404 once rotated out. |
| GET | `/projects/{name}/versions/diff?from_version=&to_version=` | Node and edge delta between two versions. |
| GET | `/projects/{name}/metrics` | Cache hit rate, tokens, cost, latency, and the raw run rows. |
| GET | `/projects/{name}/benchmark` | Raw source tokens vs. extracted-structure tokens. |
| POST | `/projects/{name}/explain` | `{file_path}` — plain-English summary of one file. |

Rate limited: `analyze`, `webhook/delta`, `explain`, `repeatability`, and
`model-comparison` share a per-user hourly budget, because each can spend money.

### Analysis response

```jsonc
{
  "version": 7,
  "gate": {
    "strategy": "structural",
    "should_invoke_llm": false,
    "decision": "reused-cached-version",
    "reason": "AST-derived structural fingerprint is unchanged; formatting-only edits are ignored.",
    "delta": { "added_nodes": 0, "changed_nodes": 0, "unchanged_nodes": 42, "...": 0 },
    "impact_node_count": 0,
    "isomorphic": null
  },
  "llm": { "model": "gpt-4o", "provider": "openai", "invoked": false, "prompt_tokens": 0, "...": 0 },
  "similarity_score": 84,
  "similarity_score_rule_based": 81.25,   // exact, from parsing
  "similarity_score_source": "cache",     // llm | cache
  "difference": {
    "missing_classes": ["AuditLog"],
    "relation_findings": [
      { "source": "OrderService", "target": "OrderRepository", "relation": "association",
        "evidence": "strong", "evidence_detail": "Field 'repo' is declared with type OrderRepository.",
        "scored": false, "satisfied": true }
    ],
    "association_scoring": false
  },
  "call_resolution": { "total_call_sites": 61, "resolved": 52, "resolution_rate": 0.852,
                       "ambiguous": 4, "external": 5 },
  "graph_validation": { "llm_node_count": 30, "grounded_nodes": 27, "grounded_node_ratio": 0.9 },
  "graph_data": { "nodes": [], "links": [] },
  "uml": { "filename": "design.mdj", "error": null, "element_count": 6, "relation_count": 4 },
  "source": { "file_count": 12, "parse_errors": [], "typescript_grammar": true }
}
```

Two scores are always returned. `similarity_score_rule_based` is computed by
parsing and is exact; `similarity_score` may come from a model or from cache,
and `similarity_score_source` says which.

## Research

| Method | Path | Purpose |
|---|---|---|
| POST | `/projects/{name}/repeatability` | `{runs}` (2–10). Re-runs on identical input; returns mean, stdev, min, max, range for score, gap count, and graph size. |
| POST | `/projects/{name}/model-comparison` | `{models: ["openai:gpt-4o", "anthropic:claude-sonnet-4-5"]}` — empty means all configured. Returns per-model results and pairwise agreement. Writes nothing to history. |

## GitHub (optional)

| Method | Path | Purpose |
|---|---|---|
| GET | `/github/status` | Whether this user has connected an account. |
| POST | `/github/callback` | `{code}` from the OAuth redirect. |
| POST | `/github/disconnect` | Forget the stored token. |
| GET | `/github/repos` | Repositories, with each one's default branch. |
| POST | `/github/webhook` | Push receiver. HMAC-verified when `GITHUB_WEBHOOK_SECRET` is set. |
