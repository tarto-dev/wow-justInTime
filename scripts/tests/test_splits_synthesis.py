"""Tests for collect_observed_ratios + synthesize_splits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jit_update.splits_synthesis import collect_observed_ratios


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
