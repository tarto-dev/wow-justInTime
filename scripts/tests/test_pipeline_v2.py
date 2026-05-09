"""Tests for the rewritten pipeline (Blizzard discovery + synthesis).

These will be merged into test_pipeline.py once Task 13 retires the
v1 build_document / per-affix code.
"""

from __future__ import annotations

from typing import Any

import pytest

from jit_update.models import BlizzardRun


class StubBlizzardClient:
    """Fakes BlizzardClient for pipeline testing."""

    def __init__(
        self,
        period_id: int,
        realm_ids: list[int],
        runs_by_realm_dungeon: dict[tuple[int, int], list[BlizzardRun]],
    ) -> None:
        self._period_id = period_id
        self._realm_ids = realm_ids
        self._runs = runs_by_realm_dungeon
        self.calls: list[tuple[int, int]] = []

    def get_current_period_id(self) -> int:
        return self._period_id

    def get_connected_realms_index(self) -> list[int]:
        return self._realm_ids

    def get_leaderboard_runs(
        self,
        *,
        realm_id: int,
        dungeon_id: int,
        period_id: int,
        dungeon_slug: str,
    ) -> list[BlizzardRun]:
        self.calls.append((realm_id, dungeon_id))
        return self._runs.get((realm_id, dungeon_id), [])


def test_discover_runs_aggregates_by_dungeon_and_level() -> None:
    from jit_update.pipeline import discover_runs

    run_a_19 = BlizzardRun(
        dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062,
        keystone_level=19, duration_ms=1816344, completed_timestamp=1,
    )
    run_a_15 = BlizzardRun(
        dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062,
        keystone_level=15, duration_ms=2103556, completed_timestamp=2,
    )
    run_a_15_b = BlizzardRun(
        dungeon_slug="algethar-academy", region="eu", realm_id=1084, period=1062,
        keystone_level=15, duration_ms=2200000, completed_timestamp=3,
    )
    runs_by_realm = {
        (1080, 402): [run_a_19, run_a_15],
        (1084, 402): [run_a_15_b],
    }
    blizz = StubBlizzardClient(
        period_id=1062, realm_ids=[1080, 1084], runs_by_realm_dungeon=runs_by_realm
    )
    dungeons = [{"slug": "algethar-academy", "map_challenge_mode_id": 402}]

    result = discover_runs(blizz, dungeons=dungeons, levels=[15, 19])

    assert set(result.keys()) == {"algethar-academy"}
    assert sorted(result["algethar-academy"].keys()) == [15, 19]
    assert len(result["algethar-academy"][15]) == 2
    assert len(result["algethar-academy"][19]) == 1


def test_discover_runs_filters_levels_outside_scope() -> None:
    from jit_update.pipeline import discover_runs

    run_2 = BlizzardRun(
        dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062,
        keystone_level=2, duration_ms=999, completed_timestamp=1,
    )
    run_15 = BlizzardRun(
        dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062,
        keystone_level=15, duration_ms=2103556, completed_timestamp=2,
    )
    runs_by_realm = {(1080, 402): [run_2, run_15]}
    blizz = StubBlizzardClient(
        period_id=1062, realm_ids=[1080], runs_by_realm_dungeon=runs_by_realm
    )
    dungeons = [{"slug": "algethar-academy", "map_challenge_mode_id": 402}]

    result = discover_runs(blizz, dungeons=dungeons, levels=[15, 16, 17])

    assert 2 not in result["algethar-academy"]
    assert 15 in result["algethar-academy"]


def test_select_slowest_percentile_returns_slowest_runs() -> None:
    from jit_update.pipeline import select_slowest_percentile

    runs = [
        BlizzardRun(
            dungeon_slug="d", region="eu", realm_id=1, period=1,
            keystone_level=15, duration_ms=ms, completed_timestamp=i,
        )
        for i, ms in enumerate([1_000_000, 1_500_000, 2_000_000, 2_500_000, 3_000_000])
    ]
    # 20% of 5 = 1, but min_count=2, so we get 2 slowest
    selected = select_slowest_percentile(runs, percentile=20, min_count=2)
    assert len(selected) == 2
    assert {r.duration_ms for r in selected} == {3_000_000, 2_500_000}


