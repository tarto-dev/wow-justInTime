"""End-to-end integration test with mocked HTTP."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import respx
from typer.testing import CliRunner

from jit_update.cli import app


def _runs_payload(level: int, run_ids: list[int]) -> dict[str, Any]:
    rankings: list[dict[str, Any]] = []
    for i, rid in enumerate(run_ids):
        rankings.append(
            {
                "rank": i + 1,
                "score": 0,
                "run": {
                    "keystone_run_id": rid,
                    "season": "season-mn-1",
                    "status": "finished",
                    "dungeon": {
                        "id": 14032,
                        "name": "Algeth'ar Academy",
                        "short_name": "AA",
                        "slug": "algethar-academy",
                        "map_challenge_mode_id": 402,
                        "keystone_timer_ms": 1800000,
                        "num_bosses": 4,
                    },
                    "mythic_level": level,
                    "clear_time_ms": 1700000 + i * 5000,
                    "keystone_time_ms": 1800000,
                    "completed_at": "2026-04-23T16:01:45.000Z",
                    "num_chests": 1,
                    "time_remaining_ms": 100000 - i * 5000,
                    "weekly_modifiers": [
                        {"id": 10, "slug": "fortified"},
                        {"id": 147, "slug": "xalataths-guile"},
                    ],
                },
            }
        )
    return {"rankings": rankings}


def _details_payload(run_id: int) -> dict[str, Any]:
    return {
        "season": "season-mn-1",
        "keystone_run_id": run_id,
        "mythic_level": 12,
        "clear_time_ms": 1742000,
        "keystone_time_ms": 1800000,
        "num_chests": 1,
        "time_remaining_ms": 58000,
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
            "keystone_timer_ms": 1800000,
            "num_bosses": 4,
        },
        "logged_details": {
            "encounters": [
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 180000,
                    "approximate_relative_ended_at": 280000,
                    "boss": {
                        "slug": "boss1",
                        "name": "Boss 1",
                        "ordinal": 1,
                        "wowEncounterId": 1001,
                    },
                },
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 640000,
                    "approximate_relative_ended_at": 740000,
                    "boss": {
                        "slug": "boss2",
                        "name": "Boss 2",
                        "ordinal": 2,
                        "wowEncounterId": 1002,
                    },
                },
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 1100000,
                    "approximate_relative_ended_at": 1200000,
                    "boss": {
                        "slug": "boss3",
                        "name": "Boss 3",
                        "ordinal": 3,
                        "wowEncounterId": 1003,
                    },
                },
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 1640000,
                    "approximate_relative_ended_at": 1742000,
                    "boss": {
                        "slug": "boss4",
                        "name": "Boss 4",
                        "ordinal": 4,
                        "wowEncounterId": 1004,
                    },
                },
            ]
        },
    }


def _static_payload() -> dict[str, Any]:
    return {
        "seasons": [
            {
                "slug": "season-mn-1",
                "is_main_season": True,
                "dungeons": [
                    {
                        "id": 14032,
                        "challenge_mode_id": 402,
                        "slug": "algethar-academy",
                        "name": "Algeth'ar Academy",
                        "short_name": "AA",
                        "keystone_timer_seconds": 1800,
                        "num_bosses": 4,
                    }
                ],
            }
        ]
    }


@respx.mock
def test_full_pipeline_writes_valid_data_lua(tmp_path: Path) -> None:
    cfg_path = tmp_path / "jit_config.toml"
    cfg_path.write_text(f"""
[raiderio]
api_base = "https://raider.io/api/v1"
expansion_id = 11
season = "season-mn-1"
region = "world"
rate_per_minute = 6000
cache_ttl_seconds = 60
timeout_seconds = 5.0
max_retries = 2

[scope]
levels = [12]
min_sample = 2
slowest_percentile = 50
max_pages_per_query = 1

[output]
data_lua_path = "{tmp_path / 'Data.lua'}"
schema_version = 1
""")

    respx.get(
        "https://raider.io/api/v1/mythic-plus/static-data",
        params={"expansion_id": "11"},
    ).mock(return_value=httpx.Response(200, json=_static_payload()))
    respx.get("https://raider.io/api/v1/mythic-plus/runs").mock(
        return_value=httpx.Response(200, json=_runs_payload(12, [101, 102, 103, 104]))
    )
    respx.get("https://raider.io/api/v1/mythic-plus/run-details").mock(
        side_effect=lambda req: httpx.Response(
            200, json=_details_payload(int(req.url.params["id"]))
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["--config", str(cfg_path)])

    assert result.exit_code == 0, result.output
    out = (tmp_path / "Data.lua").read_text()
    assert "JustInTimeData = {" in out
    assert '["algethar-academy"]' in out
    assert "[12]" in out
    assert '["fortified-xalataths-guile"]' in out
    assert "boss_splits_ms = { 280000, 740000, 1200000, 1742000 }" in out
