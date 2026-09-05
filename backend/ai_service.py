"""LLM access layer.

Design points that matter for the study:

* **Provider-agnostic.** OpenAI, any OpenAI-compatible endpoint (Azure,
  OpenRouter, Ollama, vLLM, LM Studio), and Anthropic are all reachable through
  one interface, selected by `provider:model` strings. Running the same analysis
  under a second model is what separates findings about the *approach* from
  findings about one particular model.
* **Deterministic settings.** `temperature=0` and a fixed seed where the
  provider supports it. That does not make a hosted model bit-deterministic;
  the residual variance is measured by `/projects/{name}/repeatability` rather
  than assumed away.
* **Retries with backoff and a hard timeout**, so a transient API error
  degrades to the deterministic path instead of failing the whole analysis.
* **Usage captured from the response**, not re-estimated.
* **An offline deterministic mode** that lets the entire application run, and
  the test suite pass, with no API key -- and provides the no-LLM control
  condition for the evaluation.
"""
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:  # tiktoken is an optimisation, not a requirement
    import tiktoken
except ImportError:  # pragma: no cover - depends on the install
    tiktoken = None

from config import (
    ANTHROPIC_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_MODE,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_SEED,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
)

_ENCODER: Any = None

OFFLINE_MODEL = "deterministic-offline"


