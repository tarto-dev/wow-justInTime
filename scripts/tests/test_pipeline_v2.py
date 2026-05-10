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
    dungeons = [{"slug": "algethar-academy", "challenge_mode_id": 402}]

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
    dungeons = [{"slug": "algethar-academy", "challenge_mode_id": 402}]

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


def test_aggregate_cell_uses_raiderio_when_real_splits_present() -> None:
    from jit_update.pipeline import aggregate_cell

    runs = [
        BlizzardRun(
            dungeon_slug="d", region="eu", realm_id=1, period=1,
            keystone_level=20, duration_ms=1700000, completed_timestamp=1,
        ),
        BlizzardRun(
            dungeon_slug="d", region="eu", realm_id=1, period=1,
            keystone_level=20, duration_ms=1750000, completed_timestamp=2,
        ),
    ]
    real_splits_at_level = [[425000, 850000, 1275000, 1700000]]
    observed_ratios: list[float | None] = [0.5, 0.5, 0.5, 0.5]  # would be wrong if used

    cell = aggregate_cell(runs, real_splits_at_level, observed_ratios, num_bosses=4)
    assert cell.splits_source == "raiderio"
    # Median of [1700000, 1750000] = 1725000
    assert cell.clear_time_ms == 1725000
    # Median of one input list = the input itself
    assert cell.boss_splits_ms == [425000, 850000, 1275000, 1700000]
    assert cell.sample_size == 2


def test_aggregate_cell_synthesizes_when_no_real_splits() -> None:
    from jit_update.pipeline import aggregate_cell

    runs = [
        BlizzardRun(
            dungeon_slug="d", region="eu", realm_id=1, period=1,
            keystone_level=15, duration_ms=2000000, completed_timestamp=1,
        ),
    ]
    real_splits_at_level: list[list[int]] = []
    observed_ratios: list[float | None] = [0.25, 0.5, 0.75, 1.0]

    cell = aggregate_cell(runs, real_splits_at_level, observed_ratios, num_bosses=4)
    assert cell.splits_source == "synthesized"
    assert cell.clear_time_ms == 2000000
    assert cell.boss_splits_ms == [500000, 1000000, 1500000, 2000000]


def test_aggregate_cell_falls_back_to_equidistant_when_no_ratios() -> None:
    from jit_update.pipeline import aggregate_cell

    runs = [
        BlizzardRun(
            dungeon_slug="d", region="eu", realm_id=1, period=1,
            keystone_level=15, duration_ms=2000000, completed_timestamp=1,
        ),
    ]
    cell = aggregate_cell(runs, [], [None, None, None, None], num_bosses=4)
    assert cell.splits_source == "equidistant_fallback"
    assert cell.boss_splits_ms == [500000, 1000000, 1500000, 2000000]


def test_aggregate_cell_raises_on_empty_runs() -> None:
    from jit_update.pipeline import aggregate_cell

    with pytest.raises(ValueError, match="at least one"):
        aggregate_cell([], [], [None, None, None, None], num_bosses=4)


from datetime import datetime


