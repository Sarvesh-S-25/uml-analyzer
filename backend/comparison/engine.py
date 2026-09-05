"""Deterministic rule-based conformance checking.

This is the control condition for the whole study: it uses no LLM, is fully
reproducible, and produces the same shape of output as the AI path so the two
can be compared directly on the same inputs. It also does real work in
production -- anything provably checkable is checked by parsing rather than by
prompting.

Relationship checking is graded rather than binary. Generalization and
realization are recoverable exactly from an AST, so they are scored. An
association is not: a field of the right type is strong evidence, a same-named
field or a call into the target is weak evidence, and neither is proof that the
modelled association is the one implemented. Associations are therefore reported
with their evidence level and, by default, excluded from the headline score --
a decision recorded in the output itself (`association_scoring`) so a reader is
never left guessing which convention produced a number.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from config import ASSOCIATION_SCORING
from models.design_model import (
    DifferenceModel,
    ElementDifference,
    IntermediateDesignModel,
    RelationFinding,
)

EXACT_RELATIONS = ("generalization", "realization")
EVIDENCE_RELATIONS = ("association", "dependency")

STRONG = "strong"
WEAK = "weak"
NONE = "none"


@dataclass
class LayerRule:
    """A layering constraint: `source_markers` must not reach `forbidden_markers`."""
    name: str
    source_markers: List[str]
    forbidden_markers: List[str]
    message: str


# Deliberately conservative defaults. The original single heuristic ("query" in
# a function name inside a "controller" file) fired on names like `queryParams`
# and missed everything else. These rules still state assumptions, but they are
# evaluated against recovered call and import edges rather than names alone, and
# every finding carries its evidence and is labelled heuristic.
DEFAULT_LAYER_RULES = [
    LayerRule(
        name="controller-bypasses-service",
        source_markers=["controller", "handler", "route", "view", "resource"],
        forbidden_markers=["repository", "dao", "entitymanager", "session", "cursor",
                           "execute_sql", "executequery"],
        message="Presentation-layer component reaches the persistence layer directly.",
    ),
    LayerRule(
        name="model-depends-on-presentation",
        source_markers=["model", "entity", "domain"],
        forbidden_markers=["controller", "render", "template", "httpresponse", "jsx"],
        message="Domain-layer component depends on the presentation layer.",
    ),
    LayerRule(
        name="repository-calls-service",
        source_markers=["repository", "dao"],
        forbidden_markers=["service", "usecase", "controller"],
        message="Persistence-layer component calls back into application logic.",
    ),
]


class ComparisonEngine:
    """Structural diff between the intended design and the implementation."""

    def __init__(
        self,
        uml_model: IntermediateDesignModel,
        code_model: IntermediateDesignModel,
        architecture: Optional[Dict[str, Any]] = None,
        score_associations: Optional[bool] = None,
    ):
        self.uml_model = uml_model
        self.code_model = code_model
        self.architecture = architecture or {"files": []}
        self.score_associations = (
            ASSOCIATION_SCORING if score_associations is None else score_associations
        )
        self.diff = DifferenceModel()

    # -- public ---------------------------------------------------------------

    def compare(self) -> DifferenceModel:
        uml_elements = {element.name: element for element in self.uml_model.elements}
        code_elements = {element.name: element for element in self.code_model.elements}

        uml_keys: Set[str] = set(uml_elements)
        code_keys: Set[str] = set(code_elements)

        self.diff.missing_classes = sorted(uml_keys - code_keys)
        self.diff.extra_classes = sorted(code_keys - uml_keys)

        matching = uml_keys & code_keys
        member_total, member_passed = self._compare_members(matching, uml_elements, code_elements)
        relation_total, relation_passed = self._compare_relations(code_elements)

        total = len(uml_keys) + member_total + relation_total
        passed = len(matching) + member_passed + relation_passed

        self.diff.checks_total = total
        self.diff.checks_passed = passed
        self.diff.association_scoring = self.score_associations
        # An empty design model means "nothing was specified", which is not the
        # same as "everything conforms"; reporting 100% there was misleading.
        self.diff.similarity_score = round((passed / total) * 100, 2) if total > 0 else 0.0
        return self.diff

    # -- members --------------------------------------------------------------

    def _compare_members(self, matching, uml_elements, code_elements):
        total = 0
        passed = 0

        for class_name in sorted(matching):
            uml_class = uml_elements[class_name]
            code_class = code_elements[class_name]
            element_diff = ElementDifference(element_name=class_name)

            uml_attributes = {attribute.name for attribute in uml_class.attributes}
            code_attributes = {attribute.name for attribute in code_class.attributes}
            element_diff.missing_attributes = sorted(uml_attributes - code_attributes)
            element_diff.extra_attributes = sorted(code_attributes - uml_attributes)
            total += len(uml_attributes)
            passed += len(uml_attributes & code_attributes)

            uml_methods = {method.name for method in uml_class.methods}
            code_methods = {method.name for method in code_class.methods}
            element_diff.missing_methods = sorted(uml_methods - code_methods)
            element_diff.extra_methods = sorted(code_methods - uml_methods)
            total += len(uml_methods)
            passed += len(uml_methods & code_methods)

            if (
                element_diff.missing_attributes
                or element_diff.extra_attributes
                or element_diff.missing_methods
                or element_diff.extra_methods
            ):
                self.diff.element_differences.append(element_diff)

        return total, passed

    # -- relationships ---------------------------------------------------------

    def _compare_relations(self, code_elements):
        implemented_inheritance = {
            (element.name, element.extends, "generalization")
            for element in self.code_model.elements
            if element.extends
        } | {
            (element.name, interface, "realization")
            for element in self.code_model.elements
            for interface in element.implements
        }

        total = 0
        passed = 0

        for relation in self.uml_model.relations:
            if relation.relation in EXACT_RELATIONS:
                total += 1
                satisfied = (
                    relation.source,
                    relation.target,
                    relation.relation,
                ) in implemented_inheritance
                if satisfied:
                    passed += 1
                else:
                    self.diff.missing_relations.append(
                        f"{relation.source} --{relation.relation}--> {relation.target}"
                    )
                self.diff.relation_findings.append(
                    RelationFinding(
                        source=relation.source,
                        target=relation.target,
                        relation=relation.relation,
                        evidence=STRONG if satisfied else NONE,
                        evidence_detail=(
                            "Declared in the code's inheritance clause."
                            if satisfied
                            else "No inheritance clause connects these types."
                        ),
                        scored=True,
                        satisfied=satisfied,
                    )
                )
                continue

            if relation.relation not in EVIDENCE_RELATIONS:
                continue

            evidence, detail = self._association_evidence(relation, code_elements)
            satisfied = evidence in (STRONG, WEAK)
            self.diff.relation_findings.append(
                RelationFinding(
                    source=relation.source,
                    target=relation.target,
                    relation=relation.relation,
                    evidence=evidence,
                    evidence_detail=detail,
                    scored=self.score_associations,
                    satisfied=satisfied,
                )
            )
            if evidence == NONE:
                self.diff.unimplemented_associations.append(
                    f"{relation.source} --{relation.relation}--> {relation.target}"
                )
            if self.score_associations:
                total += 1
                if evidence == STRONG:
                    passed += 1
                elif evidence == WEAK:
                    # Weak evidence earns partial credit rather than a verdict.
                    passed += 0.5

        return total, passed

    def _association_evidence(self, relation, code_elements):
        source = code_elements.get(relation.source)
        target_name = relation.target

        if source is None:
            return NONE, f"{relation.source} is not implemented, so the association cannot be."

        for attribute in source.attributes:
            if attribute.type and attribute.type.split(".")[-1] == target_name:
                return (
                    STRONG,
                    f"Field '{attribute.name}' is declared with type {target_name}.",
                )

        record = self._file_record_for(relation.source)
        if record:
            klass = next(
                (c for c in record.get("classes", []) if c["name"] == relation.source), None
            )
            if klass:
                for method in klass.get("methods", []):
                    for parameter_type in method.get("param_types", []) or []:
                        if parameter_type and parameter_type.split(".")[-1] == target_name:
                            return (
                                STRONG,
                                f"Method '{method['name']}' takes a parameter of type {target_name}.",
                            )
                    if method.get("returns") and method["returns"].split(".")[-1] == target_name:
                        return (
                            STRONG,
                            f"Method '{method['name']}' returns {target_name}.",
                        )
                    for ref in method.get("call_refs", []) or []:
                        if ref.get("instantiation") and ref["name"] == target_name:
                            return (
                                WEAK,
                                f"Method '{method['name']}' instantiates {target_name}, but no "
                                "field or signature records the relationship.",
                            )
                for field in klass.get("fields", []):
                    if field["name"].lower() in (
                        target_name.lower(),
                        target_name.lower() + "s",
                        target_name.lower() + "_list",
                    ):
                        return (
                            WEAK,
                            f"Field '{field['name']}' matches the target name but carries no "
                            "declared type.",
                        )

        for attribute in source.attributes:
            if attribute.name.lower().startswith(target_name.lower()):
                return (
                    WEAK,
                    f"Field '{attribute.name}' is named after {target_name} but is untyped.",
                )

        return NONE, f"No typed field, signature, or instantiation links {relation.source} to {target_name}."

    def _file_record_for(self, class_name: str) -> Optional[Dict[str, Any]]:
        for record in self.architecture.get("files", []):
            for klass in record.get("classes", []):
                if klass["name"] == class_name:
                    return record
        return None


# --- projections and rules ---------------------------------------------------


def architecture_to_design_model(architecture: Dict[str, Any]) -> IntermediateDesignModel:
    """Project the polyglot parser output onto the UML-shaped design model so
    the two can be diffed by name."""
    from models.design_model import DesignElement, ElementAttribute, ElementMethod

    model = IntermediateDesignModel(project_id="implementation")
    for record in architecture.get("files", []):
        for klass in record.get("classes", []):
            element = DesignElement(
                name=klass["name"],
                element_type="interface" if klass.get("kind") == "interface" else "class",
                attributes=[
                    ElementAttribute(name=field["name"], type=field.get("type") or "Object")
                    for field in klass.get("fields", [])
                ],
                methods=[
                    ElementMethod(
                        name=method["name"],
                        return_type=method.get("returns") or "void",
                        parameters=[p for p in (method.get("param_names") or []) if p],
                    )
                    for method in klass.get("methods", [])
                ],
            )
            bases = klass.get("bases", [])
            if bases:
                element.extends = bases[0]
                element.implements = bases[1:]
            model.elements.append(element)
    return model


def evaluate_layer_rules(
    architecture: Dict[str, Any], rules: Optional[List[LayerRule]] = None
) -> List[Dict[str, str]]:
    """Flag layering violations using the call and import edges the parser
    recovered, so a finding rests on what a component actually reaches."""
    rules = rules or DEFAULT_LAYER_RULES
    violations: List[Dict[str, str]] = []

    for record in architecture.get("files", []):
        path_lower = record["file_path"].lower()
        callables = list(record.get("functions", []))
        for klass in record.get("classes", []):
            callables.extend(klass.get("methods", []))

        evidence_pool = {call.lower() for entry in callables for call in entry.get("calls", [])}
        evidence_pool |= {
            (ref.get("receiver") or "").lower()
            for entry in callables
            for ref in entry.get("call_refs", []) or []
        }
        evidence_pool |= {imp.lower() for imp in record.get("imports", [])}
        evidence_pool |= {
            (field.get("type") or "").lower()
            for klass in record.get("classes", [])
            for field in klass.get("fields", [])
        }
        evidence_pool.discard("")

        for rule in rules:
            if not any(marker in path_lower for marker in rule.source_markers):
                continue
            hits = sorted(
                {
                    marker
                    for marker in rule.forbidden_markers
                    if any(marker in item for item in evidence_pool)
                }
            )
            if hits:
                violations.append(
                    {
                        "rule": rule.name,
                        "file": record["file_path"],
                        "message": rule.message,
                        "evidence": ", ".join(hits),
                        "confidence": "heuristic",
                    }
                )

    return violations
