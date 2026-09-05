"""Graph-level change detection -- the gate that decides whether the LLM runs.

This module is where `networkx.algorithms.isomorphism` finally earns its import.
The pipeline supports four gate strategies so they can be compared empirically
rather than asserted:

    always      re-analyse every time (reproduces the original behaviour)
    content     re-analyse when raw file bytes changed (naive hashing baseline)
    structural  re-analyse when the AST-derived fingerprint changed
    isomorphism structural, plus: skip when the new graph is isomorphic to the
                old one under a type-preserving, name-ignoring matching, i.e.
                the change was a pure rename or reordering

The interesting research question is the trade-off between them: `content`
fires on comment edits (wasted spend), `structural` does not, and `isomorphism`
additionally absorbs renames -- at the risk of skipping a rename that genuinely
breaks conformance against a UML diagram that names the class explicitly. The
gate records enough detail for that risk to be measured instead of guessed.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from networkx.algorithms import isomorphism

# VF2 is exponential in the worst case; refuse to attempt it on large graphs
# rather than hanging a request.
ISOMORPHISM_NODE_LIMIT = 400
EDIT_DISTANCE_NODE_LIMIT = 60
EDIT_DISTANCE_TIMEOUT_SECONDS = 5.0

_TRACKED_ATTRS = (
    "kind",
    "name",
    "fingerprint",
    "fields",
    "method_names",
    "params",
    "param_types",
    "returns",
    "owner",
)


@dataclass
class GraphDelta:
    added_nodes: List[str] = field(default_factory=list)
    removed_nodes: List[str] = field(default_factory=list)
    changed_nodes: List[str] = field(default_factory=list)
    added_edges: List[Tuple[str, str]] = field(default_factory=list)
    removed_edges: List[Tuple[str, str]] = field(default_factory=list)
    unchanged_nodes: int = 0

    @property
    def touched_nodes(self) -> Set[str]:
        return set(self.added_nodes) | set(self.removed_nodes) | set(self.changed_nodes)

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_nodes
            or self.removed_nodes
            or self.changed_nodes
            or self.added_edges
            or self.removed_edges
        )

    def summary(self) -> Dict[str, int]:
        return {
            "added_nodes": len(self.added_nodes),
            "removed_nodes": len(self.removed_nodes),
            "changed_nodes": len(self.changed_nodes),
            "added_edges": len(self.added_edges),
            "removed_edges": len(self.removed_edges),
            "unchanged_nodes": self.unchanged_nodes,
        }


@dataclass
class GateDecision:
    strategy: str
    should_invoke_llm: bool
    reason: str
    delta: GraphDelta
    impact_nodes: List[str] = field(default_factory=list)
    isomorphic: Optional[bool] = None
    edit_distance: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "should_invoke_llm": self.should_invoke_llm,
            "decision": "re-analysed" if self.should_invoke_llm else "reused-cached-version",
            "reason": self.reason,
            "delta": self.delta.summary(),
            "impact_node_count": len(self.impact_nodes),
            "isomorphic": self.isomorphic,
            "edit_distance": self.edit_distance,
        }


def _node_signature(graph: nx.DiGraph, node: str) -> Tuple:
    data = graph.nodes[node]
    return tuple(_freeze(data.get(attr)) for attr in _TRACKED_ATTRS)


def _freeze(value: Any):
    # Recurses: node attributes now hold lists of dicts (typed fields), and a
    # shallow freeze would compare those by identity and report every node as
    # changed on every run.
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    return value


def diff_graphs(old: nx.DiGraph, new: nx.DiGraph) -> GraphDelta:
    old_nodes, new_nodes = set(old.nodes), set(new.nodes)
    delta = GraphDelta(
        added_nodes=sorted(new_nodes - old_nodes),
        removed_nodes=sorted(old_nodes - new_nodes),
    )

    unchanged = 0
    for node in sorted(old_nodes & new_nodes):
        if _node_signature(old, node) != _node_signature(new, node):
            delta.changed_nodes.append(node)
        else:
            unchanged += 1
    delta.unchanged_nodes = unchanged

    old_edges = {(u, v) for u, v in old.edges}
    new_edges = {(u, v) for u, v in new.edges}
    delta.added_edges = sorted(new_edges - old_edges)
    delta.removed_edges = sorted(old_edges - new_edges)
    return delta


def _kind_match(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return a.get("kind") == b.get("kind")


def _relation_match(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return a.get("relation") == b.get("relation")


def is_label_isomorphic(old: nx.DiGraph, new: nx.DiGraph) -> Optional[bool]:
    """True when the two graphs have the same shape ignoring identifiers.

    Returns None when the check was skipped because the graphs are too large to
    test safely -- the caller must not read None as False.
    """
    if old.number_of_nodes() != new.number_of_nodes():
        return False
    if old.number_of_edges() != new.number_of_edges():
        return False
    if old.number_of_nodes() == 0:
        return True
    if old.number_of_nodes() > ISOMORPHISM_NODE_LIMIT:
        return None

    # Cheap necessary conditions first: if the degree or kind multisets differ,
    # no isomorphism exists and VF2 need never run.
    if sorted(d for _, d in old.degree()) != sorted(d for _, d in new.degree()):
        return False
    old_kinds = sorted(data.get("kind") for _, data in old.nodes(data=True))
    new_kinds = sorted(data.get("kind") for _, data in new.nodes(data=True))
    if old_kinds != new_kinds:
        return False

    matcher = isomorphism.DiGraphMatcher(
        old, new, node_match=_kind_match, edge_match=_relation_match
    )
    return bool(matcher.is_isomorphic())


def find_renames(old: nx.DiGraph, new: nx.DiGraph) -> Dict[str, str]:
    """When two graphs are isomorphic, recover the old->new node mapping.

    This is what makes a rename cheap to absorb: the cached analysis can be
    relabelled instead of regenerated.
    """
    if old.number_of_nodes() == 0 or old.number_of_nodes() > ISOMORPHISM_NODE_LIMIT:
        return {}
    matcher = isomorphism.DiGraphMatcher(
        old, new, node_match=_kind_match, edge_match=_relation_match
    )
    if not matcher.is_isomorphic():
        return {}
    return {source: target for source, target in matcher.mapping.items() if source != target}


def approximate_edit_distance(old: nx.DiGraph, new: nx.DiGraph) -> float:
    """Exact GED for small graphs, a cheap set-based surrogate otherwise."""
    if old.number_of_nodes() <= EDIT_DISTANCE_NODE_LIMIT and new.number_of_nodes() <= EDIT_DISTANCE_NODE_LIMIT:
        try:
            distance = nx.graph_edit_distance(
                old,
                new,
                node_match=_kind_match,
                edge_match=_relation_match,
                timeout=EDIT_DISTANCE_TIMEOUT_SECONDS,
            )
            if distance is not None:
                return float(distance)
        except Exception:
            pass

    delta = diff_graphs(old, new)
    return float(
        len(delta.added_nodes)
        + len(delta.removed_nodes)
        + len(delta.changed_nodes)
        + len(delta.added_edges)
        + len(delta.removed_edges)
    )


def impact_set(graph: nx.DiGraph, seeds: Set[str], radius: int = 1) -> List[str]:
    """Seed nodes plus everything within `radius` hops, in either direction.

    Conformance is not a local property: changing a method can break the
    contract of whatever calls it, so the LLM needs the neighbourhood, not just
    the changed node.
    """
    present = {node for node in seeds if node in graph}
    if not present:
        return []
    if radius <= 0:
        return sorted(present)

    undirected = graph.to_undirected(as_view=True)
    reached = set(present)
    frontier = set(present)
    for _ in range(radius):
        next_frontier: Set[str] = set()
        for node in frontier:
            next_frontier.update(undirected.neighbors(node))
        next_frontier -= reached
        if not next_frontier:
            break
        reached |= next_frontier
        frontier = next_frontier
    return sorted(reached)


def decide_gate(
    strategy: str,
    previous_graph: Optional[nx.DiGraph],
    current_graph: nx.DiGraph,
    previous_text_hash: Optional[str],
    current_text_hash: str,
    previous_structure_hash: Optional[str],
    current_structure_hash: str,
    impact_radius: int = 1,
    uml_changed: bool = False,
) -> GateDecision:
    """Decide whether this analysis needs to spend an LLM call."""
    strategy = (strategy or "structural").lower()

    if previous_graph is None:
        empty = GraphDelta(added_nodes=sorted(current_graph.nodes))
        return GateDecision(
            strategy=strategy,
            should_invoke_llm=True,
            reason="No previous version exists; this is a cold start.",
            delta=empty,
            impact_nodes=sorted(current_graph.nodes),
        )

    delta = diff_graphs(previous_graph, current_graph)

    if uml_changed:
        return GateDecision(
            strategy=strategy,
            should_invoke_llm=True,
            reason="The UML design model changed, so conformance must be re-evaluated.",
            delta=delta,
            impact_nodes=sorted(current_graph.nodes),
        )

    if strategy == "always":
        return GateDecision(
            strategy=strategy,
            should_invoke_llm=True,
            reason="Gate disabled: every run re-invokes the model (baseline mode).",
            delta=delta,
            impact_nodes=sorted(current_graph.nodes),
        )

    if strategy == "content":
        changed = previous_text_hash != current_text_hash
        return GateDecision(
            strategy=strategy,
            should_invoke_llm=changed,
            reason=(
                "Raw file bytes changed."
                if changed
                else "Raw file bytes are identical to the previous version."
            ),
            delta=delta,
            impact_nodes=impact_set(current_graph, delta.touched_nodes, impact_radius) if changed else [],
        )

    structure_changed = previous_structure_hash != current_structure_hash or not delta.is_empty

    if strategy == "isomorphism":
        isomorphic = None
        if structure_changed:
            isomorphic = is_label_isomorphic(previous_graph, current_graph)
        if structure_changed and isomorphic is True:
            return GateDecision(
                strategy=strategy,
                should_invoke_llm=False,
                reason=(
                    "The implementation graph is isomorphic to the previous version under a "
                    "type-preserving matching: the change is a rename or reordering, "
                    "so the cached analysis was relabelled instead of regenerated."
                ),
                delta=delta,
                impact_nodes=[],
                isomorphic=True,
            )
        return GateDecision(
            strategy=strategy,
            should_invoke_llm=structure_changed,
            reason=(
                "Structural fingerprint changed and the graph is not isomorphic to the previous version."
                if structure_changed
                else "Structural fingerprint is unchanged."
            ),
            delta=delta,
            impact_nodes=impact_set(current_graph, delta.touched_nodes, impact_radius)
            if structure_changed
            else [],
            isomorphic=isomorphic,
        )

    # default: structural
    return GateDecision(
        strategy="structural",
        should_invoke_llm=structure_changed,
        reason=(
            "AST-derived structural fingerprint changed."
            if structure_changed
            else "AST-derived structural fingerprint is unchanged; formatting-only edits are ignored."
        ),
        delta=delta,
        impact_nodes=impact_set(current_graph, delta.touched_nodes, impact_radius)
        if structure_changed
        else [],
    )