def test_build_document_from_discovered_assembles_meta_and_dungeons_with_v2_schema(
    tmp_path: Any,
) -> None:
    from jit_update.cache import FileCache
    from jit_update.pipeline import build_document_from_discovered

    static = {
        "seasons": [
            {
                "slug": "season-mn-1",
                "dungeons": [
                    {
                        "slug": "algethar-academy",
                        "id": 14032,
                        "name": "Algeth'ar Academy",
                        "short_name": "AA",
                        "challenge_mode_id": 402,
                        "map_challenge_mode_id": 402,
                        "keystone_timer_seconds": 1861,
                    }
                ],
            }
        ]
    }

    runs_at_15 = [
        BlizzardRun(
            dungeon_slug="algethar-academy", region="eu", realm_id=1, period=1062,
            keystone_level=15, duration_ms=2000000, completed_timestamp=1,
        ),
        BlizzardRun(
            dungeon_slug="algethar-academy", region="eu", realm_id=1, period=1062,
            keystone_level=15, duration_ms=2050000, completed_timestamp=2,
        ),
    ] * 15  # 30 runs to clear min_sample
    runs_at_22 = [
        BlizzardRun(
            dungeon_slug="algethar-academy", region="eu", realm_id=1, period=1062,
            keystone_level=22, duration_ms=1700000, completed_timestamp=3,
        ),
    ] * 30
    discovered = {"algethar-academy": {15: runs_at_15, 22: runs_at_22}}

    class StubRaider:
        def get_static_data(self, expansion_id: int) -> dict[str, Any]:
            return static

        def get_runs(
            self, season: str, region: str, dungeon: str, page: int, affixes: str = "all"
        ) -> dict[str, Any]:
            return {"rankings": [{"run": {"keystone_run_id": 1, "mythic_level": 22}}]}

        def get_run_details(self, season: str, run_id: int) -> dict[str, Any]:
            return {
                "season": season,
                "status": "finished",
                "keystone_run_id": run_id,
                "mythic_level": 22,
                "clear_time_ms": 1700000,
                "keystone_time_ms": 1860999,
                "completed_at": "2026-05-03T07:33:46.051Z",
                "logged_run_id": 99,
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
                "logged_details": {
                    "encounters": [
                        {
                            "id": i,
                            "status": "finished",
                            "duration_ms": 1,
                            "is_success": True,
                            "approximate_relative_started_at": 0,
                            "approximate_relative_ended_at": v,
                            "boss": {
                                "name": f"B{i}",
                                "slug": f"b{i}",
                                "ordinal": i,
                                "wowEncounterId": 1000 + i,
                            },
                        }
                        for i, v in enumerate([425000, 850000, 1275000, 1700000])
                    ]
                },
            }

    cache = FileCache(tmp_path / "ratios_cache", ttl_seconds=7 * 24 * 3600)

    cfg = type("Cfg", (), {})()
    cfg.raiderio = type(
        "R", (), {"expansion_id": 11, "season": "season-mn-1", "region": "world"}
    )()
    cfg.scope = type(
        "S", (), {"levels": [15, 16, 17, 18, 19, 20, 21, 22], "min_sample": 20, "slowest_percentile": 10}
    )()
    cfg.output = type("O", (), {"schema_version": 2})()

    doc = build_document_from_discovered(
        discovered, StubRaider(), cache, cfg, datetime(2026, 5, 9, 18, 30, 0)
    )

    assert doc["meta"]["schema_version"] == 2
    assert doc["meta"]["season"] == "season-mn-1"
    assert doc["meta"]["source"] == "blizzard+raiderio"
    assert "algethar-academy" in doc["dungeons"]
    aa = doc["dungeons"]["algethar-academy"]
    assert aa["timer_ms"] == 1861000
    assert aa["challenge_mode_id"] == 402
    assert aa["num_bosses"] == 4
    assert aa["short_name"] == "AA"
    assert 15 in aa["levels"]
    assert 22 in aa["levels"]
    # No affix sub-key — direct cell dict
    assert "boss_splits_ms" in aa["levels"][15]
    assert aa["levels"][15]["splits_source"] == "synthesized"
    assert aa["levels"][22]["splits_source"] == "raiderio"
    # Bosses is a list with 0-indexed ordinals
    assert isinstance(aa["bosses"], list)
    assert aa["bosses"][0]["ordinal"] == 0
    assert aa["bosses"][3]["ordinal"] == 3
    assert aa["bosses"][0]["wow_encounter_id"] == 1000
    assert aa["bosses"][3]["wow_encounter_id"] == 1003


def test_discover_runs_skips_realms_that_raise_blizzard_error(capsys: pytest.CaptureFixture[str]) -> None:
    from jit_update.blizzard import BlizzardError
    from jit_update.pipeline import discover_runs

    healthy_run = BlizzardRun(
        dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062,
        keystone_level=18, duration_ms=1900000, completed_timestamp=1,
    )

    class FlakyBlizz:
        def get_current_period_id(self) -> int:
            return 1062

        def get_connected_realms_index(self) -> list[int]:
            return [1080, 1923]  # 1923 will fail

        def get_leaderboard_runs(
            self,
            *,
            realm_id: int,
            dungeon_id: int,
            period_id: int,
            dungeon_slug: str,
        ) -> list[BlizzardRun]:
            if realm_id == 1923:
                raise BlizzardError("status=500 Downstream Error")
            return [healthy_run]

    dungeons = [{"slug": "algethar-academy", "challenge_mode_id": 402}]
    result = discover_runs(FlakyBlizz(), dungeons=dungeons, levels=[18])

    assert "algethar-academy" in result
    assert len(result["algethar-academy"][18]) == 1  # only the healthy realm's run
    captured = capsys.readouterr()
    assert "1923" in captured.err
    assert "skipping" in captured.err.lower() or "skip" in captured.err.lower()


def test_merge_discovered_concatenates_run_lists() -> None:
    from jit_update.pipeline import merge_discovered

    eu_runs = [
        BlizzardRun(
            dungeon_slug="d", region="eu", realm_id=1, period=1,
            keystone_level=15, duration_ms=2_000_000, completed_timestamp=1,
        ),
    ]
    us_runs = [
        BlizzardRun(
            dungeon_slug="d", region="us", realm_id=2, period=1,
            keystone_level=15, duration_ms=2_100_000, completed_timestamp=2,
        ),
        BlizzardRun(
            dungeon_slug="d", region="us", realm_id=2, period=1,
            keystone_level=22, duration_ms=1_700_000, completed_timestamp=3,
        ),
    ]
    eu = {"d": {15: eu_runs}}
    us = {"d": {15: us_runs[:1], 22: us_runs[1:]}}

    merged = merge_discovered(eu, us)

    assert set(merged.keys()) == {"d"}
    assert sorted(merged["d"].keys()) == [15, 22]
    assert len(merged["d"][15]) == 2  # 1 EU + 1 US
    assert len(merged["d"][22]) == 1  # only US
    # Region tags preserved
    assert {r.region for r in merged["d"][15]} == {"eu", "us"}
