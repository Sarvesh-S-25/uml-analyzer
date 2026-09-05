"""Builds NetworkX graphs from the deterministic parser output.

Two graphs are produced from facts alone -- no LLM involved:

* the *implementation graph*, from the parsed source tree
* the *design graph*, from the StarUML model

Call edges are resolved through a project-wide symbol table rather than by
matching unqualified names. The previous approach linked a call to *every*
definition sharing its name (capped at four), which over-approximated the call
graph: safe, because it only ever caused unnecessary re-analysis, but it
inflated the impact set and therefore the cost the system is trying to reduce.
Resolution now attributes each call site to at most one target and records how
it was resolved, so the residual imprecision is a reported number rather than an
unknown.
"""
import os
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from models.design_model import IntermediateDesignModel

MODULE = "module"
CLASS = "class"
INTERFACE = "interface"
ENUM = "enum"
FUNCTION = "function"
METHOD = "method"

RESOLUTION_BUCKETS = (
    "self",           # this.method() within the same class or its bases
    "field",          # through a typed field: self.repo.save()
    "local",          # through a local variable of known type
    "static",         # through a class name: OrderRepository.save()
    "import",         # through an imported symbol
    "same_file",      # a definition in the same file
    "unique_global",  # exactly one definition project-wide with that name
    "instantiation",  # new Foo() / Foo()
    "ambiguous",      # several candidates, none preferred -- left unresolved
    "external",       # no candidate: standard library or third-party
)


def module_id(path: str) -> str:
    return f"module::{path}"


def class_id(path: str, name: str) -> str:
    return f"class::{path}::{name}"


def function_id(path: str, name: str) -> str:
    return f"function::{path}::{name}"


def method_id(path: str, class_name: str, name: str) -> str:
    return f"method::{path}::{class_name}.{name}"


def design_id(name: str) -> str:
    return f"design::{name}"


# --- symbol table ------------------------------------------------------------


def _module_keys(file_path: str) -> List[str]:
    """Every plausible import string that could refer to this file."""
    without_extension = os.path.splitext(file_path)[0]
    slashed = without_extension.replace("\\", "/")
    dotted = slashed.replace("/", ".")
    leaf = slashed.split("/")[-1]
    keys = {slashed, dotted, leaf, file_path}
    # `app/repository/__init__.py` is imported as `app.repository`
    if leaf == "__init__":
        package = "/".join(slashed.split("/")[:-1])
        if package:
            keys.add(package)
            keys.add(package.replace("/", "."))
    # `src/lib/api.ts` may be imported as `lib/api` or `./api`
    parts = slashed.split("/")
    for index in range(1, len(parts)):
        keys.add("/".join(parts[index:]))
        keys.add(".".join(parts[index:]))
    return [key for key in keys if key]


def _normalise_module(module: str) -> str:
    cleaned = module.strip().strip("'\"")
    cleaned = cleaned.replace("\\", "/")
    while cleaned.startswith(("./", "../")):
        cleaned = cleaned[3:] if cleaned.startswith("../") else cleaned[2:]
    cleaned = cleaned.lstrip("./")
    for extension in (".js", ".jsx", ".ts", ".tsx", ".py", ".java", ".mjs"):
        if cleaned.endswith(extension):
            cleaned = cleaned[: -len(extension)]
    return cleaned


class SymbolTable:
    """Project-wide index used to attribute call sites to definitions."""

    def __init__(self, architecture: Dict[str, Any]):
        self.files: Dict[str, Dict[str, Any]] = {
            record["file_path"]: record for record in architecture.get("files", [])
        }
        self.module_index: Dict[str, List[str]] = {}
        self.class_nodes: Dict[Tuple[str, str], str] = {}
        self.class_by_name: Dict[str, List[str]] = {}
        self.class_bases: Dict[str, List[str]] = {}
        self.class_fields: Dict[str, Dict[str, Optional[str]]] = {}
        self.methods: Dict[str, Dict[str, str]] = {}
        self.functions_by_file: Dict[Tuple[str, str], str] = {}
        self.callable_by_name: Dict[str, List[str]] = {}

        for path, record in self.files.items():
            for key in _module_keys(path):
                self.module_index.setdefault(key, []).append(path)

            for klass in record.get("classes", []):
                node = class_id(path, klass["name"])
                self.class_nodes[(path, klass["name"])] = node
                self.class_by_name.setdefault(klass["name"], []).append(node)
                self.class_bases[node] = list(klass.get("bases", []))
                self.class_fields[node] = {
                    field["name"]: field.get("type") for field in klass.get("fields", [])
                }
                method_map: Dict[str, str] = {}
                for method in klass.get("methods", []):
                    identifier = method_id(path, klass["name"], method["name"])
                    method_map.setdefault(method["name"], identifier)
                    self.callable_by_name.setdefault(method["name"], []).append(identifier)
                self.methods[node] = method_map

            for function in record.get("functions", []):
                identifier = function_id(path, function["name"])
                self.functions_by_file.setdefault((path, function["name"]), identifier)
                self.callable_by_name.setdefault(function["name"], []).append(identifier)

    # -- lookups --------------------------------------------------------------

    def resolve_module(self, module: str) -> Optional[str]:
        candidates = self.module_index.get(_normalise_module(module))
        if candidates and len(candidates) == 1:
            return candidates[0]
        return None

    def resolve_class(self, type_name: Optional[str]) -> Optional[str]:
        if not type_name:
            return None
        candidates = self.class_by_name.get(type_name.split(".")[-1])
        if candidates and len(candidates) == 1:
            return candidates[0]
        return None

    def method_of(self, class_node: str, name: str, depth: int = 0) -> Optional[str]:
        """A class's own method, or an inherited one."""
        own = self.methods.get(class_node, {}).get(name)
        if own:
            return own
        if depth >= 4:
            return None
        for base in self.class_bases.get(class_node, []):
            base_node = self.resolve_class(base)
            if base_node and base_node != class_node:
                inherited = self.method_of(base_node, name, depth + 1)
                if inherited:
                    return inherited
        return None

    def import_target(self, file_path: str, symbol: str) -> Optional[Tuple[str, Optional[str]]]:
        """Resolve an imported symbol to (file, symbol) inside the project."""
        record = self.files.get(file_path)
        if not record:
            return None
        for binding in record.get("import_bindings", []):
            bound_name = binding.get("alias") or binding.get("symbol")
            if bound_name and bound_name == symbol:
                target = self.resolve_module(binding["module"])
                if target:
                    return target, binding.get("symbol")
            if binding.get("symbol") is None:
                # `import app.repository` binds the module itself
                module = binding["module"]
                if module.split(".")[-1].split("/")[-1] == symbol:
                    target = self.resolve_module(module)
                    if target:
                        return target, None
        return None


