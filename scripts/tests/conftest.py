"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def load_fixture(fixtures_dir: Path):
    """Load a JSON fixture by filename."""

    def _load(name: str) -> dict:
        path = fixtures_dir / name
        return json.loads(path.read_text())

    return _load
