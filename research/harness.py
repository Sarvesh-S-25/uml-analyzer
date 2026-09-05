"""Shared plumbing for the research scripts.

The experiments drive the pipeline in-process rather than over HTTP. That keeps
a replay of a few thousand commits fast, avoids authentication and rate limits
in a measurement context, and -- importantly -- means the code under test is
exactly the code the application runs, not a reimplementation of it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Experiments must never call a paid API by accident, and must be reproducible.
# Both are settable from the command line, but this is the default.
os.environ.setdefault("LLM_MODE", "offline")
os.environ.setdefault("SECRET_KEY", "research-harness-not-a-deployment")

GATE_STRATEGIES = ("always", "content", "structural", "isomorphism")


class GitError(RuntimeError):
    pass


def preflight() -> Optional[str]:
    """Return a human-readable reason the experiments cannot run, or None.

    Checked before any work starts, so a missing native dependency surfaces as
    one clear line rather than as a stack trace on the first commit.
    """
    try:
        import parsers.polyglot_parser  # noqa: F401
    except Exception as exc:
        return (
            "The tree-sitter grammars are not importable, so source cannot be parsed "
            f"({exc}). Install them with:\n"
            "    pip install tree-sitter tree-sitter-python tree-sitter-javascript "
            "tree-sitter-java tree-sitter-typescript"
        )
    return None


def run_git(repo: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def clone_or_reuse(source: str, cache_dir: str) -> str:
    """A URL is cloned into the cache; a local path is used as-is."""
    if os.path.isdir(source):
        return os.path.abspath(source)

    os.makedirs(cache_dir, exist_ok=True)
    name = source.rstrip("/").split("/")[-1].replace(".git", "")
    destination = os.path.join(cache_dir, name)
    if not os.path.isdir(os.path.join(destination, ".git")):
        result = subprocess.run(
            ["git", "clone", "--quiet", source, destination],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise GitError(f"Could not clone {source}: {result.stderr.strip()}")
    return destination


def commit_list(repo: str, limit: int, branch: Optional[str] = None) -> List[str]:
    """Oldest-first list of the most recent `limit` commits."""
    args = ["log", f"-{limit}", "--format=%H", "--no-merges"]
    if branch:
        args.append(branch)
    output = run_git(repo, *args)
    commits = [line for line in output.splitlines() if line]
    return list(reversed(commits))


def checkout_worktree(repo: str, commit: str, destination: str) -> None:
    """Materialise one commit's tree into `destination` without touching the repo.

    `git archive` is used rather than `git checkout` so the source repository is
    never modified and several commits can be materialised concurrently.
    """
    os.makedirs(destination, exist_ok=True)
    for entry in os.listdir(destination):
        target = os.path.join(destination, entry)
        shutil.rmtree(target, ignore_errors=True) if os.path.isdir(target) else os.remove(target)

    archive = subprocess.run(
        ["git", "-C", repo, "archive", "--format=tar", commit],
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise GitError(f"git archive failed for {commit[:8]}: {archive.stderr.decode()[:200]}")

    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        for member in tar.getmembers():
            if member.isdir() or member.issym() or member.islnk():
                continue
            if member.name.startswith("/") or ".." in member.name.split("/"):
                continue
            target = os.path.join(destination, member.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with open(target, "wb") as handle:
                handle.write(extracted.read())


@dataclass
class ProjectSpec:
    """One corpus entry."""
    name: str
    source: str                      # local path or clone URL
    uml: Optional[str] = None        # path to a .mdj model
    commits: int = 30
    branch: Optional[str] = None
    subdirectory: Optional[str] = None
    notes: str = ""

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "ProjectSpec":
        return ProjectSpec(
            name=payload["name"],
            source=payload["source"],
            uml=payload.get("uml"),
            commits=int(payload.get("commits", 30)),
            branch=payload.get("branch"),
            subdirectory=payload.get("subdirectory"),
            notes=payload.get("notes", ""),
        )


def load_corpus(path: str) -> List[ProjectSpec]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    entries = payload.get("projects", payload if isinstance(payload, list) else [])
    return [ProjectSpec.from_dict(entry) for entry in entries]


@dataclass
class Sandbox:
    """A throwaway project directory in the pipeline's expected layout."""
    root: str
    keep: bool = False
    _created: List[str] = field(default_factory=list)

    @classmethod
    def create(cls, base: Optional[str] = None, keep: bool = False) -> "Sandbox":
        root = base or tempfile.mkdtemp(prefix="conformance-research-")
        os.makedirs(root, exist_ok=True)
        return cls(root=root, keep=keep)

    def project(self, name: str) -> str:
        path = os.path.join(self.root, name)
        for sub in ("source", "uml", "reports"):
            os.makedirs(os.path.join(path, sub), exist_ok=True)
        self._created.append(path)
        return path

    def reset(self, name: str) -> str:
        path = os.path.join(self.root, name)
        shutil.rmtree(path, ignore_errors=True)
        return self.project(name)

    def cleanup(self):
        if not self.keep:
            shutil.rmtree(self.root, ignore_errors=True)


def install_uml(project_path: str, uml_source: Optional[str]) -> bool:
    if not uml_source or not os.path.isfile(uml_source):
        return False
    shutil.copy2(uml_source, os.path.join(project_path, "uml", os.path.basename(uml_source)))
    return True


def copy_source(tree: str, project_path: str, subdirectory: Optional[str] = None) -> int:
    """Copy a materialised commit tree into the project's virtual directory."""
    source_root = os.path.join(tree, subdirectory) if subdirectory else tree
    destination = os.path.join(project_path, "source")
    shutil.rmtree(destination, ignore_errors=True)
    os.makedirs(destination, exist_ok=True)

    if not os.path.isdir(source_root):
        return 0

    copied = 0
    for current, dirs, files in os.walk(source_root):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", "venv"}]
        for filename in files:
            absolute = os.path.join(current, filename)
            relative = os.path.relpath(absolute, source_root)
            target = os.path.join(destination, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                shutil.copy2(absolute, target)
                copied += 1
            except OSError:
                continue
    return copied


def finding_signature(result: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a result a gate is responsible for keeping correct.

    Deliberately the *deterministic* findings: they are exact, so a difference
    between a gated run and a forced one is a real missed change rather than
    model noise. Model-authored gaps are compared separately, against the
    repeatability baseline.
    """
    difference = result.get("difference", {})
    return {
        "missing_classes": sorted(difference.get("missing_classes", [])),
        "extra_classes": sorted(difference.get("extra_classes", [])),
        "missing_relations": sorted(difference.get("missing_relations", [])),
        "unimplemented_associations": sorted(difference.get("unimplemented_associations", [])),
        "element_differences": sorted(
            f"{item['element_name']}:{','.join(sorted(item['missing_methods']))}"
            f"|{','.join(sorted(item['missing_attributes']))}"
            for item in difference.get("element_differences", [])
        ),
        "rule_violations": sorted(
            f"{item['rule']}@{item['file']}" for item in result.get("rule_violations", [])
        ),
        "similarity_score_rule_based": result.get("similarity_score_rule_based"),
    }


def signatures_differ(left: Dict[str, Any], right: Dict[str, Any]) -> List[str]:
    return sorted(key for key in left if left[key] != right.get(key))


def write_csv(path: str, rows: Sequence[Dict[str, Any]], columns: Optional[Iterable[str]] = None):
    import csv

    if not rows:
        return
    fieldnames = list(columns) if columns else list(rows[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str, payload: Any):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
