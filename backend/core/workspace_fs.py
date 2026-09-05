"""The virtual directory: a project's source tree, editable without git.

GitHub import is one way to fill a project. It is not the only one, and nothing
in the analysis pipeline depends on it: a project's `source/` folder is an
ordinary directory, and this module is the full set of operations over it --
create, read, write, rename, move, delete, mkdir, batch upload, and export.

Every path arriving from a request is resolved through `core.paths.resolve_within`
against the project's own source directory, so no operation here can touch
anything outside it.
"""
import io
import os
import shutil
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.paths import UnsafePathError, resolve_within, safe_relative_member

TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".json", ".md", ".txt", ".yml",
    ".yaml", ".toml", ".ini", ".cfg", ".xml", ".html", ".css", ".scss", ".sql",
    ".sh", ".bat", ".ps1", ".env", ".gitignore", ".properties", ".kt", ".go",
    ".rb", ".php", ".c", ".h", ".cpp", ".cs", ".rs", ".svelte", ".vue",
}

HIDDEN_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}

MAX_EDITABLE_BYTES = 1024 * 1024
MAX_TREE_ENTRIES = 5000


class WorkspaceError(Exception):
    """An operation on the virtual directory could not be completed."""


class Workspace:
    """Operations on one project's `source/` directory."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.root = resolve_within(project_dir, "source")
        os.makedirs(self.root, exist_ok=True)

    # -- resolution -----------------------------------------------------------

    def _resolve(self, relative_path: str, *, must_exist: bool = False) -> str:
        cleaned = (relative_path or "").strip().replace("\\", "/")
        if not cleaned:
            raise WorkspaceError("A path is required.")
        # An absolute path is rejected, not silently reinterpreted as relative:
        # quietly turning "/etc/passwd" into "source/etc/passwd" would write to a
        # location the caller never asked for.
        if safe_relative_member(cleaned) is None:
            raise WorkspaceError(f"Invalid path: {relative_path}")
        try:
            target = resolve_within(self.root, cleaned)
        except UnsafePathError as exc:
            raise WorkspaceError(str(exc)) from exc
        if must_exist and not os.path.exists(target):
            raise WorkspaceError(f"Not found: {cleaned}")
        return target

    def relative(self, absolute: str) -> str:
        return os.path.relpath(absolute, self.root).replace(os.sep, "/")

    # -- listing --------------------------------------------------------------

    def tree(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for current, dirs, files in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in HIDDEN_DIRS)
            for directory in dirs:
                relative = self.relative(os.path.join(current, directory))
                entries.append({"path": relative, "type": "tree", "size": None, "editable": False})
            for filename in sorted(files):
                absolute = os.path.join(current, filename)
                relative = self.relative(absolute)
                try:
                    size = os.path.getsize(absolute)
                except OSError:
                    size = 0
                entries.append(
                    {
                        "path": relative,
                        "type": "blob",
                        "size": size,
                        "editable": self.is_editable(filename, size),
                    }
                )
            if len(entries) > MAX_TREE_ENTRIES:
                break

        entries.sort(key=lambda e: (e["path"].count("/"), e["type"] == "blob", e["path"]))
        return entries[:MAX_TREE_ENTRIES]

    @staticmethod
    def is_editable(filename: str, size: int) -> bool:
        if size > MAX_EDITABLE_BYTES:
            return False
        extension = os.path.splitext(filename)[1].lower()
        return extension in TEXT_EXTENSIONS or filename in (".gitignore", "Dockerfile", "Makefile")

    def stats(self) -> Dict[str, Any]:
        files = 0
        directories = 0
        total_bytes = 0
        for current, dirs, names in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in HIDDEN_DIRS]
            directories += len(dirs)
            for name in names:
                files += 1
                try:
                    total_bytes += os.path.getsize(os.path.join(current, name))
                except OSError:
                    pass
        return {"files": files, "directories": directories, "bytes": total_bytes}

    # -- reads ----------------------------------------------------------------

    def read(self, relative_path: str) -> Dict[str, Any]:
        target = self._resolve(relative_path, must_exist=True)
        if os.path.isdir(target):
            raise WorkspaceError("That path is a folder, not a file.")

        size = os.path.getsize(target)
        if size > MAX_EDITABLE_BYTES:
            raise WorkspaceError(
                f"File is {size} bytes; only files under {MAX_EDITABLE_BYTES} can be opened here."
            )
        try:
            with open(target, "r", encoding="utf-8") as handle:
                content = handle.read()
        except (UnicodeDecodeError, OSError) as exc:
            raise WorkspaceError("This file is binary or unreadable as text.") from exc

        return {
            "path": self.relative(target),
            "content": content,
            "size": size,
            "modified_at": datetime.fromtimestamp(
                os.path.getmtime(target), tz=timezone.utc
            ).isoformat(),
        }

    # -- writes ---------------------------------------------------------------

    def write(self, relative_path: str, content: str, *, create_only: bool = False) -> Dict[str, Any]:
        target = self._resolve(relative_path)
        if create_only and os.path.exists(target):
            raise WorkspaceError(f"{self.relative(target)} already exists.")
        if os.path.isdir(target):
            raise WorkspaceError("That path is a folder.")

        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return {"path": self.relative(target), "size": len(content.encode("utf-8"))}

    def write_bytes(self, relative_path: str, content: bytes) -> Dict[str, Any]:
        target = self._resolve(relative_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(content)
        return {"path": self.relative(target), "size": len(content)}

    def mkdir(self, relative_path: str) -> Dict[str, Any]:
        target = self._resolve(relative_path)
        if os.path.exists(target):
            raise WorkspaceError(f"{self.relative(target)} already exists.")
        os.makedirs(target, exist_ok=True)
        return {"path": self.relative(target), "type": "tree"}

    def move(self, source_path: str, destination_path: str) -> Dict[str, Any]:
        source = self._resolve(source_path, must_exist=True)
        destination = self._resolve(destination_path)
        if os.path.exists(destination):
            raise WorkspaceError(f"{self.relative(destination)} already exists.")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        return {"from": self.relative(source), "to": self.relative(destination)}

    def delete(self, relative_path: str) -> Dict[str, Any]:
        target = self._resolve(relative_path, must_exist=True)
        if os.path.isdir(target):
            shutil.rmtree(target)
            return {"path": self.relative(target), "type": "tree"}
        os.remove(target)
        return {"path": self.relative(target), "type": "blob"}

    def clear(self) -> Dict[str, Any]:
        removed = self.stats()
        shutil.rmtree(self.root, ignore_errors=True)
        os.makedirs(self.root, exist_ok=True)
        return removed

    # -- bulk -----------------------------------------------------------------

    def write_many(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        """Write a batch of files, reporting per-item outcomes.

        Used by folder upload: the browser sends each file with its relative
        path, and the folder structure is reproduced verbatim.
        """
        written: List[str] = []
        rejected: List[Dict[str, str]] = []
        for item in items:
            try:
                result = self.write(item["path"], item.get("content", ""))
                written.append(result["path"])
            except (WorkspaceError, KeyError, OSError) as exc:
                rejected.append({"path": item.get("path", "?"), "reason": str(exc)})
        return {"written": written, "rejected": rejected}

    def export_zip(self) -> bytes:
        """The whole source tree as a zip, so a project can leave the tool."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for current, dirs, files in os.walk(self.root):
                dirs[:] = [d for d in dirs if d not in HIDDEN_DIRS]
                for filename in sorted(files):
                    absolute = os.path.join(current, filename)
                    archive.write(absolute, self.relative(absolute))
        return buffer.getvalue()


