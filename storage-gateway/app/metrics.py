"""
Count requests and errors, and serve them in the Prometheus text format (``GET /v1/metrics``).

Requests are counted by route template, never by path or query: a path names a user's file and the
query carries the link's token. A request that fails while its body is streaming has already been
counted with the status it started with.
"""
from __future__ import annotations

import threading
from collections import Counter

PREFIX = "posix_file_service"


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._errors = 0

    def request(self, method: str, route: str, code: int):
        with self._lock:
            self._requests[(method, route, code)] += 1

    def error(self):
        """Count an unhandled exception (also counted as a 500 request)."""
        with self._lock:
            self._errors += 1

    def render(self) -> str:
        """
        Return the counters as Prometheus text.

        Example: ``posix_file_service_requests_total{method="GET",route="/v1/health",code="200"} 3``
        """
        with self._lock:
            requests = sorted(self._requests.items())
            errors = self._errors
        lines = [
            f"# HELP {PREFIX}_requests_total Requests by method, route and status code.",
            f"# TYPE {PREFIX}_requests_total counter",
        ]
        for (method, route, code), count in requests:
            labels = f'method="{method}",route="{route}",code="{code}"'
            lines.append(f"{PREFIX}_requests_total{{{labels}}} {count}")
        lines += [
            f"# HELP {PREFIX}_errors_total Requests that ended in an unhandled exception.",
            f"# TYPE {PREFIX}_errors_total counter",
            f"{PREFIX}_errors_total {errors}",
        ]
        return "\n".join(lines) + "\n"