# --- tokens ------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Exact when tiktoken is installed, a ~4-chars-per-token estimate
    otherwise. Which one produced a figure is reported alongside it, so an
    estimate is never presented as a measurement."""
    global _ENCODER
    if _ENCODER is None:
        if tiktoken is None:
            _ENCODER = False
        else:
            try:
                _ENCODER = tiktoken.get_encoding("cl100k_base")
            except Exception:
                _ENCODER = False
    if _ENCODER is False:
        return max(1, len(text) // 4)
    return len(_ENCODER.encode(text))


def token_counts_are_exact() -> bool:
    count_tokens("")
    return _ENCODER not in (None, False)


# --- results -----------------------------------------------------------------


@dataclass
class LlmResult:
    payload: Dict[str, Any]
    model: str
    invoked: bool
    provider: str = "offline"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    attempts: int = 0
    degraded: bool = False
    notes: List[str] = field(default_factory=list)

    def usage(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "invoked": self.invoked,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": round(self.latency_ms, 1),
            "attempts": self.attempts,
            "degraded": self.degraded,
            "notes": self.notes,
        }


class LlmUnavailable(Exception):
    """The model could not be reached or returned unusable output."""


RESPONSE_SCHEMA_DESCRIPTION = """{
  "similarity_score": <integer 0-100>,
  "gaps": ["<deviation between the design and the implementation>"],
  "recommendations": ["<concrete refactoring step>"],
  "unit_tests": [
    {"target_file": "<path>", "framework": "PyTest|Jest|JUnit", "code": "<test source>"}
  ],
  "semantic_graph": {
    "nodes": [{"id": "<name>", "type": "class|function|module|interface"}],
    "edges": [{"source": "<name>", "target": "<name>", "relation": "depends_on|calls|implements|extends"}]
  }
}"""

SYSTEM_PROMPT = (
    "You are a precise architectural conformance and testing engine. "
    "Output strictly valid JSON matching the requested schema. "
    "Report only deviations you can justify from the structures given; "
    "if the design model is empty, say so in `gaps` rather than inventing findings."
)


# --- provider selection -------------------------------------------------------


def parse_model_spec(spec: str) -> Tuple[str, str]:
    """`"anthropic:claude-sonnet-4-5"` -> `("anthropic", "claude-sonnet-4-5")`.

    A bare model name uses the configured default provider. Model names contain
    no colon in any provider's naming scheme currently in use, so the split is
    unambiguous; a URL-style spec would not be.
    """
    if ":" in spec:
        provider, _, model = spec.partition(":")
        provider = provider.strip().lower()
        if provider in ("openai", "compatible", "anthropic", "offline"):
            return provider, model.strip()
    return LLM_PROVIDER, spec.strip()


def provider_available(provider: str) -> bool:
    if LLM_MODE == "offline" or provider == "offline":
        return False
    if LLM_MODE == "api":
        return True
    if provider == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    if provider == "compatible":
        return bool(LLM_BASE_URL)
    return bool(OPENAI_API_KEY)


def llm_available() -> bool:
    return provider_available(LLM_PROVIDER)


def available_models() -> List[Dict[str, Any]]:
    """Every model the server is configured to be able to call."""
    seen: Dict[str, Dict[str, Any]] = {}
    for spec in [f"{LLM_PROVIDER}:{LLM_MODEL}", *_comparison_specs()]:
        provider, model = parse_model_spec(spec)
        key = f"{provider}:{model}"
        if key not in seen:
            seen[key] = {
                "spec": key,
                "provider": provider,
                "model": model,
                "available": provider_available(provider),
            }
    seen[OFFLINE_MODEL] = {
        "spec": f"offline:{OFFLINE_MODEL}",
        "provider": "offline",
        "model": OFFLINE_MODEL,
        "available": True,
    }
    return list(seen.values())


def _comparison_specs() -> List[str]:
    from config import LLM_COMPARISON_MODELS

    return LLM_COMPARISON_MODELS


# --- transport ----------------------------------------------------------------


def _openai_client(provider: str):
    from openai import OpenAI  # imported lazily so offline mode needs no SDK

    if provider == "compatible":
        return OpenAI(
            api_key=OPENAI_API_KEY or "not-needed",
            base_url=LLM_BASE_URL or None,
            timeout=LLM_TIMEOUT_SECONDS,
        )
    return OpenAI(api_key=OPENAI_API_KEY or None, timeout=LLM_TIMEOUT_SECONDS)


def _anthropic_client():
    from anthropic import Anthropic  # optional dependency

    return Anthropic(api_key=ANTHROPIC_API_KEY or None, timeout=LLM_TIMEOUT_SECONDS)


def _call_openai(provider: str, model: str, system: str, user: str):
    kwargs: Dict[str, Any] = {
        "model": model,
        "temperature": LLM_TEMPERATURE,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    # Not every OpenAI-compatible server implements these; drop them and retry
    # rather than failing outright.
    optional = {"response_format": {"type": "json_object"}, "seed": LLM_SEED}
    client = _openai_client(provider)
    try:
        response = client.chat.completions.create(**kwargs, **optional)
    except TypeError:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if "response_format" in str(exc) or "seed" in str(exc):
            response = client.chat.completions.create(**kwargs)
        else:
            raise
    usage = getattr(response, "usage", None)
    return (
        response.choices[0].message.content or "{}",
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


def _call_anthropic(model: str, system: str, user: str):
    client = _anthropic_client()
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        temperature=LLM_TEMPERATURE,
        system=system + " Respond with a single JSON object and no prose.",
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    usage = getattr(response, "usage", None)
    return (
        text or "{}",
        getattr(usage, "input_tokens", 0) or 0,
        getattr(usage, "output_tokens", 0) or 0,
    )


def _extract_json(text: str) -> Dict[str, Any]:
    """Tolerate a fenced or prose-wrapped object.

    Providers without a JSON mode will occasionally wrap the object in a code
    fence; failing the whole analysis over that would be a transport problem
    masquerading as a model problem.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _chat_json(provider: str, model: str, system: str, user: str) -> LlmResult:
    last_error: Optional[Exception] = None
    started = time.perf_counter()

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            if provider == "anthropic":
                content, prompt_tokens, completion_tokens = _call_anthropic(model, system, user)
            else:
                content, prompt_tokens, completion_tokens = _call_openai(
                    provider, model, system, user
                )
            return LlmResult(
                payload=_extract_json(content),
                model=model,
                provider=provider,
                invoked=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=(time.perf_counter() - started) * 1000,
                attempts=attempt,
            )
        except Exception as exc:  # network, rate limit, auth, malformed JSON
            last_error = exc

        if attempt < LLM_MAX_RETRIES:
            time.sleep(min((2 ** (attempt - 1)) + random.uniform(0, 0.5), 8.0))

    raise LlmUnavailable(str(last_error) if last_error else "Unknown LLM failure")


# --- normalisation ------------------------------------------------------------


