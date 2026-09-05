"""Parser tests against real source files.

Skipped automatically when the native tree-sitter grammars are not installed,
so the rest of the suite still runs in a minimal environment.
"""
import pathlib
import shutil
import tempfile
import unittest

try:
    from parsers.polyglot_parser import PolyglotParser

    TREE_SITTER_AVAILABLE = True
    SKIP_REASON = ""
except Exception as exc:  # ImportError, or a grammar/ABI mismatch
    TREE_SITTER_AVAILABLE = False
    SKIP_REASON = f"tree-sitter grammars unavailable: {exc}"


PYTHON_SOURCE = '''
import os
from app.repository import OrderRepository


class OrderService(Base):
    """Docstring should not affect the structural fingerprint."""

    def __init__(self, repo: OrderRepository):
        self.repo = repo
        self.audit = None

    def place(self, order):
        return self.repo.save(order)


def bootstrap():
    return OrderService(OrderRepository())
'''

PYTHON_REFORMATTED = '''
import os
from app.repository import OrderRepository


class OrderService(Base):
    """A completely different docstring, and extra blank lines."""



    def __init__(self, repo: OrderRepository):
        # assign the collaborator
        self.repo = repo
        self.audit = None

    def place(self, order):
        # delegate to the repository
        return self.repo.save(order)


def bootstrap():
    return OrderService(OrderRepository())
'''

JAVA_SOURCE = """
package app;

import java.util.List;

public interface Repository {
    void save(Order order);
}

public class OrderService implements Repository {
    private Repository repo;

    public void save(Order order) {
        repo.save(order);
    }
}
"""

JS_SOURCE = """
import { save } from './repo';

export class OrderService {
  constructor(repo) {
    this.repo = repo;
  }

  place(order) {
    return this.repo.save(order);
  }
}

export function bootstrap() {
  return new OrderService();
}
"""


@unittest.skipUnless(TREE_SITTER_AVAILABLE, SKIP_REASON)
class PolyglotParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def parse(self, filename: str, content: str, folder: str = "src"):
        directory = self.tmp / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / filename).write_text(content, encoding="utf-8")
        return PolyglotParser(str(directory)).parse()

    def test_python_declarations(self):
        result = self.parse("service.py", PYTHON_SOURCE)
        self.assertEqual(len(result["files"]), 1)
        record = result["files"][0]

        classes = {c["name"]: c for c in record["classes"]}
        self.assertIn("OrderService", classes)
        self.assertIn("Base", classes["OrderService"]["bases"])
        self.assertEqual(
            {m["name"] for m in classes["OrderService"]["methods"]}, {"__init__", "place"}
        )
        fields = {f["name"]: f["type"] for f in classes["OrderService"]["fields"]}
        self.assertIn("repo", fields)
        # `self.repo = repo` carries no annotation of its own; the type has to
        # come from `__init__`'s own parameter annotation. Missing this was a
        # real undercount on real code -- see polyglot_parser.py's `_fields`.
        self.assertEqual(fields["repo"], "OrderRepository")
        self.assertIn("bootstrap", {f["name"] for f in record["functions"]})

    def test_call_edges_are_captured(self):
        record = self.parse("service.py", PYTHON_SOURCE)["files"][0]
        place = next(
            m
            for c in record["classes"]
            for m in c["methods"]
            if m["name"] == "place"
        )
        # Without this, a body-only change would be invisible to the gate.
        self.assertIn("save", place["calls"])

    def test_formatting_and_comments_do_not_change_the_structural_hash(self):
        original = self.parse("service.py", PYTHON_SOURCE, folder="a")
        reformatted = self.parse("service.py", PYTHON_REFORMATTED, folder="b")
        self.assertNotEqual(
            original["project_text_sha256"], reformatted["project_text_sha256"]
        )
        self.assertEqual(
            original["project_structure_sha256"], reformatted["project_structure_sha256"]
        )

    def test_java_interface_and_class(self):
        record = self.parse("Service.java", JAVA_SOURCE)["files"][0]
        kinds = {c["name"]: c["kind"] for c in record["classes"]}
        self.assertEqual(kinds.get("Repository"), "interface")
        self.assertEqual(kinds.get("OrderService"), "class")

    def test_javascript_class_and_function(self):
        record = self.parse("service.js", JS_SOURCE)["files"][0]
        self.assertIn("OrderService", {c["name"] for c in record["classes"]})
        self.assertIn("bootstrap", {f["name"] for f in record["functions"]})

    def test_syntax_errors_are_flagged_not_fatal(self):
        result = self.parse("broken.py", "class Broken(:\n  def (self)\n")
        self.assertEqual(len(result["files"]), 1)
        self.assertTrue(result["files"][0]["parse_error"])
        self.assertIn("broken.py", result["parse_errors"])

    def test_vendored_directories_are_skipped(self):
        (self.tmp / "src" / "node_modules" / "pkg").mkdir(parents=True)
        (self.tmp / "src" / "node_modules" / "pkg" / "index.js").write_text(
            "class Vendored {}", encoding="utf-8"
        )
        result = self.parse("service.py", PYTHON_SOURCE)
        paths = {f["file_path"] for f in result["files"]}
        self.assertNotIn("node_modules/pkg/index.js", paths)

    def test_empty_directory_is_handled(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        result = PolyglotParser(str(empty)).parse()
        self.assertEqual(result["files"], [])
        self.assertTrue(result["project_structure_sha256"])

    def test_missing_directory_is_handled(self):
        result = PolyglotParser(str(self.tmp / "does-not-exist")).parse()
        self.assertEqual(result["files"], [])


if __name__ == "__main__":
    unittest.main()
