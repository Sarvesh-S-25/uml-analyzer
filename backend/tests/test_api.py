"""HTTP-level tests.

Includes the full manual workflow -- create a project, fill it through the
virtual directory, upload a diagram, analyse -- with GitHub never touched, since
that is the path most users take and the one that must never depend on git.

Skipped automatically when FastAPI/SQLAlchemy are not installed.
"""
import io
import json
import unittest
import zipfile

try:
    from fastapi.testclient import TestClient

    import main

    API_AVAILABLE = True
    SKIP_REASON = ""
except Exception as exc:
    API_AVAILABLE = False
    SKIP_REASON = f"API dependencies unavailable: {exc}"

try:
    import parsers.polyglot_parser  # noqa: F401

    PARSER_AVAILABLE = True
except Exception:
    PARSER_AVAILABLE = False


UML_MODEL = {
    "_type": "Project",
    "_id": "p",
    "ownedElements": [
        {
            "_type": "UMLClass",
            "_id": "c1",
            "name": "Service",
            "attributes": [
                {"_type": "UMLAttribute", "name": "repo", "type": {"$ref": "c2"}}
            ],
            "operations": [
                {"_type": "UMLOperation", "name": "run"},
                {"_type": "UMLOperation", "name": "missing_on_purpose"},
            ],
        },
        {
            "_type": "UMLClass",
            "_id": "c2",
            "name": "Repository",
            "attributes": [],
            "operations": [{"_type": "UMLOperation", "name": "save"}],
        },
        {
            "_type": "UMLAssociation",
            "_id": "a1",
            "end1": {"_type": "UMLAssociationEnd", "reference": {"$ref": "c1"}},
            "end2": {"_type": "UMLAssociationEnd", "reference": {"$ref": "c2"}},
        },
    ],
}

SERVICE_CODE = """
from repository import Repository


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    def run(self, payload):
        return self.repo.save(payload)
"""

REPOSITORY_CODE = """
class Repository:
    def save(self, payload):
        return True
"""


@unittest.skipUnless(API_AVAILABLE, SKIP_REASON)
class ApiTestCase(unittest.TestCase):
    client = None
    headers = None

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()
        cls.client.post(
            "/register",
            json={
                "username": "tester",
                "email": "tester@example.com",
                "password": "correct-horse",
            },
        )
        response = cls.client.post(
            "/login", data={"username": "tester", "password": "correct-horse"}
        )
        assert response.status_code == 200, response.text
        cls.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def make_project(self, name: str):
        response = self.client.post("/projects", json={"name": name}, headers=self.headers)
        assert response.status_code in (200, 400), response.text
        return name


