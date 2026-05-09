"""Tests for lua_renderer schema v2 output."""

from __future__ import annotations

from jit_update.lua_renderer import render_data_lua


def test_render_emits_schema_version_2() -> None:
    doc = {
        "meta": {
            "generated_at": "2026-05-09T18:30:00Z",
            "schema_version": 2,
            "season": "season-mn-1",
            "source": "blizzard+raiderio",
        },
        "dungeons": {},
    }
    out = render_data_lua(doc)
    assert "schema_version = 2" in out
    assert '"blizzard+raiderio"' in out
    assert '"season-mn-1"' in out


def test_render_drops_affix_id_to_slug_table() -> None:
    doc = {
        "meta": {
            "generated_at": "2026-05-09T18:30:00Z",
            "schema_version": 2,
            "season": "season-mn-1",
            "source": "blizzard+raiderio",
        },
        "dungeons": {},
    }
    out = render_data_lua(doc)
    assert "affix_id_to_slug" not in out


def test_render_levels_have_no_affix_subkey() -> None:
    doc = {
        "meta": {
            "generated_at": "2026-05-09T18:30:00Z",
            "schema_version": 2,
            "season": "season-mn-1",
            "source": "blizzard+raiderio",
        },
        "dungeons": {
            "algethar-academy": {
                "keystone_timer_ms": 1861000,
                "bosses": {1: {"ordinal": 1, "slug": "boss-1", "name": "Boss 1"}},
                "levels": {
                    15: {
                        "clear_time_ms": 2000000,
                        "boss_splits_ms": [500000, 1000000, 1500000, 2000000],
                        "sample_size": 30,
                        "splits_source": "synthesized",
                    },
                },
            }
        },
    }
    out = render_data_lua(doc)
    # The level entry is a direct dict, not nested under an affix combo
    assert "[15] = {" in out
    assert '"synthesized"' in out
    # No affix combo strings anywhere
    assert "fortified" not in out.lower() or "fortified" not in out  # neither slug nor key
    assert "tyrannical" not in out.lower() or "tyrannical" not in out


def test_render_includes_all_three_splits_sources() -> None:
    doc = {
        "meta": {
            "generated_at": "2026-05-09T18:30:00Z",
            "schema_version": 2,
            "season": "season-mn-1",
            "source": "blizzard+raiderio",
        },
        "dungeons": {
            "d": {
                "keystone_timer_ms": 1861000,
                "bosses": {1: {"ordinal": 1, "slug": "b1", "name": "B1"}},
                "levels": {
                    15: {
                        "clear_time_ms": 2000000,
                        "boss_splits_ms": [500000, 1000000, 1500000, 2000000],
                        "sample_size": 30,
                        "splits_source": "synthesized",
                    },
                    18: {
                        "clear_time_ms": 1800000,
                        "boss_splits_ms": [450000, 900000, 1350000, 1800000],
                        "sample_size": 50,
                        "splits_source": "raiderio",
                    },
                    22: {
                        "clear_time_ms": 1700000,
                        "boss_splits_ms": [425000, 850000, 1275000, 1700000],
                        "sample_size": 25,
                        "splits_source": "equidistant_fallback",
                    },
                },
            }
        },
    }
    out = render_data_lua(doc)
    assert "synthesized" in out
    assert "raiderio" in out
    assert "equidistant_fallback" in out


def test_render_emits_bosses_block() -> None:
    doc = {
        "meta": {
            "generated_at": "2026-05-09T18:30:00Z",
            "schema_version": 2,
            "season": "season-mn-1",
            "source": "blizzard+raiderio",
        },
        "dungeons": {
            "d": {
                "keystone_timer_ms": 1861000,
                "bosses": {
                    1: {"ordinal": 1, "slug": "first-boss", "name": "First Boss"},
                    2: {"ordinal": 2, "slug": "second-boss", "name": "Second Boss"},
                },
                "levels": {},
            }
        },
    }
    out = render_data_lua(doc)
    assert '"first-boss"' in out
    assert '"second-boss"' in out
    assert "First Boss" in out


def test_render_output_is_deterministic() -> None:
    """Same input → same output, byte-for-byte."""
    doc = {
        "meta": {
            "generated_at": "2026-05-09T18:30:00Z",
            "schema_version": 2,
            "season": "season-mn-1",
            "source": "blizzard+raiderio",
        },
        "dungeons": {
            "z-dungeon": {
                "keystone_timer_ms": 1800000,
                "bosses": {1: {"ordinal": 1, "slug": "b1", "name": "B1"}},
                "levels": {
                    20: {"clear_time_ms": 1700000, "boss_splits_ms": [1, 2, 3, 4], "sample_size": 5, "splits_source": "raiderio"},
                    15: {"clear_time_ms": 2000000, "boss_splits_ms": [5, 6, 7, 8], "sample_size": 30, "splits_source": "synthesized"},
                },
            },
            "a-dungeon": {
                "keystone_timer_ms": 1900000,
                "bosses": {1: {"ordinal": 1, "slug": "b1", "name": "B1"}},
                "levels": {
                    18: {"clear_time_ms": 1850000, "boss_splits_ms": [9, 10, 11, 12], "sample_size": 50, "splits_source": "raiderio"},
                },
            },
        },
    }
    out1 = render_data_lua(doc)
    out2 = render_data_lua(doc)
    assert out1 == out2
    # Determinism implies sorted keys: a-dungeon before z-dungeon
    assert out1.index("a-dungeon") < out1.index("z-dungeon")
    # Within z-dungeon, level 15 before 20
    z_section = out1[out1.index("z-dungeon"):]
    assert z_section.index("[15]") < z_section.index("[20]")
