"""Deterministic, language-agnostic structural extraction via tree-sitter.

What each declaration carries, and why:

* **Call sites with their receiver** (`self.repo.save` -> receiver `self.repo`,
  name `save`), so calls can be resolved to a specific target instead of to
  every same-named definition in the project.
* **Import bindings** (module, symbol, alias), so a call to an imported symbol
  resolves across files.
* **Types** on fields, parameters and returns, so UML associations can be
  checked against real type references rather than guessed from names.
* **Local variable types** from `x = ClassName(...)`, so a call through a local
  binding resolves too.

Fingerprint discipline: `structure_sha256` covers declarations, types, imports
and the *leaf* names of calls -- but NOT receivers, local variable names, or
call-site detail. Renaming a local variable therefore does not force a
re-analysis, while adding a call to a different collaborator does.

TypeScript: parsed with the TypeScript grammar when `tree-sitter-typescript` is
installed, otherwise with the JavaScript grammar, which cannot see type
annotations. Which grammar was used is recorded per file so a study can exclude
files that were parsed without types.
"""
import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
JAVA_LANGUAGE = Language(tsjava.language())

# Optional: real TypeScript/TSX grammars. Without them .ts/.tsx still parse,
# but type annotations are invisible.
try:
    import tree_sitter_typescript as tstypescript

    TS_LANGUAGE = Language(tstypescript.language_typescript())
    TSX_LANGUAGE = Language(tstypescript.language_tsx())
    TYPESCRIPT_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the install
    TS_LANGUAGE = JS_LANGUAGE
    TSX_LANGUAGE = JS_LANGUAGE
    TYPESCRIPT_AVAILABLE = False


EXT_LANGUAGE: Dict[str, Tuple[str, Language, str]] = {
    ".py": ("python", PY_LANGUAGE, "python"),
    ".js": ("javascript", JS_LANGUAGE, "javascript"),
    ".jsx": ("javascript", JS_LANGUAGE, "javascript"),
    ".mjs": ("javascript", JS_LANGUAGE, "javascript"),
    ".ts": ("typescript", TS_LANGUAGE, "typescript" if TYPESCRIPT_AVAILABLE else "javascript"),
    ".tsx": ("typescript", TSX_LANGUAGE, "typescript" if TYPESCRIPT_AVAILABLE else "javascript"),
    ".java": ("java", JAVA_LANGUAGE, "java"),
}

