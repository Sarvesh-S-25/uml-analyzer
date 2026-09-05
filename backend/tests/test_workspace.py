"""The virtual directory: everything a user needs without git."""
import pathlib
import shutil
import tempfile
import unittest
import zipfile
import io

from core.workspace_fs import (
    Workspace,
    WorkspaceError,
    delete_uml_model,
    list_uml_models,
)


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "source").mkdir()
        (self.tmp / "uml").mkdir()
        self.workspace = Workspace(str(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class FileOperationTests(WorkspaceTestCase):
    def test_create_read_and_overwrite(self):
        self.workspace.write("app/service.py", "class Service:\n    pass\n")
        read = self.workspace.read("app/service.py")
        self.assertIn("class Service", read["content"])
        self.assertEqual(read["path"], "app/service.py")

        self.workspace.write("app/service.py", "changed")
        self.assertEqual(self.workspace.read("app/service.py")["content"], "changed")

    def test_create_only_refuses_to_clobber(self):
        self.workspace.write("a.py", "first")
        with self.assertRaises(WorkspaceError):
            self.workspace.write("a.py", "second", create_only=True)
        self.assertEqual(self.workspace.read("a.py")["content"], "first")

    def test_nested_directories_are_created_on_write(self):
        self.workspace.write("deep/nested/path/file.py", "x = 1")
        self.assertTrue((self.tmp / "source" / "deep" / "nested" / "path" / "file.py").exists())

    def test_mkdir_move_and_delete(self):
        self.workspace.mkdir("pkg")
        self.workspace.write("pkg/old.py", "x = 1")
        self.workspace.move("pkg/old.py", "pkg/new.py")
        self.assertEqual(self.workspace.read("pkg/new.py")["content"], "x = 1")

        self.workspace.delete("pkg/new.py")
        with self.assertRaises(WorkspaceError):
            self.workspace.read("pkg/new.py")

        self.workspace.delete("pkg")
        self.assertFalse((self.tmp / "source" / "pkg").exists())

    def test_move_refuses_to_overwrite(self):
        self.workspace.write("a.py", "a")
        self.workspace.write("b.py", "b")
        with self.assertRaises(WorkspaceError):
            self.workspace.move("a.py", "b.py")

    def test_missing_file_raises(self):
        with self.assertRaises(WorkspaceError):
            self.workspace.read("nope.py")
        with self.assertRaises(WorkspaceError):
            self.workspace.delete("nope.py")


class ContainmentTests(WorkspaceTestCase):
    def test_traversal_is_refused_on_every_operation(self):
        for path in ("../escape.py", "../../escape.py", "/etc/passwd", "a/../../b.py"):
            with self.subTest(path=path):
                with self.assertRaises(WorkspaceError):
                    self.workspace.write(path, "x")
                with self.assertRaises(WorkspaceError):
                    self.workspace.read(path)
                with self.assertRaises(WorkspaceError):
                    self.workspace.delete(path)

    def test_empty_path_is_refused(self):
        with self.assertRaises(WorkspaceError):
            self.workspace.write("", "x")

    def test_move_target_cannot_escape(self):
        self.workspace.write("a.py", "a")
        with self.assertRaises(WorkspaceError):
            self.workspace.move("a.py", "../a.py")


class TreeAndStatsTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.workspace.write("app/service.py", "class Service: pass")
        self.workspace.write("app/util.py", "def helper(): pass")
        self.workspace.write("README.md", "# Docs")

    def test_tree_lists_folders_and_files(self):
        tree = self.workspace.tree()
        paths = {entry["path"] for entry in tree}
        self.assertIn("app", paths)
        self.assertIn("app/service.py", paths)
        self.assertIn("README.md", paths)
        folder = next(entry for entry in tree if entry["path"] == "app")
        self.assertEqual(folder["type"], "tree")

    def test_text_files_are_marked_editable(self):
        tree = self.workspace.tree()
        service = next(entry for entry in tree if entry["path"] == "app/service.py")
        self.assertTrue(service["editable"])

    def test_binary_is_not_editable(self):
        self.workspace.write_bytes("logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        tree = self.workspace.tree()
        logo = next(entry for entry in tree if entry["path"] == "logo.png")
        self.assertFalse(logo["editable"])
        with self.assertRaises(WorkspaceError):
            self.workspace.read("logo.png")

    def test_stats_count_the_tree(self):
        stats = self.workspace.stats()
        self.assertEqual(stats["files"], 3)
        self.assertGreater(stats["bytes"], 0)

    def test_vendored_folders_are_hidden(self):
        self.workspace.write("node_modules/pkg/index.js", "module.exports = {}")
        paths = {entry["path"] for entry in self.workspace.tree()}
        self.assertNotIn("node_modules", paths)


class BulkTests(WorkspaceTestCase):
    def test_write_many_reports_per_item_outcomes(self):
        result = self.workspace.write_many(
            [
                {"path": "a/one.py", "content": "1"},
                {"path": "a/two.py", "content": "2"},
                {"path": "../escape.py", "content": "no"},
            ]
        )
        self.assertEqual(sorted(result["written"]), ["a/one.py", "a/two.py"])
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(result["rejected"][0]["path"], "../escape.py")

    def test_export_zip_round_trips(self):
        self.workspace.write("app/service.py", "class Service: pass")
        self.workspace.write("README.md", "# Docs")
        payload = self.workspace.export_zip()

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            self.assertIn("app/service.py", names)
            self.assertIn("README.md", names)
            self.assertIn(b"class Service", archive.read("app/service.py"))

    def test_clear_empties_the_tree_but_keeps_the_root(self):
        self.workspace.write("a.py", "x")
        removed = self.workspace.clear()
        self.assertEqual(removed["files"], 1)
        self.assertEqual(self.workspace.tree(), [])
        self.assertTrue((self.tmp / "source").is_dir())


class UmlModelTests(WorkspaceTestCase):
    def test_models_are_listed_with_the_active_one_marked(self):
        (self.tmp / "uml" / "alpha.mdj").write_text("{}", encoding="utf-8")
        (self.tmp / "uml" / "beta.mdj").write_text("{}", encoding="utf-8")
        models = list_uml_models(str(self.tmp))
        self.assertEqual([m["filename"] for m in models], ["alpha.mdj", "beta.mdj"])
        self.assertTrue(models[0]["active"])
        self.assertFalse(models[1]["active"])

    def test_delete_removes_only_the_named_model(self):
        (self.tmp / "uml" / "alpha.mdj").write_text("{}", encoding="utf-8")
        (self.tmp / "uml" / "beta.mdj").write_text("{}", encoding="utf-8")
        delete_uml_model(str(self.tmp), "alpha.mdj")
        self.assertEqual([m["filename"] for m in list_uml_models(str(self.tmp))], ["beta.mdj"])

    def test_delete_rejects_traversal_and_non_models(self):
        for name in ("../../secret.mdj", "notes.txt", ""):
            with self.subTest(name=name):
                with self.assertRaises(WorkspaceError):
                    delete_uml_model(str(self.tmp), name)


if __name__ == "__main__":
    unittest.main()
