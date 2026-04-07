"""Structured logging via loguru.

Import the shared ``logger`` in application modules::

    from app.logger import logger

Call :func:`configure_logging` once at process startup to apply settings from
YAML (`loguru-config`). By default this loads :file:`app/logging.yaml`; override
with the ``BUNDLER_LOG_CONFIG`` environment variable or the ``config_path``
argument.

The bundled YAML enables ``enqueue: true`` so logging is non-blocking, uses a
thread for sink I/O, and routes records through a multiprocessing-safe queue
(see Loguru's ``logger.add(..., enqueue=True)``). Call :func:`flush_logging`
before a worker process exits, and rely on the registered atexit hook for
normal process shutdown.
"""
from __future__ import annotations

import atexit
import os
from pathlib import Path

from loguru import logger
from loguru_config import LoguruConfig

_DEFAULT_YAML = Path(__file__).resolve().parent / "logging.yaml"

_atexit_registered = False


def flush_logging() -> None:
    """Wait for enqueued records to reach sinks (use before leaving a child process).

    When ``enqueue`` is enabled, Loguru buffers to a queue; call this from
    multiprocessing workers or other short-lived processes so messages are not
    dropped. Safe to call if enqueue is off (no-op for the queue step).
    """
    logger.complete()


def _flush_on_exit() -> None:
    try:
        logger.complete()
    except Exception:
        pass


def configure_logging(
    *,
    config_path: str | Path | None = None,
    env_path_var: str = "BUNDLER_LOG_CONFIG",
    register_atexit: bool = True,
) -> None:
    """Apply loguru configuration from a YAML file using ``loguru-config``.

    Resolution order:

    1. ``config_path`` if provided.
    2. Path from the environment variable named by ``env_path_var`` (default
       ``BUNDLER_LOG_CONFIG``) if set and non-empty.
    3. The bundled default :file:`app/logging.yaml`.

    ``loguru-config`` maps the file to :meth:`loguru.logger.configure`; see
    https://loguru.readthedocs.io/en/stable/api/logger.html#loguru._logger.Logger.configure

    If ``register_atexit`` is true (default), registers a one-time atexit hook
    that calls :func:`flush_logging` so enqueued messages are not lost on
    normal interpreter shutdown.
    """
    global _atexit_registered

    if config_path is not None:
        path = Path(config_path).expanduser().resolve()
    else:
        env = os.environ.get(env_path_var, "").strip()
        path = Path(env).expanduser().resolve() if env else _DEFAULT_YAML

    if not path.is_file():
        raise FileNotFoundError(f"Loguru config file not found: {path}")

    LoguruConfig.load(path)

    if register_atexit and not _atexit_registered:
        atexit.register(_flush_on_exit)
        _atexit_registered = True


__all__ = ["configure_logging", "flush_logging", "logger"]
