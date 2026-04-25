"""Tests for lua_renderer."""

from __future__ import annotations

from pathlib import Path

from jit_update.lua_renderer import render_data_lua


def test_render_minimal_document(fixtures_dir: Path) -> None:
    """Rendered output matches the hand-verified golden file byte-for-byte."""
    document = {
        "meta": {
            "generated_at": "2026-04-25T14:30:00Z",
            "season": "season-mn-1",
            "schema_version": 1,
        },
        "affix_id_to_slug": {
            9: "tyrannical",
            10: "fortified",
            147: "xalataths-guile",
        },
        "dungeons": {
            "algethar-academy": {
                "short_name": "AA",
                "challenge_mode_id": 402,
                "timer_ms": 1800999,
                "num_bosses": 4,
                "bosses": [
                    {
                        "ordinal": 1,
                        "slug": "overgrown-ancient",
                        "name": "Overgrown Ancient",
                        "wow_encounter_id": 2563,
                    },
                    {"ordinal": 2, "slug": "boss2", "name": "Boss 2", "wow_encounter_id": 2564},
                    {"ordinal": 3, "slug": "boss3", "name": "Boss 3", "wow_encounter_id": 2565},
                    {"ordinal": 4, "slug": "boss4", "name": "Boss 4", "wow_encounter_id": 2566},
                ],
                "levels": {
                    12: {
                        "fortified-xalataths-guile": {
                            "sample_size": 3,
                            "clear_time_ms": 1742000,
                            "boss_splits_ms": [280000, 740000, 1200000, 1742000],
                        },
                    },
                },
            },
        },
    }
    rendered = render_data_lua(document)
    expected = (fixtures_dir / "expected_minimal.lua").read_text()
    assert rendered == expected


def test_render_escapes_string_values() -> None:
    """Double-quotes inside string values are escaped as backslash-quote."""
    document = {
        "meta": {
            "generated_at": "2026-04-25T14:30:00Z",
            "season": "season-mn-1",
            "schema_version": 1,
        },
        "affix_id_to_slug": {},
        "dungeons": {
            "ara-kara-city-of-echoes": {
                "short_name": "AK",
                "challenge_mode_id": 503,
                "timer_ms": 1800000,
                "num_bosses": 3,
                "bosses": [
                    {
                        "ordinal": 1,
                        "slug": "the-king",
                        "name": 'King "Tharin"',
                        "wow_encounter_id": 100,
                    },
                    {"ordinal": 2, "slug": "queen", "name": "Queen", "wow_encounter_id": 101},
                    {"ordinal": 3, "slug": "duke", "name": "Duke", "wow_encounter_id": 102},
                ],
                "levels": {},
            },
        },
    }
    rendered = render_data_lua(document)
    assert 'name = "King \\"Tharin\\""' in rendered


def test_render_orders_keys_deterministically() -> None:
    """Integer affix keys are always ordered numerically regardless of insertion order."""
    document = {
        "meta": {
            "generated_at": "2026-04-25T14:30:00Z",
            "season": "season-mn-1",
            "schema_version": 1,
        },
        "affix_id_to_slug": {147: "xalataths-guile", 10: "fortified", 9: "tyrannical"},
        "dungeons": {},
    }
    rendered = render_data_lua(document)
    assert rendered.index("[9]") < rendered.index("[10]") < rendered.index("[147]")
