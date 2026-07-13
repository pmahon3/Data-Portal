from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveBuildContext:
    """Dependencies passed into an archive build strategy for one job."""

    archive_name_from_url: Callable[[str, int], str | None]
    download_url_to_file: Callable[..., Awaitable[None]]
    download_concurrency: int
    http_timeout_seconds: float
