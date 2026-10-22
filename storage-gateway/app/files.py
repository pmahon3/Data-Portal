"""Mapping resources to files under the root, byte ranges and validators."""
import mimetypes
import os
from collections.abc import Iterator
from email.utils import formatdate
from pathlib import Path


class BadPath(ValueError):
    """The resource isn't a safe path inside this service's namespace."""


def resolve(root: Path, namespace: str, resource: str) -> Path:
    """
    Map ``namespace/key`` to a path under ``root``.

    :raises BadPath: If the resource is in another namespace, has empty, ``.`` or ``..`` segments,
        or resolves outside the root (for example through a symlink).
    """
    ns, sep, key = resource.partition("/")
    if not sep or ns != namespace or not key or "\x00" in key:
        raise BadPath(resource)
    if any(segment in ("", ".", "..") for segment in key.split("/")):
        raise BadPath(resource)
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise BadPath(resource)
    return path


def etag(stat: os.stat_result) -> str:
    """A validator that changes whenever the file's size or modification time changes."""
    return f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'


def file_headers(path: Path, stat: os.stat_result) -> dict[str, str]:
    """Headers describing a file, shared by GET and HEAD."""
    content_type, _ = mimetypes.guess_type(path.name)
    return {
        "Content-Length": str(stat.st_size),
        "Content-Type": content_type or "application/octet-stream",
        "ETag": etag(stat),
        "Last-Modified": formatdate(stat.st_mtime, usegmt=True),
        "Accept-Ranges": "bytes",
    }


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """
    Parse a single ``Range: bytes=…`` header into an inclusive (start, end) pair.

    :return: None to serve the whole file (no header, or several ranges, which are allowed to be
        ignored).
    :raises ValueError: If the range is malformed or can't be satisfied.
    """
    if not header:
        return None
    unit, _, spec = header.partition("=")
    if unit.strip().lower() != "bytes" or not spec:
        raise ValueError(header)
    if "," in spec:
        return None
    first, dash, last = spec.strip().partition("-")
    if not dash:
        raise ValueError(header)
    if first == "":
        # Suffix range: the last N bytes.
        if not last.isdigit() or int(last) == 0 or size == 0:
            raise ValueError(header)
        return max(size - int(last), 0), size - 1
    if not first.isdigit() or (last and not last.isdigit()):
        raise ValueError(header)
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError(header)
    return start, end


def read_chunks(path: Path, start: int, end: int, chunk_size: int) -> Iterator[bytes]:
    """Yield bytes ``start``..``end`` (inclusive) of a file."""
    remaining = end - start + 1
    with open(path, "rb") as f:
        f.seek(start)
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk
