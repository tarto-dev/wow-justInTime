"""Tests for pipeline orchestration."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from jit_update.models import Run
from jit_update.pipeline import (
    collect_timed_runs,
    select_slowest_percentile,
)


def _make_run_payload(
    run_id: int,
    level: int,
    clear_time_ms: int,
    chests: int = 1,
    affixes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "rank": run_id,
        "score": 0,
        "run": {
            "keystone_run_id": run_id,
            "season": "season-mn-1",
            "status": "finished",
            "dungeon": {
                "id": 14032,
                "name": "Algeth'ar Academy",
                "short_name": "AA",
                "slug": "algethar-academy",
                "map_challenge_mode_id": 402,
                "keystone_timer_ms": 1800999,
                "num_bosses": 4,
            },
            "mythic_level": level,
            "clear_time_ms": clear_time_ms,
            "keystone_time_ms": 1800999,
            "completed_at": "2026-04-23T16:01:45.000Z",
            "num_chests": chests,
            "time_remaining_ms": 0,
            "weekly_modifiers": affixes
            or [
                {"id": 10, "slug": "fortified", "name": "Fortified"},
                {"id": 147, "slug": "xalataths-guile", "name": "Xal'atath's Guile"},
            ],
        },
    }


def test_collect_timed_runs_filters_by_level_and_affixes() -> None:
    page0 = {
        "rankings": [
            _make_run_payload(1, 14, 1700000),
            _make_run_payload(2, 12, 1700000),
            _make_run_payload(3, 12, 1750000),
            _make_run_payload(
                4,
                12,
                1800000,
                affixes=[
                    {"id": 9, "slug": "tyrannical", "name": "Tyrannical"},
                    {"id": 147, "slug": "xalataths-guile", "name": "Xal'atath's Guile"},
                ],
            ),
        ]
    }
    page1: dict[str, Any] = {"rankings": []}

    client = MagicMock()
    client.get_runs.side_effect = [page0, page1]

    runs = collect_timed_runs(
        client=client,
        season="season-mn-1",
        region="world",
        dungeon="algethar-academy",
        target_level=12,
        target_affix_combo="fortified-xalataths-guile",
        min_sample=10,
        max_pages=5,
    )

    assert {r.keystone_run_id for r in runs} == {2, 3}


def test_collect_stops_when_min_sample_reached() -> None:
    page0 = {"rankings": [_make_run_payload(i, 12, 1700000 + i) for i in range(20)]}
    client = MagicMock()
    client.get_runs.return_value = page0

    runs = collect_timed_runs(
        client=client,
        season="season-mn-1",
        region="world",
        dungeon="algethar-academy",
        target_level=12,
        target_affix_combo="fortified-xalataths-guile",
        min_sample=10,
        max_pages=5,
    )

    assert len(runs) >= 10
    assert client.get_runs.call_count == 1


def test_collect_excludes_untimed_runs() -> None:
    page0 = {
        "rankings": [
            _make_run_payload(1, 12, 1900000, chests=0),
            _make_run_payload(2, 12, 1700000, chests=1),
            _make_run_payload(3, 12, 1750000, chests=2),
        ]
    }
    page1: dict[str, Any] = {"rankings": []}
    client = MagicMock()
    client.get_runs.side_effect = [page0, page1]

    runs = collect_timed_runs(
        client=client,
        season="season-mn-1",
        region="world",
        dungeon="algethar-academy",
        target_level=12,
        target_affix_combo="fortified-xalataths-guile",
        min_sample=10,
        max_pages=5,
    )

    assert {r.keystone_run_id for r in runs} == {2, 3}


def test_select_slowest_percentile_minimum_two() -> None:
    runs = [
        Run.model_validate(_make_run_payload(i, 12, 1700000 + i * 1000)["run"]) for i in range(50)
    ]
    selected = select_slowest_percentile(runs, percentile=10, min_count=2)
    assert len(selected) == 5
    assert {r.keystone_run_id for r in selected} == {45, 46, 47, 48, 49}


def test_select_slowest_floors_at_min_count() -> None:
    runs = [
        Run.model_validate(_make_run_payload(i, 12, 1700000 + i * 1000)["run"]) for i in range(5)
    ]
    selected = select_slowest_percentile(runs, percentile=10, min_count=2)
    assert len(selected) == 2
    assert {r.keystone_run_id for r in selected} == {3, 4}
