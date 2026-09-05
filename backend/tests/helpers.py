"""Shared fixtures: synthetic architectures in the exact shape the parser emits.

Building these by hand lets the gate, resolution, versioning and reporting logic
be tested deterministically and without a native tree-sitter build, while the
parser itself is tested separately against real source files.
"""
import hashlib
import json
from typing import Any, Dict, List, Optional


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def make_call(name: str, receiver: Optional[str] = None, instantiation: bool = False):
    return {"name": name, "receiver": receiver, "instantiation": instantiation}


def make_method(
    name: str,
    params: int = 1,
    calls: Optional[List[Dict[str, Any]]] = None,
    param_types: Optional[List[Optional[str]]] = None,
    param_names: Optional[List[str]] = None,
    returns: Optional[str] = None,
    local_types: Optional[Dict[str, str]] = None,
):
    calls = calls or []
    return {
        "name": name,
        "params": params,
        "param_types": param_types or [None] * params,
        "param_names": param_names or [f"arg{index}" for index in range(params)],
        "returns": returns,
        "calls": sorted({call["name"] for call in calls}),
        "call_refs": calls,
        "local_types": local_types or {},
    }


def make_field(name: str, type_name: Optional[str] = None):
    return {"name": name, "type": type_name}


def make_class(name, methods=None, fields=None, bases=None, kind="class"):
    return {
        "name": name,
        "kind": kind,
        "bases": sorted(bases or []),
        "fields": sorted(fields or [], key=lambda field: field["name"]),
        "methods": sorted(methods or [], key=lambda method: method["name"]),
    }


def make_file(
    path: str,
    classes: Optional[List[Dict[str, Any]]] = None,
    functions: Optional[List[Dict[str, Any]]] = None,
    imports: Optional[List[str]] = None,
    import_bindings: Optional[List[Dict[str, Any]]] = None,
    text_salt: str = "",
    language: str = "python",
) -> Dict[str, Any]:
    """One file record.

    `text_salt` simulates a comment-only edit: it changes the raw-bytes hash
    without touching the structural hash.
    """
    classes = classes or []
    functions = functions or []
    imports = sorted(imports or [])

    def callable_view(entry):
        return {
            "name": entry["name"],
            "params": entry["params"],
            "param_types": entry["param_types"],
            "returns": entry["returns"],
            "calls": entry["calls"],
        }

    structure = {
        "imports": imports,
        "classes": [
            {
                "name": klass["name"],
                "kind": klass["kind"],
                "bases": klass["bases"],
                "fields": klass["fields"],
                "methods": [callable_view(method) for method in klass["methods"]],
            }
            for klass in classes
        ],
        "functions": [callable_view(function) for function in functions],
    }

    return {
        "file_path": path,
        "language": language,
        "grammar": language,
        "loc": 40,
        "text_sha256": canonical_hash([structure, text_salt]),
        "structure_sha256": canonical_hash(structure),
        "imports": imports,
        "import_bindings": import_bindings or [],
        "classes": classes,
        "functions": functions,
        "parse_error": False,
    }


