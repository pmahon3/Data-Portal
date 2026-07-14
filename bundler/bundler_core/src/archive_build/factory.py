from __future__ import annotations

import os

from bundler_core.archive_build.protocol import ArchiveBuildStrategy
from bundler_core.archive_build.sequential import SequentialArchiveBuildStrategy

_STRATEGY_SEQUENTIAL = "sequential"
_STRATEGY_PIPELINED = "pipelined"
_VALID_STRATEGIES = frozenset({_STRATEGY_SEQUENTIAL, _STRATEGY_PIPELINED})


def create_archive_build_strategy(name: str | None = None) -> ArchiveBuildStrategy:
    """Return an archive build strategy from ``name`` or ``BUNDLER_ARCHIVE_BUILD_STRATEGY``."""
    resolved = (name or os.getenv("BUNDLER_ARCHIVE_BUILD_STRATEGY", _STRATEGY_SEQUENTIAL)).strip().lower()
    if resolved == _STRATEGY_SEQUENTIAL:
        return SequentialArchiveBuildStrategy()
    if resolved == _STRATEGY_PIPELINED:
        raise NotImplementedError(
            "pipelined archive build strategy is not implemented yet; use sequential"
        )
    raise ValueError(
        f"Unknown BUNDLER_ARCHIVE_BUILD_STRATEGY={resolved!r}; "
        f"expected one of {sorted(_VALID_STRATEGIES)}"
    )
