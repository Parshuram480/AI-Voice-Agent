"""Latency tracking utilities."""

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator


class LatencyTracker:
    """Collects timing metrics into a provided dict."""

    def __init__(self, timings: dict[str, float]) -> None:
        self._timings = timings

    @contextmanager
    def track(self, name: str) -> Iterator[None]:
        start = perf_counter()
        yield
        self._timings[name] = round(perf_counter() - start, 4)
