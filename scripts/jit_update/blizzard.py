"""HTTP client for Battle.net Game Data API (mythic-keystone-leaderboard)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter


class BlizzardError(RuntimeError):
    """Raised when Battle.net responds with an unrecoverable error."""


REGION_BASE_URLS = {
    "us": "https://us.api.blizzard.com",
    "eu": "https://eu.api.blizzard.com",
    "kr": "https://kr.api.blizzard.com",
    "tw": "https://tw.api.blizzard.com",
}

OAUTH_TOKEN_URL = "https://oauth.battle.net/token"
TOKEN_TTL_BUFFER_SECONDS = 3600  # refresh 1h before stated expiry


class BlizzardClient:
    """Battle.net Game Data API client with OAuth + cache + rate limit + retry.

    Read-only. Token is cached in memory + on disk for ~23h.

    Note: FileCache stores raw bytes, so token metadata is JSON-serialised
    before writing and deserialised on read.  FileCache.get() uses a URL-style
    string key whose TTL is governed by the cache's own ttl_seconds — callers
    should construct the cache with an appropriate TTL (e.g. 23 hours).
    RateLimiter is initialised with rate_per_minute + capacity rather than
    rate_per_second.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        region: str,
        cache: FileCache,
        rate_limiter: RateLimiter,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        if region not in REGION_BASE_URLS:
            raise ValueError(
                f"unsupported region {region!r}; expected one of {list(REGION_BASE_URLS)}"
            )
        self._client_id = client_id
        self._client_secret = client_secret
        self._region = region
        self._namespace = f"dynamic-{region}"
        self._base = REGION_BASE_URLS[region]
        self._cache = cache
        self._rl = rate_limiter
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(timeout=timeout_seconds)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _ensure_token(self, force_refresh: bool = False) -> str:
        """Return a valid access token, fetching a new one when needed.

        Uses an in-memory short-circuit first, then falls back to the disk
        cache (FileCache stores bytes; token envelope is JSON-encoded).
        force_refresh bypasses both caches and always hits the OAuth endpoint.
        """
        now = time.time()
        if not force_refresh and self._token and now < self._token_expires_at:
            return self._token

        # Disk cache check — FileCache.get() returns bytes | None
        cache_key = f"blizzard/oauth_token/{self._client_id}"
        if not force_refresh:
            cached_bytes = self._cache.get(cache_key)
            if cached_bytes is not None:
                try:
                    cached = json.loads(cached_bytes.decode("utf-8"))
                    if isinstance(cached, dict) and cached.get("expires_at", 0) > now:
                        self._token = cached["token"]
                        self._token_expires_at = cached["expires_at"]
                        return self._token
                except (ValueError, KeyError):
                    pass  # corrupt cache entry — fall through to re-fetch

        # Request a new token from Battle.net OAuth endpoint
        resp = self._http.post(
            OAUTH_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
        )
        if resp.status_code != 200:
            raise BlizzardError(
                f"OAuth token request failed: status={resp.status_code} body={resp.text[:200]}"
            )
        payload = resp.json()
        token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 86400))
        expires_at = now + max(60, expires_in - TOKEN_TTL_BUFFER_SECONDS)

        self._token = token
        self._token_expires_at = expires_at

        # Persist to disk — FileCache.set() expects bytes
        envelope = json.dumps({"token": token, "expires_at": expires_at}).encode("utf-8")
        self._cache.set(cache_key, envelope)

        return token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET a Game Data endpoint with token + namespace + retry on 401."""
        params = dict(params or {})
        params.setdefault("namespace", self._namespace)
        params.setdefault("locale", "en_US")
        url = f"{self._base}{path}"
        attempted_refresh = False

        for attempt in range(self._max_retries + 1):
            self._rl.acquire()
            token = self._ensure_token(force_refresh=False)
            resp = self._http.get(
                url, params=params, headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401 and not attempted_refresh:
                # Invalidate in-memory token so _ensure_token fetches fresh
                self._token = None
                self._token_expires_at = 0.0
                self._ensure_token(force_refresh=True)
                attempted_refresh = True
                continue
            if resp.status_code in (429, 503):
                if attempt < self._max_retries:
                    time.sleep(2**attempt)
                    continue
            raise BlizzardError(
                f"Battle.net request failed: GET {url} "
                f"status={resp.status_code} body={resp.text[:200]}"
            )

        raise BlizzardError(f"Battle.net request exhausted retries: GET {url}")

    # ------------------------------------------------------------------
    # Game Data endpoints
    # ------------------------------------------------------------------

    def get_current_period_id(self) -> int:
        """Return the current Mythic+ period ID for the configured region."""
        payload = self._request_json("/data/wow/mythic-keystone/period/index")
        period = payload.get("current_period")
        if not isinstance(period, dict) or "id" not in period:
            raise BlizzardError(f"unexpected /period/index payload: {payload!r}")
        return int(period["id"])

    def get_connected_realms_index(self) -> list[int]:
        """Return all connected-realm IDs for the configured region.

        Parses the ``connected_realms[].href`` URLs to extract numeric IDs.
        """
        import re

        payload = self._request_json("/data/wow/connected-realm/index")
        result: list[int] = []
        for item in payload.get("connected_realms", []):
            href = item.get("href", "")
            m = re.search(r"/connected-realm/(\d+)", href)
            if m:
                result.append(int(m.group(1)))
        return result

    def get_dungeons_index(self) -> dict[int, str]:
        """Return mapping ``dungeon_id -> dungeon name`` (English locale)."""
        payload = self._request_json("/data/wow/mythic-keystone/dungeon/index")
        return {
            int(d["id"]): d["name"]
            for d in payload.get("dungeons", [])
            if "id" in d and "name" in d
        }

    def get_leaderboard_runs(
        self,
        *,
        realm_id: int,
        dungeon_id: int,
        period_id: int,
        dungeon_slug: str,
    ) -> list["BlizzardRun"]:
        """Return normalized BlizzardRun objects for one realm/dungeon/period leaderboard.

        The Blizzard payload is parsed via ``BlizzardLeaderboardResponse`` and each
        leading_group is wrapped in a ``BlizzardRun`` carrying the dungeon slug,
        region, realm_id, and period that the raw response omits.
        """
        from jit_update.models import BlizzardLeaderboardResponse, BlizzardRun

        path = (
            f"/data/wow/connected-realm/{realm_id}"
            f"/mythic-leaderboard/{dungeon_id}/period/{period_id}"
        )
        payload = self._request_json(path)
        parsed = BlizzardLeaderboardResponse.model_validate(payload)
        return [
            BlizzardRun.from_group(
                g,
                dungeon_slug=dungeon_slug,
                region=self._region,
                realm_id=realm_id,
                period=period_id,
            )
            for g in parsed.leading_groups
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()
