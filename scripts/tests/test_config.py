"""Tests for config loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from jit_update.config import load_config


def test_load_default_jit_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "jit_config.toml"
    cfg_path.write_text("""
[raiderio]
api_base = "https://raider.io/api/v1"
expansion_id = 11
season = "season-mn-1"
region = "world"
rate_per_minute = 300
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3

[scope]
levels = [10, 12, 14]
min_sample = 20
slowest_percentile = 10
max_pages_per_query = 50

[output]
data_lua_path = "../addon/JustInTime/Data.lua"
schema_version = 1
""")
    cfg = load_config(cfg_path)
    assert cfg.raiderio.season == "season-mn-1"
    assert cfg.scope.levels == [10, 12, 14]
    assert cfg.output.data_lua_path == "../addon/JustInTime/Data.lua"


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "absent.toml")


def test_config_validates_levels_range(tmp_path: Path) -> None:
    cfg_path = tmp_path / "jit_config.toml"
    cfg_path.write_text("""
[raiderio]
api_base = "https://raider.io/api/v1"
expansion_id = 11
season = "season-mn-1"
region = "world"
rate_per_minute = 300
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3

[scope]
levels = [1]
min_sample = 20
slowest_percentile = 10
max_pages_per_query = 50

[output]
data_lua_path = "../addon/JustInTime/Data.lua"
schema_version = 1
""")
    with pytest.raises(ValueError, match="level"):
        load_config(cfg_path)
