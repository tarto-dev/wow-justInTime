"""Shared pytest fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def load_fixture(fixtures_dir: Path) -> Callable[[str], dict[str, Any]]:
    """Load a JSON fixture by filename."""

    def _load(name: str) -> dict[str, Any]:
        path = fixtures_dir / name
        return cast(dict[str, Any], json.loads(path.read_text()))

    return _load
