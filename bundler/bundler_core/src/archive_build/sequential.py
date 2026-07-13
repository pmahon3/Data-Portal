from __future__ import annotations

import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import anyio
import httpx

from bundler_core.archive_build.context import ArchiveBuildContext
from bundler_core.archive_build.timings import ArchiveBuildResult, build_archive_timings
from bundler_core.models import BundleRecord


@dataclass(frozen=True)
class _BuildPhaseMarks:
    """``perf_counter`` checkpoints captured around download and zip phases."""

    build_started: float
    download_finished: float
    zip_finished: float


async def _download_eligible_urls(
    record: BundleRecord,
    ctx: ArchiveBuildContext,
    temp_dir: Path,
) -> list[tuple[str, Path]]:
    """Download each eligible URL into ``temp_dir``. Returns staged (archive_name, path) pairs."""
    downloaded_files: list[tuple[str, Path]] = []
    timeout = httpx.Timeout(ctx.http_timeout_seconds)
    semaphore = anyio.Semaphore(ctx.download_concurrency)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with anyio.create_task_group() as tg:
            for index, url in enumerate(record.urls, start=1):
                archive_name = ctx.archive_name_from_url(url, index)
                if archive_name is None:
                    continue
                stage_path = temp_dir / f"download-{index:05d}.bin"
                downloaded_files.append((archive_name, stage_path))
                tg.start_soon(
                    ctx.download_url_to_file,
                    client,
                    semaphore,
                    url,
                    stage_path,
                )

    return downloaded_files


def _zip_from_files(files: list[tuple[str, Path]], bundle_id: str) -> Path:
    with tempfile.NamedTemporaryFile(prefix=f"bundle-{bundle_id}-", suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    with zipfile.ZipFile(tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for archive_name, file_path in files:
            zf.write(file_path, arcname=archive_name)
    return tmp_path


class SequentialArchiveBuildStrategy:
    """Download all URLs in parallel, then zip staged files (Phase A default)."""

    STRATEGY_NAME = "sequential"

    async def build(self, record: BundleRecord, ctx: ArchiveBuildContext) -> ArchiveBuildResult:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"bundle-stage-{record.id}-"))
        try:
            archive_path, url_count, phase_marks = await self._build_archive(record, ctx, temp_dir)
        finally:
            await anyio.to_thread.run_sync(shutil.rmtree, temp_dir, True)

        # --- observability: assemble timings from phase checkpoints (see ``timings`` module) ---
        timings = build_archive_timings(
            build_started=phase_marks.build_started,
            download_finished=phase_marks.download_finished,
            zip_finished=phase_marks.zip_finished,
            url_count=url_count,
        )
        return ArchiveBuildResult(archive_path=archive_path, timings=timings)

    async def _build_archive(
        self,
        record: BundleRecord,
        ctx: ArchiveBuildContext,
        temp_dir: Path,
    ) -> tuple[Path, int, _BuildPhaseMarks]:
        """Run download-then-zip. Returns archive path, eligible URL count, and phase checkpoints."""
        build_started = time.perf_counter()

        downloaded_files = await _download_eligible_urls(record, ctx, temp_dir)
        download_finished = time.perf_counter()

        archive_path = await anyio.to_thread.run_sync(
            _zip_from_files,
            downloaded_files,
            record.id,
        )
        zip_finished = time.perf_counter()

        phase_marks = _BuildPhaseMarks(
            build_started=build_started,
            download_finished=download_finished,
            zip_finished=zip_finished,
        )
        return archive_path, len(downloaded_files), phase_marks
