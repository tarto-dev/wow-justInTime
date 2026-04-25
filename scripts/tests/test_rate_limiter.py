"""Tests for the token-bucket rate limiter."""

from __future__ import annotations

import time

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
    assert 0.15 < elapsed < 0.5, f"expected ~0.2s of throttling, got {elapsed:.3f}s"


def test_invalid_rate_raises() -> None:
    with pytest.raises(ValueError):
        RateLimiter(rate_per_minute=0, capacity=1)
    with pytest.raises(ValueError):
        RateLimiter(rate_per_minute=10, capacity=0)
