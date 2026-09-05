"""Static cross-module import check.

Verifies that every `from <local module> import <name>` in this codebase refers
to a name the target module actually defines. Runs on the AST alone, so it
works in an environment where the third-party dependencies (FastAPI,
tree-sitter) are not installed and the modules cannot be imported.

Usage:  python tools/check_imports.py
Exit code 0 means every local import resolves.
"""
import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules", "tools"}


def module_files():
    for current, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(current, name)


def module_name(path: str) -> str:
    relative = os.path.relpath(path, ROOT).replace(os.sep, ".")
    if relative.endswith(".__init__.py"):
        return relative[: -len(".__init__.py")]
    return relative[: -len(".py")]


def top_level_names(tree: ast.Module) -> set:
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Try):
            # e.g. the optional `import tiktoken` guard
            for sub in node.body + [n for handler in node.handlers for n in handler.body]:
                if isinstance(sub, ast.Import):
                    for alias in sub.names:
                        names.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        if isinstance(target, ast.Name):
                            names.add(target.id)
    return names


def main() -> int:
    trees = {}
    for path in module_files():
        with open(path, "r", encoding="utf-8") as handle:
            try:
                trees[module_name(path)] = (path, ast.parse(handle.read(), filename=path))
            except SyntaxError as exc:
                print(f"SYNTAX ERROR {path}:{exc.lineno}: {exc.msg}")
                return 1

    exports = {name: top_level_names(tree) for name, (_, tree) in trees.items()}
    problems = []

    for name, (path, tree) in sorted(trees.items()):
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level:
                continue
            target = node.module or ""
            if target not in exports:
                continue  # third-party or stdlib
            for alias in node.names:
                if alias.name == "*":
                    continue
                if alias.name not in exports[target] and f"{target}.{alias.name}" not in exports:
                    problems.append(
                        f"{os.path.relpath(path, ROOT)}:{node.lineno}: "
                        f"'{target}' does not define '{alias.name}'"
                    )

    if problems:
        print("Unresolved local imports:")
        for problem in problems:
            print("  " + problem)
        return 1

    print(f"OK: every local import resolves across {len(trees)} modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
