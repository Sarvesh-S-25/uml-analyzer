from typing import List, Optional

from pydantic import BaseModel, Field


class ElementAttribute(BaseModel):
    name: str
    type: str = "void"
    visibility: str = "public"


class ElementMethod(BaseModel):
    name: str
    return_type: str = "void"
    visibility: str = "public"
    parameters: List[str] = []


class DesignElement(BaseModel):
    name: str
    element_type: str  # "class" or "interface"
    attributes: List[ElementAttribute] = []
    methods: List[ElementMethod] = []
    extends: Optional[str] = None
    implements: List[str] = []


class DesignRelation(BaseModel):
    """An explicit relationship between two named UML elements.

    Previously only inheritance implied by `extends`/`implements` was captured,
    which meant associations and dependencies drawn in the diagram were dropped
    on the floor and could never be checked against the code.
    """
    source: str
    target: str
    relation: str  # generalization | realization | association | dependency


class IntermediateDesignModel(BaseModel):
    project_id: str = Field(default="default_project")
    elements: List[DesignElement] = []
    relations: List[DesignRelation] = []
    # Populated by the parser so callers can tell "the diagram is empty" apart
    # from "the diagram failed to parse".
    parse_warnings: List[str] = []


class ElementDifference(BaseModel):
    element_name: str
    missing_attributes: List[str] = []
    missing_methods: List[str] = []
    extra_attributes: List[str] = []
    extra_methods: List[str] = []


class RelationFinding(BaseModel):
    """The verdict on one modelled relationship, with the evidence behind it.

    Inheritance is recoverable exactly from an AST, so `evidence` is strong or
    none. An association cannot be proven from code -- a typed field is strong
    evidence, a name match or an instantiation is weak -- so the finding records
    which it was, and whether it counted toward the score.
    """
    source: str
    target: str
    relation: str
    evidence: str  # strong | weak | none
    evidence_detail: str
    scored: bool
    satisfied: bool


class DifferenceModel(BaseModel):
    missing_classes: List[str] = []
    extra_classes: List[str] = []
    missing_relations: List[str] = []
    unimplemented_associations: List[str] = []
    relation_findings: List[RelationFinding] = []
    element_differences: List[ElementDifference] = []
    similarity_score: float = 100.0
    checks_total: float = 0
    checks_passed: float = 0
    association_scoring: bool = False
