"""The seeded-deviation set must apply cleanly and leave valid code behind.

A mutation whose search text has drifted out of the reference project would
silently drop out of the experiment, and one that produces a syntax error would
be measured as a parse failure rather than as the deviation it is meant to be.
Both would corrupt the results quietly, so both are tested here.
"""
import ast
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

RESEARCH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "research")
)
BASE_DIR = os.path.join(RESEARCH, "deviations", "base")

if os.path.isdir(RESEARCH):
    sys.path.insert(0, RESEARCH)
    sys.path.insert(0, os.path.join(RESEARCH, "deviations"))

try:
    from mutations import BY_ID, MUTATIONS, branch_name

    AVAILABLE = os.path.isdir(BASE_DIR)
    SKIP_REASON = "" if AVAILABLE else f"reference project not found at {BASE_DIR}"
except Exception as exc:  # pragma: no cover - depends on layout
    AVAILABLE = False
    SKIP_REASON = f"deviation set unavailable: {exc}"
    MUTATIONS = []
    BY_ID = {}


def stage(destination: str) -> None:
    for entry in sorted(os.listdir(BASE_DIR)):
        if entry == "design.mdj":
            continue
        source = os.path.join(BASE_DIR, entry)
        target = os.path.join(destination, entry)
        if os.path.isdir(source):
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def python_files(root: str):
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(current, name)


def read_all(root: str) -> dict:
    return {
        os.path.relpath(path, root): pathlib.Path(path).read_text(encoding="utf-8")
        for path in python_files(root)
    }