def uml_dir(project_dir: str) -> str:
    path = resolve_within(project_dir, "uml")
    os.makedirs(path, exist_ok=True)
    return path


def list_uml_models(project_dir: str) -> List[Dict[str, Any]]:
    directory = uml_dir(project_dir)
    models = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".mdj"):
            continue
        absolute = os.path.join(directory, filename)
        models.append(
            {
                "filename": filename,
                "size": os.path.getsize(absolute),
                "modified_at": datetime.fromtimestamp(
                    os.path.getmtime(absolute), tz=timezone.utc
                ).isoformat(),
                "active": False,
            }
        )
    if models:
        # The pipeline reads the alphabetically first model; say so explicitly
        # rather than leaving the user to guess which one is in force.
        models[0]["active"] = True
    return models


def delete_uml_model(project_dir: str, filename: str) -> str:
    safe = safe_relative_member(os.path.basename(filename or ""))
    if not safe or not safe.endswith(".mdj"):
        raise WorkspaceError("Invalid model filename.")
    target = resolve_within(uml_dir(project_dir), safe)
    if not os.path.isfile(target):
        raise WorkspaceError("Model not found.")
    os.remove(target)
    return safe


def active_uml_path(project_dir: str) -> Optional[str]:
    models = list_uml_models(project_dir)
    if not models:
        return None
    return os.path.join(uml_dir(project_dir), models[0]["filename"])
