"""Tests for the typer CLI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from jit_update.cache import FileCache
from jit_update.cli import build_blizzard_clients_from_env


def test_cli_fails_loudly_when_blizzard_creds_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("BLIZZARD_CLIENT_ID", raising=False)
    monkeypatch.delenv("BLIZZARD_CLIENT_SECRET", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        build_blizzard_clients_from_env(
            regions=["eu"],
            rate_per_second=80.0,
            cache=None,
            timeout=30.0,
            max_retries=3,
        )
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "BLIZZARD_CLIENT_ID" in captured.err
    assert "develop.battle.net" in captured.err


def test_cli_builds_one_client_per_region(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BLIZZARD_CLIENT_ID", "id")
    monkeypatch.setenv("BLIZZARD_CLIENT_SECRET", "secret")
    cache = FileCache(tmp_path / "cache", ttl_seconds=3600.0)

    clients = build_blizzard_clients_from_env(
        regions=["eu", "us"],
        rate_per_second=80.0,
        cache=cache,
        timeout=30.0,
        max_retries=3,
    )

    assert set(clients.keys()) == {"eu", "us"}
    assert clients["eu"]._region == "eu"
    assert clients["us"]._region == "us"
