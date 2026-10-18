"""Replay with a real local model in the loop (Ollama), and measure what it costs.

The offline replay (replay.py) can only say how large a prompt a gate *would*
have sent. This script sends it. Every gate re-analysis goes to a local model
served by Ollama, and the run records what Ollama itself reports: prompt tokens
evaluated, tokens generated, and how long each took. No hosted API and no key
are involved.

What is and is not called
-------------------------
* The oracle never reaches a model. Its findings are deterministic, and the
  drift measures depend on them alone.
* Every gate re-analysis is sent, except where `--always-sample` thins out the
  `always` baseline (see below) or the prompt does not fit.
* A prompt larger than the context window is **not sent**. Ollama truncates an
  over-long prompt silently and answers as though it had read all of it, so
  sending it would record a cost for an analysis of part of the project. Such a
  run is recorded as `no_fit` with its estimated size; it is neither a call nor
  a saving.
* Responses are cached on disk by a hash of (model, context, system, prompt).
  Two gates that send byte-identical prompts at a commit share one call; the
  cached row still reports the measured tokens and time of that call, flagged
  `cache_hit`, so cost is attributed to each gate that needed it.

`--always-sample k` calls the model for `always` at commit 0, at every commit
whose deterministic findings changed, and at every k-th commit otherwise.
Unsampled `always` runs are recorded as `not_sampled`; their cost is
estimated from the measured calls, and the paper says so.

Usage
-----
    python research/live_llm.py --corpus research/corpus.json --out results/live \
        --model qwen2.5-coder:7b --num-ctx 32768
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", required=True)
    p.add_argument("--only", help="Comma-separated project names to run from the corpus.")
    p.add_argument("--out", default="results/live")
    p.add_argument("--cache", default=".corpus-cache")
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--num-ctx", type=int, default=32768)
    p.add_argument("--num-predict", type=int, default=2048,
                   help="Cap on generated tokens per call (default 2048).")
    p.add_argument("--fit-margin", type=float, default=0.85,
                   help="Send only prompts estimated below this share of num_ctx.")
    p.add_argument("--always-sample", type=int, default=0,
                   help="0 = call `always` at every commit; k = commit 0, changes, and every k-th.")
    p.add_argument("--strategies", default="always,content,structural,isomorphism")
    p.add_argument("--timeout", type=float, default=3600.0)
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


IDENT = re.compile(r"`([A-Za-z_][\w.]*)`|'([A-Za-z_][\w.]*)'|\"([A-Za-z_][\w.]*)\"|\b([A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+)\b")


def mentioned_identifiers(texts) -> set:
    """Identifiers a model's prose refers to: quoted names and CamelCase words."""
    found = set()
    for text in texts or []:
        if not isinstance(text, str):
            text = json.dumps(text)
        for match in IDENT.finditer(text):
            name = next(g for g in match.groups() if g)
            for part in re.split(r"[.()]", name):
                if len(part) >= 3:
                    found.add(part)
    return found


def deviation_elements(difference: Dict[str, Any]) -> set:
    names = set(difference.get("missing_classes", []) or []) | set(difference.get("extra_classes", []) or [])
    for item in difference.get("element_differences", []) or []:
        names.add(item["element_name"])
    return names


WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_vocabulary_cache: Dict[str, set] = {}


def project_vocabulary(project_path: str) -> set:
    """Every identifier-like word in the analysed source and the design model.

    A name the model mentions that is not in here exists nowhere in the code or
    the diagram it was asked about -- the strict sense of "invented".
    """
    words: set = set()
    for sub in ("source", "uml"):
        root = os.path.join(project_path, sub)
        for current, _, files in os.walk(root):
            for filename in files:
                try:
                    with open(os.path.join(current, filename), encoding="utf-8", errors="replace") as handle:
                        words.update(WORD.findall(handle.read()))
                except OSError:
                    continue
    return words


def grounded_names(result: Dict[str, Any]) -> set:
    names = set()
    for node in (result.get("graph_data") or {}).get("nodes", []):
        for key in ("id", "label", "name"):
            value = node.get(key)
            if isinstance(value, str):
                names.update(p for p in re.split(r"[^\w]+", value) if p)
    difference = result.get("difference") or {}
    names |= deviation_elements(difference)
    for item in difference.get("element_differences", []) or []:
        for key in ("missing_methods", "missing_attributes", "extra_methods", "extra_attributes"):
            names.update(item.get(key, []) or [])
    for relation in (difference.get("missing_relations", []) or []) + (difference.get("unimplemented_associations", []) or []):
        names.update(p for p in re.split(r"[^\w]+", str(relation)) if p)
    return names