CLASS_NODES = {
    "class_definition",
    "class_declaration",
    "interface_declaration",
    "abstract_class_declaration",
    "enum_declaration",
}
FUNCTION_NODES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "constructor_declaration",
    "method_signature",
    "function_signature",
}
CALL_NODES = {
    "call",
    "call_expression",
    "method_invocation",
    "object_creation_expression",
    "new_expression",
}
INSTANTIATION_NODES = {"object_creation_expression", "new_expression"}
IMPORT_NODES = {
    "import_statement",
    "import_from_statement",
    "import_declaration",
}

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".idea", ".vscode", "target", ".mypy_cache", ".pytest_cache", "site-packages",
    ".next", "coverage", ".tox", "bin", "obj",
}

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CALLS_PER_CALLABLE = 96
SELF_RECEIVERS = {"self", "this"}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_hash(obj: Any) -> str:
    return _sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class PolyglotParser:
    """Walks a source tree and returns a language-neutral architecture dict."""

    def __init__(self, source_dir: str):
        self.source_dir = source_dir
        self.parser = Parser()

    # -- public API -----------------------------------------------------------

    def parse(self) -> Dict[str, Any]:
        files: List[Dict[str, Any]] = []

        if not os.path.isdir(self.source_dir):
            return _empty_architecture()

        for root, dirs, filenames in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for filename in sorted(filenames):
                extension = os.path.splitext(filename)[1].lower()
                if extension not in EXT_LANGUAGE:
                    continue
                absolute = os.path.join(root, filename)
                try:
                    if os.path.getsize(absolute) > MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                record = self._parse_file(absolute, *EXT_LANGUAGE[extension])
                if record:
                    files.append(record)

        files.sort(key=lambda record: record["file_path"])

        return {
            "files": files,
            "project_structure_sha256": canonical_hash(
                [[f["file_path"], f["structure_sha256"]] for f in files]
            ),
            "project_text_sha256": canonical_hash(
                [[f["file_path"], f["text_sha256"]] for f in files]
            ),
            "parse_errors": [f["file_path"] for f in files if f.get("parse_error")],
            "typescript_grammar": TYPESCRIPT_AVAILABLE,
            "files_without_types": sorted(
                f["file_path"]
                for f in files
                if f["language"] == "typescript" and f["grammar"] != "typescript"
            ),
        }

    # -- per file -------------------------------------------------------------

    def _parse_file(
        self, absolute: str, language_name: str, language: Language, grammar: str
    ) -> Optional[Dict[str, Any]]:
        try:
            with open(absolute, "rb") as handle:
                code = handle.read()
        except OSError:
            return None

        relative = os.path.relpath(absolute, self.source_dir).replace(os.sep, "/")
        record: Dict[str, Any] = {
            "file_path": relative,
            "language": language_name,
            "grammar": grammar,
            "loc": code.count(b"\n") + 1,
            "text_sha256": _sha256(code),
            "imports": [],
            "import_bindings": [],
            "classes": [],
            "functions": [],
            "parse_error": False,
        }

        try:
            self.parser.language = language
            tree = self.parser.parse(code)
        except Exception:
            record["parse_error"] = True
            record["structure_sha256"] = canonical_hash({"error": relative})
            return record

        if tree.root_node.has_error:
            # tree-sitter recovers rather than raising; surface it instead of
            # silently trusting a partial tree.
            record["parse_error"] = True

        try:
            self._collect(tree.root_node, code, record, None)
        except RecursionError:
            record["parse_error"] = True

        self._normalise(record)
        record["structure_sha256"] = canonical_hash(self._fingerprint_view(record))
        return record

    def _normalise(self, record: Dict[str, Any]):
        record["imports"] = sorted(set(record["imports"]))
        record["import_bindings"].sort(key=lambda b: (b["module"], b["symbol"] or ""))
        record["classes"].sort(key=lambda c: c["name"])
        record["functions"].sort(key=lambda f: f["name"])
        for klass in record["classes"]:
            klass["methods"].sort(key=lambda m: (m["name"], m["params"]))
            klass["bases"] = sorted(set(klass["bases"]))
            deduped: Dict[str, Dict[str, Any]] = {}
            for field in klass["fields"]:
                existing = deduped.get(field["name"])
                # A typed declaration beats an untyped assignment for the same name.
                if existing is None or (existing["type"] is None and field["type"]):
                    deduped[field["name"]] = field
            klass["fields"] = [deduped[name] for name in sorted(deduped)]

    @staticmethod
    def _fingerprint_view(record: Dict[str, Any]) -> Dict[str, Any]:
        """The projection that decides whether a re-analysis is needed.

        Receivers, local variable names and call-site ordering are deliberately
        excluded: renaming a local must not look like an architectural change.
        """
        def callable_view(entry: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "name": entry["name"],
                "params": entry["params"],
                "param_types": entry["param_types"],
                "returns": entry["returns"],
                "calls": entry["calls"],
            }

        return {
            "imports": record["imports"],
            "classes": [
                {
                    "name": klass["name"],
                    "kind": klass["kind"],
                    "bases": klass["bases"],
                    "fields": klass["fields"],
                    "methods": [callable_view(method) for method in klass["methods"]],
                }
                for klass in record["classes"]
            ],
            "functions": [callable_view(function) for function in record["functions"]],
        }

    # -- node helpers ---------------------------------------------------------

    def _text(self, node, code: bytes) -> str:
        return code[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _name_of(self, node, code: bytes) -> Optional[str]:
        named = node.child_by_field_name("name")
        if named is not None:
            return self._text(named, code)
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier"):
                return self._text(child, code)
        return None

    def _type_text(self, node, code: bytes) -> Optional[str]:
        if node is None:
            return None
        text = self._text(node, code).strip()
        text = text.lstrip(":").strip()
        if not text:
            return None
        # Reduce `List[Order]`, `Optional[Repo]`, `Repo<T>` to the informative
        # head; the container is rarely the modelled relationship.
        for opener in ("[", "<", "("):
            if opener in text:
                head, _, inner = text.partition(opener)
                head = head.strip()
                if head in ("List", "list", "Optional", "Set", "set", "Iterable", "Sequence",
                            "Array", "Collection", "ArrayList", "Mapping"):
                    text = inner.rstrip("]>)").split(",")[-1].strip()
                else:
                    text = head
                break
        text = text.split("|")[0].strip().strip('"').strip("'")
        return text or None

    def _parameters(self, node, code: bytes) -> List[Dict[str, Optional[str]]]:
        container = node.child_by_field_name("parameters")
        if container is None:
            for child in node.children:
                if child.type in ("parameters", "formal_parameters", "parameter_list"):
                    container = child
                    break
        if container is None:
            return []

        parameters: List[Dict[str, Optional[str]]] = []
        for child in container.children:
            if not child.is_named or child.type in ("comment",):
                continue
            if child.type == "identifier":
                parameters.append({"name": self._text(child, code), "type": None})
                continue
            name_node = child.child_by_field_name("name") or child.child_by_field_name("pattern")
            type_node = child.child_by_field_name("type")
            if type_node is not None and type_node.type == "type_annotation":
                type_node = type_node.children[-1] if type_node.children else None
            name = self._text(name_node, code) if name_node is not None else None
            if name is None:
                text = self._text(child, code)
                name = text.split(":")[0].split("=")[0].strip() or None
            if name in ("self", "this"):
                continue
            parameters.append({"name": name, "type": self._type_text(type_node, code)})
        return parameters

    def _return_type(self, node, code: bytes) -> Optional[str]:
        for field in ("return_type", "type"):
            candidate = node.child_by_field_name(field)
            if candidate is not None:
                if candidate.type == "type_annotation" and candidate.children:
                    candidate = candidate.children[-1]
                return self._type_text(candidate, code)
        return None

    def _split_callee(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """`self.repo.save` -> (receiver `self.repo`, name `save`)."""
        cleaned = " ".join(text.split())
        cleaned = cleaned.split("(")[0].strip()
        if not cleaned or len(cleaned) > 200:
            return None, None
        parts = [part for part in cleaned.split(".") if part]
        if not parts:
            return None, None
        name = parts[-1].strip()
        if not name.isidentifier():
            return None, None
        receiver = ".".join(parts[:-1]) or None
        return receiver, name

    def _call_sites(self, node, code: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Callee names and call-site detail, not descending into nested declarations."""
        refs: List[Dict[str, Any]] = []

        def walk(current, depth: int):
            if depth > 0 and current.type in CLASS_NODES | FUNCTION_NODES:
                return
            if current.type in CALL_NODES:
                target = (
                    current.child_by_field_name("function")
                    or current.child_by_field_name("name")
                    or current.child_by_field_name("constructor")
                    or current.child_by_field_name("type")
                )
                receiver_node = current.child_by_field_name("object")
                if target is not None:
                    receiver, name = self._split_callee(self._text(target, code))
                    if receiver is None and receiver_node is not None:
                        receiver = " ".join(self._text(receiver_node, code).split())[:120] or None
                    if name:
                        refs.append(
                            {
                                "name": name,
                                "receiver": receiver,
                                "instantiation": current.type in INSTANTIATION_NODES,
                            }
                        )
            for child in current.children:
                walk(child, depth + 1)

        for child in node.children:
            walk(child, 0)

        refs = refs[:MAX_CALLS_PER_CALLABLE]
        names = sorted({ref["name"] for ref in refs})
        return names, refs

    def _local_types(self, node, code: bytes) -> Dict[str, str]:
        """`repo = OrderRepository()` / `Repo repo = new Repo()` -> {repo: Repo}."""
        bindings: Dict[str, str] = {}

        def record(name: Optional[str], type_name: Optional[str]):
            if name and type_name and name.isidentifier() and type_name[:1].isupper():
                bindings.setdefault(name, type_name)

        def walk(current, depth: int):
            if depth > 0 and current.type in CLASS_NODES | FUNCTION_NODES:
                return
            if current.type in ("assignment", "variable_declarator"):
                left = current.child_by_field_name("left") or current.child_by_field_name("name")
                right = current.child_by_field_name("right") or current.child_by_field_name("value")
                declared = current.child_by_field_name("type")
                if left is not None:
                    name = self._text(left, code).strip()
                    if declared is not None:
                        record(name, self._type_text(declared, code))
                    elif right is not None and right.type in CALL_NODES:
                        callee = (
                            right.child_by_field_name("function")
                            or right.child_by_field_name("constructor")
                            or right.child_by_field_name("type")
                        )
                        if callee is not None:
                            _, type_name = self._split_callee(self._text(callee, code))
                            record(name, type_name)
            elif current.type == "local_variable_declaration":
                declared = current.child_by_field_name("type")
                type_name = self._type_text(declared, code) if declared is not None else None
                for child in current.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        if name_node is not None:
                            record(self._text(name_node, code), type_name)
            for child in current.children:
                walk(child, depth + 1)

        for child in node.children:
            walk(child, 0)
        return bindings

    def _bases(self, node, code: bytes) -> List[str]:
        bases: List[str] = []
        containers = []
        for field in ("superclass", "interfaces", "superclasses"):
            candidate = node.child_by_field_name(field)
            if candidate is not None:
                containers.append(candidate)
        for child in node.children:
            if child.type in (
                "argument_list", "superclass", "super_interfaces", "extends_interfaces",
                "class_heritage", "extends_clause", "implements_clause", "type_list",
            ):
                containers.append(child)

        for container in containers:
            for sub in container.children:
                if sub.type in ("identifier", "type_identifier", "generic_type", "attribute",
                                "scoped_type_identifier"):
                    name = self._type_text(sub, code)
                    if name:
                        bases.append(name)
                elif sub.type in ("extends_clause", "implements_clause", "type_list"):
                    for inner in sub.children:
                        if inner.type in ("identifier", "type_identifier", "generic_type"):
                            name = self._type_text(inner, code)
                            if name:
                                bases.append(name)
        return [base for base in bases if base and base not in ("object", "Object")]

    def _fields(self, node, code: bytes) -> List[Dict[str, Optional[str]]]:
        fields: List[Dict[str, Optional[str]]] = []

        def walk(current, depth: int, param_types: Dict[str, Optional[str]]):
            if depth > 0 and current.type in CLASS_NODES:
                return
            if current.type in FUNCTION_NODES:
                # Re-scoped for every method: a name that is a constructor
                # parameter in `__init__` means nothing about a same-named
                # parameter, or lack of one, in a sibling method.
                param_types = {
                    p["name"]: p["type"] for p in self._parameters(current, code) if p["name"]
                }
            if current.type in (
                "field_declaration", "field_definition", "public_field_definition",
                "property_signature",
            ):
                declared = current.child_by_field_name("type")
                if declared is not None and declared.type == "type_annotation" and declared.children:
                    declared = declared.children[-1]
                type_name = self._type_text(declared, code) if declared is not None else None
                found = False
                for sub in current.children:
                    if sub.type == "variable_declarator":
                        name_node = sub.child_by_field_name("name")
                        if name_node is not None:
                            fields.append(
                                {"name": self._text(name_node, code), "type": type_name}
                            )
                            found = True
                    elif sub.type in ("property_identifier", "identifier") and not found:
                        fields.append({"name": self._text(sub, code), "type": type_name})
                        found = True
                if not found:
                    declarator = current.child_by_field_name("declarator")
                    if declarator is not None:
                        name = self._name_of(declarator, code)
                        if name:
                            fields.append({"name": name, "type": type_name})
            # Python has no field declarations; `self.x = ...` inside any method
            # is the closest equivalent.
            if current.type == "assignment":
                left = current.child_by_field_name("left")
                right = current.child_by_field_name("right")
                if left is not None and left.type == "attribute":
                    text = self._text(left, code)
                    if text.startswith(("self.", "this.")):
                        leaf = text.split(".", 1)[1]
                        if leaf.isidentifier():
                            type_name = None
                            declared = current.child_by_field_name("type")
                            if declared is not None:
                                type_name = self._type_text(declared, code)
                            elif right is not None and right.type in CALL_NODES:
                                callee = right.child_by_field_name("function")
                                if callee is not None:
                                    _, candidate = self._split_callee(self._text(callee, code))
                                    if candidate and candidate[:1].isupper():
                                        type_name = candidate
                            elif right is not None and right.type == "identifier":
                                # `self.repo = repo`: no annotation on the
                                # assignment itself, but if the right-hand
                                # name is a parameter of the enclosing method
                                # (almost always `__init__`), that parameter's
                                # own annotation *is* the type being stored.
                                # This is the single most common way a Python
                                # field acquires a type in practice; missing
                                # it was undercounting call resolution (and
                                # this exact case) on real, typed code.
                                type_name = param_types.get(self._text(right, code))
                            fields.append({"name": leaf, "type": type_name})
            for child in current.children:
                walk(child, depth + 1, param_types)

        for child in node.children:
            walk(child, 0, {})
        return fields

    def _callable_record(self, node, code: bytes) -> Optional[Dict[str, Any]]:
        name = self._name_of(node, code)
        if not name:
            return None
        parameters = self._parameters(node, code)
        calls, refs = self._call_sites(node, code)
        return {
            "name": name,
            "params": len(parameters),
            "param_types": [p["type"] for p in parameters],
            "param_names": [p["name"] for p in parameters],
            "returns": self._return_type(node, code),
            "calls": calls,
            "call_refs": refs,
            "local_types": self._local_types(node, code),
        }

    # -- traversal ------------------------------------------------------------

    def _collect(self, node, code: bytes, record: Dict[str, Any], enclosing_class):
        for child in node.children:
            if child.type in IMPORT_NODES:
                self._record_import(child, code, record)
                continue

            if child.type in CLASS_NODES:
                name = self._name_of(child, code)
                if name:
                    kind = "interface" if child.type == "interface_declaration" else "class"
                    if child.type == "enum_declaration":
                        kind = "enum"
                    klass = {
                        "name": name,
                        "kind": kind,
                        "bases": self._bases(child, code),
                        "fields": self._fields(child, code),
                        "methods": [],
                    }
                    record["classes"].append(klass)
                    self._collect(child, code, record, klass)
                    continue

            if child.type in FUNCTION_NODES:
                entry = self._callable_record(child, code)
                if entry is not None:
                    entry["owner"] = enclosing_class["name"] if enclosing_class else None
                    if enclosing_class is not None:
                        enclosing_class["methods"].append(entry)
                    else:
                        record["functions"].append(entry)
                    self._collect(child, code, record, None)
                    continue

            self._collect(child, code, record, enclosing_class)

    def _record_import(self, node, code: bytes, record: Dict[str, Any]):
        text = " ".join(self._text(node, code).split())
        module: Optional[str] = None
        symbols: List[Tuple[str, Optional[str]]] = []

        module_node = node.child_by_field_name("module_name")
        if module_node is not None:
            module = self._text(module_node, code).strip("'\";")

        if node.type == "import_from_statement":
            for child in node.children:
                if child == module_node:
                    continue
                if child.type in ("dotted_name", "identifier"):
                    symbols.append((self._text(child, code), None))
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node is not None:
                        symbols.append(
                            (
                                self._text(name_node, code),
                                self._text(alias_node, code) if alias_node is not None else None,
                            )
                        )
        elif node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    module = module or self._text(child, code)
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node is not None:
                        module = module or self._text(name_node, code)
                        if alias_node is not None:
                            symbols.append(
                                (self._text(name_node, code), self._text(alias_node, code))
                            )
                elif child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "identifier":
                            symbols.append((self._text(sub, code), None))
                        elif sub.type in ("named_imports", "namespace_import"):
                            for spec in sub.children:
                                if spec.type == "import_specifier":
                                    name_node = spec.child_by_field_name("name")
                                    alias_node = spec.child_by_field_name("alias")
                                    if name_node is not None:
                                        symbols.append(
                                            (
                                                self._text(name_node, code),
                                                self._text(alias_node, code)
                                                if alias_node is not None
                                                else None,
                                            )
                                        )
                                elif spec.type == "identifier":
                                    symbols.append((self._text(spec, code), None))
        elif node.type == "import_declaration":  # Java
            for child in node.children:
                if child.type in ("scoped_identifier", "identifier"):
                    module = self._text(child, code)
            if module:
                leaf = module.split(".")[-1]
                if leaf and leaf != "*":
                    symbols.append((leaf, None))

        if module is None:
            for token in text.replace(";", " ").split():
                if token not in ("import", "from", "require", "package"):
                    module = token.strip("'\"")
                    break

        if not module:
            return

        record["imports"].append(module)
        if symbols:
            for symbol, alias in symbols:
                record["import_bindings"].append(
                    {"module": module, "symbol": symbol, "alias": alias}
                )
        else:
            record["import_bindings"].append({"module": module, "symbol": None, "alias": None})


def _empty_architecture() -> Dict[str, Any]:
    return {
        "files": [],
        "project_structure_sha256": canonical_hash([]),
        "project_text_sha256": canonical_hash([]),
        "parse_errors": [],
        "typescript_grammar": TYPESCRIPT_AVAILABLE,
        "files_without_types": [],
    }
