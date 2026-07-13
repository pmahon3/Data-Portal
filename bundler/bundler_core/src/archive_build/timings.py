"""Archive build timing types and helpers.

These types support observability (logging and in-memory ``BundleRecord`` fields).
They are not part of the bundle archive contract and do not affect job success,
failure, or archive contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveBuildTimings:
    """Wall-clock breakdown of one archive build attempt."""

    download_seconds: float
    zip_seconds: float
    total_seconds: float
    url_count: int


@dataclass(frozen=True)
class ArchiveBuildResult:
    """Archive path plus observability metadata from the build strategy."""

    archive_path: Path
    timings: ArchiveBuildTimings


def build_archive_timings(
    *,
    build_started: float,
    download_finished: float,
    zip_finished: float,
    url_count: int,
) -> ArchiveBuildTimings:
    """Assemble timing metrics from ``perf_counter`` checkpoints.

    Checkpoints must be captured around business-logic phases only (download, zip).
    Staging cleanup and other post-build work are excluded from these numbers.
    """
    download_seconds = download_finished - build_started
    zip_seconds = zip_finished - download_finished
    total_seconds = zip_finished - build_started
    return ArchiveBuildTimings(
        download_seconds=download_seconds,
        zip_seconds=zip_seconds,
        total_seconds=total_seconds,
        url_count=url_count,
    )