def _normalise(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce whatever came back into the documented schema.

    A model that returns a string where a list was requested should degrade the
    result, not crash the endpoint.
    """
    def as_list(value) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    score = payload.get("similarity_score", 0)
    try:
        score = max(0, min(100, int(round(float(score)))))
    except (TypeError, ValueError):
        score = 0

    graph = payload.get("semantic_graph") or {}
    if not isinstance(graph, dict):
        graph = {}

    nodes: List[Dict[str, str]] = []
    for node in as_list(graph.get("nodes")):
        if isinstance(node, dict) and node.get("id"):
            nodes.append({"id": str(node["id"]), "type": str(node.get("type", "unknown"))})
        elif isinstance(node, str):
            nodes.append({"id": node, "type": "unknown"})

    edges: List[Dict[str, str]] = []
    known = {node["id"] for node in nodes}
    for edge in as_list(graph.get("edges")):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("source"), edge.get("target")
        if not source or not target:
            continue
        # Dropping an edge whose endpoints the model never declared would hide
        # invented structure; keep it and mark the endpoints instead.
        for endpoint in (source, target):
            if endpoint not in known:
                nodes.append({"id": str(endpoint), "type": "inferred"})
                known.add(endpoint)
        edges.append(
            {
                "source": str(source),
                "target": str(target),
                "relation": str(edge.get("relation", "depends_on")),
            }
        )

    tests = []
    for test in as_list(payload.get("unit_tests")):
        if isinstance(test, dict) and test.get("code"):
            tests.append(
                {
                    "target_file": str(test.get("target_file", "unknown")),
                    "framework": str(test.get("framework", "unknown")),
                    "code": str(test["code"]),
                }
            )

    return {
        "similarity_score": score,
        "gaps": [str(gap) for gap in as_list(payload.get("gaps"))],
        "recommendations": [str(item) for item in as_list(payload.get("recommendations"))],
        "unit_tests": tests,
        "semantic_graph": {"nodes": nodes, "edges": edges},
    }


# --- public API ---------------------------------------------------------------


def build_prompt(
    uml_design: Dict[str, Any],
    code_architecture: Dict[str, Any],
    scope: Optional[Dict[str, Any]] = None,
    rule_findings: Optional[Dict[str, Any]] = None,
) -> str:
    if scope:
        scope_block = (
            "This is an INCREMENTAL re-evaluation. Only the following components "
            "changed since the last analysis; every other component was verified "
            "previously and is unchanged. Restrict findings to this impact set and "
            "to anything it demonstrably breaks.\n"
            f"Changed and impacted components:\n{json.dumps(scope.get('impact', []), indent=2)}\n"
            f"Change summary: {json.dumps(scope.get('summary', {}))}\n"
        )
        architecture_block = json.dumps(scope.get("architecture", code_architecture))
    else:
        scope_block = "This is a FULL evaluation of the whole project.\n"
        architecture_block = json.dumps(code_architecture)

    rule_block = ""
    if rule_findings:
        rule_block = (
            "\nA deterministic parser already computed the following. Treat it as "
            "ground truth about structure; do not contradict it, and use it to "
            "avoid re-deriving what is already known:\n"
            f"{json.dumps(rule_findings, indent=2)}\n"
        )

    return (
        "Compare the intended UML design against the actual codebase architecture.\n\n"
        f"{scope_block}"
        f"\nUML Design (intended):\n{json.dumps(uml_design)}\n"
        f"\nCode Architecture (actual):\n{architecture_block}\n"
        f"{rule_block}"
        f"\nReturn ONLY a valid JSON object matching this schema:\n{RESPONSE_SCHEMA_DESCRIPTION}\n"
    )


def evaluate_conformance(
    uml_design: Dict[str, Any],
    code_architecture: Dict[str, Any],
    *,
    scope: Optional[Dict[str, Any]] = None,
    rule_findings: Optional[Dict[str, Any]] = None,
    model_spec: Optional[str] = None,
) -> LlmResult:
    """Compare intended design against implementation.

    When `scope` is supplied the prompt describes only the changed subgraph and
    states that everything else was verified previously -- this is what makes an
    incremental run cheaper than a cold one.
    """
    provider, model = parse_model_spec(model_spec or f"{LLM_PROVIDER}:{LLM_MODEL}")

    if not provider_available(provider):
        result = _offline_result(code_architecture, rule_findings)
        if model_spec and provider != "offline":
            result.notes.append(f"{provider} is not configured; used the deterministic path.")
        return result

    prompt = build_prompt(uml_design, code_architecture, scope, rule_findings)

    try:
        result = _chat_json(provider, model, SYSTEM_PROMPT, prompt)
    except LlmUnavailable as exc:
        fallback = _offline_result(code_architecture, rule_findings)
        fallback.degraded = True
        fallback.notes.append(f"LLM unavailable, fell back to deterministic analysis: {exc}")
        return fallback

    result.payload = _normalise(result.payload)
    if not result.prompt_tokens:
        result.prompt_tokens = count_tokens(SYSTEM_PROMPT + prompt)
    return result


def _offline_result(
    code_architecture: Dict[str, Any], rule_findings: Optional[Dict[str, Any]]
) -> LlmResult:
    """Deterministic analysis with no network call.

    Everything here is derived by parsing, so it is reproducible and serves as
    the study's control condition. It is labelled as such in the output so a
    result produced this way can never be mistaken for a model's judgement.
    """
    findings = rule_findings or {}
    gaps: List[str] = []

    for name in findings.get("missing_classes", []) or []:
        gaps.append(f"Class '{name}' appears in the UML design but not in the code.")
    for name in findings.get("extra_classes", []) or []:
        gaps.append(f"Class '{name}' exists in the code but not in the UML design.")
    for relation in findings.get("missing_relations", []) or []:
        gaps.append(f"Relationship not implemented: {relation}")
    for relation in findings.get("unimplemented_associations", []) or []:
        gaps.append(f"Association has no supporting evidence in the code: {relation}")
    for difference in findings.get("element_differences", []) or []:
        for method in difference.get("missing_methods", []):
            gaps.append(f"{difference['element_name']}.{method}() is designed but not implemented.")
        for attribute in difference.get("missing_attributes", []):
            gaps.append(f"{difference['element_name']}.{attribute} is designed but not implemented.")

    recommendations = []
    if findings.get("missing_classes"):
        recommendations.append(
            "Implement the missing classes, or remove them from the diagram if the design moved on."
        )
    if findings.get("extra_classes"):
        recommendations.append(
            "Add the undocumented classes to the UML model so the diagram stays authoritative."
        )
    if findings.get("unimplemented_associations"):
        recommendations.append(
            "Give each modelled association a typed field or signature so it is visible in the code."
        )
    if not recommendations:
        recommendations.append("No structural divergence detected by the deterministic checker.")

    nodes = []
    edges = []
    for record in code_architecture.get("files", []):
        path = record["file_path"]
        nodes.append({"id": path, "type": "module"})
        for klass in record.get("classes", []):
            nodes.append({"id": klass["name"], "type": klass.get("kind", "class")})
            edges.append({"source": path, "target": klass["name"], "relation": "contains"})
            for base in klass.get("bases", []):
                edges.append({"source": klass["name"], "target": base, "relation": "extends"})

    return LlmResult(
        payload={
            "similarity_score": int(findings.get("similarity_score", 0) or 0),
            "gaps": gaps,
            "recommendations": recommendations,
            "unit_tests": [],
            "semantic_graph": {"nodes": nodes, "edges": edges},
        },
        model=OFFLINE_MODEL,
        provider="offline",
        invoked=False,
        notes=["Produced without an LLM: structural findings only, no generated tests."],
    )


def explain_file(file_content: str, file_path: str) -> Dict[str, Any]:
    provider, model = parse_model_spec(f"{LLM_PROVIDER}:{LLM_MODEL}")
    if not provider_available(provider):
        return {
            "explanation": (
                "AI explanations are disabled (no model configured). "
                f"{file_path} is {len(file_content.splitlines())} lines long."
            ),
            "model": OFFLINE_MODEL,
            "invoked": False,
        }

    # Truncate rather than send an unbounded file: cost scales with input.
    excerpt = file_content[:20000]
    prompt = (
        f"Analyse this source file: {file_path}\n\n{excerpt}\n\n"
        "Give a concise 3-4 sentence plain-English summary of what it does."
    )
    system = "You are a senior developer explaining codebase context to a new team member."

    try:
        if provider == "anthropic":
            text, prompt_tokens, completion_tokens = _call_anthropic(model, system, prompt)
        else:
            text, prompt_tokens, completion_tokens = _call_openai(provider, model, system, prompt)
        return {
            "explanation": text,
            "model": model,
            "provider": provider,
            "invoked": True,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
    except Exception as exc:
        return {
            "explanation": f"Could not generate an explanation: {exc}",
            "model": model,
            "invoked": False,
            "error": True,
        }
