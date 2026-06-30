from __future__ import annotations

import sys
from enum import Enum

import httpx

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

MAX_BUNDLE_RETRIES = 3


class FailureKind(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


_TRANSIENT_HTTP_STATUS_CODES = frozenset({502, 503, 504})
_PERMANENT_HTTP_STATUS_CODES = frozenset({403, 404})


def _classify_leaf(exc: Exception) -> FailureKind:
    """Map bundle processing exceptions to retry policy categories."""
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in _TRANSIENT_HTTP_STATUS_CODES:
            return FailureKind.TRANSIENT
        if status_code in _PERMANENT_HTTP_STATUS_CODES:
            return FailureKind.PERMANENT
        return FailureKind.UNKNOWN

    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return FailureKind.TRANSIENT

    return FailureKind.UNKNOWN


def classify_failure(exc: Exception) -> FailureKind:
    """Map bundle processing exceptions to retry policy categories."""
    if isinstance(exc, BaseExceptionGroup):
        kinds = [classify_failure(sub) for sub in exc.exceptions if isinstance(sub, Exception)]
        if not kinds:
            return FailureKind.UNKNOWN
        if FailureKind.PERMANENT in kinds:
            return FailureKind.PERMANENT
        if FailureKind.TRANSIENT in kinds:
            return FailureKind.TRANSIENT
        return FailureKind.UNKNOWN

    return _classify_leaf(exc)
