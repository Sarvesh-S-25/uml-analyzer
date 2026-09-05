"""Append-only record of every analysis run.

This is deliberately more than logging: it is the evaluation dataset. Each row
carries what a cost/benefit claim about incremental re-analysis needs -- the
gate strategy in force, whether the LLM actually ran, token counts, wall-clock
latency, and the size of the change that triggered it. Aggregating the ledger
yields the headline numbers (LLM calls avoided, tokens saved, latency saved)
directly from real usage rather than from a simulation.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import USD_PER_1M_INPUT_TOKENS, USD_PER_1M_OUTPUT_TOKENS
from core.paths import resolve_within

LEDGER_FILENAME = "runs.jsonl"
MAX_ROWS_RETURNED = 500


class RunLedger:
    def __init__(self, project_dir: str):
        self.path = resolve_within(project_dir, "reports", LEDGER_FILENAME)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def record(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(entry)
        row.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        return row

    def rows(self, limit: int = MAX_ROWS_RETURNED) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        collected: List[Dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    collected.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a partially-written row must not break reporting
        return collected[-limit:]

    def metrics(self) -> Dict[str, Any]:
        rows = self.rows(limit=10_000)
        if not rows:
            return _empty_metrics()

        # The cache-hit rate is a property of the *gate*, not of whether a
        # network call happened: in offline mode no model is ever reached, and
        # counting that as a cache hit would report a 100% hit rate for a
        # pipeline that never cached anything.
        def gate_allowed(row: Dict[str, Any]) -> bool:
            if "gate_allowed_llm" in row:
                return bool(row["gate_allowed_llm"])
            return bool(row.get("llm_invoked"))

        allowed = [r for r in rows if gate_allowed(r)]
        skipped = [r for r in rows if not gate_allowed(r)]
        invoked = [r for r in rows if r.get("llm_invoked")]

        prompt_tokens = sum(r.get("prompt_tokens", 0) or 0 for r in rows)
        completion_tokens = sum(r.get("completion_tokens", 0) or 0 for r in rows)

        # Counterfactual: what the same sequence of runs would have cost under
        # the original "always call the model" behaviour. Per-run averages come
        # from the runs that did call, so the estimate uses this project's own
        # observed cost rather than a generic constant.
        mean_prompt = (
            sum(r.get("prompt_tokens", 0) or 0 for r in invoked) / len(invoked) if invoked else 0.0
        )
        mean_completion = (
            sum(r.get("completion_tokens", 0) or 0 for r in invoked) / len(invoked)
            if invoked
            else 0.0
        )
        # Over `invoked`, not `allowed`: the gate permitting a re-analysis and
        # the model actually being reached are different facts (the same
        # distinction `gate_allowed_llm` vs `llm_invoked` draws everywhere
        # else), and they diverge in offline mode or behind a degraded
        # fallback. Averaging over `allowed` mixed in runs that were
        # permitted but never actually called the model -- near-zero latency
        # -- which understated "mean_latency_ms_llm" below its name.
        mean_latency_invoked = (
            sum(r.get("latency_ms", 0) or 0 for r in invoked) / len(invoked) if invoked else 0.0
        )
        mean_latency_skipped = (
            sum(r.get("latency_ms", 0) or 0 for r in skipped) / len(skipped) if skipped else 0.0
        )

        baseline_prompt = mean_prompt * len(rows)
        baseline_completion = mean_completion * len(rows)

        actual_cost = _cost(prompt_tokens, completion_tokens)
        baseline_cost = _cost(baseline_prompt, baseline_completion)

        by_strategy: Dict[str, Dict[str, int]] = {}
        for row in rows:
            bucket = by_strategy.setdefault(
                row.get("gate_strategy", "unknown"),
                {"runs": 0, "reanalyses": 0, "llm_calls": 0},
            )
            bucket["runs"] += 1
            if gate_allowed(row):
                bucket["reanalyses"] += 1
            if row.get("llm_invoked"):
                bucket["llm_calls"] += 1

        return {
            "total_runs": len(rows),
            "reanalyses": len(allowed),
            "llm_calls": len(invoked),
            "cached_runs": len(skipped),
            "cache_hit_rate": round(len(skipped) / len(rows), 4),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "baseline_total_tokens": int(baseline_prompt + baseline_completion),
            "tokens_saved": max(0, int(baseline_prompt + baseline_completion) - (prompt_tokens + completion_tokens)),
            "actual_cost_usd": round(actual_cost, 4),
            "baseline_cost_usd": round(baseline_cost, 4),
            "cost_saved_usd": round(max(0.0, baseline_cost - actual_cost), 4),
            "mean_latency_ms_llm": round(mean_latency_invoked, 1),
            "mean_latency_ms_cached": round(mean_latency_skipped, 1),
            "latency_saved_ms": round(
                max(0.0, (mean_latency_invoked - mean_latency_skipped) * len(skipped)), 1
            ),
            "by_strategy": by_strategy,
            "similarity_scores": [
                r.get("similarity_score") for r in rows if r.get("similarity_score") is not None
            ],
            "score_variance": _variance(
                [r.get("similarity_score") for r in rows if isinstance(r.get("similarity_score"), (int, float))]
            ),
        }


def _cost(prompt_tokens: float, completion_tokens: float) -> float:
    return (prompt_tokens / 1_000_000) * USD_PER_1M_INPUT_TOKENS + (
        completion_tokens / 1_000_000
    ) * USD_PER_1M_OUTPUT_TOKENS


def _variance(values: List[float]) -> Optional[float]:
    """Population variance of the similarity score across this ledger's runs.

    This describes how much the score moved as the *code itself* changed from
    commit to commit -- every run here is a different version of the project.
    It is not a measurement of model non-determinism (the same commit
    analysed twice could give a different score under a real model provider),
    which is a separate question with its own dedicated instrument: hit
    `/repeatability` to re-run one fixed commit N times and see the spread
    across those identical inputs. Pull the non-determinism number for the
    paper from there, not from this field.
    """
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return round(sum((v - mean) ** 2 for v in values) / len(values), 4)


def _empty_metrics() -> Dict[str, Any]:
    return {
        "total_runs": 0,
        "reanalyses": 0,
        "llm_calls": 0,
        "cached_runs": 0,
        "cache_hit_rate": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "baseline_total_tokens": 0,
        "tokens_saved": 0,
        "actual_cost_usd": 0.0,
        "baseline_cost_usd": 0.0,
        "cost_saved_usd": 0.0,
        "mean_latency_ms_llm": 0.0,
        "mean_latency_ms_cached": 0.0,
        "latency_saved_ms": 0.0,
        "by_strategy": {},
        "similarity_scores": [],
        "score_variance": None,
    }
