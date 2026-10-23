"""
Files under the root, opened without following symlinks; byte ranges and validators.

Every path is walked one component at a time from a handle on the root, refusing symlinks at
each step, and files are read through the handle that was checked. There's no gap between
checking a path and opening it, so a symlink swapped in by someone working on the machine can't
redirect a request outside the root (CWE-59, the race fixed in rsync's CVE-2026-29518).
"""
import errno
import mimetypes
import os
import stat as stat_module
import uuid
from collections.abc import Iterator
from email.utils import formatdate
from pathlib import Path


class BadPath(ValueError):
    """The resource isn't a safe path inside this service's namespace."""


def split_key(namespace: str, resource: str) -> list[str]:
    """
    Split ``namespace/key`` into the key's path components.

    :raises BadPath: If the resource is in another namespace, or has empty, ``.`` or ``..``
        segments or a NUL byte.
    """
    ns, sep, key = resource.partition("/")
    if not sep or ns != namespace or not key or "\x00" in key:
        raise BadPath(resource)
    parts = key.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise BadPath(resource)
    return parts


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
# O_NONBLOCK so opening a FIFO planted in the root can't hang the request; it doesn't affect
# reads of regular files.
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def _is_symlink(name: str, dir_fd: int) -> bool:
    try:
        return stat_module.S_ISLNK(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode)
    except OSError:
        return False


def _refusal(error: OSError, name: str, dir_fd: int) -> Exception:
    """Turn an open failure into BadPath (a symlink) or FileNotFoundError (anything missing)."""
    if error.errno in (errno.ELOOP, errno.EMLINK, errno.ENOTDIR) and _is_symlink(name, dir_fd):
        return BadPath(name)
    if error.errno in (errno.ENOENT, errno.ENOTDIR):
        return FileNotFoundError(name)
    return error


class Root:
    """The directory this service serves."""

    def __init__(self, path: Path):
        self.path = path

    def _open_root(self) -> int:
        return os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)

    def _open_dir(self, parts: list[str], create: bool = False) -> int:
        """Open the directory ``parts`` under the root, component by component, never following symlinks."""
        fd = self._open_root()
        try:
            for name in parts:
                try:
                    next_fd = os.open(name, _DIR_FLAGS, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(name, 0o750, dir_fd=fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(name, _DIR_FLAGS, dir_fd=fd)
                except OSError as e:
                    raise _refusal(e, name, fd) from e
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    def open_file(self, parts: list[str]) -> tuple[int, os.stat_result]:
        """
        Open a regular file for reading.

        :return: The open file descriptor and its stat. The caller closes the descriptor.
        :raises BadPath: If any component is a symlink.
        :raises FileNotFoundError: If it doesn't exist or isn't a regular file.
        """
        dir_fd = self._open_dir(parts[:-1])
        try:
            try:
                fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=dir_fd)
            except OSError as e:
                raise _refusal(e, parts[-1], dir_fd) from e
        finally:
            os.close(dir_fd)
        st = os.fstat(fd)
        if not stat_module.S_ISREG(st.st_mode):
            os.close(fd)
            raise FileNotFoundError(parts[-1])
        return fd, st

    def stat_file(self, parts: list[str]) -> os.stat_result:
        fd, st = self.open_file(parts)
        os.close(fd)
        return st

    def begin_write(self, parts: list[str]) -> "PendingWrite":
        """
        Start writing a file: creates missing parent folders and a temporary file beside the target.

        :raises BadPath: If any component is a symlink.
        :raises IsADirectoryError: If a folder exists at the target path.
        """
        dir_fd = self._open_dir(parts[:-1], create=True)
        try:
            name = parts[-1]
            try:
                existing = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None and stat_module.S_ISLNK(existing.st_mode):
                raise BadPath(name)
            if existing is not None and stat_module.S_ISDIR(existing.st_mode):
                raise IsADirectoryError(name)
            tmp_name = f".upload-{uuid.uuid4().hex}"
            fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=dir_fd)
        except BaseException:
            os.close(dir_fd)
            raise
        return PendingWrite(dir_fd, fd, tmp_name, name, existed=existing is not None)

    def delete_file(self, parts: list[str]) -> None:
        """
        :raises BadPath: If any component is a symlink.
        :raises FileNotFoundError: If it doesn't exist or isn't a regular file.
        """
        dir_fd = self._open_dir(parts[:-1])
        try:
            try:
                st = os.stat(parts[-1], dir_fd=dir_fd, follow_symlinks=False)
            except OSError as e:
                raise _refusal(e, parts[-1], dir_fd) from e
            if stat_module.S_ISLNK(st.st_mode):
                raise BadPath(parts[-1])
            if not stat_module.S_ISREG(st.st_mode):
                raise FileNotFoundError(parts[-1])
            os.unlink(parts[-1], dir_fd=dir_fd)
        finally:
            os.close(dir_fd)


class PendingWrite:
    """A temporary file that becomes the target on commit, or disappears on abort."""

    def __init__(self, dir_fd: int, fd: int, tmp_name: str, name: str, existed: bool):
        self.dir_fd, self.fd, self.tmp_name, self.name, self.existed = dir_fd, fd, tmp_name, name, existed

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(self.fd, view)
            view = view[written:]

    def commit(self) -> os.stat_result:
        """Move the finished file into place (atomically) and return its stat."""
        os.fsync(self.fd)
        st = os.fstat(self.fd)
        os.close(self.fd)
        try:
            os.replace(self.tmp_name, self.name, src_dir_fd=self.dir_fd, dst_dir_fd=self.dir_fd)
        finally:
            os.close(self.dir_fd)
        return st

    def abort(self) -> None:
        os.close(self.fd)
        try:
            os.unlink(self.tmp_name, dir_fd=self.dir_fd)
        finally:
            os.close(self.dir_fd)


def etag(st: os.stat_result) -> str:
    """A validator that changes whenever the file's size or modification time changes."""
    return f'"{st.st_mtime_ns:x}-{st.st_size:x}"'


def file_headers(name: str, st: os.stat_result) -> dict[str, str]:
    """Headers describing a file, shared by GET and HEAD."""
    content_type, _ = mimetypes.guess_type(name)
    return {
        "Content-Length": str(st.st_size),
        "Content-Type": content_type or "application/octet-stream",
        "ETag": etag(st),
        "Last-Modified": formatdate(st.st_mtime, usegmt=True),
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


def read_chunks(fd: int, start: int, end: int, chunk_size: int) -> Iterator[bytes]:
    """Yield bytes ``start``..``end`` (inclusive) of an open file, then close it."""
    try:
        position, remaining = start, end - start + 1
        while remaining > 0:
            chunk = os.pread(fd, min(chunk_size, remaining), position)
            if not chunk:
                return
            position += len(chunk)
            remaining -= len(chunk)
            yield chunk
    finally:
        os.close(fd)
