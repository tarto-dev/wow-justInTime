"""Tests for the token-bucket rate limiter."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from jit_update.rate_limiter import RateLimiter


def test_first_n_calls_within_capacity_are_immediate() -> None:
    rl = RateLimiter(rate_per_minute=600, capacity=10)  # 10 req/sec
    start = time.monotonic()
    for _ in range(5):
        rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, "first 5 calls should be near-instant"


def test_calls_beyond_capacity_are_throttled() -> None:
    rl = RateLimiter(rate_per_minute=600, capacity=2)  # 10 req/sec, 2 burst
    start = time.monotonic()
    for _ in range(4):
        rl.acquire()
    elapsed = time.monotonic() - start
    # 4 tokens needed, 2 in burst → 2 require ~0.1s each at 10/s
    assert 0.10 < elapsed < 0.5, f"expected ~0.2s of throttling, got {elapsed:.3f}s"


def test_invalid_rate_raises() -> None:
    with pytest.raises(ValueError):
        RateLimiter(rate_per_minute=0, capacity=1)
    with pytest.raises(ValueError):
        RateLimiter(rate_per_minute=10, capacity=0)


def test_concurrent_acquires_respect_capacity() -> None:
    """8 threads acquire 1 token each from a 4-capacity 600/min limiter; total
    elapsed should reflect ~4 tokens worth of throttling (~0.4s for the second
    half), not zero (which would indicate the race condition was reintroduced)."""
    rl = RateLimiter(rate_per_minute=600, capacity=4)
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda _: rl.acquire(), range(8)))
    elapsed = time.monotonic() - start
    # 4 immediate (burst) + 4 throttled @ 10/sec ≈ 0.4s minimum
    assert elapsed > 0.3, f"expected throttling to take >0.3s, got {elapsed:.3f}s"
    assert elapsed < 1.0, f"expected <1.0s upper bound, got {elapsed:.3f}s"