class MetaTests(ApiTestCase):
    def test_health(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_config_does_not_leak_secrets(self):
        config = self.client.get("/config").json()
        self.assertIn("github_client_id", config)
        self.assertIn("gate_strategies", config)
        self.assertIn("available_models", config)
        self.assertNotIn("github_client_secret", config)
        self.assertNotIn("secret_key", config)

    def test_openapi_is_generated(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/projects/{project_name}/analyze", schema["paths"])
        self.assertIn("/projects/{project_name}/files", schema["paths"])


class AuthTests(ApiTestCase):
    def test_registration_validation(self):
        cases = [
            {"username": "ab", "email": "x@y.com", "password": "longenough"},
            {"username": "gooduser", "email": "not-an-email", "password": "longenough"},
            {"username": "gooduser", "email": "a@b.com", "password": "short"},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/register", json=payload).status_code, 422)

    def test_protected_routes_require_a_token(self):
        self.assertEqual(self.client.get("/projects").status_code, 401)
        self.assertEqual(self.client.get("/projects/x/versions").status_code, 401)
        self.assertEqual(self.client.get("/projects/x/tree").status_code, 401)

    def test_garbage_token_is_rejected(self):
        response = self.client.get(
            "/projects", headers={"Authorization": "Bearer not-a-real-token"}
        )
        self.assertEqual(response.status_code, 401)


class ProjectTests(ApiTestCase):
    def test_lifecycle(self):
        created = self.client.post("/projects", json={"name": "Demo App"}, headers=self.headers)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["project_name"], "Demo App")

        listing = self.client.get("/projects", headers=self.headers).json()["projects"]
        entry = next(p for p in listing if p["name"] == "Demo App")
        self.assertEqual(entry["file_count"], 0)
        self.assertFalse(entry["has_uml"])

        duplicate = self.client.post("/projects", json={"name": "Demo App"}, headers=self.headers)
        self.assertEqual(duplicate.status_code, 400)

        detail = self.client.get("/projects/Demo App", headers=self.headers).json()
        self.assertEqual(detail["name"], "Demo App")

        self.assertEqual(
            self.client.delete("/projects/Demo App", headers=self.headers).status_code, 200
        )

    def test_traversal_names_are_rejected(self):
        self.assertEqual(
            self.client.post("/projects", json={"name": "../../evil"}, headers=self.headers).status_code,
            400,
        )
        self.assertIn(
            self.client.delete("/projects/..%2F..", headers=self.headers).status_code, (400, 404)
        )

    def test_unknown_project_is_404(self):
        self.assertEqual(
            self.client.get("/projects/NoSuchProject/tree", headers=self.headers).status_code, 404
        )


class VirtualDirectoryTests(ApiTestCase):
    """The manual workflow: no GitHub, no git, no archive required."""

    def setUp(self):
        self.project = "Virtual Dir"
        self.make_project(self.project)
        self.client.delete(f"/projects/{self.project}/source", headers=self.headers)

    def url(self, suffix: str) -> str:
        return f"/projects/{self.project}{suffix}"

    def test_create_read_edit_and_delete_a_file(self):
        created = self.client.post(
            self.url("/files"),
            json={"path": "app/service.py", "content": "class Service:\n    pass\n"},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)

        read = self.client.get(
            self.url("/files"), params={"path": "app/service.py"}, headers=self.headers
        ).json()
        self.assertIn("class Service", read["content"])

        saved = self.client.put(
            self.url("/files"),
            json={"path": "app/service.py", "content": "class Service:\n    def run(self): pass\n"},
            headers=self.headers,
        )
        self.assertEqual(saved.status_code, 200)
        self.assertIn(
            "def run",
            self.client.get(
                self.url("/files"), params={"path": "app/service.py"}, headers=self.headers
            ).json()["content"],
        )

        self.assertEqual(
            self.client.delete(
                self.url("/files"), params={"path": "app/service.py"}, headers=self.headers
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                self.url("/files"), params={"path": "app/service.py"}, headers=self.headers
            ).status_code,
            400,
        )

    def test_create_refuses_to_clobber(self):
        self.client.post(
            self.url("/files"), json={"path": "a.py", "content": "1"}, headers=self.headers
        )
        second = self.client.post(
            self.url("/files"), json={"path": "a.py", "content": "2"}, headers=self.headers
        )
        self.assertEqual(second.status_code, 400)

    def test_folders_and_moves(self):
        self.assertEqual(
            self.client.post(
                self.url("/folders"), json={"path": "pkg"}, headers=self.headers
            ).status_code,
            200,
        )
        self.client.post(
            self.url("/files"), json={"path": "pkg/old.py", "content": "x = 1"}, headers=self.headers
        )
        moved = self.client.post(
            self.url("/files/move"),
            json={"source": "pkg/old.py", "destination": "pkg/new.py"},
            headers=self.headers,
        )
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(
            self.client.get(
                self.url("/files"), params={"path": "pkg/new.py"}, headers=self.headers
            ).status_code,
            200,
        )

    def test_traversal_is_refused_on_every_file_route(self):
        evil = "../../escaped.py"
        self.assertEqual(
            self.client.post(
                self.url("/files"), json={"path": evil, "content": "x"}, headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.put(
                self.url("/files"), json={"path": evil, "content": "x"}, headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                self.url("/files"), params={"path": evil}, headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.delete(
                self.url("/files"), params={"path": evil}, headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.url("/files/move"),
                json={"source": "a.py", "destination": evil},
                headers=self.headers,
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.url("/folders"), json={"path": evil}, headers=self.headers
            ).status_code,
            400,
        )

    def test_batch_write(self):
        response = self.client.post(
            self.url("/files/batch"),
            json={
                "files": [
                    {"path": "batch/one.py", "content": "one = 1"},
                    {"path": "batch/two.py", "content": "two = 2"},
                    {"path": "../nope.py", "content": "no"},
                ]
            },
            headers=self.headers,
        ).json()
        self.assertEqual(sorted(response["written"]), ["batch/one.py", "batch/two.py"])
        self.assertEqual(len(response["rejected"]), 1)

    def test_folder_upload_preserves_relative_paths(self):
        files = [
            ("files", ("service.py", b"class Service: pass", "text/plain")),
            ("files", ("util.py", b"def helper(): pass", "text/plain")),
        ]
        response = self.client.post(
            self.url("/upload/source-batch"),
            files=files,
            data={"paths": json.dumps(["app/service.py", "app/lib/util.py"])},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(response.json()["written"]), ["app/lib/util.py", "app/service.py"]
        )

        tree = self.client.get(self.url("/tree"), headers=self.headers).json()
        paths = {node["path"] for node in tree["tree"]}
        self.assertIn("app/service.py", paths)
        self.assertIn("app/lib/util.py", paths)
        self.assertEqual(tree["stats"]["files"], 2)

    def test_batch_upload_rejects_mismatched_path_count(self):
        response = self.client.post(
            self.url("/upload/source-batch"),
            files=[("files", ("a.py", b"a", "text/plain"))],
            data={"paths": json.dumps(["a.py", "b.py"])},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_zip_upload_rejects_unsafe_members(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("app/ok.py", "ok = True")
            archive.writestr("../escaped.py", "should never be written")

        response = self.client.post(
            self.url("/upload/source"),
            files={"file": ("code.zip", buffer.getvalue(), "application/zip")},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("../escaped.py", response.json()["extracted"]["rejected"])

    def test_export_returns_a_zip(self):
        self.client.post(
            self.url("/files"), json={"path": "app/a.py", "content": "a = 1"}, headers=self.headers
        )
        response = self.client.get(self.url("/export"), headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn("app/a.py", archive.namelist())

    def test_clear_empties_the_directory(self):
        self.client.post(
            self.url("/files"), json={"path": "a.py", "content": "x"}, headers=self.headers
        )
        self.client.delete(self.url("/source"), headers=self.headers)
        tree = self.client.get(self.url("/tree"), headers=self.headers).json()
        self.assertEqual(tree["tree"], [])


class UmlRouteTests(ApiTestCase):
    def setUp(self):
        self.project = "Uml Routes"
        self.make_project(self.project)

    def test_upload_list_and_delete(self):
        response = self.client.post(
            f"/projects/{self.project}/upload/uml",
            files={"file": ("design.mdj", json.dumps(UML_MODEL).encode(), "application/json")},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        models = response.json()["models"]
        self.assertEqual(models[0]["filename"], "design.mdj")
        self.assertTrue(models[0]["active"])

        listed = self.client.get(f"/projects/{self.project}/uml", headers=self.headers).json()
        self.assertEqual(len(listed["models"]), 1)

        removed = self.client.delete(
            f"/projects/{self.project}/uml/design.mdj", headers=self.headers
        )
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json()["models"], [])

    def test_malformed_model_is_rejected_at_upload_time(self):
        response = self.client.post(
            f"/projects/{self.project}/upload/uml",
            files={"file": ("design.mdj", b"{not json", "application/json")},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_non_mdj_is_rejected(self):
        response = self.client.post(
            f"/projects/{self.project}/upload/uml",
            files={"file": ("design.xml", b"<xml/>", "application/xml")},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_uml_delete_rejects_traversal(self):
        response = self.client.delete(
            f"/projects/{self.project}/uml/..%2F..%2Fsecret.mdj", headers=self.headers
        )
        self.assertIn(response.status_code, (400, 404))


@unittest.skipUnless(PARSER_AVAILABLE, "tree-sitter grammars unavailable")
class ManualWorkflowTests(ApiTestCase):
    """The original intent, end to end, without GitHub anywhere in the path."""

    def setUp(self):
        self.project = "Manual Flow"
        # Every test method in this class shares one project name (and, via
        # setUpClass, one underlying user and TestClient for the whole
        # class), so a project left over from a previous test -- its version
        # history and uploaded UML model included, not just its source files
        # -- was silently carried into the next one. Deleting and recreating
        # the project outright is the only reset that is actually complete;
        # clearing `/source` alone left `test_full_cycle` asserting
        # `version == 1` on a project that had already been analysed by
        # whichever test ran before it.
        self.client.delete(f"/projects/{self.project}", headers=self.headers)
        self.make_project(self.project)

    def url(self, suffix: str) -> str:
        return f"/projects/{self.project}{suffix}"

    def populate(self):
        self.client.post(
            self.url("/files/batch"),
            json={
                "files": [
                    {"path": "service.py", "content": SERVICE_CODE},
                    {"path": "repository.py", "content": REPOSITORY_CODE},
                ]
            },
            headers=self.headers,
        )
        self.client.post(
            self.url("/upload/uml"),
            files={"file": ("design.mdj", json.dumps(UML_MODEL).encode(), "application/json")},
            headers=self.headers,
        )

    def test_full_cycle(self):
        self.populate()

        first = self.client.post(self.url("/analyze"), json={}, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()

        self.assertEqual(body["version"], 1)
        self.assertTrue(body["gate"]["should_invoke_llm"])
        self.assertTrue(body["graph_data"]["nodes"])
        self.assertEqual(body["uml"]["element_count"], 2)
        self.assertGreaterEqual(body["uml"]["relation_count"], 1)

        # The diagram specifies an operation the code does not implement.
        missing = [
            method
            for element in body["difference"]["element_differences"]
            for method in element["missing_methods"]
        ]
        self.assertIn("missing_on_purpose", missing)

        # The association is backed by a typed field, so the evidence is strong.
        associations = [
            finding
            for finding in body["difference"]["relation_findings"]
            if finding["relation"] == "association"
        ]
        self.assertTrue(associations)
        self.assertEqual(associations[0]["evidence"], "strong")

        # Cross-file call resolution linked Service.run to Repository.save.
        self.assertGreater(body["call_resolution"]["total_call_sites"], 0)
        self.assertGreater(body["call_resolution"]["resolved"], 0)

        second = self.client.post(self.url("/analyze"), json={}, headers=self.headers).json()
        self.assertFalse(second["gate"]["should_invoke_llm"])
        self.assertEqual(second["reused_from_version"], 1)

    def test_editing_a_file_in_the_browser_triggers_reanalysis(self):
        self.populate()
        self.client.post(self.url("/analyze"), json={}, headers=self.headers)

        # A comment-only edit must not.
        self.client.put(
            self.url("/files"),
            json={"path": "service.py", "content": "# a comment\n" + SERVICE_CODE},
            headers=self.headers,
        )
        commented = self.client.post(self.url("/analyze"), json={}, headers=self.headers).json()
        self.assertFalse(commented["gate"]["should_invoke_llm"])

        # Adding the designed-but-missing method must.
        self.client.put(
            self.url("/files"),
            json={
                "path": "service.py",
                "content": SERVICE_CODE + "\n    def missing_on_purpose(self):\n        return 1\n",
            },
            headers=self.headers,
        )
        changed = self.client.post(self.url("/analyze"), json={}, headers=self.headers).json()
        self.assertTrue(changed["gate"]["should_invoke_llm"])

    def test_versions_metrics_and_benchmark(self):
        self.populate()
        self.client.post(self.url("/analyze"), json={}, headers=self.headers)
        self.client.post(self.url("/analyze"), json={}, headers=self.headers)

        versions = self.client.get(self.url("/versions"), headers=self.headers).json()
        self.assertEqual(versions["max_versions"], 3)
        self.assertEqual(len(versions["versions"]), 2)

        graph = self.client.get(self.url("/versions/1/graph"), headers=self.headers)
        self.assertEqual(graph.status_code, 200)
        self.assertTrue(graph.json()["graph_data"]["nodes"])

        diff = self.client.get(
            self.url("/versions/diff"),
            params={"from_version": 1, "to_version": 2},
            headers=self.headers,
        )
        self.assertEqual(diff.status_code, 200)

        metrics = self.client.get(self.url("/metrics"), headers=self.headers).json()["metrics"]
        self.assertEqual(metrics["total_runs"], 2)
        self.assertEqual(metrics["cached_runs"], 1)

        benchmark = self.client.get(self.url("/benchmark"), headers=self.headers)
        self.assertEqual(benchmark.status_code, 200)
        self.assertIn("token_reduction_percentage", benchmark.json())

    def test_repeatability_is_stable_offline(self):
        self.populate()
        response = self.client.post(
            self.url("/repeatability"), json={"runs": 3}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["similarity_score"]["stdev"], 0.0)

    def test_model_comparison_does_not_write_history(self):
        self.populate()
        self.client.post(self.url("/analyze"), json={}, headers=self.headers)
        before = len(self.client.get(self.url("/versions"), headers=self.headers).json()["versions"])

        response = self.client.post(
            self.url("/model-comparison"), json={"models": []}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["models"])

        after = len(self.client.get(self.url("/versions"), headers=self.headers).json()["versions"])
        self.assertEqual(before, after)

    def test_unknown_gate_strategy_is_rejected(self):
        response = self.client.post(
            self.url("/analyze"), json={"gate_strategy": "telepathy"}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_explain_rejects_traversal(self):
        response = self.client.post(
            self.url("/explain"), json={"file_path": "../../../../.env"}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)


class WebhookTests(ApiTestCase):
    def test_non_push_events_are_ignored(self):
        response = self.client.post(
            "/github/webhook", json={"zen": "hi"}, headers={"X-GitHub-Event": "ping"}
        )
        self.assertEqual(response.json()["status"], "ignored")

    def test_changed_files_are_collected(self):
        payload = {
            "repository": {"full_name": "octocat/demo"},
            "commits": [{"added": ["a.py"], "modified": ["b.py"], "removed": ["c.py"]}],
        }
        body = self.client.post(
            "/github/webhook", json=payload, headers={"X-GitHub-Event": "push"}
        ).json()
        self.assertEqual(body["status"], "webhook_received")
        self.assertEqual(set(body["modified_files"]), {"a.py", "b.py", "c.py"})


if __name__ == "__main__":
    unittest.main()
