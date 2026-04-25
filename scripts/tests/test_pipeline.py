"""Tests for pipeline orchestration."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from jit_update.models import Run, RunDetails
from jit_update.pipeline import (
    collect_timed_runs,
    compute_reference_cell,
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


def test_collect_raises_on_malformed_runs_payload() -> None:
    """Raider.IO returning 200 with no 'rankings' key should raise loudly."""
    client = MagicMock()
    client.get_runs.return_value = {"error": "rate limited", "code": 429}

    with pytest.raises(RuntimeError, match="no 'rankings' key"):
        collect_timed_runs(
            client=client,
            season="season-mn-1",
            region="world",
            dungeon="algethar-academy",
            target_level=12,
            target_affix_combo="fortified-xalataths-guile",
            min_sample=10,
            max_pages=5,
        )


def test_collect_raises_when_rankings_is_not_a_list() -> None:
    """Defend against unexpected schemas where rankings is e.g. a dict."""
    client = MagicMock()
    client.get_runs.return_value = {"rankings": {"unexpected": "shape"}}

    with pytest.raises(RuntimeError, match="rankings not a list"):
        collect_timed_runs(
            client=client,
            season="season-mn-1",
            region="world",
            dungeon="algethar-academy",
            target_level=12,
            target_affix_combo="fortified-xalataths-guile",
            min_sample=10,
            max_pages=5,
        )


def test_select_slowest_rejects_invalid_percentile() -> None:
    runs = [
        Run.model_validate(_make_run_payload(i, 12, 1700000 + i * 1000)["run"]) for i in range(5)
    ]
    with pytest.raises(ValueError, match="percentile must be in"):
        select_slowest_percentile(runs, percentile=150, min_count=2)
    with pytest.raises(ValueError, match="percentile must be in"):
        select_slowest_percentile(runs, percentile=-1, min_count=2)


def _make_details_payload(splits_ms: list[int], num_bosses: int = 4) -> dict[str, Any]:
    encounters = [
        {
            "duration_ms": 100000,
            "is_success": True,
            "approximate_relative_started_at": (splits_ms[i] - 100000),
            "approximate_relative_ended_at": splits_ms[i],
            "boss": {
                "slug": f"boss{i + 1}",
                "name": f"Boss {i + 1}",
                "ordinal": i + 1,
                "wowEncounterId": 1000 + i,
            },
        }
        for i in range(num_bosses)
    ]
    return {
        "season": "season-mn-1",
        "keystone_run_id": 99,
        "mythic_level": 12,
        "clear_time_ms": splits_ms[-1],
        "keystone_time_ms": 1800999,
        "num_chests": 1,
        "time_remaining_ms": 0,
        "weekly_modifiers": [
            {"id": 10, "slug": "fortified"},
            {"id": 147, "slug": "xalataths-guile"},
        ],
        "dungeon": {
            "id": 14032,
            "name": "Algeth'ar Academy",
            "short_name": "AA",
            "slug": "algethar-academy",
            "map_challenge_mode_id": 402,
            "keystone_timer_ms": 1800999,
            "num_bosses": num_bosses,
        },
        "logged_details": {"encounters": encounters},
    }


def test_compute_reference_cell_takes_median_per_boss() -> None:
    details = [
        RunDetails.model_validate(_make_details_payload([280000, 740000, 1200000, 1742000])),
        RunDetails.model_validate(_make_details_payload([300000, 760000, 1220000, 1760000])),
        RunDetails.model_validate(_make_details_payload([260000, 720000, 1180000, 1740000])),
    ]
    cell = compute_reference_cell(details, num_bosses=4)
    assert cell is not None
    assert cell.sample_size == 3
    assert cell.boss_splits_ms == [280000, 740000, 1200000, 1742000]
    assert cell.clear_time_ms == 1742000


def test_compute_reference_cell_handles_missing_boss_split() -> None:
    a = _make_details_payload([280000, 740000, 1200000, 1742000])
    b = _make_details_payload([300000, 760000, 1220000, 1760000])
    b["logged_details"]["encounters"][1]["is_success"] = False
    details = [
        RunDetails.model_validate(a),
        RunDetails.model_validate(b),
    ]
    cell = compute_reference_cell(details, num_bosses=4)
    assert cell is not None
    assert cell.sample_size == 2
    assert cell.boss_splits_ms[1] == 740000


def test_compute_reference_cell_empty_returns_none() -> None:
    cell = compute_reference_cell([], num_bosses=4)
    assert cell is None
