"""StarUML (.mdj) reader.

Two passes: index every element by its `_id` first, then resolve classes and
relationships. The single-pass version could not resolve associations or
generalizations at all, because those reference their endpoints by id and the
target is frequently defined later in the file.

Parse failures now raise `UmlParseError` instead of being swallowed, so the API
can tell the user their diagram did not load rather than silently scoring the
project against an empty design.
"""
import json
import os
from typing import Any, Dict, Optional

from models.design_model import (
    DesignElement,
    DesignRelation,
    ElementAttribute,
    ElementMethod,
    IntermediateDesignModel,
)

CLASSIFIER_TYPES = {"UMLClass", "UMLInterface"}
RELATION_TYPES = {
    "UMLGeneralization": "generalization",
    "UMLInterfaceRealization": "realization",
    "UMLAssociation": "association",
    "UMLDependency": "dependency",
}


class UmlParseError(Exception):
    """The .mdj file could not be read as a StarUML model."""


class StarUMLParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.model = IntermediateDesignModel()
        self._by_id: Dict[str, Dict[str, Any]] = {}

    def parse(self) -> IntermediateDesignModel:
        if not os.path.exists(self.file_path):
            raise UmlParseError(f"UML file not found: {os.path.basename(self.file_path)}")

        try:
            with open(self.file_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise UmlParseError(f"Not valid StarUML JSON: {exc.msg} (line {exc.lineno})") from exc
        except OSError as exc:
            raise UmlParseError(f"Could not read UML file: {exc}") from exc

        self._index(data)
        self._extract(data)

        if not self.model.elements:
            self.model.parse_warnings.append(
                "No UMLClass or UMLInterface elements were found in this model."
            )
        return self.model

    # -- pass 1 ---------------------------------------------------------------

    def _index(self, node: Any):
        if isinstance(node, dict):
            node_id = node.get("_id")
            if isinstance(node_id, str):
                self._by_id[node_id] = node
            for value in node.values():
                self._index(value)
        elif isinstance(node, list):
            for item in node:
                self._index(item)

    def _resolve_name(self, ref: Any) -> Optional[str]:
        """Turn a `{"$ref": "..."}` pointer into the referenced element's name."""
        if isinstance(ref, dict):
            target_id = ref.get("$ref")
            if isinstance(target_id, str):
                target = self._by_id.get(target_id)
                if isinstance(target, dict):
                    return target.get("name") or None
            if ref.get("name"):
                return ref["name"]
        elif isinstance(ref, str):
            target = self._by_id.get(ref)
            if isinstance(target, dict):
                return target.get("name") or None
        return None

    # -- pass 2 ---------------------------------------------------------------

    def _extract(self, node: Any):
        if isinstance(node, dict):
            node_type = node.get("_type")
            if node_type in CLASSIFIER_TYPES:
                self._extract_element(node, node_type)
            elif node_type in RELATION_TYPES:
                self._extract_relation(node, RELATION_TYPES[node_type])
            for value in node.values():
                self._extract(value)
        elif isinstance(node, list):
            for item in node:
                self._extract(item)

    def _type_name(self, raw: Any) -> str:
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        resolved = self._resolve_name(raw)
        return resolved or "Object"

    def _extract_element(self, node: Dict[str, Any], node_type: str):
        name = node.get("name")
        if not name:
            self.model.parse_warnings.append(
                f"Skipped an unnamed {node_type} element (id {node.get('_id', '?')})."
            )
            return

        if any(existing.name == name for existing in self.model.elements):
            return  # the same element can be reached through several views

        element = DesignElement(
            name=name,
            element_type="class" if node_type == "UMLClass" else "interface",
        )

        for attr_node in node.get("attributes", []) or []:
            if not isinstance(attr_node, dict) or attr_node.get("_type") != "UMLAttribute":
                continue
            element.attributes.append(
                ElementAttribute(
                    name=attr_node.get("name") or "unnamed",
                    type=self._type_name(attr_node.get("type")),
                    visibility=attr_node.get("visibility") or "public",
                )
            )

        for op_node in node.get("operations", []) or []:
            if not isinstance(op_node, dict) or op_node.get("_type") != "UMLOperation":
                continue
            method = ElementMethod(
                name=op_node.get("name") or "unnamed",
                visibility=op_node.get("visibility") or "public",
            )
            for param in op_node.get("parameters", []) or []:
                if not isinstance(param, dict):
                    continue
                if param.get("direction") == "return":
                    method.return_type = self._type_name(param.get("type"))
                else:
                    method.parameters.append(param.get("name") or "arg")
            element.methods.append(method)

        self.model.elements.append(element)

    def _extract_relation(self, node: Dict[str, Any], relation: str):
        source = self._resolve_name(node.get("source"))
        target = self._resolve_name(node.get("target"))

        if source is None or target is None:
            end1 = node.get("end1") or {}
            end2 = node.get("end2") or {}
            source = source or self._resolve_name(end1.get("reference") if isinstance(end1, dict) else None)
            target = target or self._resolve_name(end2.get("reference") if isinstance(end2, dict) else None)

        if not source or not target:
            return

        self.model.relations.append(
            DesignRelation(source=source, target=target, relation=relation)
        )

    # -- convenience ----------------------------------------------------------

    @staticmethod
    def apply_relations(model: IntermediateDesignModel) -> IntermediateDesignModel:
        """Fold generalization/realization edges back onto the elements so both
        representations agree."""
        by_name = {element.name: element for element in model.elements}
        for relation in model.relations:
            element = by_name.get(relation.source)
            if element is None:
                continue
            if relation.relation == "generalization" and not element.extends:
                element.extends = relation.target
            elif relation.relation == "realization" and relation.target not in element.implements:
                element.implements.append(relation.target)
        return model