# --- implementation graph ----------------------------------------------------


def build_implementation_graph(architecture: Dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    table = SymbolTable(architecture)
    stats = {bucket: 0 for bucket in RESOLUTION_BUCKETS}
    stats["total_call_sites"] = 0

    for path, record in table.files.items():
        module_node = module_id(path)
        graph.add_node(
            module_node,
            kind=MODULE,
            name=path,
            language=record.get("language", "unknown"),
            grammar=record.get("grammar", "unknown"),
            loc=record.get("loc", 0),
            fingerprint=record.get("structure_sha256", ""),
            source_file=path,
        )

        for klass in record.get("classes", []):
            node = class_id(path, klass["name"])
            kind = {"interface": INTERFACE, "enum": ENUM}.get(klass.get("kind"), CLASS)
            graph.add_node(
                node,
                kind=kind,
                name=klass["name"],
                source_file=path,
                fields=[
                    {"name": field["name"], "type": field.get("type")}
                    for field in klass.get("fields", [])
                ],
                method_names=sorted(method["name"] for method in klass.get("methods", [])),
            )
            graph.add_edge(module_node, node, relation="contains")

            for method in klass.get("methods", []):
                identifier = method_id(path, klass["name"], method["name"])
                graph.add_node(
                    identifier,
                    kind=METHOD,
                    name=method["name"],
                    owner=klass["name"],
                    source_file=path,
                    params=method.get("params", 0),
                    param_types=list(method.get("param_types", [])),
                    returns=method.get("returns"),
                )
                graph.add_edge(node, identifier, relation="contains")

        for function in record.get("functions", []):
            identifier = function_id(path, function["name"])
            graph.add_node(
                identifier,
                kind=FUNCTION,
                name=function["name"],
                source_file=path,
                params=function.get("params", 0),
                param_types=list(function.get("param_types", [])),
                returns=function.get("returns"),
            )
            graph.add_edge(module_node, identifier, relation="contains")

    # Second pass: inheritance and resolved call edges.
    for path, record in table.files.items():
        for klass in record.get("classes", []):
            node = class_id(path, klass["name"])
            for base in klass.get("bases", []):
                target = table.resolve_class(base)
                if target and target != node:
                    relation = (
                        "implements"
                        if graph.nodes[target].get("kind") == INTERFACE
                        else "extends"
                    )
                    graph.add_edge(node, target, relation=relation)

            for method in klass.get("methods", []):
                _resolve_calls(
                    graph,
                    table,
                    stats,
                    source=method_id(path, klass["name"], method["name"]),
                    file_path=path,
                    class_node=node,
                    callable_record=method,
                )

        for function in record.get("functions", []):
            _resolve_calls(
                graph,
                table,
                stats,
                source=function_id(path, function["name"]),
                file_path=path,
                class_node=None,
                callable_record=function,
            )

    resolved = stats["total_call_sites"] - stats["ambiguous"] - stats["external"]
    stats["resolved"] = resolved
    stats["resolution_rate"] = (
        round(resolved / stats["total_call_sites"], 4) if stats["total_call_sites"] else None
    )
    graph.graph["call_resolution"] = stats
    return graph


def _resolve_calls(
    graph: nx.DiGraph,
    table: SymbolTable,
    stats: Dict[str, Any],
    *,
    source: str,
    file_path: str,
    class_node: Optional[str],
    callable_record: Dict[str, Any],
):
    local_types: Dict[str, str] = callable_record.get("local_types", {}) or {}
    seen: set = set()

    for ref in callable_record.get("call_refs", []):
        stats["total_call_sites"] += 1
        target, bucket = _resolve_one(table, file_path, class_node, local_types, ref)
        stats[bucket] = stats.get(bucket, 0) + 1

        if not target or target == source or target not in graph:
            continue
        relation = "instantiates" if bucket == "instantiation" else "calls"
        key = (target, relation)
        if key in seen:
            continue
        seen.add(key)
        graph.add_edge(source, target, relation=relation)


def _resolve_one(
    table: SymbolTable,
    file_path: str,
    class_node: Optional[str],
    local_types: Dict[str, str],
    ref: Dict[str, Any],
) -> Tuple[Optional[str], str]:
    name = ref["name"]
    receiver = ref.get("receiver")

    if ref.get("instantiation"):
        target = table.resolve_class(name)
        return (target, "instantiation") if target else (None, "external")

    if receiver:
        head, _, rest = receiver.partition(".")

        if head in ("self", "this"):
            if not rest and class_node:
                own = table.method_of(class_node, name)
                if own:
                    return own, "self"
            if rest and class_node:
                field_type = table.class_fields.get(class_node, {}).get(rest.split(".")[0])
                target_class = table.resolve_class(field_type)
                if target_class:
                    method = table.method_of(target_class, name)
                    if method:
                        return method, "field"
                    return None, "external"
            return None, "external"

        local_type = local_types.get(head)
        if local_type:
            target_class = table.resolve_class(local_type)
            if target_class:
                method = table.method_of(target_class, name)
                if method:
                    return method, "local"
                return None, "external"

        as_class = table.resolve_class(head)
        if as_class:
            method = table.method_of(as_class, name)
            if method:
                return method, "static"
            return None, "external"

        imported = table.import_target(file_path, head)
        if imported:
            target_file, _symbol = imported
            function_node = table.functions_by_file.get((target_file, name))
            if function_node:
                return function_node, "import"
            class_in_target = table.class_nodes.get((target_file, name))
            if class_in_target:
                return class_in_target, "import"
            return None, "external"

        return None, "external"

    # Bare call.
    if class_node:
        own = table.method_of(class_node, name)
        if own:
            return own, "self"

    same_file = table.functions_by_file.get((file_path, name))
    if same_file:
        return same_file, "same_file"

    class_same_file = table.class_nodes.get((file_path, name))
    if class_same_file:
        return class_same_file, "instantiation"

    imported = table.import_target(file_path, name)
    if imported:
        target_file, _symbol = imported
        function_node = table.functions_by_file.get((target_file, name))
        if function_node:
            return function_node, "import"
        class_in_target = table.class_nodes.get((target_file, name))
        if class_in_target:
            return class_in_target, "instantiation"

    candidates = table.callable_by_name.get(name, [])
    if len(candidates) == 1:
        return candidates[0], "unique_global"
    if len(candidates) > 1:
        # Several same-named definitions and nothing to choose between them.
        # Linking to all of them would re-inflate the impact set, so the call is
        # left unresolved and counted.
        return None, "ambiguous"

    class_candidates = table.class_by_name.get(name, [])
    if len(class_candidates) == 1:
        return class_candidates[0], "instantiation"

    return None, "external"


# --- design graph ------------------------------------------------------------


def build_design_graph(uml_model: Optional[IntermediateDesignModel]) -> nx.DiGraph:
    graph = nx.DiGraph()
    if uml_model is None:
        return graph

    for element in uml_model.elements:
        graph.add_node(
            design_id(element.name),
            kind=INTERFACE if element.element_type == "interface" else CLASS,
            name=element.name,
            origin="uml",
            fields=[{"name": a.name, "type": a.type} for a in element.attributes],
            method_names=sorted(method.name for method in element.methods),
        )

    for element in uml_model.elements:
        source = design_id(element.name)
        if element.extends:
            graph.add_edge(source, design_id(element.extends), relation="extends")
        for interface in element.implements:
            graph.add_edge(source, design_id(interface), relation="implements")

    for relation in uml_model.relations:
        graph.add_edge(
            design_id(relation.source), design_id(relation.target), relation=relation.relation
        )

    for node in list(graph.nodes):
        if "kind" not in graph.nodes[node]:
            graph.nodes[node].update(
                {"kind": CLASS, "name": node.split("::", 1)[-1], "origin": "uml-implied"}
            )

    return graph


def graph_to_payload(graph: nx.DiGraph) -> Dict[str, Any]:
    """Frontend-friendly serialisation (this is the `graph_data` the UI needs)."""
    return {
        "nodes": [
            {
                "id": node,
                "label": data.get("name", node),
                "kind": data.get("kind", "unknown"),
                "group": data.get("kind", "unknown"),
                "status": data.get("status", "unknown"),
                "source_file": data.get("source_file"),
            }
            for node, data in graph.nodes(data=True)
        ],
        "links": [
            {"source": u, "target": v, "relation": data.get("relation", "related")}
            for u, v, data in graph.edges(data=True)
        ],
    }
