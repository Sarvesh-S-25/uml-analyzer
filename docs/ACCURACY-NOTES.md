# Interpreting corrected CompX results

The main score is the deterministic structural comparison, rounded to two decimal
places: `100 * checks_passed / checks_total`. These are class-name, member-name
and scored relationship checks. This is not a measure of complete behavioral
correctness, and there is no target score for a repository or model.

Ollama supplies advisory findings. Its estimate is returned separately as
`model_score` and does not alter the main score. Repeatability and model-comparison
experiments retain their separate model-estimate measurements.

Missing class models, no parsed source classes, parse errors and detected
unsupported source languages make the primary score unavailable (`null`).
The UI displays Cannot evaluate. A use-case or sequence-only model is rejected
on upload. Old saved results need a full re-check.

Source parsing includes Python, JavaScript, TypeScript, Java, C# and PHP.
The parser excludes common build and dependency folders, including `vendor`.
Language support is structural extraction, not compilation or execution. Call
resolution and type inference are incomplete; inspect coverage and parse warnings.

## Verified local uploads

- Banking: its own `sistema-bancario.staruml.mdj` gives 32/40 checks, **80.00%**.
  The unrelated registration diagram was retained as `.mdj.backup` and is no
  longer selected. The original correct diagram was copied from the source ZIP.
- GameSpark: 63 C# source files parse without syntax errors. Its uploaded model
  gives 432/471 checks, **91.72%**, after distinguishing implemented interfaces.
- MyDiary: its uploaded model contains no supported class/interface elements.
  Supply an independently appropriate class diagram before interpreting a score.
- FLUDJ: PHP now parses, but the current import has no uploaded class model and
  a template parse error. Select the intended application source scope and a
  suitable class model before evaluation. Do not copy a different project's UML.

These measurements used the existing uploads, without changing source to fit
the diagrams. They are not expected scores for other commits or corpora.

## Ollama

Ollama uses its native `/api/chat` endpoint with JSON output and explicit
`options.num_ctx`, temperature and seed. Token counts come from
`prompt_eval_count` and `eval_count`. Local token prices are zero in `.env`;
this represents no provider bill, not zero electricity or hardware cost.

Restart the backend from `backend/` after configuration changes, refresh the
frontend, and use **Force a full re-check** to produce new saved results. Existing
history has not been rewritten and old results are not corrected retroactively.
