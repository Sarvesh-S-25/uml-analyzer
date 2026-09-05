"""Relationship checking: exact for inheritance, evidence-graded for associations."""
import unittest

from comparison.engine import ComparisonEngine, architecture_to_design_model
from models.design_model import DesignRelation, IntermediateDesignModel
from parsers.uml_parser import StarUMLParser
from tests.helpers import arch_with_association


def design_from(relations):
    model = IntermediateDesignModel()
    from models.design_model import DesignElement

    model.elements = [
        DesignElement(name="OrderService", element_type="class"),
        DesignElement(name="OrderRepository", element_type="class"),
    ]
    model.relations = relations
    return model


class AssociationEvidenceTests(unittest.TestCase):
    def _findings(self, typed: bool, score: bool = False):
        architecture = arch_with_association(typed=typed)
        design = design_from(
            [
                DesignRelation(
                    source="OrderService", target="OrderRepository", relation="association"
                )
            ]
        )
        difference = ComparisonEngine(
            design,
            architecture_to_design_model(architecture),
            architecture=architecture,
            score_associations=score,
        ).compare()
        return difference

    def test_typed_field_is_strong_evidence(self):
        difference = self._findings(typed=True)
        finding = difference.relation_findings[0]
        self.assertEqual(finding.evidence, "strong")
        self.assertTrue(finding.satisfied)
        self.assertIn("OrderRepository", finding.evidence_detail)

    def test_untyped_field_named_after_the_target_is_weak_evidence(self):
        architecture = arch_with_association(typed=False)
        design = design_from(
            [DesignRelation(source="OrderService", target="Repo", relation="association")]
        )
        # The field is called `repo`, which matches `Repo` by name only.
        difference = ComparisonEngine(
            design, architecture_to_design_model(architecture), architecture=architecture
        ).compare()
        finding = difference.relation_findings[0]
        self.assertEqual(finding.evidence, "weak")

    def test_absent_relationship_is_reported_as_none(self):
        architecture = arch_with_association(typed=True)
        design = design_from(
            [
                DesignRelation(
                    source="OrderService", target="AuditLog", relation="association"
                )
            ]
        )
        difference = ComparisonEngine(
            design, architecture_to_design_model(architecture), architecture=architecture
        ).compare()
        finding = difference.relation_findings[0]
        self.assertEqual(finding.evidence, "none")
        self.assertFalse(finding.satisfied)
        self.assertIn("OrderService --association--> AuditLog", difference.unimplemented_associations)

    def test_associations_are_excluded_from_the_score_by_default(self):
        excluded = self._findings(typed=True, score=False)
        included = self._findings(typed=True, score=True)
        self.assertFalse(excluded.association_scoring)
        self.assertTrue(included.association_scoring)
        # Excluding them means the association contributes no check at all.
        self.assertLess(excluded.checks_total, included.checks_total)

    def test_the_scoring_convention_is_recorded_in_the_result(self):
        difference = self._findings(typed=True)
        self.assertIn("association_scoring", difference.model_dump())
        self.assertFalse(difference.model_dump()["association_scoring"])


class InheritanceTests(unittest.TestCase):
    def test_generalization_is_scored_exactly(self):
        from tests.helpers import (
            make_architecture,
            make_class,
            make_file,
            make_method,
        )

        architecture = make_architecture(
            [
                make_file(
                    "shapes.py",
                    classes=[
                        make_class("Shape", methods=[make_method("draw", 1)]),
                        make_class("Circle", bases=["Shape"]),
                    ],
                )
            ]
        )
        from models.design_model import DesignElement

        design = IntermediateDesignModel()
        design.elements = [
            DesignElement(name="Shape", element_type="class"),
            DesignElement(name="Circle", element_type="class"),
        ]
        design.relations = [
            DesignRelation(source="Circle", target="Shape", relation="generalization")
        ]

        difference = ComparisonEngine(
            design, architecture_to_design_model(architecture), architecture=architecture
        ).compare()
        finding = difference.relation_findings[0]
        self.assertEqual(finding.evidence, "strong")
        self.assertTrue(finding.scored)
        self.assertEqual(difference.missing_relations, [])

    def test_missing_generalization_is_reported(self):
        from tests.helpers import make_architecture, make_class, make_file

        architecture = make_architecture(
            [make_file("shapes.py", classes=[make_class("Circle")])]
        )
        from models.design_model import DesignElement

        design = IntermediateDesignModel()
        design.elements = [DesignElement(name="Circle", element_type="class")]
        design.relations = [
            DesignRelation(source="Circle", target="Shape", relation="generalization")
        ]

        difference = ComparisonEngine(
            design, architecture_to_design_model(architecture), architecture=architecture
        ).compare()
        self.assertIn("Circle --generalization--> Shape", difference.missing_relations)


class UmlAssociationParsingTests(unittest.TestCase):
    def test_association_ends_are_resolved_to_names(self):
        import json
        import tempfile
        import os

        from tests.helpers import UML_MODEL

        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "design.mdj")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(UML_MODEL, handle)

        model = StarUMLParser(path).parse()
        associations = [r for r in model.relations if r.relation == "association"]
        self.assertEqual(len(associations), 1)
        self.assertEqual(associations[0].source, "OrderService")
        self.assertEqual(associations[0].target, "OrderRepository")

    def test_attribute_type_reference_is_resolved(self):
        import json
        import os
        import tempfile

        from tests.helpers import UML_MODEL

        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "design.mdj")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(UML_MODEL, handle)

        model = StarUMLParser(path).parse()
        service = next(e for e in model.elements if e.name == "OrderService")
        # `type` is a {"$ref": ...} pointer in a real StarUML file, not a string.
        self.assertEqual(service.attributes[0].type, "OrderRepository")


if __name__ == "__main__":
    unittest.main()
