from __future__ import annotations

from typing import ClassVar, Protocol

from bundler_core.archive_build.context import ArchiveBuildContext
from bundler_core.archive_build.timings import ArchiveBuildResult
from bundler_core.models import BundleRecord


class ArchiveBuildStrategy(Protocol):
    """Build a bundle zip archive from a pending/processing job record."""

    STRATEGY_NAME: ClassVar[str]

    async def build(self, record: BundleRecord, ctx: ArchiveBuildContext) -> ArchiveBuildResult:
        """Download source URLs and produce a zip file path with build timings."""