def make_architecture(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    files = sorted(files, key=lambda record: record["file_path"])
    return {
        "files": files,
        "project_structure_sha256": canonical_hash(
            [[f["file_path"], f["structure_sha256"]] for f in files]
        ),
        "project_text_sha256": canonical_hash(
            [[f["file_path"], f["text_sha256"]] for f in files]
        ),
        "parse_errors": [],
        "typescript_grammar": True,
        "files_without_types": [],
    }


# --- concrete scenarios ------------------------------------------------------


def arch_base(text_salt: str = "") -> Dict[str, Any]:
    return make_architecture(
        [
            make_file(
                "orders.py",
                classes=[
                    make_class(
                        "OrderService",
                        fields=[make_field("repo", "OrderRepository")],
                        methods=[
                            make_method(
                                "place", 2, [make_call("save", "self.repo")], returns="bool"
                            )
                        ],
                    ),
                    make_class("OrderRepository", methods=[make_method("save", 2)]),
                ],
                text_salt=text_salt,
            )
        ]
    )


def arch_comment_only() -> Dict[str, Any]:
    """Same structure, different bytes -- a comment or reformat."""
    return arch_base(text_salt="a new comment")


def arch_renamed() -> Dict[str, Any]:
    """Identical shape, different identifiers -- a pure rename."""
    return make_architecture(
        [
            make_file(
                "orders.py",
                classes=[
                    make_class(
                        "PurchaseService",
                        fields=[make_field("repo", "PurchaseRepository")],
                        methods=[
                            make_method(
                                "place", 2, [make_call("save", "self.repo")], returns="bool"
                            )
                        ],
                    ),
                    make_class("PurchaseRepository", methods=[make_method("save", 2)]),
                ],
            )
        ]
    )


def arch_new_method() -> Dict[str, Any]:
    """A genuine structural addition."""
    return make_architecture(
        [
            make_file(
                "orders.py",
                classes=[
                    make_class(
                        "OrderService",
                        fields=[make_field("repo", "OrderRepository")],
                        methods=[
                            make_method(
                                "place", 2, [make_call("save", "self.repo")], returns="bool"
                            ),
                            make_method(
                                "cancel", 2, [make_call("delete", "self.repo")], returns="bool"
                            ),
                        ],
                    ),
                    make_class(
                        "OrderRepository",
                        methods=[make_method("save", 2), make_method("delete", 2)],
                    ),
                ],
            )
        ]
    )


def arch_cross_file() -> Dict[str, Any]:
    """Two files: a service importing and calling a repository in another module."""
    return make_architecture(
        [
            make_file(
                "app/repository.py",
                classes=[
                    make_class(
                        "OrderRepository",
                        methods=[make_method("save", 2), make_method("delete", 2)],
                    )
                ],
            ),
            make_file(
                "app/service.py",
                classes=[
                    make_class(
                        "OrderService",
                        fields=[make_field("repo", "OrderRepository")],
                        methods=[
                            make_method(
                                "place",
                                2,
                                [make_call("save", "self.repo")],
                                param_types=[None, "Order"],
                            ),
                            make_method(
                                "build",
                                1,
                                [make_call("OrderRepository", None, instantiation=True)],
                            ),
                        ],
                    )
                ],
                imports=["app.repository"],
                import_bindings=[
                    {"module": "app.repository", "symbol": "OrderRepository", "alias": None}
                ],
            ),
        ]
    )


def arch_ambiguous_calls() -> Dict[str, Any]:
    """Two unrelated classes both defining `save`, called without a receiver."""
    return make_architecture(
        [
            make_file(
                "a.py",
                classes=[make_class("Alpha", methods=[make_method("save", 1)])],
            ),
            make_file(
                "b.py",
                classes=[make_class("Beta", methods=[make_method("save", 1)])],
            ),
            make_file(
                "c.py",
                functions=[make_method("run", 0, [make_call("save")])],
            ),
        ]
    )


def arch_layering_violation() -> Dict[str, Any]:
    """A controller that reaches the repository directly."""
    return make_architecture(
        [
            make_file(
                "api/order_controller.py",
                classes=[
                    make_class(
                        "OrderController",
                        methods=[
                            make_method(
                                "get", 1, [make_call("repository"), make_call("render")]
                            )
                        ],
                    )
                ],
                imports=["app.repository"],
            )
        ]
    )


def arch_with_association(typed: bool = True) -> Dict[str, Any]:
    """OrderService holding an OrderRepository, with or without a declared type."""
    return make_architecture(
        [
            make_file(
                "orders.py",
                classes=[
                    make_class(
                        "OrderService",
                        fields=[make_field("repo", "OrderRepository" if typed else None)],
                        methods=[make_method("place", 2, [make_call("save", "self.repo")])],
                    ),
                    make_class("OrderRepository", methods=[make_method("save", 2)]),
                ],
            )
        ]
    )


# --- UML fixtures -------------------------------------------------------------

UML_MODEL = {
    "_type": "Project",
    "_id": "p1",
    "name": "Design",
    "ownedElements": [
        {
            "_type": "UMLModel",
            "_id": "m1",
            "ownedElements": [
                {
                    "_type": "UMLClass",
                    "_id": "c1",
                    "name": "OrderService",
                    "attributes": [
                        {"_type": "UMLAttribute", "name": "repo", "type": {"$ref": "c2"}}
                    ],
                    "operations": [
                        {"_type": "UMLOperation", "name": "place", "parameters": []},
                        {"_type": "UMLOperation", "name": "refund", "parameters": []},
                    ],
                },
                {
                    "_type": "UMLClass",
                    "_id": "c2",
                    "name": "OrderRepository",
                    "attributes": [],
                    "operations": [{"_type": "UMLOperation", "name": "save"}],
                },
                {
                    "_type": "UMLClass",
                    "_id": "c3",
                    "name": "AuditLog",
                    "attributes": [],
                    "operations": [],
                },
                {
                    "_type": "UMLGeneralization",
                    "_id": "g1",
                    "source": {"$ref": "c3"},
                    "target": {"$ref": "c1"},
                },
                {
                    "_type": "UMLAssociation",
                    "_id": "a1",
                    "end1": {"_type": "UMLAssociationEnd", "reference": {"$ref": "c1"}},
                    "end2": {"_type": "UMLAssociationEnd", "reference": {"$ref": "c2"}},
                },
            ],
        }
    ],
}


def write_project(root, *, with_uml: bool = True, uml_model: Optional[Dict] = None):
    """Create the on-disk project layout the pipeline expects."""
    (root / "source").mkdir(parents=True, exist_ok=True)
    (root / "uml").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    if with_uml:
        (root / "uml" / "design.mdj").write_text(
            json.dumps(uml_model or UML_MODEL), encoding="utf-8"
        )
    return root