def test_select_slowest_percentile_handles_empty_input() -> None:
    from jit_update.pipeline import select_slowest_percentile

    assert select_slowest_percentile([], percentile=10, min_count=2) == []


def test_select_slowest_percentile_rejects_invalid_percentile() -> None:
    from jit_update.pipeline import select_slowest_percentile

    with pytest.raises(ValueError):
        select_slowest_percentile([], percentile=150, min_count=2)


def test_index_real_splits_by_level_groups_by_keystone_level() -> None:
    from jit_update.pipeline import index_real_splits_by_level

    splits_22 = [425000, 850000, 1275000, 1700000]
    splits_18 = [500000, 1000000, 1500000, 2000000]

    class StubRaider:
        def get_runs(
            self,
            season: str,
            region: str,
            dungeon: str,
            page: int,
            affixes: str = "all",
        ) -> dict[str, Any]:
            return {
                "rankings": [
                    {"run": {"keystone_run_id": 1, "mythic_level": 22}},
                    {"run": {"keystone_run_id": 2, "mythic_level": 18}},
                    {"run": {"keystone_run_id": 3, "mythic_level": 14}},  # outside scope
                ]
            }

        def get_run_details(self, season: str, run_id: int) -> dict[str, Any]:
            base = {
                "season": season,
                "status": "finished",
                "keystone_run_id": run_id,
                "keystone_time_ms": 1860999,
                "completed_at": "2026-05-03T07:33:46.051Z",
                "logged_run_id": 99 if run_id != 3 else None,
                "num_chests": 1,
                "time_remaining_ms": 100000,
                "weekly_modifiers": [],
                "dungeon": {
                    "id": 14032,
                    "name": "Algeth'ar Academy",
                    "slug": "algethar-academy",
                    "short_name": "AA",
                    "map_challenge_mode_id": 402,
                    "keystone_timer_ms": 1860999,
                    "num_bosses": 4,
                },
            }
            if run_id == 1:
                base["mythic_level"] = 22
                base["clear_time_ms"] = 1700000
                base["logged_details"] = {
                    "encounters": [
                        {
                            "id": i,
                            "status": "finished",
                            "duration_ms": 1,
                            "is_success": True,
                            "approximate_relative_started_at": 0,
                            "approximate_relative_ended_at": s,
                            "boss": {
                                "name": f"B{i}",
                                "slug": f"b{i}",
                                "ordinal": i,
                                "wowEncounterId": 1000 + i,
                            },
                        }
                        for i, s in enumerate(splits_22)
                    ]
                }
            elif run_id == 2:
                base["mythic_level"] = 18
                base["clear_time_ms"] = 2000000
                base["logged_details"] = {
                    "encounters": [
                        {
                            "id": i,
                            "status": "finished",
                            "duration_ms": 1,
                            "is_success": True,
                            "approximate_relative_started_at": 0,
                            "approximate_relative_ended_at": s,
                            "boss": {
                                "name": f"B{i}",
                                "slug": f"b{i}",
                                "ordinal": i,
                                "wowEncounterId": 1000 + i,
                            },
                        }
                        for i, s in enumerate(splits_18)
                    ]
                }
            else:  # run_id == 3, no logged details
                base["mythic_level"] = 14
                base["clear_time_ms"] = 2500000
                base["logged_details"] = None
            return base

    result = index_real_splits_by_level(
        StubRaider(),
        season="season-mn-1",
        dungeon_slug="algethar-academy",
        levels_in_scope=[18, 19, 20, 21, 22],
        num_bosses=4,
    )
    assert sorted(result.keys()) == [18, 22]
    assert result[22] == [splits_22]
    assert result[18] == [splits_18]
