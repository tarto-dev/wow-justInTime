"""Tests for BlizzardClient OAuth + Game Data endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from jit_update.blizzard import BlizzardClient, BlizzardError
from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter


@pytest.fixture
def cache(tmp_path: Path) -> FileCache:
    # TTL of 1 day — effectively never expires during a test run
    return FileCache(tmp_path / "cache", ttl_seconds=86400.0)


@pytest.fixture
def rate_limiter() -> RateLimiter:
    # rate_per_minute + capacity: effectively no blocking in tests
    return RateLimiter(rate_per_minute=60000.0, capacity=10000)


@pytest.fixture
def client(cache: FileCache, rate_limiter: RateLimiter) -> BlizzardClient:
    return BlizzardClient(
        client_id="test_id",
        client_secret="test_secret",
        region="eu",
        cache=cache,
        rate_limiter=rate_limiter,
    )


@respx.mock
def test_client_obtains_oauth_token_on_first_call(client: BlizzardClient) -> None:
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok_123", "expires_in": 86400, "token_type": "bearer"}
        )
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        return_value=httpx.Response(200, json={"current_period": {"id": 1062}, "periods": []})
    )
    period_id = client.get_current_period_id()
    assert period_id == 1062


@respx.mock
def test_client_caches_token_between_calls(client: BlizzardClient) -> None:
    token_route = respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok_456", "expires_in": 86400, "token_type": "bearer"}
        )
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        return_value=httpx.Response(200, json={"current_period": {"id": 1062}, "periods": []})
    )
    client.get_current_period_id()
    client.get_current_period_id()
    # Token call only once even though we hit two endpoints
    assert token_route.call_count == 1


@respx.mock
def test_client_refreshes_token_on_401(client: BlizzardClient) -> None:
    token_calls = respx.post("https://oauth.battle.net/token").mock(
        side_effect=[
            httpx.Response(
                200, json={"access_token": "stale", "expires_in": 86400, "token_type": "bearer"}
            ),
            httpx.Response(
                200, json={"access_token": "fresh", "expires_in": 86400, "token_type": "bearer"}
            ),
        ]
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        side_effect=[
            httpx.Response(401, json={"error": "unauthorized"}),
            httpx.Response(200, json={"current_period": {"id": 1062}, "periods": []}),
        ]
    )
    period_id = client.get_current_period_id()
    assert period_id == 1062
    assert token_calls.call_count == 2


@respx.mock
def test_client_raises_on_repeated_401(client: BlizzardClient) -> None:
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok", "expires_in": 86400, "token_type": "bearer"}
        )
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    with pytest.raises(BlizzardError, match="unauthorized|401"):
        client.get_current_period_id()


import json


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@respx.mock
def test_get_connected_realms_index_returns_realm_ids(client: BlizzardClient) -> None:
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "t", "expires_in": 86400}
        )
    )
    respx.get("https://eu.api.blizzard.com/data/wow/connected-realm/index").mock(
        return_value=httpx.Response(
            200,
            json={
                "connected_realms": [
                    {"href": "https://eu.api.blizzard.com/data/wow/connected-realm/1080?namespace=dynamic-eu"},
                    {"href": "https://eu.api.blizzard.com/data/wow/connected-realm/1084?namespace=dynamic-eu"},
                ]
            },
        )
    )
    realms = client.get_connected_realms_index()
    assert realms == [1080, 1084]


@respx.mock
def test_get_dungeons_index_returns_id_to_name_mapping(client: BlizzardClient) -> None:
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "t", "expires_in": 86400}
        )
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/dungeon/index").mock(
        return_value=httpx.Response(
            200,
            json={
                "dungeons": [
                    {"id": 402, "name": "Algeth'ar Academy"},
                    {"id": 499, "name": "Priory of the Sacred Flame"},
                    {"id": 500, "name": "The Rookery"},
                ]
            },
        )
    )
    mapping = client.get_dungeons_index()
    assert mapping == {
        402: "Algeth'ar Academy",
        499: "Priory of the Sacred Flame",
        500: "The Rookery",
    }


@respx.mock
def test_client_retries_on_500(client: BlizzardClient) -> None:
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "t", "expires_in": 86400}
        )
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        side_effect=[
            httpx.Response(500, text="Downstream Error"),
            httpx.Response(200, json={"current_period": {"id": 1062}, "periods": []}),
        ]
    )
    period_id = client.get_current_period_id()
    assert period_id == 1062


@respx.mock
def test_client_raises_after_repeated_500(client: BlizzardClient) -> None:
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "t", "expires_in": 86400}
        )
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        return_value=httpx.Response(500, text="Downstream Error")
    )
    with pytest.raises(BlizzardError, match="500|Downstream"):
        client.get_current_period_id()


@respx.mock
def test_get_leaderboard_runs_parses_leading_groups(client: BlizzardClient) -> None:
    sample = json.loads((FIXTURE_DIR / "blizzard_leaderboard_sample.json").read_text())
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "t", "expires_in": 86400}
        )
    )
    respx.get(
        "https://eu.api.blizzard.com/data/wow/connected-realm/1080/mythic-leaderboard/402/period/1062"
    ).mock(return_value=httpx.Response(200, json=sample))
    runs = client.get_leaderboard_runs(
        realm_id=1080,
        dungeon_id=402,
        period_id=1062,
        dungeon_slug="algethar-academy",
    )
    assert len(runs) == 3
    assert {r.keystone_level for r in runs} == {15, 16, 19}
    assert all(r.realm_id == 1080 and r.region == "eu" for r in runs)
