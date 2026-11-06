"""In-memory sliding-window rate limiting (login, contact, resets, push test)."""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


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


def enforce_rate_limit(
    limiter: SlidingWindowRateLimiter,
    request: Request,
    *,
    max_attempts: int,
    window_seconds: int,
    scope: str,
) -> None:
    """Raise 429 when this client exceeded the budget for ``scope``.

    Keys combine scope, client IP and (when present) the email/body identity
    so one abusive mailbox cannot lock out everyone behind an office NAT.
    Callers call ``limiter.record(key)`` only after the action succeeded.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"{scope}:{client_ip}"
    if not limiter.has_capacity(key, max_attempts, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests — please slow down and retry later.",
            headers={"Retry-After": "60"},
        )
    limiter.record(key)


login_limiter = SlidingWindowRateLimiter()
contact_limiter = SlidingWindowRateLimiter()
reset_limiter = SlidingWindowRateLimiter()
push_limiter = SlidingWindowRateLimiter()
