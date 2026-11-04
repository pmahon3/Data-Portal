"""
Build a ZIP archive on the fly from files on disk (DS-posix-stream in docs/design/decision-log.md).

Files are stored, not compressed: imaging data is mostly compressed already, and stored entries make
every byte's position known before anything is sent. That gives the exact total size up front (a real
progress bar) and any byte range on demand, so a broken download resumes where it stopped.

ZIP64 is always used, so single files and whole archives can exceed 4 GB, and the layout is the same
whatever the sizes. Each file's CRC-32 is written after its data, so the stream can start before any
checksum is known. Checksums are computed while files are read and can be saved and supplied again; a
resumed download then jumps straight to its starting point instead of re-reading earlier files.

The same bytes come out for the same entries every time: names, sizes, modification times and order
fix the layout, and the contents fix the checksums.
"""
from __future__ import annotations

import struct
import time
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import BinaryIO

_LOCAL = 0x04034B50
_DESCRIPTOR = 0x08074B50
_CENTRAL = 0x02014B50
_ZIP64_END = 0x06064B50
_ZIP64_LOCATOR = 0x07064B50
_END = 0x06054B50

_VERSION = 45                       # ZIP64
_MADE_BY = (3 << 8) | _VERSION      # Unix
_FLAGS = 0x0808                     # bit 3: sizes and CRC after the data; bit 11: UTF-8 names
_STORED = 0
_FILE_ATTRS = 0o100644 << 16
_MAX32 = 0xFFFFFFFF
_MAX16 = 0xFFFF

_LOCAL_FIXED = 30
_LOCAL_EXTRA = 20                   # ZIP64 extra: id, size, uncompressed, compressed
_DESCRIPTOR_LEN = 24
_CENTRAL_FIXED = 46
_CENTRAL_EXTRA = 28                 # ZIP64 extra: id, size, uncompressed, compressed, offset
_TAIL_LEN = 56 + 20 + 22            # ZIP64 end record, ZIP64 locator, end record


class FileChanged(RuntimeError):
    """A file's size changed while it was being read; the archive would be inconsistent."""


@dataclass
class Entry:
    """
    One file in the archive.

    ``name`` is its path inside the archive (``/``-separated); ``size`` its size in bytes, which the
    file must still have when read; ``mtime`` its modification time (seconds since the epoch). ``open``
    returns the file opened for binary reading. ``crc32`` is the file's CRC-32 if already known (from
    an earlier download).
    """

    name: str
    size: int
    mtime: float
    open: Callable[[], BinaryIO]
    crc32: int | None = None


def _dos_time(mtime: float) -> tuple[int, int]:
    """
    Return the MS-DOS (time, date) pair ZIP records hold, in UTC; times before 1980 become 1980.

    Example: 2024-03-05 14:30:10 UTC -> (0x73C5, 0x5865)
    """
    t = time.gmtime(max(mtime, 315532800))  # ZIP times start in 1980
    dos_time = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    dos_date = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    return dos_time, dos_date


