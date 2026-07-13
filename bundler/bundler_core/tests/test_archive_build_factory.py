from __future__ import annotations

import pytest

from bundler_core.archive_build.factory import create_archive_build_strategy
from bundler_core.archive_build.sequential import SequentialArchiveBuildStrategy


def test_create_archive_build_strategy_defaults_to_sequential() -> None:
    strategy = create_archive_build_strategy("sequential")
    assert isinstance(strategy, SequentialArchiveBuildStrategy)


def test_create_archive_build_strategy_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown BUNDLER_ARCHIVE_BUILD_STRATEGY"):
        create_archive_build_strategy("parallel")


def test_create_archive_build_strategy_pipelined_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="pipelined"):
        create_archive_build_strategy("pipelined")
