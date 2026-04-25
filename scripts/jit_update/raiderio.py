"""HTTP client for Raider.IO Mythic+ endpoints."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter


class RaiderIOError(RuntimeError):
    """Raised when Raider.IO responds with an unrecoverable error."""


class RaiderIOClient:
    """Thin wrapper around Raider.IO endpoints with rate limit + cache + retry.

    Read-only. Stateless beyond the cache + rate limiter passed at construction.

    `max_retries` counts *additional* retries after the first attempt.
    Default 3 means up to 4 total HTTP calls per logical request.
    """

    def __init__(
        self,
        base_url: str,
        rate_limiter: RateLimiter,
        cache: FileCache,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._rl = rate_limiter
        self._cache = cache
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._client = httpx.Client(timeout=timeout_seconds)

    def _build_url(self, path: str, params: dict[str, str | int] | None) -> str:
        url = f"{self._base_url}{path}"
        if params:
            sorted_items = sorted(params.items())
            query = "&".join(f"{k}={v}" for k, v in sorted_items)
            url = f"{url}?{query}"
        return url

    def _request_json(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> dict[str, Any]:
        url = self._build_url(path, params)

        cached = self._cache.get(url)
        if cached is not None:
            try:
                decoded_cached: dict[str, Any] = json.loads(cached.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise RaiderIOError(f"corrupt cache for {url}") from exc
            return decoded_cached

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._rl.acquire()
            try:
                resp = self._client.get(url)
                if resp.status_code >= 500:
                    last_exc = RaiderIOError(f"server error {resp.status_code} on {url}")
                    self._sleep_backoff(attempt)
                    continue
                if resp.status_code >= 400:
                    raise RaiderIOError(f"client error {resp.status_code} on {url}")
                payload = resp.content
                try:
                    decoded_fresh: dict[str, Any] = json.loads(payload.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise RaiderIOError(f"invalid JSON from {url}") from exc
                self._cache.set(url, payload)
                return decoded_fresh
            except httpx.TimeoutException as exc:
                last_exc = exc
                self._sleep_backoff(attempt)
                continue
        raise RaiderIOError(
            f"giving up after {self._max_retries + 1} attempts on {url}"
        ) from last_exc

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        time.sleep(min(2.0**attempt, 8.0))

    # ─── public endpoints ───────────────────────────────────────────────

    def get_static_data(self, expansion_id: int) -> dict[str, Any]:
        """Fetch static Mythic+ data for the given expansion.

        Args:
            expansion_id: Numeric expansion ID (e.g. 11 for The War Within).

        Returns:
            Parsed JSON payload from the static-data endpoint.
        """
        return self._request_json("/mythic-plus/static-data", {"expansion_id": expansion_id})

    def get_runs(
        self,
        season: str,
        region: str,
        dungeon: str,
        page: int = 0,
        affixes: str = "all",
    ) -> dict[str, Any]:
        """Fetch ranked Mythic+ runs for a dungeon/season/region combo.

        Args:
            season: Season slug (e.g. "season-mn-1").
            region: Region slug (e.g. "world", "us", "eu").
            dungeon: Dungeon slug (e.g. "algethar-academy").
            page: Zero-based page index.
            affixes: Affixes filter ("all" returns all affix combinations).

        Returns:
            Parsed JSON payload with ``rankings`` list.
        """
        return self._request_json(
            "/mythic-plus/runs",
            {
                "season": season,
                "region": region,
                "dungeon": dungeon,
                "affixes": affixes,
                "page": page,
            },
        )

    def get_run_details(self, season: str, run_id: int) -> dict[str, Any]:
        """Fetch detailed information for a single Mythic+ run.

        Args:
            season: Season slug (e.g. "season-mn-1").
            run_id: Numeric keystone run ID.

        Returns:
            Parsed JSON payload with boss encounter details.
        """
        return self._request_json("/mythic-plus/run-details", {"season": season, "id": run_id})

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
