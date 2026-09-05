"""Versioned persistence for semantic graphs.

The previous implementation kept exactly one `semantic_graph.json` and
overwrote it on every analysis, so there was no history to diff against and no
way to roll back. This store keeps a bounded ring of the most recent
`MAX_GRAPH_VERSIONS` snapshots (default 3), each with the metadata needed to
decide -- and later to audit -- whether an LLM call was necessary.
"""
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import networkx as nx

from config import MAX_GRAPH_VERSIONS
from core.paths import resolve_within

INDEX_FILENAME = "index.json"


# --- NetworkX serialisation compatibility ------------------------------------
# The `edges=` keyword and the default link key changed across NetworkX 3.x.
# Pinning it explicitly keeps files written by one version readable by another.

def _node_link_data(graph: nx.DiGraph) -> Dict[str, Any]:
    try:
        return nx.node_link_data(graph, edges="links")
    except TypeError:
        return nx.node_link_data(graph)


def _node_link_graph(payload: Dict[str, Any]) -> nx.DiGraph:
    try:
        return nx.node_link_graph(payload, directed=True, multigraph=False, edges="links")
    except TypeError:
        return nx.node_link_graph(payload, directed=True, multigraph=False)


def _atomic_write_json(path: str, payload: Any):
    """Write via a temp file + replace so a crash mid-write cannot corrupt the
    store and leave the project unanalysable."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", delete=False, dir=directory, encoding="utf-8", suffix=".tmp"
    )
    try:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


class GraphVersionStore:
    def __init__(self, project_dir: str, max_versions: int = MAX_GRAPH_VERSIONS):
        self.root = resolve_within(project_dir, "reports", "versions")
        self.max_versions = max(1, max_versions)
        os.makedirs(self.root, exist_ok=True)
        self.index_path = os.path.join(self.root, INDEX_FILENAME)

    # -- index ----------------------------------------------------------------

    def _read_index(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.index_path):
            return []
        try:
            with open(self.index_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data.get("versions", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_index(self, versions: List[Dict[str, Any]]):
        _atomic_write_json(
            self.index_path,
            {"max_versions": self.max_versions, "versions": versions},
        )

    # -- reads ----------------------------------------------------------------

    def list_versions(self) -> List[Dict[str, Any]]:
        return sorted(self._read_index(), key=lambda v: v["version"], reverse=True)

    def latest(self) -> Optional[Dict[str, Any]]:
        versions = self.list_versions()
        return versions[0] if versions else None

    def get(self, version: int) -> Optional[Dict[str, Any]]:
        for record in self._read_index():
            if record["version"] == version:
                return record
        return None

    def _load(self, filename: str) -> Optional[nx.DiGraph]:
        path = os.path.join(self.root, filename)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return _node_link_graph(json.load(handle))
        except (json.JSONDecodeError, OSError, KeyError, nx.NetworkXError):
            return None

    def load_graph(self, version: int) -> Optional[nx.DiGraph]:
        """The presentation graph: implementation + design + model-inferred nodes."""
        return self._load(f"v{version}.graph.json")

    def load_gate_graph(self, version: int) -> Optional[nx.DiGraph]:
        """The graph the gate compares against.

        This must be the purely parser-derived implementation graph. Comparing
        against the presentation graph instead would mean every run diffed
        parsed structure against structure that also contained UML and
        model-inferred nodes, so nothing would ever compare equal and the cache
        could never hit.
        """
        return self._load(f"v{version}.gate.json") or self.load_graph(version)

    def latest_graph(self) -> Optional[nx.DiGraph]:
        latest = self.latest()
        return self.load_graph(latest["version"]) if latest else None

    def latest_gate_graph(self) -> Optional[nx.DiGraph]:
        latest = self.latest()
        return self.load_gate_graph(latest["version"]) if latest else None

    # -- writes ---------------------------------------------------------------

    def save(
        self,
        graph: nx.DiGraph,
        *,
        gate_graph: Optional[nx.DiGraph] = None,
        structure_hash: str,
        text_hash: str,
        uml_hash: str,
        analysis: Dict[str, Any],
        gate: Dict[str, Any],
        llm: Dict[str, Any],
        reused_from: Optional[int] = None,
    ) -> Dict[str, Any]:
        versions = self._read_index()
        next_version = (max((v["version"] for v in versions), default=0)) + 1
        parent = max((v["version"] for v in versions), default=None)

        record = {
            "version": next_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parent_version": parent,
            "reused_from": reused_from,
            "structure_hash": structure_hash,
            "text_hash": text_hash,
            "uml_hash": uml_hash,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "similarity_score": analysis.get("similarity_score"),
            "gap_count": len(analysis.get("gaps", []) or []),
            "gate": gate,
            "llm": llm,
            "analysis": analysis,
        }

        _atomic_write_json(
            os.path.join(self.root, f"v{next_version}.graph.json"), _node_link_data(graph)
        )
        _atomic_write_json(
            os.path.join(self.root, f"v{next_version}.gate.json"),
            _node_link_data(gate_graph if gate_graph is not None else graph),
        )

        versions.append(record)
        versions.sort(key=lambda v: v["version"])
        retained = versions[-self.max_versions:]
        for dropped in versions[:-self.max_versions]:
            self._remove_graph_file(dropped["version"])
        self._write_index(retained)
        return record

    def _remove_graph_file(self, version: int):
        for suffix in ("graph", "gate"):
            path = os.path.join(self.root, f"v{version}.{suffix}.json")
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def clear(self):
        shutil.rmtree(self.root, ignore_errors=True)
        os.makedirs(self.root, exist_ok=True)

    # -- comparison -----------------------------------------------------------

    def diff(self, version_a: int, version_b: int) -> Dict[str, Any]:
        from core.graph_diff import diff_graphs  # local import avoids a cycle

        graph_a = self.load_graph(version_a)
        graph_b = self.load_graph(version_b)
        if graph_a is None or graph_b is None:
            raise FileNotFoundError("One or both versions are no longer retained.")

        delta = diff_graphs(graph_a, graph_b)
        record_a = self.get(version_a) or {}
        record_b = self.get(version_b) or {}
        return {
            "from_version": version_a,
            "to_version": version_b,
            "summary": delta.summary(),
            "added_nodes": delta.added_nodes[:200],
            "removed_nodes": delta.removed_nodes[:200],
            "changed_nodes": delta.changed_nodes[:200],
            "similarity_score_from": record_a.get("similarity_score"),
            "similarity_score_to": record_b.get("similarity_score"),
        }