def declaration_surface(source: str) -> dict:
    """An independent structural read of a Python file.

    Built on Python's own parser, with no reference to the tool's fingerprint.
    Captures imports, classes with their bases, `self.x` fields, and method
    signatures -- and deliberately excludes docstrings, statement bodies, local
    variable names, and declaration order.
    """
    tree = ast.parse(source)
    imports = set()
    classes = {}
    functions = {}

    def signature(node) -> str:
        args = [arg.arg for arg in node.args.args if arg.arg not in ("self", "cls")]
        return f"{node.name}({','.join(args)})"

    def self_fields(node) -> set:
        fields = set()
        for descendant in ast.walk(node):
            if isinstance(descendant, ast.Assign):
                for target in descendant.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        fields.add(target.attr)
        return fields

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = {
                "bases": sorted(ast.unparse(base) for base in node.bases),
                "methods": sorted(
                    signature(item)
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ),
                "fields": sorted(self_fields(node)),
            }

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = signature(node)

    return {
        "imports": sorted(imports),
        "classes": classes,
        "functions": dict(sorted(functions.items())),
    }


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class ReferenceProjectTests(unittest.TestCase):
    def test_reference_project_parses(self):
        tree = tempfile.mkdtemp()
        stage(tree)
        for path in python_files(tree):
            with self.subTest(path=os.path.basename(path)):
                ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))

    def test_reference_diagram_is_valid_staruml(self):
        import json

        with open(os.path.join(BASE_DIR, "design.mdj"), "r", encoding="utf-8") as handle:
            model = json.load(handle)
        self.assertEqual(model["_type"], "Project")

        found = set()

        def walk(node):
            if isinstance(node, dict):
                if node.get("_type") in ("UMLClass", "UMLInterface") and node.get("name"):
                    found.add(node["name"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(model)
        self.assertEqual(
            found,
            {"Order", "Repository", "OrderRepository", "OrderService", "AuditLog", "OrderController"},
        )


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class MutationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tree = os.path.join(self.tmp, "tree")
        os.makedirs(self.tree)
        stage(self.tree)
        self.before = read_all(self.tree)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_mutation_applies_and_changes_something(self):
        for mutation in MUTATIONS:
            with self.subTest(mutation=mutation.id):
                shutil.rmtree(self.tree)
                os.makedirs(self.tree)
                stage(self.tree)

                mutation.apply(self.tree)
                after = read_all(self.tree)
                self.assertNotEqual(
                    self.before, after, f"{mutation.id} left the tree untouched"
                )

    def test_every_mutation_leaves_parsable_python(self):
        for mutation in MUTATIONS:
            with self.subTest(mutation=mutation.id):
                shutil.rmtree(self.tree)
                os.makedirs(self.tree)
                stage(self.tree)
                mutation.apply(self.tree)

                for path in python_files(self.tree):
                    source = pathlib.Path(path).read_text(encoding="utf-8")
                    try:
                        ast.parse(source)
                    except SyntaxError as exc:
                        self.fail(
                            f"{mutation.id} broke {os.path.relpath(path, self.tree)}: {exc}"
                        )

    def test_negative_controls_do_not_change_the_declaration_surface(self):
        """A negative control must be invisible to an independent structural read.

        The oracle here is `declaration_surface`, built with Python's own parser
        and with no knowledge of the tool's fingerprint, so the two cannot agree
        by sharing a bug. It deliberately ignores docstrings, statement bodies,
        local names, and declaration order -- exactly the things the fingerprint
        also excludes, and the things these mutations touch.
        """
        negatives = [m for m in MUTATIONS if m.category == "negative"]
        self.assertTrue(negatives)

        for mutation in negatives:
            with self.subTest(mutation=mutation.id):
                shutil.rmtree(self.tree)
                os.makedirs(self.tree)
                stage(self.tree)
                baseline = {
                    path: declaration_surface(source)
                    for path, source in read_all(self.tree).items()
                }

                mutation.apply(self.tree)
                mutated = {
                    path: declaration_surface(source)
                    for path, source in read_all(self.tree).items()
                }

                self.assertEqual(
                    baseline, mutated, f"{mutation.id} altered the declaration surface"
                )

    def test_positive_mutations_do_change_the_declaration_surface(self):
        """The converse: a seeded deviation that no independent reader can see
        would not be testing anything."""
        for mutation in MUTATIONS:
            if mutation.category == "negative":
                continue
            with self.subTest(mutation=mutation.id):
                shutil.rmtree(self.tree)
                os.makedirs(self.tree)
                stage(self.tree)
                baseline = {
                    path: declaration_surface(source)
                    for path, source in read_all(self.tree).items()
                }

                mutation.apply(self.tree)
                mutated = {
                    path: declaration_surface(source)
                    for path, source in read_all(self.tree).items()
                }

                self.assertNotEqual(
                    baseline, mutated, f"{mutation.id} is invisible to a structural read"
                )

    def test_ids_are_unique_and_branch_names_are_safe(self):
        ids = [mutation.id for mutation in MUTATIONS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(BY_ID), len(MUTATIONS))
        for mutation in MUTATIONS:
            name = branch_name(mutation)
            self.assertTrue(name.startswith("deviation/"))
            self.assertNotIn(" ", name)

    def test_the_set_covers_both_directions(self):
        categories = {mutation.category for mutation in MUTATIONS}
        self.assertIn("positive", categories)
        self.assertIn("negative", categories)
        # Without negative controls the experiment can only measure recall.
        self.assertGreaterEqual(
            sum(1 for m in MUTATIONS if m.category == "negative"), 4
        )
        self.assertGreaterEqual(
            sum(1 for m in MUTATIONS if m.category == "positive"), 6
        )

    def test_expectations_are_internally_consistent(self):
        for mutation in MUTATIONS:
            with self.subTest(mutation=mutation.id):
                if mutation.expect_conformance_change:
                    # Findings cannot move without the structure moving first.
                    self.assertTrue(
                        mutation.expect_structural_change,
                        f"{mutation.id} claims a conformance change with no structural change",
                    )
                if mutation.category == "negative":
                    self.assertFalse(mutation.expect_structural_change)
                    self.assertFalse(mutation.expect_conformance_change)


if __name__ == "__main__":
    unittest.main()
