"""The analysis pipeline: parse -> fingerprint -> gate -> (maybe) LLM -> persist.

This module is the concrete implementation of the incremental design. The order
matters: everything deterministic happens first, so that by the time the gate is
consulted we already know exactly what changed, and by the time the model is
called we can hand it a bounded scope plus the facts we have already proven.
"""
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import networkx as nx

import ai_service
from comparison.engine import (
    ComparisonEngine,
    architecture_to_design_model,
    evaluate_layer_rules,
)
import config
from config import DEFAULT_GATE_STRATEGY, IMPACT_RADIUS
from core.graph_builder import build_design_graph, build_implementation_graph, graph_to_payload
from core.graph_diff import decide_gate, find_renames
from core.graph_store import GraphVersionStore
from core.paths import resolve_within
from core.run_ledger import RunLedger
from models.design_model import IntermediateDesignModel
from parsers.uml_parser import StarUMLParser, UmlParseError


@dataclass
class UmlLoad:
    model: Optional[IntermediateDesignModel]
    hash: str
    filename: Optional[str]
    error: Optional[str]
    warnings: List[str]


def load_uml(project_dir: str) -> UmlLoad:
    """Read the project's StarUML model, reporting failures instead of hiding them."""
    uml_dir = resolve_within(project_dir, "uml")
    if not os.path.isdir(uml_dir):
        return UmlLoad(None, "none", None, None, [])

    candidates = sorted(f for f in os.listdir(uml_dir) if f.endswith(".mdj"))
    if not candidates:
        return UmlLoad(None, "none", None, None, [])

    filename = candidates[0]
    try:
        parser = StarUMLParser(os.path.join(uml_dir, filename))
        model = StarUMLParser.apply_relations(parser.parse())
    except UmlParseError as exc:
        # Previously this was swallowed, and the project was then scored against
        # an empty design as though that were a valid result.
        return UmlLoad(None, "error", filename, str(exc), [])

    payload = json.dumps(model.model_dump(), sort_keys=True)
    import hashlib

    return UmlLoad(
        model=model,
        hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        filename=filename,
        error=None,
        warnings=model.parse_warnings,
    )


def reflexion_counts(difference: Dict[str, Any]) -> Dict[str, Any]:
    """Restate the comparison in reflexion-model terms.

    Murphy et al.'s vocabulary -- convergence, divergence, absence -- is what
    three decades of conformance literature uses, so the numbers are reported in
    it as well as in the tool's own field names. Counting is at element *and*
    member level: a class that exists but is missing two designed methods is one
    convergence and two absences, not simply "partial".
    """
    missing_classes = difference.get("missing_classes", []) or []
    extra_classes = difference.get("extra_classes", []) or []
    element_differences = difference.get("element_differences", []) or []
    relation_findings = difference.get("relation_findings", []) or []

    missing_members = sum(
        len(entry.get("missing_methods", [])) + len(entry.get("missing_attributes", []))
        for entry in element_differences
    )
    extra_members = sum(
        len(entry.get("extra_methods", [])) + len(entry.get("extra_attributes", []))
        for entry in element_differences
    )

    satisfied_relations = sum(1 for finding in relation_findings if finding.get("satisfied"))
    unsatisfied_relations = sum(1 for finding in relation_findings if not finding.get("satisfied"))

    checks_total = difference.get("checks_total") or 0
    checks_passed = difference.get("checks_passed") or 0

    return {
        # Present in both the design and the implementation.
        "convergences": int(checks_passed) + satisfied_relations,
        # In the implementation, absent from the design.
        "divergences": len(extra_classes) + extra_members,
        # In the design, absent from the implementation.
        "absences": len(missing_classes) + missing_members + unsatisfied_relations,
        "checks_total": int(checks_total),
        "detail": {
            "missing_classes": len(missing_classes),
            "extra_classes": len(extra_classes),
            "missing_members": missing_members,
            "extra_members": extra_members,
            "unsatisfied_relations": unsatisfied_relations,
        },
    }


