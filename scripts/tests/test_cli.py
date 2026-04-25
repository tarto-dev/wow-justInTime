"""Tests for the typer CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from jit_update.cli import app


def _write_minimal_config(path: Path) -> Path:
    cfg = path / "jit_config.toml"
    cfg.write_text("""
[raiderio]
api_base = "https://raider.io/api/v1"
expansion_id = 11
season = "season-mn-1"
region = "world"
rate_per_minute = 600
cache_ttl_seconds = 60
timeout_seconds = 5.0
max_retries = 2

[scope]
levels = [12]
min_sample = 2
slowest_percentile = 50
max_pages_per_query = 1

[output]
data_lua_path = "{out}"
schema_version = 1
""".format(out=str(path / "Data.lua")))
    return cfg


def _fake_doc() -> dict[str, Any]:
    return {
        "meta": {
            "generated_at": "2026-04-25T14:30:00Z",
            "season": "season-mn-1",
            "schema_version": 1,
        },
        "affix_id_to_slug": {},
        "dungeons": {},
    }


def test_cli_dry_run_does_not_write_file(tmp_path: Path) -> None:
    cfg_path = _write_minimal_config(tmp_path)

    with patch("jit_update.cli.build_document", return_value=_fake_doc()):
        runner = CliRunner()
        result = runner.invoke(app, ["--config", str(cfg_path), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert not (tmp_path / "Data.lua").exists()
    assert "season-mn-1" in result.output


def test_cli_writes_data_lua(tmp_path: Path) -> None:
    cfg_path = _write_minimal_config(tmp_path)

    with patch("jit_update.cli.build_document", return_value=_fake_doc()):
        runner = CliRunner()
        result = runner.invoke(app, ["--config", str(cfg_path)])

    assert result.exit_code == 0, result.output
    out_file = tmp_path / "Data.lua"
    assert out_file.exists()
    content = out_file.read_text()
    assert "JustInTimeData = {" in content
    assert "season-mn-1" in content


def test_cli_out_overrides_config(tmp_path: Path) -> None:
    cfg_path = _write_minimal_config(tmp_path)
    target = tmp_path / "override" / "Custom.lua"

    with patch("jit_update.cli.build_document", return_value=_fake_doc()):
        runner = CliRunner()
        result = runner.invoke(app, ["--config", str(cfg_path), "--out", str(target)])

    assert result.exit_code == 0, result.output
    assert target.exists()
