"""Path containment helpers.

Every filesystem path in this application is derived from user input at some
point (project names come from a URL segment, file paths come from a request
body, archive member names come from an uploaded zip). Each of those is a
directory-traversal vector, so all path construction funnels through here.
"""
import os
import re
from typing import Optional

_SAFE_NAME = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")


class UnsafePathError(ValueError):
    """Raised when a requested path would escape its intended root."""


def sanitize_project_name(name: str) -> str:
    """Reduce an arbitrary string to a safe single path segment.

    Anything that looks like a path -- a separator or a `..` component -- is
    rejected outright rather than quietly rewritten, because silently turning
    `../../etc` into `etc` would operate on a project the caller never named.
    Benign-but-unwanted characters (dots in `my.app`, punctuation) are stripped.
    """
    raw = (name or "").strip()
    if not raw:
        raise UnsafePathError("Project name must not be empty.")
    if "/" in raw or "\\" in raw or ".." in raw or raw in (".", ".."):
        raise UnsafePathError("Project name must not contain path separators or '..'.")

    cleaned = "".join(c for c in raw if c.isalnum() or c in (" ", "_", "-")).strip()
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    if not cleaned or not _SAFE_NAME.match(cleaned):
        raise UnsafePathError(
            "Project name must be 1-64 characters of letters, digits, space, _ or -."
        )
    return cleaned


def resolve_within(root: str, *parts: str) -> str:
    """Join parts onto root and guarantee the result stays inside root.

    This is what stops `project_name="../.."` from turning a delete endpoint
    into an arbitrary-directory removal, and `file_path="../../.env"` from
    turning a file-explain endpoint into an arbitrary-file read.
    """
    root_abs = os.path.abspath(root)
    candidate = os.path.abspath(os.path.join(root_abs, *parts))
    if candidate != root_abs and not candidate.startswith(root_abs + os.sep):
        raise UnsafePathError("Resolved path escapes its permitted root.")
    return candidate


def safe_relative_member(name: str) -> Optional[str]:
    """Normalise an archive member name, or return None if it is unsafe.

    Rejects absolute paths, drive letters, and any component that walks upward
    ("zip slip"). Also strips the single leading directory that GitHub zipballs
    wrap everything in.
    """
    if not name or name.endswith("/"):
        return None
    normalised = name.replace("\\", "/")
    if normalised.startswith("/") or re.match(r"^[A-Za-z]:", normalised):
        return None
    parts = [p for p in normalised.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    if not parts:
        return None
    return os.path.join(*parts)


def strip_leading_dir(relative_path: str) -> str:
    """Drop the wrapper directory GitHub adds around zipball contents."""
    parts = relative_path.replace("\\", "/").split("/", 1)
    return parts[1] if len(parts) > 1 else relative_path
