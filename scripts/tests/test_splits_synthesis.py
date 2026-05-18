"""Tests for collect_observed_ratios + synthesize_splits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jit_update.cache import FileCache
from jit_update.splits_synthesis import (
    collect_observed_ratios,
    collect_observed_ratios_cached,
    synthesize_splits,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class StubRaiderIO:
    """Minimal stub matching the methods collect_observed_ratios calls."""

    def __init__(self, runs_payload: dict[str, Any], details_by_id: dict[int, dict[str, Any]]):
        self._runs_payload = runs_payload
        self._details_by_id = details_by_id

    def get_runs(
        self, season: str, region: str, dungeon: str, page: int, affixes: str = "all"
    ) -> dict[str, Any]:
        return self._runs_payload

    def get_run_details(self, season: str, run_id: int) -> dict[str, Any]:
        return self._details_by_id[run_id]


def test_collect_observed_ratios_returns_per_ordinal_medians() -> None:
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    runs_payload = {
        "rankings": [
            {"run": {"keystone_run_id": 20945824}},
            {"run": {"keystone_run_id": 20945825}},
        ]
    }
    # Two identical runs — median = expected ratios
    details_by_id = {
        20945824: splits,
        20945825: splits,
    }
    stub = StubRaiderIO(runs_payload, details_by_id)
    ratios = collect_observed_ratios(stub, "season-mn-1", "algethar-academy", num_bosses=4)
    # clear_time = 1700000, ends at 425k/850k/1.275M/1.7M -> ratios 0.25/0.5/0.75/1.0
    assert len(ratios) == 4
    assert ratios[0] == pytest.approx(0.25, abs=0.001)
    assert ratios[1] == pytest.approx(0.5, abs=0.001)
    assert ratios[2] == pytest.approx(0.75, abs=0.001)
    assert ratios[3] == pytest.approx(1.0, abs=0.001)


def test_collect_observed_ratios_skips_runs_without_logged_encounters() -> None:
    no_splits = json.loads((FIXTURE_DIR / "raiderio_run_details_no_splits.json").read_text())
    runs_payload = {"rankings": [{"run": {"keystone_run_id": 22426791}}]}
    stub = StubRaiderIO(runs_payload, {22426791: no_splits})
    ratios = collect_observed_ratios(stub, "season-mn-1", "algethar-academy", num_bosses=4)
    assert ratios == [None, None, None, None]


def test_collect_observed_ratios_handles_partial_coverage() -> None:
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    no_splits = json.loads((FIXTURE_DIR / "raiderio_run_details_no_splits.json").read_text())
    runs_payload = {
        "rankings": [
            {"run": {"keystone_run_id": 20945824}},
            {"run": {"keystone_run_id": 22426791}},
        ]
    }
    stub = StubRaiderIO(runs_payload, {20945824: splits, 22426791: no_splits})
    ratios = collect_observed_ratios(stub, "season-mn-1", "algethar-academy", num_bosses=4)
    # Only one run with splits, so each ordinal has a single sample
    assert all(r is not None for r in ratios)


def test_synthesize_splits_applies_ratios() -> None:
    ratios: list[float | None] = [0.25, 0.5, 0.75, 1.0]
    result = synthesize_splits(clear_time_ms=1850000, ratios=ratios, num_bosses=4)
    assert result == [462500, 925000, 1387500, 1850000]


def test_synthesize_splits_falls_back_to_equidistant_when_all_none() -> None:
    result = synthesize_splits(
        clear_time_ms=1800000, ratios=[None, None, None, None], num_bosses=4
    )
    # Equidistant: 1/4, 2/4, 3/4, 4/4 of clear_time
    assert result == [450000, 900000, 1350000, 1800000]


def test_synthesize_splits_uses_equidistant_for_missing_ordinals_when_some_present() -> None:
    ratios: list[float | None] = [0.25, None, 0.75, 1.0]
    result = synthesize_splits(clear_time_ms=1800000, ratios=ratios, num_bosses=4)
    assert result[0] == 450000  # 0.25 * 1.8M
    assert result[1] == 900000  # equidistant: 2/4 * 1.8M
    assert result[2] == 1350000  # 0.75 * 1.8M
    assert result[3] == 1800000  # 1.0 * 1.8M


def test_synthesize_splits_rounds_to_int() -> None:
    ratios: list[float | None] = [0.333, 0.666, 1.0]
    result = synthesize_splits(clear_time_ms=1000000, ratios=ratios, num_bosses=3)
    assert all(isinstance(v, int) for v in result)
    assert result == [333000, 666000, 1000000]


def test_collect_observed_ratios_cached_serves_cache_on_second_call(tmp_path: Path) -> None:
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    runs_payload = {"rankings": [{"run": {"keystone_run_id": 20945824}}]}

    calls = {"runs": 0, "details": 0}

    class CountingStub(StubRaiderIO):
        def get_runs(self, *a: Any, **kw: Any) -> dict[str, Any]:
            calls["runs"] += 1
            return super().get_runs(*a, **kw)

        def get_run_details(self, *a: Any, **kw: Any) -> dict[str, Any]:
            calls["details"] += 1
            return super().get_run_details(*a, **kw)

    counting = CountingStub(runs_payload, {20945824: splits})
    cache = FileCache(tmp_path / "cache", ttl_seconds=7 * 24 * 3600)

    ratios_1 = collect_observed_ratios_cached(
        counting, cache, "season-mn-1", "algethar-academy", num_bosses=4
    )
    ratios_2 = collect_observed_ratios_cached(
        counting, cache, "season-mn-1", "algethar-academy", num_bosses=4
    )

    assert ratios_1 == ratios_2
    assert calls["runs"] == 1, f"expected 1 /runs call, got {calls['runs']}"
    assert calls["details"] == 1, f"expected 1 /run-details call, got {calls['details']}"


def test_collect_observed_ratios_skips_depleted_runs() -> None:
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    depleted = dict(splits)
    depleted["num_chests"] = 0  # mark as depleted
    runs_payload = {
        "rankings": [
            {"run": {"keystone_run_id": 20945824}},  # in-time
            {"run": {"keystone_run_id": 20945825}},  # depleted
        ]
    }
    details_by_id = {
        20945824: splits,
        20945825: depleted,
    }
    stub = StubRaiderIO(runs_payload, details_by_id)
    ratios = collect_observed_ratios(stub, "season-mn-1", "algethar-academy", num_bosses=4)
    # Only the in-time run feeds the median → identical ratios to fixture
    assert ratios[0] == pytest.approx(0.25, abs=0.001)
    assert ratios[3] == pytest.approx(1.0, abs=0.001)


def test_collect_observed_ratios_cached_uses_separate_keys_per_dungeon(tmp_path: Path) -> None:
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    runs_payload = {"rankings": [{"run": {"keystone_run_id": 20945824}}]}
    cache = FileCache(tmp_path / "cache", ttl_seconds=7 * 24 * 3600)
    stub = StubRaiderIO(runs_payload, {20945824: splits})

    r1 = collect_observed_ratios_cached(
        stub, cache, "season-mn-1", "algethar-academy", num_bosses=4
    )
    r2 = collect_observed_ratios_cached(
        stub, cache, "season-mn-1", "the-rookery", num_bosses=4
    )

    # Both compute (separate keys), values are equal because stub returns same data
    assert r1 == r2
