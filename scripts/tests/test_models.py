"""Tests for Pydantic models."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from jit_update.models import (
    AffixModifier,
    BlizzardLeaderboardResponse,
    BlizzardRun,
    BossInfo,
    Encounter,
    ReferenceCell,
    Run,
    RunDetails,
    affix_combo_slug,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_run_parses_minimal_payload(load_fixture: Callable[[str], dict[str, Any]]) -> None:
    raw = load_fixture("run_sample.json")
    run = Run.model_validate(raw["run"])
    assert run.keystone_run_id == 16544744
    assert run.dungeon.slug == "algethar-academy"
    assert run.mythic_level == 12
    assert run.clear_time_ms == 1742595
    assert run.num_chests == 1
    assert run.is_timed is True
    assert {m.slug for m in run.weekly_modifiers} == {"fortified", "tyrannical", "xalataths-guile"}


def test_run_is_timed_false_when_no_chests(load_fixture: Callable[[str], dict[str, Any]]) -> None:
    raw = load_fixture("run_sample.json")
    raw["run"]["num_chests"] = 0
    run = Run.model_validate(raw["run"])
    assert run.is_timed is False


def test_affix_combo_slug_is_sorted_and_joined() -> None:
    mods = [
        AffixModifier(id=147, slug="xalataths-guile"),
        AffixModifier(id=10, slug="fortified"),
    ]
    assert affix_combo_slug(mods) == "fortified-xalataths-guile"


def test_run_details_extracts_encounter_splits(
    load_fixture: Callable[[str], dict[str, Any]],
) -> None:
    raw = load_fixture("run_details_sample.json")
    details = RunDetails.model_validate(raw)
    assert details.keystone_run_id == 16544744
    assert len(details.encounters) == 4
    splits = details.boss_splits_ms()
    assert splits == [280000, 740000, 1200000, 1742000]


def test_run_details_skips_failed_encounters(
    load_fixture: Callable[[str], dict[str, Any]],
) -> None:
    raw = load_fixture("run_details_sample.json")
    raw["logged_details"]["encounters"][1]["is_success"] = False
    details = RunDetails.model_validate(raw)
    splits = details.boss_splits_ms()
    assert splits == [280000, None, 1200000, 1742000]


def test_boss_info_ordering() -> None:
    a = BossInfo(slug="a", name="A", ordinal=2)
    b = BossInfo(slug="b", name="B", ordinal=1)
    assert sorted([a, b], key=lambda x: x.ordinal) == [b, a]


def test_encounter_validates_required_fields() -> None:
    raw = {
        "duration_ms": 100000,
        "is_success": True,
        "approximate_relative_started_at": 0,
        "approximate_relative_ended_at": 100000,
        "boss": {"slug": "x", "name": "X", "ordinal": 1},
    }
    enc = Encounter.model_validate(raw)
    assert enc.boss.slug == "x"
    assert enc.is_success is True


def test_run_affix_combo_method_delegates_to_helper(
    load_fixture: Callable[[str], dict[str, Any]],
) -> None:
    raw = load_fixture("run_sample.json")
    run = Run.model_validate(raw["run"])
    assert run.affix_combo() == "fortified-tyrannical-xalataths-guile"


def test_run_details_empty_encounters_returns_empty_list() -> None:
    raw = {
        "season": "season-mn-1",
        "keystone_run_id": 1,
        "mythic_level": 12,
        "clear_time_ms": 1000000,
        "keystone_time_ms": 1800000,
        "num_chests": 1,
        "time_remaining_ms": 800000,
        "weekly_modifiers": [],
        "dungeon": {
            "id": 1,
            "name": "Test Dungeon",
            "short_name": "TD",
            "slug": "test-dungeon",
            "map_challenge_mode_id": 1,
            "keystone_timer_ms": 1800000,
            "num_bosses": 4,
        },
        "logged_details": {"encounters": []},
    }
    details = RunDetails.model_validate(raw)
    assert details.boss_splits_ms() == []


def test_run_details_ordinal_zero_is_valid() -> None:
    """Ordinal 0 is the first boss in the 0-based Raider.IO API scheme."""
    raw = {
        "season": "season-mn-1",
        "keystone_run_id": 1,
        "mythic_level": 12,
        "clear_time_ms": 1000000,
        "keystone_time_ms": 1800000,
        "num_chests": 1,
        "time_remaining_ms": 800000,
        "weekly_modifiers": [],
        "dungeon": {
            "id": 1,
            "name": "Test Dungeon",
            "short_name": "TD",
            "slug": "test-dungeon",
            "map_challenge_mode_id": 1,
            "keystone_timer_ms": 1800000,
            "num_bosses": 4,
        },
        "logged_details": {
            "encounters": [
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 0,
                    "approximate_relative_ended_at": 100000,
                    "boss": {"slug": "x", "name": "X", "ordinal": 0},
                }
            ]
        },
    }
    details = RunDetails.model_validate(raw)
    splits = details.boss_splits_ms()
    assert splits == [100000]


def test_blizzard_leaderboard_response_parses_sample() -> None:
    raw = json.loads((FIXTURE_DIR / "blizzard_leaderboard_sample.json").read_text())
    parsed = BlizzardLeaderboardResponse.model_validate(raw)
    assert parsed.map_challenge_mode_id == 402
    assert parsed.period == 1062
    assert len(parsed.leading_groups) == 3


def test_blizzard_run_extracts_keystone_level_and_duration() -> None:
    raw = json.loads((FIXTURE_DIR / "blizzard_leaderboard_sample.json").read_text())
    parsed = BlizzardLeaderboardResponse.model_validate(raw)
    runs = [
        BlizzardRun.from_group(
            g, dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062
        )
        for g in parsed.leading_groups
    ]
    assert {r.keystone_level for r in runs} == {15, 16, 19}
    assert {r.duration_ms for r in runs} == {1816344, 1893221, 2103556}
    assert all(r.dungeon_slug == "algethar-academy" for r in runs)
    assert all(r.region == "eu" for r in runs)


def test_reference_cell_has_splits_source_field() -> None:
    cell = ReferenceCell(
        sample_size=10,
        clear_time_ms=1700000,
        boss_splits_ms=[425000, 850000, 1275000, 1700000],
        splits_source="raiderio",
    )
    assert cell.splits_source == "raiderio"


def test_reference_cell_accepts_synthesized_source() -> None:
    cell = ReferenceCell(
        sample_size=5,
        clear_time_ms=1850000,
        boss_splits_ms=[462500, 925000, 1387500, 1850000],
        splits_source="synthesized",
    )
    assert cell.splits_source == "synthesized"


def test_reference_cell_accepts_equidistant_fallback_source() -> None:
    cell = ReferenceCell(
        sample_size=2,
        clear_time_ms=1900000,
        boss_splits_ms=[475000, 950000, 1425000, 1900000],
        splits_source="equidistant_fallback",
    )
    assert cell.splits_source == "equidistant_fallback"


def test_reference_cell_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        ReferenceCell(
            sample_size=5,
            clear_time_ms=1850000,
            boss_splits_ms=[1, 2, 3, 4],
            splits_source="bogus",
        )
