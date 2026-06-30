"""Failure-kind classification tests for bundle retry policy (Option 3 / Phase B).

Boundary: pure unit tests for ``classify_failure()`` mapping exceptions to
``transient`` / ``permanent`` / ``unknown``. Retry orchestration and
``retry_count`` behavior live in ``tests/test_bundle_retry.py``.

Rule of thumb: if the question is "how should this exception be categorized
for retry policy?", this suite is the right place.

``test_classify_failure_kind`` is parametrized; each case id below is a
separate assertion (`pytest anatomy
<https://docs.pytest.org/en/stable/explanation/anatomy.html>`__).

Leaf exceptions:

- ``httpx-timeout``: ``httpx.TimeoutException`` → ``transient``.
- ``httpx-connect``: ``httpx.ConnectError`` → ``transient``.
- ``http-502`` / ``http-503`` / ``http-504``: ``httpx.HTTPStatusError`` for gateway errors → ``transient``.
- ``http-404`` / ``http-403``: ``httpx.HTTPStatusError`` for client errors → ``permanent``.
- ``runtime-unknown``: unclassified ``RuntimeError`` → ``unknown``.

AnyIO task-group shape (``ExceptionGroup`` wrapping parallel download failures):

- ``exception-group-connect``: multiple ``ConnectError`` → ``transient``.
- ``exception-group-timeout``: wrapped ``TimeoutException`` → ``transient``.
- ``exception-group-404``: wrapped 404 → ``permanent``.
- ``exception-group-mixed-permanent-wins``: connect + 404 in one group → ``permanent``.
- ``exception-group-nested``: nested ``ExceptionGroup`` with ``ConnectError`` → ``transient``.

"""

from __future__ import annotations

import sys

import httpx
import pytest

from bundler_core.failures import MAX_BUNDLE_RETRIES, FailureKind, classify_failure

if sys.version_info < (3, 11):
    # AnyIO's ExceptionGroup is not supported in Python 3.10, so we use the exceptiongroup library instead.
    from exceptiongroup import ExceptionGroup


def _exception_group(*exceptions: Exception) -> ExceptionGroup:
    return ExceptionGroup("task group failure", list(exceptions))


@pytest.mark.parametrize(
    ("exc", "expected_kind"),
    [
        pytest.param(httpx.TimeoutException("download timed out"), FailureKind.TRANSIENT, id="httpx-timeout"),
        pytest.param(httpx.ConnectError("connection reset"), FailureKind.TRANSIENT, id="httpx-connect"),
        pytest.param(
            httpx.HTTPStatusError(
                "bad gateway",
                request=httpx.Request("GET", "https://example.com/object"),
                response=httpx.Response(502),
            ),
            FailureKind.TRANSIENT,
            id="http-502",
        ),
        pytest.param(
            httpx.HTTPStatusError(
                "service unavailable",
                request=httpx.Request("GET", "https://example.com/object"),
                response=httpx.Response(503),
            ),
            FailureKind.TRANSIENT,
            id="http-503",
        ),
        pytest.param(
            httpx.HTTPStatusError(
                "gateway timeout",
                request=httpx.Request("GET", "https://example.com/object"),
                response=httpx.Response(504),
            ),
            FailureKind.TRANSIENT,
            id="http-504",
        ),
        pytest.param(
            httpx.HTTPStatusError(
                "not found",
                request=httpx.Request("GET", "https://example.com/missing.txt"),
                response=httpx.Response(404),
            ),
            FailureKind.PERMANENT,
            id="http-404",
        ),
        pytest.param(
            httpx.HTTPStatusError(
                "forbidden",
                request=httpx.Request("GET", "https://example.com/denied.txt"),
                response=httpx.Response(403),
            ),
            FailureKind.PERMANENT,
            id="http-403",
        ),
        pytest.param(RuntimeError("zip finalize failed"), FailureKind.UNKNOWN, id="runtime-unknown"),
        # AnyIO's ExceptionGroup is not supported in Python 3.10, so we use the exceptiongroup library instead.
        pytest.param(
            _exception_group(
                httpx.ConnectError("all connection attempts failed"),
                httpx.ConnectError("all connection attempts failed"),
            ),
            FailureKind.TRANSIENT,
            id="exception-group-connect",
        ),
        pytest.param(
            _exception_group(
                httpx.TimeoutException("download timed out"),
            ),
            FailureKind.TRANSIENT,
            id="exception-group-timeout",
        ),
        pytest.param(
            _exception_group(
                httpx.HTTPStatusError(
                    "not found",
                    request=httpx.Request("GET", "https://example.com/missing.txt"),
                    response=httpx.Response(404),
                ),
            ),
            FailureKind.PERMANENT,
            id="exception-group-404",
        ),
        pytest.param(
            _exception_group(
                httpx.ConnectError("connection reset"),
                httpx.HTTPStatusError(
                    "not found",
                    request=httpx.Request("GET", "https://example.com/missing.txt"),
                    response=httpx.Response(404),
                ),
            ),
            FailureKind.PERMANENT,
            id="exception-group-mixed-permanent-wins",
        ),
        pytest.param(
            _exception_group(
                _exception_group(httpx.ConnectError("nested connect error")),
            ),
            FailureKind.TRANSIENT,
            id="exception-group-nested",
        ),
    ],
)
def test_classify_failure_kind(exc: Exception, expected_kind: FailureKind) -> None:
    """Map download/build exceptions to retry policy categories."""
    assert classify_failure(exc) == expected_kind
