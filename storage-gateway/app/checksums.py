"""
Remember the CRC-32s of files already sent in multi-file downloads, by path and ETag (a changed file
has a new ETag), so a resume needn't re-read the files before the resume point. With a state folder
they're kept in SQLite there and survive a restart; without one, in memory. Only checksums are kept,
never file contents or names beyond the path the link already carries.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

MEMORY_LIMIT = 1_000_000  # entries kept in memory before starting over


class ChecksumStore:
    def __init__(self, state_dir: Path | None):
        self._lock = threading.Lock()
        self._memory: dict[tuple[str, str], int] = {}
        self._db = None
        if state_dir is not None:
            self._db = sqlite3.connect(Path(state_dir) / "checksums.sqlite3", check_same_thread=False)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS checksums "
                "(path TEXT, etag TEXT, crc INTEGER, PRIMARY KEY (path, etag))",
            )
            self._db.commit()

    def get(self, path: str, etag: str) -> int | None:
        with self._lock:
            if self._db is None:
                return self._memory.get((path, etag))
            row = self._db.execute(
                "SELECT crc FROM checksums WHERE path = ? AND etag = ?",
                (path, etag),
            ).fetchone()
            if row:
                return row[0]
            return None

    def put_many(self, items: list[tuple[str, str, int]]) -> None:
        with self._lock:
            if self._db is None:
                if len(self._memory) > MEMORY_LIMIT:
                    self._memory.clear()
                self._memory.update({(p, e): crc for p, e, crc in items})
                return
            self._db.executemany("INSERT OR REPLACE INTO checksums VALUES (?, ?, ?)", items)
            self._db.commit()
