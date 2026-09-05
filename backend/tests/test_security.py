"""Regression tests for the traversal and archive-extraction fixes."""
import io
import os
import tempfile
import unittest
import zipfile

from core.archive import ArchiveError, extract_zip
from core.paths import UnsafePathError, resolve_within, safe_relative_member, sanitize_project_name


class ProjectNameTests(unittest.TestCase):
    def test_traversal_names_are_rejected(self):
        for candidate in ["../..", "../../etc", "..", "", "   ", "a/b", "x" * 65,
                          "..\\..\\windows", "sub/dir"]:
            with self.subTest(candidate=candidate):
                with self.assertRaises(UnsafePathError):
                    sanitize_project_name(candidate)

    def test_ordinary_names_survive(self):
        self.assertEqual(sanitize_project_name("My Project_1"), "My Project_1")
        self.assertEqual(sanitize_project_name("  Trimmed  "), "Trimmed")

    def test_benign_punctuation_is_stripped_not_rejected(self):
        self.assertEqual(sanitize_project_name("my.app"), "myapp")
        self.assertEqual(sanitize_project_name("repo (v2)"), "repo v2")


class ContainmentTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_normal_join_is_allowed(self):
        self.assertTrue(resolve_within(self.root, "a", "b").startswith(self.root))

    def test_escape_is_blocked(self):
        for parts in (("..", "..", "etc"), ("../../../../.env",), ("sub/../../../out",)):
            with self.subTest(parts=parts):
                with self.assertRaises(UnsafePathError):
                    resolve_within(self.root, *parts)


class ArchiveMemberTests(unittest.TestCase):
    def test_member_validation(self):
        self.assertIsNotNone(safe_relative_member("a/b.py"))
        self.assertIsNone(safe_relative_member("../evil.py"))
        self.assertIsNone(safe_relative_member("/etc/passwd"))
        self.assertIsNone(safe_relative_member("C:/Windows/system32"))
        self.assertIsNone(safe_relative_member("dir/"))


def _zip_with(names):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "print('x')\n")
    return buffer.getvalue()


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.destination = os.path.join(self.tmp, "out")

    def test_zip_slip_member_is_rejected(self):
        report = extract_zip(_zip_with(["../../escaped.py", "safe.py"]), self.destination)
        self.assertEqual(report["written"], 1)
        self.assertIn("../../escaped.py", report["rejected"])
        self.assertTrue(os.path.exists(os.path.join(self.destination, "safe.py")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escaped.py")))

    def test_github_wrapper_directory_is_stripped(self):
        extract_zip(_zip_with(["repo-abc123/src/app.py"]), self.destination, strip_root=True)
        self.assertTrue(os.path.exists(os.path.join(self.destination, "src", "app.py")))

    def test_non_archive_raises(self):
        with self.assertRaises(ArchiveError):
            extract_zip(b"not a zip file at all", self.destination)


if __name__ == "__main__":
    unittest.main()
