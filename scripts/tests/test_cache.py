"""Tests for FileCache."""

from __future__ import annotations

import time
from pathlib import Path

from jit_update.cache import FileCache


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    assert cache.get("https://example.com/foo") is None


def test_cache_set_then_get(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("https://example.com/foo", b'{"hello": "world"}')
    assert cache.get("https://example.com/foo") == b'{"hello": "world"}'


def test_cache_expires_after_ttl(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=0)  # immediate expiry
    cache.set("https://example.com/foo", b"payload")
    time.sleep(0.01)
    assert cache.get("https://example.com/foo") is None


def test_cache_creates_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir"
    cache = FileCache(target, ttl_seconds=60)
    cache.set("https://example.com/x", b"y")
    assert target.exists()


def test_cache_keys_are_url_independent_paths(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("https://example.com/a", b"A")
    cache.set("https://example.com/b", b"B")
    assert cache.get("https://example.com/a") == b"A"
    assert cache.get("https://example.com/b") == b"B"