def findings_fingerprint(difference: Dict[str, Any], violations: List[Dict[str, Any]]) -> str:
    """A hash of the deterministic findings only.

    Two runs whose fingerprints differ had a real conformance change between
    them. Because it covers only parser-derived findings and never the model's
    prose, it is stable across runs and can be used as a label without an oracle.
    """
    import hashlib

    payload = json.dumps(
        {
            "missing_classes": sorted(difference.get("missing_classes", []) or []),
            "extra_classes": sorted(difference.get("extra_classes", []) or []),
            "missing_relations": sorted(difference.get("missing_relations", []) or []),
            "unimplemented_associations": sorted(
                difference.get("unimplemented_associations", []) or []
            ),
            "element_differences": sorted(
                f"{entry['element_name']}|"
                f"{','.join(sorted(entry.get('missing_methods', [])))}|"
                f"{','.join(sorted(entry.get('missing_attributes', [])))}|"
                f"{','.join(sorted(entry.get('extra_methods', [])))}|"
                f"{','.join(sorted(entry.get('extra_attributes', [])))}"
                for entry in (difference.get("element_differences", []) or [])
            ),
            "violations": sorted(f"{v['rule']}@{v['file']}" for v in violations),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def scope_architecture(architecture: Dict[str, Any], impact_nodes: List[str]) -> Dict[str, Any]:
    """Reduce the architecture to the files touched by the impact set.

    This is the mechanism by which an incremental run costs less than a full
    one: the prompt carries the changed neighbourhood, not the whole project.
    """
    if not impact_nodes:
        return {"files": []}

    touched_files = set()
    for node in impact_nodes:
        parts = node.split("::")
        if len(parts) >= 2:
            touched_files.add(parts[1])

    return {
        "files": [f for f in architecture.get("files", []) if f["file_path"] in touched_files]
    }


def annotate_conformance(
    graph: nx.DiGraph, design_graph: nx.DiGraph, difference: Dict[str, Any]
) -> nx.DiGraph:
    """Tag each node with its conformance status and add nodes for designed-but-
    absent classes, so the visualisation shows both sides of the comparison."""
    merged = graph.copy()
    missing = set(difference.get("missing_classes", []) or [])
    extra = set(difference.get("extra_classes", []) or [])
    partial = {d["element_name"] for d in (difference.get("element_differences") or [])}

    for node, data in merged.nodes(data=True):
        if data.get("kind") not in ("class", "interface"):
            data.setdefault("status", "not_applicable")
            continue
        name = data.get("name")
        if name in partial:
            data["status"] = "partial"
        elif name in extra:
            data["status"] = "undocumented"
        else:
            data["status"] = "conforming"

    for design_node, data in design_graph.nodes(data=True):
        if data.get("name") in missing:
            merged.add_node(
                design_node,
                kind=data.get("kind", "class"),
                name=data.get("name"),
                origin="uml",
                status="missing",
            )

    for source, target, data in design_graph.edges(data=True):
        if source in merged and target in merged:
            if not merged.has_edge(source, target):
                merged.add_edge(source, target, relation=data.get("relation", "designed"), origin="uml")

    return merged


def merge_semantic_graph(
    graph: nx.DiGraph, semantic_graph: Dict[str, Any]
) -> Tuple[nx.DiGraph, Dict[str, Any]]:
    """Fold the model's inferred graph into the parsed one and score it.

    `grounded_node_ratio` is the fraction of the model's nodes that correspond
    to something the parser actually found. It is the cheapest available check
    on whether the model invented structure, and it is recorded per run.
    """
    merged = graph.copy()
    known_names = {
        data.get("name") for _, data in graph.nodes(data=True) if data.get("name")
    }
    known_names |= {os.path.basename(str(n)) for n in known_names if n}

    nodes = semantic_graph.get("nodes", []) or []
    edges = semantic_graph.get("edges", []) or []
    grounded = 0
    alias: Dict[str, str] = {}

    for node in nodes:
        node_id = str(node.get("id", "")).strip()
        if not node_id:
            continue
        match = _find_node_by_name(graph, node_id)
        if match is not None:
            grounded += 1
            alias[node_id] = match
            merged.nodes[match]["llm_type"] = node.get("type", "unknown")
        else:
            synthetic = f"llm::{node_id}"
            alias[node_id] = synthetic
            merged.add_node(
                synthetic,
                kind=str(node.get("type", "unknown")),
                name=node_id,
                origin="llm",
                status="model_inferred",
            )

    for edge in edges:
        source = alias.get(str(edge.get("source", "")))
        target = alias.get(str(edge.get("target", "")))
        if not source or not target or source == target:
            continue
        if merged.has_edge(source, target):
            merged.edges[source, target].setdefault("relation", edge.get("relation", "depends_on"))
            merged.edges[source, target]["llm_confirmed"] = True
        else:
            merged.add_edge(
                source, target, relation=str(edge.get("relation", "depends_on")), origin="llm"
            )

    validation = {
        "llm_node_count": len(nodes),
        "grounded_nodes": grounded,
        "grounded_node_ratio": round(grounded / len(nodes), 4) if nodes else None,
        "ungrounded_nodes": len(nodes) - grounded,
    }
    return merged, validation


def _find_node_by_name(graph: nx.DiGraph, name: str) -> Optional[str]:
    if name in graph:
        return name
    normalised = name.replace("\\", "/").strip()
    for node, data in graph.nodes(data=True):
        if data.get("name") == normalised:
            return node
    for node, data in graph.nodes(data=True):
        if str(data.get("name", "")).split("/")[-1] == normalised.split("/")[-1]:
            return node
    return None


def default_parse_source(source_dir: str) -> Dict[str, Any]:
    # Imported lazily: the native tree-sitter grammars are the only compiled
    # dependency in the project, and nothing else in the pipeline needs them.
    from parsers.polyglot_parser import PolyglotParser

    return PolyglotParser(source_dir).parse()


def run_analysis(
    project_dir: str,
    *,
    gate_strategy: Optional[str] = None,
    force: bool = False,
    impact_radius: int = IMPACT_RADIUS,
    parse_source: Optional[Callable[[str], Dict[str, Any]]] = None,
    model_spec: Optional[str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Execute one analysis and return the full API response payload.

    `parse_source` is injectable so the gating, versioning, and reporting logic
    can be tested against synthetic architectures without a native tree-sitter
    build in the loop. `persist=False` runs the whole pipeline without writing a
    version or a ledger row, which is what the cross-model comparison needs: it
    must not pollute the history it is measuring.
    """
    started = time.perf_counter()
    strategy = "always" if force else (gate_strategy or DEFAULT_GATE_STRATEGY)

    source_dir = resolve_within(project_dir, "source")
    store = GraphVersionStore(project_dir)
    ledger = RunLedger(project_dir)

    # 1. Deterministic extraction -------------------------------------------
    uml = load_uml(project_dir)
    architecture = (parse_source or default_parse_source)(source_dir)
    implementation_graph = build_implementation_graph(architecture)
    design_graph = build_design_graph(uml.model)

    # 2. Deterministic comparison -------------------------------------------
    code_model = architecture_to_design_model(architecture)
    difference = (
        ComparisonEngine(
            uml.model or IntermediateDesignModel(),
            code_model,
            architecture=architecture,
        )
        .compare()
        .model_dump()
    )
    layer_violations = evaluate_layer_rules(architecture)

    # 3. Gate ----------------------------------------------------------------
    previous = store.latest()
    previous_graph = store.latest_gate_graph() if previous else None
    uml_changed = bool(previous and previous.get("uml_hash") != uml.hash)

    decision = decide_gate(
        strategy=strategy,
        previous_graph=previous_graph,
        current_graph=implementation_graph,
        previous_text_hash=previous.get("text_hash") if previous else None,
        current_text_hash=architecture["project_text_sha256"],
        previous_structure_hash=previous.get("structure_hash") if previous else None,
        current_structure_hash=architecture["project_structure_sha256"],
        impact_radius=impact_radius,
        uml_changed=uml_changed,
    )

    rule_findings = {
        "similarity_score": difference["similarity_score"],
        "missing_classes": difference["missing_classes"][:50],
        "extra_classes": difference["extra_classes"][:50],
        "missing_relations": difference["missing_relations"][:50],
        "unimplemented_associations": difference["unimplemented_associations"][:50],
        "element_differences": difference["element_differences"][:50],
    }

    # 4. Model call, or reuse -------------------------------------------------
    reused_from: Optional[int] = None
    renames: Dict[str, str] = {}

    if decision.should_invoke_llm:
        scope = None
        if previous is not None and decision.impact_nodes:
            scope = {
                "impact": decision.impact_nodes[:400],
                "summary": decision.delta.summary(),
                "architecture": scope_architecture(architecture, decision.impact_nodes),
            }
        llm_result = ai_service.evaluate_conformance(
            uml.model.model_dump() if uml.model else {},
            architecture,
            scope=scope,
            rule_findings=rule_findings,
            model_spec=model_spec,
        )
    else:
        cached = previous.get("analysis", {}) if previous else {}
        llm_result = ai_service.LlmResult(
            payload={
                "similarity_score": cached.get("similarity_score", difference["similarity_score"]),
                "gaps": cached.get("gaps", []),
                "recommendations": cached.get("recommendations", []),
                "unit_tests": cached.get("unit_tests", []),
                "semantic_graph": {"nodes": [], "edges": []},
            },
            model=(previous or {}).get("llm", {}).get("model", "cache"),
            invoked=False,
            notes=[f"Reused analysis from version {previous['version']}."] if previous else [],
        )
        reused_from = previous["version"] if previous else None

        if decision.isomorphic:
            # A rename does not change the architecture, but it does change the
            # identifiers the cached findings refer to. Relabel rather than
            # re-derive.
            renames = find_renames(previous_graph, implementation_graph)
            if renames:
                llm_result.notes.append(
                    f"Relabelled {len(renames)} renamed component(s) in the cached analysis."
                )

    # 5. Assemble the graph ---------------------------------------------------
    annotated = annotate_conformance(implementation_graph, design_graph, difference)
    merged, graph_validation = merge_semantic_graph(
        annotated, llm_result.payload.get("semantic_graph", {})
    )

    similarity_source = "llm" if decision.should_invoke_llm else "cache"
    analysis = {
        "similarity_score": llm_result.payload.get("similarity_score", 0),
        "similarity_score_rule_based": difference["similarity_score"],
        "similarity_score_source": similarity_source,
        "gaps": llm_result.payload.get("gaps", []),
        "recommendations": llm_result.payload.get("recommendations", []),
        "unit_tests": llm_result.payload.get("unit_tests", []),
        "rule_violations": layer_violations,
        "difference": difference,
        "graph_validation": graph_validation,
    }

    # 6. Persist and record ---------------------------------------------------
    if persist:
        version_record = store.save(
            merged,
            gate_graph=implementation_graph,
            structure_hash=architecture["project_structure_sha256"],
            text_hash=architecture["project_text_sha256"],
            uml_hash=uml.hash,
            analysis=analysis,
            gate=decision.to_dict(),
            llm=llm_result.usage(),
            reused_from=reused_from,
        )
    else:
        version_record = {"version": (previous or {}).get("version", 0)}

    elapsed_ms = (time.perf_counter() - started) * 1000
    call_resolution = implementation_graph.graph.get("call_resolution", {})
    reflexion = reflexion_counts(difference)
    fingerprint = findings_fingerprint(difference, layer_violations)
    analysis["reflexion"] = reflexion
    analysis["findings_hash"] = fingerprint

    if persist:
        ledger.record(
            {
                "version": version_record["version"],
                "gate_strategy": decision.strategy,
                # Two distinct facts: whether the gate permitted a re-analysis,
                # and whether a model was actually reached. They differ in
                # offline mode and whenever an API call degrades to the
                # deterministic fallback.
                "gate_allowed_llm": decision.should_invoke_llm,
                "llm_invoked": llm_result.invoked,
                "decision": decision.to_dict()["decision"],
                "reason": decision.reason,
                "files_scanned": len(architecture.get("files", [])),
                "changed_nodes": len(decision.delta.changed_nodes),
                "added_nodes": len(decision.delta.added_nodes),
                "removed_nodes": len(decision.delta.removed_nodes),
                "impact_nodes": len(decision.impact_nodes),
                "prompt_tokens": llm_result.prompt_tokens,
                "completion_tokens": llm_result.completion_tokens,
                "latency_ms": round(elapsed_ms, 1),
                "llm_latency_ms": round(llm_result.latency_ms, 1),
                "model": llm_result.model,
                "provider": llm_result.provider,
                "degraded": llm_result.degraded,
                # Reproducibility settings, recorded per run rather than read
                # from the environment at report time -- the configuration can
                # change between a run and the day someone writes it up, and the
                # paper has to state what was actually used. Required by the
                # reporting guidelines for empirical studies involving LLMs.
                "llm_mode": config.LLM_MODE,
                "temperature": config.LLM_TEMPERATURE,
                "seed": config.LLM_SEED,
                "association_scoring": config.ASSOCIATION_SCORING,
                "impact_radius": config.IMPACT_RADIUS,
                "max_graph_versions": config.MAX_GRAPH_VERSIONS,
                "similarity_score": analysis["similarity_score"],
                "grounded_node_ratio": graph_validation.get("grounded_node_ratio"),
                "call_resolution_rate": call_resolution.get("resolution_rate"),
                "ambiguous_call_sites": call_resolution.get("ambiguous", 0),
                # Reflexion-model counts and a fingerprint of the deterministic
                # findings, so the statistics page can label a run as a
                # conformance change without needing a replay oracle.
                "convergences": reflexion["convergences"],
                "divergences": reflexion["divergences"],
                "absences": reflexion["absences"],
                "findings_hash": fingerprint,
            }
        )

    return {
        "status": "analysis_complete",
        "version": version_record["version"],
        "gate": decision.to_dict(),
        "llm": llm_result.usage(),
        "reused_from_version": reused_from,
        "renamed_components": renames,
        "similarity_score": analysis["similarity_score"],
        "similarity_score_rule_based": analysis["similarity_score_rule_based"],
        "similarity_score_source": similarity_source,
        "ai_gaps": analysis["gaps"],
        "recommendations": analysis["recommendations"],
        "unit_tests": analysis["unit_tests"],
        "rule_violations": layer_violations,
        "difference": difference,
        "graph_validation": graph_validation,
        "graph_data": graph_to_payload(merged),
        "networkx_nodes": merged.number_of_nodes(),
        "networkx_edges": merged.number_of_edges(),
        "uml": {
            "filename": uml.filename,
            "error": uml.error,
            "warnings": uml.warnings,
            "element_count": len(uml.model.elements) if uml.model else 0,
            "relation_count": len(uml.model.relations) if uml.model else 0,
        },
        "call_resolution": call_resolution,
        "reflexion": reflexion,
        "findings_hash": fingerprint,
        "source": {
            "file_count": len(architecture.get("files", [])),
            "parse_errors": architecture.get("parse_errors", []),
            "typescript_grammar": architecture.get("typescript_grammar", True),
            "files_without_types": architecture.get("files_without_types", []),
        },
        "elapsed_ms": round(elapsed_ms, 1),
    }
