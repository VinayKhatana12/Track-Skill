"""In-memory sliding-window rate limiting for the login endpoint."""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Process-local limiter, sufficient for the single-process dev API.

    Swap for a shared store (e.g. Redis) when running multiple workers.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def has_capacity(self, key: str, max_attempts: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            return len(hits) < max_attempts

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = SlidingWindowRateLimiter()
