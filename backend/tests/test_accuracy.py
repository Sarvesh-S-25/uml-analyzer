"""Regressions for real-corpus failures and honest scoring."""
import pathlib
import tempfile
import unittest
from unittest import mock

import ai_service
from parsers.polyglot_parser import PolyglotParser
from comparison.engine import architecture_to_design_model
from tests.test_pipeline import PipelineTestCase


class ScoringTests(PipelineTestCase):
    def test_model_cannot_replace_structural_score(self):
        reply = ai_service.LlmResult(payload={"similarity_score": 1}, model="test", invoked=True)
        with mock.patch.object(ai_service, "evaluate_conformance", return_value=reply):
            result = self.analyse(force=True)
        self.assertEqual(result["similarity_score"], result["similarity_score_rule_based"])
        self.assertEqual(result["model_score"], 1)

    def test_empty_source_has_no_score(self):
        from tests.helpers import arch_base
        architecture = arch_base()
        architecture["files"] = []
        result = self.analyse(architecture)
        self.assertIsNone(result["similarity_score"])
        self.assertFalse(result["evaluation"]["valid"])


class LanguageTests(unittest.TestCase):
    def parse(self, name, text):
        with tempfile.TemporaryDirectory() as directory:
            pathlib.Path(directory, name).write_text(text, encoding="utf-8")
            return PolyglotParser(directory).parse()

    def test_csharp_members_and_interface(self):
        a = self.parse("test.cs", "interface IRepo {} class Repo : IRepo { private string label; public int Count { get; set; } public void Save(int id) {} }")
        self.assertFalse(a["parse_errors"])
        repo = next(c for c in a["files"][0]["classes"] if c["name"] == "Repo")
        self.assertEqual({f["name"] for f in repo["fields"]}, {"label", "Count"})
        self.assertEqual(repo["methods"][0]["name"], "Save")
        model = architecture_to_design_model(a)
        self.assertEqual(next(c for c in model.elements if c.name == "Repo").implements, ["IRepo"])

    def test_java_superclass_is_not_chosen_alphabetically(self):
        # `bases` is sorted for the fingerprint; taking bases[0] as the
        # superclass once made this class extend Alpha.
        a = self.parse("A.java", "interface Alpha {} class Zeta {} class A extends Zeta implements Alpha {}")
        model = architecture_to_design_model(a)
        element = next(c for c in model.elements if c.name == "A")
        self.assertEqual(element.extends, "Zeta")
        self.assertEqual(element.implements, ["Alpha"])
        self.assertEqual(element.untyped_supertypes, [])

    def test_javascript_fields_assigned_through_this(self):
        a = self.parse("area.js", "class Area {\n  constructor(id) {\n    this.id = id;\n    this.players = [];\n    this.a.b = 1;\n  }\n}\n")
        area = a["files"][0]["classes"][0]
        self.assertEqual({f["name"] for f in area["fields"]}, {"id", "players"})

    def test_typescript_clauses_keep_their_kind(self):
        a = self.parse("a.ts", "interface Port {} class Base {} class Impl extends Base implements Port {}")
        element = next(c for c in architecture_to_design_model(a).elements if c.name == "Impl")
        self.assertEqual((element.extends, element.implements), ("Base", ["Port"]))

    def test_python_realization_is_satisfied_by_a_base_class(self):
        # Python has no interface keyword, so a UML realization to an abstract
        # base can only ever be written as a base class.
        from comparison.engine import ComparisonEngine
        from models.design_model import DesignElement, DesignRelation, IntermediateDesignModel

        a = self.parse("repo.py", "class Repository:\n    pass\n\nclass OrderRepository(Repository):\n    pass\n")
        design = IntermediateDesignModel(
            elements=[DesignElement(name="Repository", element_type="interface"),
                      DesignElement(name="OrderRepository", element_type="class")],
            relations=[DesignRelation(source="OrderRepository", target="Repository", relation="realization")],
        )
        diff = ComparisonEngine(design, architecture_to_design_model(a)).compare()
        self.assertEqual(diff.missing_relations, [])

    def test_java_extension_does_not_satisfy_a_realization(self):
        from comparison.engine import ComparisonEngine
        from models.design_model import DesignElement, DesignRelation, IntermediateDesignModel

        a = self.parse("R.java", "class Repository {} class OrderRepository extends Repository {}")
        design = IntermediateDesignModel(
            elements=[DesignElement(name="Repository", element_type="interface"),
                      DesignElement(name="OrderRepository", element_type="class")],
            relations=[DesignRelation(source="OrderRepository", target="Repository", relation="realization")],
        )
        diff = ComparisonEngine(design, architecture_to_design_model(a)).compare()
        self.assertEqual(diff.missing_relations, ["OrderRepository --realization--> Repository"])

    def test_php_members(self):
        a = self.parse("test.php", "<?php class Repo { private string $label; public function save(int $id): void {} }")
        self.assertFalse(a["parse_errors"])
        repo = a["files"][0]["classes"][0]
        self.assertEqual(repo["name"], "Repo")
        self.assertEqual(repo["fields"][0]["name"], "label")
        self.assertEqual(repo["methods"][0]["name"], "save")


class OllamaTransportTests(unittest.TestCase):
    def test_native_api_carries_context_and_usage(self):
        response = mock.Mock()
        response.json.return_value = {"message": {"content": "{}"}, "prompt_eval_count": 12, "eval_count": 3}
        with mock.patch("httpx.post", return_value=response) as post:
            self.assertEqual(ai_service._call_openai("ollama", "test:7b", "sys", "user"), ("{}", 12, 3))
        self.assertTrue(post.call_args.args[0].endswith("/api/chat"))
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_ctx"], ai_service.OLLAMA_NUM_CTX)
        response.raise_for_status.assert_called_once()
