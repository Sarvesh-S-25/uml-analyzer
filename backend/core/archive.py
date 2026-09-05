"""Hardened archive extraction.

The previous implementation joined archive member names straight onto the
destination directory. A member named `../../../.env` would therefore be written
outside the project ("zip slip"). Extraction now validates every member, caps
total uncompressed size and member count (zip bombs), and skips symlinks.
"""
import io
import os
import zipfile
from typing import Dict, List

from config import MAX_ARCHIVE_MEMBERS, MAX_ARCHIVE_UNCOMPRESSED_BYTES
from core.paths import UnsafePathError, resolve_within, safe_relative_member, strip_leading_dir


class ArchiveError(Exception):
    pass


def extract_zip(
    content: bytes, destination: str, *, strip_root: bool = False
) -> Dict[str, object]:
    """Extract `content` into `destination`, returning a report.

    `strip_root=True` drops the single wrapper directory GitHub puts around
    zipball contents.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("The uploaded file is not a readable .zip archive.") from exc

    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ArchiveError(
            f"Archive contains {len(members)} entries, above the limit of {MAX_ARCHIVE_MEMBERS}."
        )

    declared_size = sum(m.file_size for m in members)
    if declared_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise ArchiveError(
            f"Archive expands to {declared_size} bytes, above the limit of "
            f"{MAX_ARCHIVE_UNCOMPRESSED_BYTES}."
        )

    os.makedirs(destination, exist_ok=True)
    written: List[str] = []
    rejected: List[str] = []
    total_bytes = 0

    for member in members:
        if member.is_dir():
            continue

        # Mode bits 0xA000 mark a symlink; following one would escape the root.
        if (member.external_attr >> 16) & 0xF000 == 0xA000:
            rejected.append(member.filename)
            continue

        relative = safe_relative_member(member.filename)
        if relative is None:
            rejected.append(member.filename)
            continue

        if strip_root:
            relative = strip_leading_dir(relative)
            if not relative:
                continue

        try:
            target = resolve_within(destination, relative)
        except UnsafePathError:
            rejected.append(member.filename)
            continue

        total_bytes += member.file_size
        if total_bytes > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ArchiveError("Archive exceeded the uncompressed size limit during extraction.")

        os.makedirs(os.path.dirname(target), exist_ok=True)
        with archive.open(member) as source, open(target, "wb") as sink:
            sink.write(source.read())
        written.append(relative)

    archive.close()
    return {"written": len(written), "rejected": rejected, "bytes": total_bytes}
