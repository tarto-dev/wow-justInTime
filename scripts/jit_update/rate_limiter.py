"""Token-bucket rate limiter."""

from __future__ import annotations

import time
from threading import Lock


class RateLimiter:
    """Simple token-bucket limiter.

    Tokens replenish continuously at ``rate_per_minute / 60`` per second, up to
    ``capacity``. :meth:`acquire` blocks until a token is available.
    """

    def __init__(self, rate_per_minute: float, capacity: int) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._tokens_per_sec = rate_per_minute / 60.0
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def acquire(self) -> None:
        """Block until one token is available, then consume it."""
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._tokens_per_sec
            time.sleep(wait)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._tokens_per_sec)
        self._last_refill = now
