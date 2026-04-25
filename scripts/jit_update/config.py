"""Configuration loader for jit_update."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RaiderIOConfig:
    """Raider.IO API connection and behaviour settings."""

    api_base: str
    expansion_id: int
    season: str
    region: str
    rate_per_minute: float
    cache_ttl_seconds: float
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True)
class ScopeConfig:
    """Keystone-level and sampling settings."""

    levels: list[int]
    min_sample: int
    slowest_percentile: int
    max_pages_per_query: int


@dataclass(frozen=True)
class OutputConfig:
    """Output file settings."""

    data_lua_path: str
    schema_version: int


@dataclass(frozen=True)
class Config:
    """Top-level configuration object."""

    raiderio: RaiderIOConfig
    scope: ScopeConfig
    output: OutputConfig


def load_config(path: Path) -> Config:
    """Load a :class:`Config` from a TOML file. Validates basic invariants.

    Args:
        path: Path to the TOML configuration file.

    Returns:
        A fully validated :class:`Config` instance.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If any config value is out of the supported range.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    raw = tomllib.loads(path.read_text())

    raiderio = RaiderIOConfig(**raw["raiderio"])
    scope = ScopeConfig(**raw["scope"])
    output = OutputConfig(**raw["output"])

    for lvl in scope.levels:
        if not 2 <= lvl <= 30:
            raise ValueError(f"level {lvl} out of supported range [2..30]")

    if scope.min_sample < 1:
        raise ValueError("scope.min_sample must be >= 1")
    if not 1 <= scope.slowest_percentile <= 100:
        raise ValueError("scope.slowest_percentile must be in [1..100]")

    return Config(raiderio=raiderio, scope=scope, output=output)
