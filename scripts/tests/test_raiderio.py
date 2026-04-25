"""Tests for RaiderIOClient."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from jit_update.cache import FileCache
from jit_update.raiderio import RaiderIOClient, RaiderIOError
from jit_update.rate_limiter import RateLimiter


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the exponential backoff sleep in retry tests to keep them fast."""
    monkeypatch.setattr(RaiderIOClient, "_sleep_backoff", staticmethod(lambda _: None))


def _client(tmp_path: Path) -> RaiderIOClient:
    return RaiderIOClient(
        base_url="https://raider.io/api/v1",
        rate_limiter=RateLimiter(rate_per_minute=6000, capacity=10),
        cache=FileCache(tmp_path / "cache", ttl_seconds=60),
        timeout_seconds=5.0,
        max_retries=2,
    )


@respx.mock
def test_get_static_data_returns_payload(
    tmp_path: Path, load_fixture: Callable[[str], dict[str, Any]]
) -> None:
    payload = load_fixture("static_data_mn1.json")
    route = respx.get(
        "https://raider.io/api/v1/mythic-plus/static-data",
        params={"expansion_id": "11"},
    ).mock(return_value=httpx.Response(200, json=payload))

    client = _client(tmp_path)
    data = client.get_static_data(expansion_id=11)

    assert route.called
    assert data["seasons"][0]["slug"] == "season-mn-1"


@respx.mock
def test_get_runs_filters_via_query_params(
    tmp_path: Path, load_fixture: Callable[[str], dict[str, Any]]
) -> None:
    payload = load_fixture("runs_aa_p0.json")
    route = respx.get(
        "https://raider.io/api/v1/mythic-plus/runs",
        params={
            "season": "season-mn-1",
            "region": "world",
            "dungeon": "algethar-academy",
            "affixes": "all",
            "page": "0",
        },
    ).mock(return_value=httpx.Response(200, json=payload))

    client = _client(tmp_path)
    data = client.get_runs(season="season-mn-1", region="world", dungeon="algethar-academy", page=0)

    assert route.called
    assert data["rankings"][0]["rank"] == 1


@respx.mock
def test_cache_short_circuits_second_call(
    tmp_path: Path, load_fixture: Callable[[str], dict[str, Any]]
) -> None:
    payload = load_fixture("runs_aa_p0.json")
    route = respx.get("https://raider.io/api/v1/mythic-plus/runs").mock(
        return_value=httpx.Response(200, json=payload)
    )

    client = _client(tmp_path)
    client.get_runs(season="season-mn-1", region="world", dungeon="algethar-academy", page=0)
    client.get_runs(season="season-mn-1", region="world", dungeon="algethar-academy", page=0)

    assert route.call_count == 1, "second call should be served from cache"


@respx.mock
def test_retries_on_5xx_then_succeeds(
    tmp_path: Path, load_fixture: Callable[[str], dict[str, Any]]
) -> None:
    payload = load_fixture("runs_aa_p0.json")
    route = respx.get("https://raider.io/api/v1/mythic-plus/runs").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json=payload),
        ]
    )

    client = _client(tmp_path)
    data = client.get_runs(season="season-mn-1", region="world", dungeon="algethar-academy", page=0)

    assert route.call_count == 3
    assert data["rankings"][0]["rank"] == 1


@respx.mock
def test_gives_up_after_max_retries(tmp_path: Path) -> None:
    respx.get("https://raider.io/api/v1/mythic-plus/runs").mock(return_value=httpx.Response(500))

    client = _client(tmp_path)
    with pytest.raises(RaiderIOError):
        client.get_runs(
            season="season-mn-1",
            region="world",
            dungeon="algethar-academy",
            page=0,
        )


@respx.mock
def test_get_run_details_uses_id_path_param(
    tmp_path: Path, load_fixture: Callable[[str], dict[str, Any]]
) -> None:
    payload = load_fixture("run_details_sample.json")
    route = respx.get(
        "https://raider.io/api/v1/mythic-plus/run-details",
        params={"season": "season-mn-1", "id": "16544744"},
    ).mock(return_value=httpx.Response(200, json=payload))

    client = _client(tmp_path)
    data = client.get_run_details(season="season-mn-1", run_id=16544744)

    assert route.called
    assert data["keystone_run_id"] == 16544744