class ZipStream:
    """
    The byte layout of one archive, and its bytes over any range.

    Example: one 5-byte entry "a.txt" is laid out as local header (55 bytes), data (5), descriptor
    (24), central record (79) and tail (98), so ``size`` is 261.
    """

    def __init__(self, entries: list[Entry], chunk_size: int = 1024 * 1024):
        self.entries = entries
        self.chunk_size = chunk_size
        self._names = [e.name.encode("utf-8") for e in entries]
        # Layout: (length, kind, entry index). Kinds: local, data, descriptor, central, tail.
        self._segments: list[tuple[int, str, int]] = []
        self._local_offsets: list[int] = []
        offset = 0
        for i, entry in enumerate(entries):
            self._local_offsets.append(offset)
            pieces = (
                (_LOCAL_FIXED + len(self._names[i]) + _LOCAL_EXTRA, "local"),
                (entry.size, "data"),
                (_DESCRIPTOR_LEN, "descriptor"),
            )
            for length, kind in pieces:
                self._segments.append((length, kind, i))
                offset += length
        self._central_offset = offset
        for i in range(len(entries)):
            length = _CENTRAL_FIXED + len(self._names[i]) + _CENTRAL_EXTRA
            self._segments.append((length, "central", i))
            offset += length
        self._central_size = offset - self._central_offset
        self._segments.append((_TAIL_LEN, "tail", -1))
        self.size = offset + _TAIL_LEN

    # --- checksums ---

    def checksums(self) -> list[int | None]:
        """Return the CRC-32s known so far, to save and pass back in on a later request."""
        return [e.crc32 for e in self.entries]

    def _crc(self, i: int) -> int:
        entry = self.entries[i]
        if entry.crc32 is None:
            crc = 0
            read = 0
            with entry.open() as f:
                while chunk := f.read(self.chunk_size):
                    crc = zlib.crc32(chunk, crc)
                    read += len(chunk)
            if read != entry.size:
                raise FileChanged(entry.name)
            entry.crc32 = crc
        return entry.crc32

    # --- records ---

    def _local(self, i: int) -> bytes:
        entry = self.entries[i]
        name = self._names[i]
        tm, dt = _dos_time(entry.mtime)
        header = struct.pack(
            "<IHHHHHIIIHH",
            _LOCAL,
            _VERSION,
            _FLAGS,
            _STORED,
            tm,
            dt,
            0,
            _MAX32,
            _MAX32,
            len(name),
            _LOCAL_EXTRA,
        )
        zip64_extra = struct.pack("<HHQQ", 0x0001, 16, 0, 0)
        return header + name + zip64_extra

    def _descriptor(self, i: int) -> bytes:
        size = self.entries[i].size
        return struct.pack("<IIQQ", _DESCRIPTOR, self._crc(i), size, size)

    def _central(self, i: int) -> bytes:
        entry = self.entries[i]
        name = self._names[i]
        tm, dt = _dos_time(entry.mtime)
        header = struct.pack(
            "<IHHHHHHIIIHHHHHII",
            _CENTRAL,
            _MADE_BY,
            _VERSION,
            _FLAGS,
            _STORED,
            tm,
            dt,
            self._crc(i),
            _MAX32,
            _MAX32,
            len(name),
            _CENTRAL_EXTRA,
            0,
            0,
            0,
            _FILE_ATTRS,
            _MAX32,
        )
        zip64_extra = struct.pack(
            "<HHQQQ",
            0x0001,
            24,
            entry.size,
            entry.size,
            self._local_offsets[i],
        )
        return header + name + zip64_extra

    def _tail(self) -> bytes:
        count = len(self.entries)
        zip64_end_offset = self._central_offset + self._central_size
        zip64_end = struct.pack(
            "<IQHHIIQQQQ",
            _ZIP64_END,
            44,
            _MADE_BY,
            _VERSION,
            0,
            0,
            count,
            count,
            self._central_size,
            self._central_offset,
        )
        zip64_locator = struct.pack("<IIQI", _ZIP64_LOCATOR, 0, zip64_end_offset, 1)
        end = struct.pack("<IHHHHIIH", _END, 0, 0, _MAX16, _MAX16, _MAX32, _MAX32, 0)
        return zip64_end + zip64_locator + end

    def _record(self, kind: str, i: int) -> bytes:
        if kind == "local":
            return self._local(i)
        if kind == "descriptor":
            return self._descriptor(i)
        if kind == "central":
            return self._central(i)
        return self._tail()

    # --- bytes ---

    def _data(self, i: int, start: int, end: int) -> Iterator[bytes]:
        """Yield bytes ``start``..``end`` (exclusive) of entry ``i``; compute its CRC if reading it whole."""
        entry = self.entries[i]
        whole = start == 0 and end == entry.size and entry.crc32 is None
        crc = 0
        with entry.open() as f:
            f.seek(start)
            remaining = end - start
            while remaining > 0:
                chunk = f.read(min(self.chunk_size, remaining))
                if not chunk:
                    raise FileChanged(entry.name)
                remaining -= len(chunk)
                if whole:
                    crc = zlib.crc32(chunk, crc)
                yield chunk
            if whole:
                if f.read(1):
                    raise FileChanged(entry.name)
                entry.crc32 = crc

    def iter_bytes(self, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        """
        Yield the archive's bytes from ``start`` to ``end`` (inclusive; default: the end).

        Example: ``iter_bytes(55, 59)`` on the one-entry archive above yields just the file's 5 bytes.
        """
        if end is None:
            end = self.size - 1
        if not 0 <= start <= end < self.size:
            raise ValueError(f"range {start}-{end} outside 0-{self.size - 1}")
        position = 0
        for length, kind, i in self._segments:
            # [seg_start, seg_end)
            seg_start = position
            seg_end = position + length
            position = seg_end
            if seg_end <= start:
                continue
            if seg_start > end:
                return
            lo = max(start, seg_start) - seg_start
            hi = min(end + 1, seg_end) - seg_start
            if kind == "data":
                yield from self._data(i, lo, hi)
            else:
                yield self._record(kind, i)[lo:hi]