class LiveModel:
    """Patches ai_service so gate re-analyses reach Ollama, with a cache and a fit guard."""

    def __init__(self, args):
        self.args = args
        self.cache_dir = os.path.join(args.out, "llm-cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.calls_log = open(os.path.join(args.out, "calls.jsonl"), "a", encoding="utf-8")
        self.mode = "call"
        self.last: Dict[str, Any] = {}
        self.previous_deviations: Dict[str, set] = {}

        import ai_service
        from core import pipeline  # noqa: F401  (ensures the module that calls us is loaded)

        self.ai = ai_service
        ai_service.LLM_MODE = "auto"
        ai_service.LLM_PROVIDER = "ollama"
        ai_service.LLM_MODEL = args.model
        ai_service.OLLAMA_NUM_CTX = args.num_ctx
        ai_service._chat_json = self._chat_json

    # -- hooks called by replay.replay_project --------------------------------
    def before_run(self, strategy: str, index: int, conformance_changed: Optional[bool],
                   project_path: Optional[str] = None):
        self.last = {"llm_status": "reused"}
        self.project_path = project_path
        self.strategy = strategy
        if strategy == "oracle":
            self.mode = "suppress"
        elif strategy == "always" and self.args.always_sample:
            sampled = index == 0 or conformance_changed or index % self.args.always_sample == 0
            self.mode = "call" if sampled else "not_sampled"
        else:
            self.mode = "call"

    def row(self, result: Dict[str, Any], row: Dict[str, Any]):
        row.update({
            "llm_status": self.last.get("llm_status"),
            "cache_hit": self.last.get("cache_hit"),
            "est_prompt_tokens": self.last.get("est_prompt_tokens"),
            "ollama_prompt_tokens": self.last.get("prompt_eval_count"),
            "ollama_completion_tokens": self.last.get("eval_count"),
            "prompt_eval_s": self.last.get("prompt_eval_s"),
            "eval_s": self.last.get("eval_s"),
            "llm_wall_s": self.last.get("wall_s"),
            "json_ok": self.last.get("json_ok"),
            "prompt_key": self.last.get("key"),
        })
        # Quality of the explanation being *served* at this commit, judged
        # against the deterministic findings of this same commit.
        gaps = result.get("ai_gaps") or []
        mentioned = mentioned_identifiers(gaps + (result.get("recommendations") or []))
        deviations = deviation_elements(result.get("difference") or {})
        grounded = grounded_names(result) | deviations
        if getattr(self, "project_path", None):
            grounded |= project_vocabulary(self.project_path)
        key = (row["project"], row["gate_strategy"])
        previous = self.previous_deviations.get(key)
        changed = (deviations ^ previous) if previous is not None else set()
        self.previous_deviations[key] = deviations
        row.update({
            "served_gap_count": len(gaps),
            "served_mentions": len(mentioned),
            "mention_coverage": round(len(deviations & mentioned) / len(deviations), 4) if deviations else None,
            "changed_elements": len(changed),
            "changed_coverage": round(len(changed & mentioned) / len(changed), 4) if changed else None,
            "ungrounded_mentions": len(mentioned - grounded),
            "model_score": result.get("model_score"),
        })

    # -- the patched call ------------------------------------------------------
    def _chat_json(self, provider, model, system, user):
        ai = self.ai
        estimate = ai.count_tokens(system + user)
        self.last.update(est_prompt_tokens=estimate)
        if self.mode == "suppress":
            self.last["llm_status"] = "oracle_offline"
            raise ai.LlmUnavailable("oracle runs are deterministic by design")
        if self.mode == "not_sampled":
            self.last["llm_status"] = "not_sampled"
            raise ai.LlmUnavailable("always baseline not sampled at this commit")
        if estimate > self.args.num_ctx * self.args.fit_margin:
            self.last["llm_status"] = "no_fit"
            raise ai.LlmUnavailable(f"prompt of ~{estimate} tokens exceeds the {self.args.num_ctx}-token context")

        key = hashlib.sha256(json.dumps([model, self.args.num_ctx, self.args.num_predict, system, user]).encode()).hexdigest()[:24]
        # A repeat run re-sends the prompt and stores it beside the original,
        # so the two answers can be compared (run-to-run variation).
        if getattr(self.args, "repeat", False):
            key = key + "-r"
        path = os.path.join(self.cache_dir, key + ".json")
        cache_hit = os.path.exists(path)
        if cache_hit:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        else:
            record = self._send(model, system, user)
            record["key"] = key
            record["est_prompt_tokens"] = estimate
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(record, handle)
        self.calls_log.write(json.dumps({"key": key, "strategy": self.strategy, "cache_hit": cache_hit,
                                         **{k: v for k, v in record.items() if k != "content"}}) + "\n")
        self.calls_log.flush()
        self.last.update(
            llm_status="called" if record.get("ok") else "error",
            cache_hit=cache_hit, key=key,
            prompt_eval_count=record.get("prompt_eval_count"), eval_count=record.get("eval_count"),
            prompt_eval_s=record.get("prompt_eval_s"), eval_s=record.get("eval_s"), wall_s=record.get("wall_s"),
        )
        if not record.get("ok"):
            raise ai.LlmUnavailable(record.get("error", "call failed"))
        try:
            payload = ai._extract_json(record["content"])
            self.last["json_ok"] = True
        except Exception:
            self.last["json_ok"] = False
            self.last["llm_status"] = "bad_json"
            raise ai.LlmUnavailable("model answer was not JSON")
        return ai.LlmResult(
            payload=payload, model=model, provider=provider, invoked=True,
            prompt_tokens=record.get("prompt_eval_count") or 0,
            completion_tokens=record.get("eval_count") or 0,
            latency_ms=(record.get("wall_s") or 0) * 1000, attempts=1,
        )

    def _send(self, model, system, user) -> Dict[str, Any]:
        """The request ai_service._call_openai makes for Ollama, plus timings."""
        import httpx

        base = self.ai.OLLAMA_BASE_URL.rstrip("/").removesuffix("/v1")
        body = {"model": model, "stream": False, "format": "json",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": {"num_ctx": self.args.num_ctx, "num_predict": self.args.num_predict,
                            "temperature": self.ai.LLM_TEMPERATURE, "seed": self.ai.LLM_SEED}}
        started = time.perf_counter()
        try:
            response = httpx.post(base + "/api/chat", json=body, timeout=self.args.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return {"ok": False, "error": repr(exc)[:300], "wall_s": round(time.perf_counter() - started, 2)}
        prompt_eval_count = data.get("prompt_eval_count", 0)
        return {
            "ok": True,
            "content": data["message"]["content"],
            "prompt_eval_count": prompt_eval_count,
            "eval_count": data.get("eval_count", 0),
            "prompt_eval_s": round(data.get("prompt_eval_duration", 0) / 1e9, 2),
            "eval_s": round(data.get("eval_duration", 0) / 1e9, 2),
            "load_s": round(data.get("load_duration", 0) / 1e9, 2),
            "wall_s": round(time.perf_counter() - started, 2),
            "done_reason": data.get("done_reason"),
            # Ollama evaluated (close to) the whole window: it truncated.
            "truncated": prompt_eval_count >= self.args.num_ctx * 0.98,
        }


def main(argv=None) -> int:
    args = parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    os.environ["LLM_MODE"] = "auto"
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["LLM_MODEL"] = args.model
    os.environ["OLLAMA_NUM_CTX"] = str(args.num_ctx)
    os.environ["LLM_TIMEOUT_SECONDS"] = str(args.timeout)

    import replay
    from harness import Sandbox, git_available, load_corpus, preflight, write_csv, write_json

    if not git_available() or preflight():
        print(preflight() or "git is required", file=sys.stderr)
        return 2
    live = LiveModel(args)

    def log(message):
        if not args.quiet:
            print(message, flush=True)

    projects = load_corpus(args.corpus)
    if args.only:
        wanted = {name.strip() for name in args.only.split(",")}
        projects = [p for p in projects if p.name in wanted]
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    log(f"Live replay: {len(projects)} project(s), model {args.model}, num_ctx {args.num_ctx}")

    for spec in projects:
        sandbox = Sandbox.create()
        try:
            outcome = replay.replay_project(spec, strategies, sandbox, args.cache, log, hooks=live)
        finally:
            sandbox.cleanup()
        write_csv(os.path.join(args.out, f"runs-{spec.name}.csv"), outcome["rows"])
        write_json(os.path.join(args.out, f"summary-{spec.name}.json"),
                   {"project": spec.name, "model": args.model, "num_ctx": args.num_ctx,
                    "num_predict": args.num_predict, "always_sample": args.always_sample,
                    "by_strategy": replay.summarise(outcome["rows"]), "misses": outcome["misses"]})
        log(f"  {spec.name}: done, {len(outcome['rows'])} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
