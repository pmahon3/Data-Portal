"""
Request and error counters, served in the Prometheus text format (``GET /v1/metrics``).

Requests are counted by route template, never by path or query: a path names a user's file and the
query carries the link's token. A request that fails while its body is streaming has already been
counted with the status it started with.
"""
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
        """An unhandled exception (also counted as a 500 request)."""
        with self._lock:
            self._errors += 1

    def render(self) -> str:
        with self._lock:
            requests, errors = sorted(self._requests.items()), self._errors
        lines = [f"# HELP {PREFIX}_requests_total Requests by method, route and status code.",
                 f"# TYPE {PREFIX}_requests_total counter"]
        lines += [f'{PREFIX}_requests_total{{method="{m}",route="{r}",code="{c}"}} {n}' for (m, r, c), n in requests]
        lines += [f"# HELP {PREFIX}_errors_total Requests that ended in an unhandled exception.",
                  f"# TYPE {PREFIX}_errors_total counter",
                  f"{PREFIX}_errors_total {errors}"]
        return "\n".join(lines) + "\n"
