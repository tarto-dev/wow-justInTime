# JustInTime — Plan A : Script Python (jit_update)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python data-generation script (`uv run jit-update`) that fetches Raider.IO Mythic+ data for Midnight Season 1 and produces a valid `addon/JustInTime/Data.lua` consumable by the WoW addon.

**Architecture:** uv-managed Python package in `scripts/`. Layered modules: `models` (Pydantic) → `cache` + `rate_limiter` → `raiderio` (HTTP client) → `pipeline` (orchestration) → `lua_renderer` (output) → `cli` (typer entry-point). Driven by `jit_config.toml`. All HTTP interactions test via `httpx.MockTransport` with captured fixtures.

**Tech Stack:** Python 3.11+, uv, httpx, pydantic v2, typer, tomllib (stdlib), pytest, pytest-mock, mypy strict, ruff, black.

**Working directory:** `/home/tarto/projects/wowAddons/justInTime`

**Commit policy:** All commits on `main` only. Never push (per Claralicious workflow). Conventional Commits + gitmoji per CLAUDE.md global.

---

## File structure

```
scripts/
├── pyproject.toml                  # uv-managed
├── jit_config.toml                 # default user config
├── README.md                       # how to run
├── jit_update/
│   ├── __init__.py
│   ├── cli.py                      # typer entry-point
│   ├── config.py                   # Config dataclass + TOML loader
│   ├── models.py                   # Pydantic: Run, RunDetails, Encounter, ReferenceCell, AffixMap
│   ├── rate_limiter.py             # token-bucket rate limiter
│   ├── cache.py                    # file-based HTTP cache
│   ├── raiderio.py                 # RaiderIOClient (httpx-based)
│   ├── pipeline.py                 # collect → sample → aggregate
│   └── lua_renderer.py             # Python dict → Lua string
└── tests/
    ├── __init__.py
    ├── conftest.py                 # shared fixtures
    ├── fixtures/
    │   ├── runs_aa_p0.json         # captured /runs response
    │   ├── runs_aa_p1.json
    │   ├── run_details_X.json      # captured /run-details
    │   ├── static_data_mn1.json
    │   └── expected_data.lua       # golden file for renderer
    ├── test_models.py
    ├── test_rate_limiter.py
    ├── test_cache.py
    ├── test_raiderio.py
    ├── test_pipeline.py
    ├── test_lua_renderer.py
    ├── test_config.py
    ├── test_cli.py
    └── test_integration.py
```

---

## Task 1 — Bootstrap Python project

**Files:**
- Create: `scripts/pyproject.toml`
- Create: `scripts/jit_update/__init__.py`
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/conftest.py`
- Create: `scripts/.gitignore`

- [ ] **Step 1: Create `scripts/pyproject.toml`**

```toml
[project]
name = "jit-update"
version = "0.1.0"
description = "Generate JustInTime addon Data.lua from Raider.IO Mythic+ data"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27,<1.0",
    "pydantic>=2.6,<3.0",
    "typer>=0.12,<1.0",
    "rich>=13.7,<14.0",
]

[project.scripts]
jit-update = "jit_update.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "pytest-cov>=4.1",
    "mypy>=1.10",
    "ruff>=0.5",
    "black>=24.0",
    "respx>=0.21",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers --cov=jit_update --cov-report=term-missing --cov-fail-under=70"

[tool.mypy]
strict = true
warn_return_any = true
warn_unused_configs = true

[[tool.mypy.overrides]]
module = ["respx.*"]
ignore_missing_imports = true

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "RUF"]

[tool.black]
line-length = 100
target-version = ["py311"]
```

- [ ] **Step 2: Create empty `scripts/jit_update/__init__.py`**

```python
"""JustInTime data-generation toolkit."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create `scripts/tests/__init__.py` (empty)**

```python
```

- [ ] **Step 4: Create `scripts/tests/conftest.py`**

```python
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
```

- [ ] **Step 5: Create `scripts/.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
.cache/
htmlcov/
dist/
build/
*.egg-info/
```

- [ ] **Step 6: Run `uv sync` from `scripts/` directory**

```bash
cd scripts && uv sync
```

Expected: creates `scripts/.venv/`, no errors.

- [ ] **Step 7: Verify pytest runs (no tests yet)**

```bash
cd scripts && uv run pytest
```

Expected: `no tests ran in 0.0Xs` (exit 5 is acceptable when zero tests exist).

- [ ] **Step 8: Commit**

```bash
git add scripts/
git commit -m "🎉 chore(scripts): bootstrap jit_update Python package with uv"
```

---

## Task 2 — Pydantic models

**Files:**
- Create: `scripts/jit_update/models.py`
- Create: `scripts/tests/test_models.py`
- Create: `scripts/tests/fixtures/run_sample.json`
- Create: `scripts/tests/fixtures/run_details_sample.json`

- [ ] **Step 1: Capture API fixture — minimal Run JSON**

Create `scripts/tests/fixtures/run_sample.json`:

```json
{
  "rank": 1,
  "score": 501.2,
  "run": {
    "keystone_run_id": 16544744,
    "season": "season-mn-1",
    "status": "finished",
    "dungeon": {
      "id": 14032,
      "name": "Algeth'ar Academy",
      "short_name": "AA",
      "slug": "algethar-academy",
      "map_challenge_mode_id": 402,
      "keystone_timer_ms": 1800999,
      "num_bosses": 4
    },
    "mythic_level": 12,
    "clear_time_ms": 1742595,
    "keystone_time_ms": 1800999,
    "completed_at": "2026-04-23T16:01:45.000Z",
    "num_chests": 1,
    "time_remaining_ms": 58404,
    "weekly_modifiers": [
      {"id": 10, "slug": "fortified", "name": "Fortified"},
      {"id": 147, "slug": "xalataths-guile", "name": "Xal'atath's Guile"}
    ]
  }
}
```

- [ ] **Step 2: Capture API fixture — minimal RunDetails JSON**

Create `scripts/tests/fixtures/run_details_sample.json`:

```json
{
  "season": "season-mn-1",
  "keystone_run_id": 16544744,
  "mythic_level": 12,
  "clear_time_ms": 1742595,
  "keystone_time_ms": 1800999,
  "num_chests": 1,
  "time_remaining_ms": 58404,
  "weekly_modifiers": [
    {"id": 10, "slug": "fortified"},
    {"id": 147, "slug": "xalataths-guile"}
  ],
  "dungeon": {
    "slug": "algethar-academy",
    "map_challenge_mode_id": 402,
    "num_bosses": 4
  },
  "logged_details": {
    "encounters": [
      {
        "duration_ms": 204547,
        "is_success": true,
        "approximate_relative_started_at": 133908,
        "approximate_relative_ended_at": 280000,
        "boss": {"slug": "overgrown-ancient", "name": "Overgrown Ancient", "ordinal": 1, "wowEncounterId": 2563}
      },
      {
        "duration_ms": 180000,
        "is_success": true,
        "approximate_relative_started_at": 500000,
        "approximate_relative_ended_at": 740000,
        "boss": {"slug": "second-boss", "name": "Second", "ordinal": 2, "wowEncounterId": 9999}
      },
      {
        "duration_ms": 200000,
        "is_success": true,
        "approximate_relative_started_at": 950000,
        "approximate_relative_ended_at": 1200000,
        "boss": {"slug": "third-boss", "name": "Third", "ordinal": 3, "wowEncounterId": 9998}
      },
      {
        "duration_ms": 220000,
        "is_success": true,
        "approximate_relative_started_at": 1500000,
        "approximate_relative_ended_at": 1742000,
        "boss": {"slug": "fourth-boss", "name": "Fourth", "ordinal": 4, "wowEncounterId": 9997}
      }
    ]
  }
}
```

- [ ] **Step 3: Write failing tests for models**

Create `scripts/tests/test_models.py`:

```python
"""Tests for Pydantic models."""
from __future__ import annotations

from jit_update.models import (
    AffixModifier,
    BossInfo,
    Encounter,
    Run,
    RunDetails,
    affix_combo_slug,
)


def test_run_parses_minimal_payload(load_fixture) -> None:
    raw = load_fixture("run_sample.json")
    run = Run.model_validate(raw["run"])
    assert run.keystone_run_id == 16544744
    assert run.dungeon.slug == "algethar-academy"
    assert run.mythic_level == 12
    assert run.clear_time_ms == 1742595
    assert run.num_chests == 1
    assert run.is_timed is True
    assert {m.slug for m in run.weekly_modifiers} == {"fortified", "xalataths-guile"}


def test_run_is_timed_false_when_no_chests(load_fixture) -> None:
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


def test_run_details_extracts_encounter_splits(load_fixture) -> None:
    raw = load_fixture("run_details_sample.json")
    details = RunDetails.model_validate(raw)
    assert details.keystone_run_id == 16544744
    assert len(details.encounters) == 4
    splits = details.boss_splits_ms()
    assert splits == [280000, 740000, 1200000, 1742000]


def test_run_details_skips_failed_encounters(load_fixture) -> None:
    raw = load_fixture("run_details_sample.json")
    raw["logged_details"]["encounters"][1]["is_success"] = False
    details = RunDetails.model_validate(raw)
    splits = details.boss_splits_ms()
    # second boss skipped (None placeholder)
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
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_models.py -v
```

Expected: `ImportError` or collection errors (models module doesn't exist yet).

- [ ] **Step 5: Implement models module**

Create `scripts/jit_update/models.py`:

```python
"""Pydantic models for Raider.IO API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AffixModifier(BaseModel):
    """A weekly modifier (affix) attached to a Mythic+ run."""

    model_config = ConfigDict(extra="ignore")

    id: int
    slug: str
    name: Optional[str] = None


def affix_combo_slug(modifiers: list[AffixModifier]) -> str:
    """Return a deterministic slug joining affix slugs alphabetically with '-'.

    Used as the cell key in Data.lua: e.g. "fortified-xalataths-guile".
    """
    return "-".join(sorted(m.slug for m in modifiers))


class BossInfo(BaseModel):
    """Static info about a boss in a dungeon."""

    model_config = ConfigDict(extra="ignore")

    slug: str
    name: str
    ordinal: int
    wow_encounter_id: Optional[int] = Field(default=None, alias="wowEncounterId")


class Encounter(BaseModel):
    """A single boss encounter inside a logged run."""

    model_config = ConfigDict(extra="ignore")

    duration_ms: int
    is_success: bool
    approximate_relative_started_at: int
    approximate_relative_ended_at: int
    boss: BossInfo


class DungeonInfo(BaseModel):
    """Static info about a dungeon."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    slug: str
    short_name: str = ""
    map_challenge_mode_id: int
    keystone_timer_ms: int
    num_bosses: int


class Run(BaseModel):
    """Top-level Mythic+ run as returned by /mythic-plus/runs."""

    model_config = ConfigDict(extra="ignore")

    keystone_run_id: int
    season: str
    status: str
    dungeon: DungeonInfo
    mythic_level: int
    clear_time_ms: int
    keystone_time_ms: int
    completed_at: datetime
    num_chests: int
    time_remaining_ms: int
    weekly_modifiers: list[AffixModifier] = Field(default_factory=list)

    @property
    def is_timed(self) -> bool:
        """True if the run finished within the keystone timer (chest count >= 1)."""
        return self.num_chests >= 1

    def affix_combo(self) -> str:
        """Return the alphabetically-sorted affix combo slug."""
        return affix_combo_slug(self.weekly_modifiers)


class _LoggedDetails(BaseModel):
    """Internal container for the encounters list inside RunDetails."""

    model_config = ConfigDict(extra="ignore")

    encounters: list[Encounter] = Field(default_factory=list)


class RunDetails(BaseModel):
    """Detailed run with per-boss encounter splits.

    Returned by /mythic-plus/run-details?id=X.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    keystone_run_id: int
    season: str
    mythic_level: int
    clear_time_ms: int
    keystone_time_ms: int
    num_chests: int
    time_remaining_ms: int
    weekly_modifiers: list[AffixModifier] = Field(default_factory=list)
    dungeon: DungeonInfo
    logged_details: _LoggedDetails

    @property
    def encounters(self) -> list[Encounter]:
        return self.logged_details.encounters

    def boss_splits_ms(self) -> list[Optional[int]]:
        """Return per-boss split times (relative ms), sorted by ordinal.

        Returns None for any boss whose encounter is not successful.
        Length = max ordinal seen.
        """
        if not self.encounters:
            return []
        max_ordinal = max(e.boss.ordinal for e in self.encounters)
        result: list[Optional[int]] = [None] * max_ordinal
        for enc in self.encounters:
            idx = enc.boss.ordinal - 1
            if 0 <= idx < max_ordinal:
                result[idx] = (
                    enc.approximate_relative_ended_at if enc.is_success else None
                )
        return result


class ReferenceCell(BaseModel):
    """One cell of the reference table: (dungeon, level, affix_combo) → splits.

    This is what gets serialized into Data.lua per (dungeon × level × affix_combo).
    """

    model_config = ConfigDict(extra="ignore")

    sample_size: int
    clear_time_ms: int
    boss_splits_ms: list[int]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd scripts && uv run pytest tests/test_models.py -v
```

Expected: 7 tests pass.

- [ ] **Step 7: Run mypy strict**

```bash
cd scripts && uv run mypy jit_update/models.py
```

Expected: `Success: no issues found`.

- [ ] **Step 8: Commit**

```bash
git add scripts/jit_update/models.py scripts/tests/test_models.py scripts/tests/fixtures/
git commit -m "✨ feat(scripts): add Pydantic models for Raider.IO Run/RunDetails"
```

---

## Task 3 — Rate limiter

**Files:**
- Create: `scripts/jit_update/rate_limiter.py`
- Create: `scripts/tests/test_rate_limiter.py`

- [ ] **Step 1: Write failing tests**

Create `scripts/tests/test_rate_limiter.py`:

```python
"""Tests for the token-bucket rate limiter."""
from __future__ import annotations

import time

import pytest

from jit_update.rate_limiter import RateLimiter


def test_first_n_calls_within_capacity_are_immediate() -> None:
    rl = RateLimiter(rate_per_minute=600, capacity=10)  # 10 req/sec
    start = time.monotonic()
    for _ in range(5):
        rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, "first 5 calls should be near-instant"


def test_calls_beyond_capacity_are_throttled() -> None:
    rl = RateLimiter(rate_per_minute=600, capacity=2)  # 10 req/sec, 2 burst
    start = time.monotonic()
    for _ in range(4):
        rl.acquire()
    elapsed = time.monotonic() - start
    # We needed 4 tokens but only had 2 in burst; the next 2 require ~0.1s each at 10/s
    assert 0.15 < elapsed < 0.5, f"expected ~0.2s of throttling, got {elapsed:.3f}s"


def test_invalid_rate_raises() -> None:
    with pytest.raises(ValueError):
        RateLimiter(rate_per_minute=0, capacity=1)
    with pytest.raises(ValueError):
        RateLimiter(rate_per_minute=10, capacity=0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_rate_limiter.py -v
```

Expected: ImportError (rate_limiter module not yet present).

- [ ] **Step 3: Implement RateLimiter**

Create `scripts/jit_update/rate_limiter.py`:

```python
"""Token-bucket rate limiter."""
from __future__ import annotations

import time
from threading import Lock


class RateLimiter:
    """Simple token-bucket limiter.

    Tokens replenish continuously at `rate_per_minute / 60` per second, up to `capacity`.
    `acquire()` blocks until a token is available.
    """

    def __init__(self, rate_per_minute: float, capacity: int) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._tokens_per_sec = rate_per_minute / 60.0
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def acquire(self) -> None:
        """Block until one token is available, then consume it."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait = (1.0 - self._tokens) / self._tokens_per_sec
        time.sleep(wait)
        with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._tokens_per_sec)
        self._last_refill = now
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scripts && uv run pytest tests/test_rate_limiter.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Run mypy**

```bash
cd scripts && uv run mypy jit_update/rate_limiter.py
```

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/rate_limiter.py scripts/tests/test_rate_limiter.py
git commit -m "✨ feat(scripts): add token-bucket rate limiter"
```

---

## Task 4 — File-based HTTP cache

**Files:**
- Create: `scripts/jit_update/cache.py`
- Create: `scripts/tests/test_cache.py`

- [ ] **Step 1: Write failing tests**

Create `scripts/tests/test_cache.py`:

```python
"""Tests for FileCache."""
from __future__ import annotations

import time
from pathlib import Path

from jit_update.cache import FileCache


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    assert cache.get("https://example.com/foo") is None


def test_cache_set_then_get(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("https://example.com/foo", b'{"hello": "world"}')
    assert cache.get("https://example.com/foo") == b'{"hello": "world"}'


def test_cache_expires_after_ttl(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=0)  # immediate expiry
    cache.set("https://example.com/foo", b"payload")
    time.sleep(0.01)
    assert cache.get("https://example.com/foo") is None


def test_cache_creates_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir"
    cache = FileCache(target, ttl_seconds=60)
    cache.set("https://example.com/x", b"y")
    assert target.exists()


def test_cache_keys_are_url_independent_paths(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("https://example.com/a", b"A")
    cache.set("https://example.com/b", b"B")
    assert cache.get("https://example.com/a") == b"A"
    assert cache.get("https://example.com/b") == b"B"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_cache.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement FileCache**

Create `scripts/jit_update/cache.py`:

```python
"""File-based HTTP response cache."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path


class FileCache:
    """Disk-backed cache keyed by URL hash with a TTL.

    Stores raw response bytes alongside a meta sidecar (timestamp).
    """

    def __init__(self, root: Path, ttl_seconds: float) -> None:
        self._root = root
        self._ttl = ttl_seconds
        self._root.mkdir(parents=True, exist_ok=True)

    def _paths(self, url: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        body = self._root / f"{digest}.bin"
        meta = self._root / f"{digest}.ts"
        return body, meta

    def get(self, url: str) -> bytes | None:
        """Return cached body if fresh, else None."""
        body, meta = self._paths(url)
        if not body.exists() or not meta.exists():
            return None
        try:
            ts = float(meta.read_text().strip())
        except (ValueError, OSError):
            return None
        if (time.time() - ts) > self._ttl:
            return None
        return body.read_bytes()

    def set(self, url: str, payload: bytes) -> None:
        body, meta = self._paths(url)
        body.write_bytes(payload)
        meta.write_text(str(time.time()))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scripts && uv run pytest tests/test_cache.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/cache.py scripts/tests/test_cache.py
git commit -m "✨ feat(scripts): add file-based HTTP cache with TTL"
```

---

## Task 5 — Raider.IO HTTP client

**Files:**
- Create: `scripts/jit_update/raiderio.py`
- Create: `scripts/tests/test_raiderio.py`
- Create: `scripts/tests/fixtures/static_data_mn1.json` (small subset)
- Create: `scripts/tests/fixtures/runs_aa_p0.json` (1 page)

- [ ] **Step 1: Capture small `static_data_mn1.json` fixture**

Create `scripts/tests/fixtures/static_data_mn1.json`:

```json
{
  "seasons": [
    {
      "slug": "season-mn-1",
      "name": "MN Season 1",
      "is_main_season": true,
      "dungeons": [
        {
          "id": 14032,
          "challenge_mode_id": 402,
          "slug": "algethar-academy",
          "name": "Algeth'ar Academy",
          "short_name": "AA",
          "keystone_timer_seconds": 1800
        },
        {
          "id": 15829,
          "challenge_mode_id": 558,
          "slug": "magisters-terrace",
          "name": "Magisters' Terrace",
          "short_name": "MT",
          "keystone_timer_seconds": 2040
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Capture small `runs_aa_p0.json` fixture (one ranking entry)**

Create `scripts/tests/fixtures/runs_aa_p0.json`:

```json
{
  "rankings": [
    {
      "rank": 1,
      "score": 501.2,
      "run": {
        "keystone_run_id": 16544744,
        "season": "season-mn-1",
        "status": "finished",
        "dungeon": {
          "id": 14032,
          "name": "Algeth'ar Academy",
          "short_name": "AA",
          "slug": "algethar-academy",
          "map_challenge_mode_id": 402,
          "keystone_timer_ms": 1800999,
          "num_bosses": 4
        },
        "mythic_level": 12,
        "clear_time_ms": 1742595,
        "keystone_time_ms": 1800999,
        "completed_at": "2026-04-23T16:01:45.000Z",
        "num_chests": 1,
        "time_remaining_ms": 58404,
        "weekly_modifiers": [
          {"id": 10, "slug": "fortified", "name": "Fortified"},
          {"id": 147, "slug": "xalataths-guile", "name": "Xal'atath's Guile"}
        ]
      }
    }
  ]
}
```

- [ ] **Step 3: Write failing tests**

Create `scripts/tests/test_raiderio.py`:

```python
"""Tests for RaiderIOClient."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter
from jit_update.raiderio import RaiderIOClient, RaiderIOError


def _client(tmp_path: Path) -> RaiderIOClient:
    return RaiderIOClient(
        base_url="https://raider.io/api/v1",
        rate_limiter=RateLimiter(rate_per_minute=6000, capacity=10),
        cache=FileCache(tmp_path / "cache", ttl_seconds=60),
        timeout_seconds=5.0,
        max_retries=2,
    )


@respx.mock
def test_get_static_data_returns_payload(tmp_path: Path, load_fixture) -> None:
    payload = load_fixture("static_data_mn1.json")
    route = respx.get(
        "https://raider.io/api/v1/mythic-plus/static-data?expansion_id=11"
    ).mock(return_value=httpx.Response(200, json=payload))

    client = _client(tmp_path)
    data = client.get_static_data(expansion_id=11)

    assert route.called
    assert data["seasons"][0]["slug"] == "season-mn-1"


@respx.mock
def test_get_runs_filters_via_query_params(tmp_path: Path, load_fixture) -> None:
    payload = load_fixture("runs_aa_p0.json")
    route = respx.get(
        "https://raider.io/api/v1/mythic-plus/runs",
        params={
            "season": "season-mn-1",
            "region": "world",
            "dungeon": "algethar-academy",
            "affixes": "all",
            "page": "0",
        },
    ).mock(return_value=httpx.Response(200, json=payload))

    client = _client(tmp_path)
    data = client.get_runs(
        season="season-mn-1", region="world", dungeon="algethar-academy", page=0
    )

    assert route.called
    assert data["rankings"][0]["rank"] == 1


@respx.mock
def test_cache_short_circuits_second_call(tmp_path: Path, load_fixture) -> None:
    payload = load_fixture("runs_aa_p0.json")
    route = respx.get("https://raider.io/api/v1/mythic-plus/runs").mock(
        return_value=httpx.Response(200, json=payload)
    )

    client = _client(tmp_path)
    client.get_runs(season="season-mn-1", region="world", dungeon="algethar-academy", page=0)
    client.get_runs(season="season-mn-1", region="world", dungeon="algethar-academy", page=0)

    assert route.call_count == 1, "second call should be served from cache"


@respx.mock
def test_retries_on_5xx_then_succeeds(tmp_path: Path, load_fixture) -> None:
    payload = load_fixture("runs_aa_p0.json")
    route = respx.get("https://raider.io/api/v1/mythic-plus/runs").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json=payload),
        ]
    )

    client = _client(tmp_path)
    data = client.get_runs(
        season="season-mn-1", region="world", dungeon="algethar-academy", page=0
    )

    assert route.call_count == 3
    assert data["rankings"][0]["rank"] == 1


@respx.mock
def test_gives_up_after_max_retries(tmp_path: Path) -> None:
    respx.get("https://raider.io/api/v1/mythic-plus/runs").mock(
        return_value=httpx.Response(500)
    )

    client = _client(tmp_path)
    with pytest.raises(RaiderIOError):
        client.get_runs(
            season="season-mn-1",
            region="world",
            dungeon="algethar-academy",
            page=0,
        )


@respx.mock
def test_get_run_details_uses_id_path_param(tmp_path: Path, load_fixture) -> None:
    payload = load_fixture("run_details_sample.json")
    route = respx.get(
        "https://raider.io/api/v1/mythic-plus/run-details",
        params={"season": "season-mn-1", "id": "16544744"},
    ).mock(return_value=httpx.Response(200, json=payload))

    client = _client(tmp_path)
    data = client.get_run_details(season="season-mn-1", run_id=16544744)

    assert route.called
    assert data["keystone_run_id"] == 16544744
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_raiderio.py -v
```

Expected: ImportError.

- [ ] **Step 5: Implement RaiderIOClient**

Create `scripts/jit_update/raiderio.py`:

```python
"""HTTP client for Raider.IO Mythic+ endpoints."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter


class RaiderIOError(RuntimeError):
    """Raised when Raider.IO responds with an unrecoverable error."""


class RaiderIOClient:
    """Thin wrapper around Raider.IO endpoints with rate limit + cache + retry.

    Read-only. Stateless beyond the cache + rate limiter passed at construction.
    """

    def __init__(
        self,
        base_url: str,
        rate_limiter: RateLimiter,
        cache: FileCache,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._rl = rate_limiter
        self._cache = cache
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._client = httpx.Client(timeout=timeout_seconds)

    def _build_url(self, path: str, params: dict[str, str | int] | None) -> str:
        url = f"{self._base_url}{path}"
        if params:
            sorted_items = sorted(params.items())
            query = "&".join(f"{k}={v}" for k, v in sorted_items)
            url = f"{url}?{query}"
        return url

    def _request_json(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> dict[str, Any]:
        url = self._build_url(path, params)

        cached = self._cache.get(url)
        if cached is not None:
            return json.loads(cached.decode("utf-8"))

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._rl.acquire()
            try:
                resp = self._client.get(url)
                if resp.status_code >= 500:
                    last_exc = RaiderIOError(
                        f"server error {resp.status_code} on {url}"
                    )
                    self._sleep_backoff(attempt)
                    continue
                if resp.status_code >= 400:
                    raise RaiderIOError(
                        f"client error {resp.status_code} on {url}"
                    )
                payload = resp.content
                self._cache.set(url, payload)
                return json.loads(payload.decode("utf-8"))
            except httpx.TimeoutException as exc:
                last_exc = exc
                self._sleep_backoff(attempt)
                continue
        raise RaiderIOError(
            f"giving up after {self._max_retries + 1} attempts on {url}"
        ) from last_exc

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        time.sleep(min(2.0**attempt, 8.0))

    # ─── public endpoints ───────────────────────────────────────────────

    def get_static_data(self, expansion_id: int) -> dict[str, Any]:
        return self._request_json(
            "/mythic-plus/static-data", {"expansion_id": expansion_id}
        )

    def get_runs(
        self,
        season: str,
        region: str,
        dungeon: str,
        page: int = 0,
        affixes: str = "all",
    ) -> dict[str, Any]:
        return self._request_json(
            "/mythic-plus/runs",
            {
                "season": season,
                "region": region,
                "dungeon": dungeon,
                "affixes": affixes,
                "page": page,
            },
        )

    def get_run_details(self, season: str, run_id: int) -> dict[str, Any]:
        return self._request_json(
            "/mythic-plus/run-details", {"season": season, "id": run_id}
        )

    def close(self) -> None:
        self._client.close()
```

- [ ] **Step 6: Run tests**

```bash
cd scripts && uv run pytest tests/test_raiderio.py -v
```

Expected: 6 tests pass.

- [ ] **Step 7: Run mypy**

```bash
cd scripts && uv run mypy jit_update/
```

Expected: `Success: no issues found in 4 source files` (or similar — accept all green).

- [ ] **Step 8: Commit**

```bash
git add scripts/jit_update/raiderio.py scripts/tests/test_raiderio.py scripts/tests/fixtures/
git commit -m "✨ feat(scripts): Raider.IO HTTP client with cache + retry + rate limit"
```

---

## Task 6 — Pipeline: collect timed runs

**Files:**
- Create: `scripts/jit_update/pipeline.py`
- Create: `scripts/tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `scripts/tests/test_pipeline.py`:

```python
"""Tests for pipeline orchestration."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from jit_update.models import Run
from jit_update.pipeline import (
    collect_timed_runs,
    select_slowest_percentile,
)


def _make_run_payload(
    run_id: int,
    level: int,
    clear_time_ms: int,
    chests: int = 1,
    affixes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "rank": run_id,
        "score": 0,
        "run": {
            "keystone_run_id": run_id,
            "season": "season-mn-1",
            "status": "finished",
            "dungeon": {
                "id": 14032,
                "name": "Algeth'ar Academy",
                "short_name": "AA",
                "slug": "algethar-academy",
                "map_challenge_mode_id": 402,
                "keystone_timer_ms": 1800999,
                "num_bosses": 4,
            },
            "mythic_level": level,
            "clear_time_ms": clear_time_ms,
            "keystone_time_ms": 1800999,
            "completed_at": "2026-04-23T16:01:45.000Z",
            "num_chests": chests,
            "time_remaining_ms": 0,
            "weekly_modifiers": affixes
            or [
                {"id": 10, "slug": "fortified", "name": "Fortified"},
                {"id": 147, "slug": "xalataths-guile", "name": "Xal'atath's Guile"},
            ],
        },
    }


def test_collect_timed_runs_filters_by_level_and_affixes() -> None:
    page0 = {
        "rankings": [
            _make_run_payload(1, 14, 1700000),  # wrong level
            _make_run_payload(2, 12, 1700000),  # match
            _make_run_payload(3, 12, 1750000),  # match
            _make_run_payload(
                4,
                12,
                1800000,
                affixes=[
                    {"id": 9, "slug": "tyrannical", "name": "Tyrannical"},
                    {"id": 147, "slug": "xalataths-guile", "name": "Xal'atath's Guile"},
                ],
            ),  # wrong affixes
        ]
    }
    page1 = {"rankings": []}

    client = MagicMock()
    client.get_runs.side_effect = [page0, page1]

    runs = collect_timed_runs(
        client=client,
        season="season-mn-1",
        region="world",
        dungeon="algethar-academy",
        target_level=12,
        target_affix_combo="fortified-xalataths-guile",
        min_sample=10,
        max_pages=5,
    )

    assert {r.keystone_run_id for r in runs} == {2, 3}


def test_collect_stops_when_min_sample_reached() -> None:
    page0 = {
        "rankings": [_make_run_payload(i, 12, 1700000 + i) for i in range(20)]
    }
    client = MagicMock()
    client.get_runs.return_value = page0

    runs = collect_timed_runs(
        client=client,
        season="season-mn-1",
        region="world",
        dungeon="algethar-academy",
        target_level=12,
        target_affix_combo="fortified-xalataths-guile",
        min_sample=10,
        max_pages=5,
    )

    assert len(runs) >= 10
    # Should have stopped before exhausting pages
    assert client.get_runs.call_count == 1


def test_collect_excludes_untimed_runs() -> None:
    page0 = {
        "rankings": [
            _make_run_payload(1, 12, 1900000, chests=0),  # over time, untimed
            _make_run_payload(2, 12, 1700000, chests=1),
            _make_run_payload(3, 12, 1750000, chests=2),
        ]
    }
    page1 = {"rankings": []}
    client = MagicMock()
    client.get_runs.side_effect = [page0, page1]

    runs = collect_timed_runs(
        client=client,
        season="season-mn-1",
        region="world",
        dungeon="algethar-academy",
        target_level=12,
        target_affix_combo="fortified-xalataths-guile",
        min_sample=10,
        max_pages=5,
    )

    assert {r.keystone_run_id for r in runs} == {2, 3}


def test_select_slowest_percentile_minimum_two() -> None:
    runs = [
        Run.model_validate(_make_run_payload(i, 12, 1700000 + i * 1000)["run"])
        for i in range(50)
    ]
    selected = select_slowest_percentile(runs, percentile=10, min_count=2)
    # 10% of 50 = 5
    assert len(selected) == 5
    # selected = the 5 with the largest clear_time_ms
    assert {r.keystone_run_id for r in selected} == {45, 46, 47, 48, 49}


def test_select_slowest_floors_at_min_count() -> None:
    runs = [
        Run.model_validate(_make_run_payload(i, 12, 1700000 + i * 1000)["run"])
        for i in range(5)
    ]
    selected = select_slowest_percentile(runs, percentile=10, min_count=2)
    # 10% of 5 = 0.5 → floored, but min_count=2
    assert len(selected) == 2
    assert {r.keystone_run_id for r in selected} == {3, 4}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement initial pipeline functions**

Create `scripts/jit_update/pipeline.py`:

```python
"""Pipeline orchestration: fetch → filter → sample → aggregate."""
from __future__ import annotations

import math
from typing import Any, Protocol

from jit_update.models import Run


class RaiderIOClientLike(Protocol):
    """Protocol matching what the pipeline needs from the HTTP client."""

    def get_runs(
        self, season: str, region: str, dungeon: str, page: int, affixes: str = ...
    ) -> dict[str, Any]: ...

    def get_run_details(self, season: str, run_id: int) -> dict[str, Any]: ...


def collect_timed_runs(
    client: RaiderIOClientLike,
    season: str,
    region: str,
    dungeon: str,
    target_level: int,
    target_affix_combo: str,
    min_sample: int,
    max_pages: int,
) -> list[Run]:
    """Paginate /mythic-plus/runs and return up to `min_sample`+ matching timed runs.

    Filters client-side on:
      * mythic_level == target_level
      * weekly_modifiers combo == target_affix_combo
      * is_timed (num_chests >= 1)

    Stops as soon as we have `min_sample` matches OR `max_pages` consumed.
    """
    matched: list[Run] = []
    for page in range(max_pages):
        payload = client.get_runs(
            season=season, region=region, dungeon=dungeon, page=page
        )
        rankings = payload.get("rankings", [])
        if not rankings:
            break
        for entry in rankings:
            run = Run.model_validate(entry["run"])
            if run.mythic_level != target_level:
                continue
            if run.affix_combo() != target_affix_combo:
                continue
            if not run.is_timed:
                continue
            matched.append(run)
        if len(matched) >= min_sample:
            break
    return matched


def select_slowest_percentile(
    runs: list[Run], percentile: int, min_count: int = 2
) -> list[Run]:
    """Return the slowest `percentile`% of runs by clear_time_ms.

    `min_count` floors the result so we always have a usable sample.
    """
    if not runs:
        return []
    sorted_desc = sorted(runs, key=lambda r: r.clear_time_ms, reverse=True)
    count = max(min_count, math.floor(len(runs) * percentile / 100))
    count = min(count, len(runs))
    return sorted_desc[:count]
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/pipeline.py scripts/tests/test_pipeline.py
git commit -m "✨ feat(scripts): pipeline collect_timed_runs + select_slowest_percentile"
```

---

## Task 7 — Pipeline: boss splits aggregation

**Files:**
- Modify: `scripts/jit_update/pipeline.py`
- Modify: `scripts/tests/test_pipeline.py`

- [ ] **Step 1: Append failing tests to `scripts/tests/test_pipeline.py`**

Add at the bottom of the file:

```python
from jit_update.models import RunDetails
from jit_update.pipeline import compute_reference_cell


def _make_details_payload(splits_ms: list[int], num_bosses: int = 4) -> dict[str, Any]:
    encounters = [
        {
            "duration_ms": 100000,
            "is_success": True,
            "approximate_relative_started_at": (splits_ms[i] - 100000),
            "approximate_relative_ended_at": splits_ms[i],
            "boss": {
                "slug": f"boss{i + 1}",
                "name": f"Boss {i + 1}",
                "ordinal": i + 1,
                "wowEncounterId": 1000 + i,
            },
        }
        for i in range(num_bosses)
    ]
    return {
        "season": "season-mn-1",
        "keystone_run_id": 99,
        "mythic_level": 12,
        "clear_time_ms": splits_ms[-1],
        "keystone_time_ms": 1800999,
        "num_chests": 1,
        "time_remaining_ms": 0,
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
            "keystone_timer_ms": 1800999,
            "num_bosses": num_bosses,
        },
        "logged_details": {"encounters": encounters},
    }


def test_compute_reference_cell_takes_median_per_boss() -> None:
    details = [
        RunDetails.model_validate(_make_details_payload([280000, 740000, 1200000, 1742000])),
        RunDetails.model_validate(_make_details_payload([300000, 760000, 1220000, 1760000])),
        RunDetails.model_validate(_make_details_payload([260000, 720000, 1180000, 1740000])),
    ]
    cell = compute_reference_cell(details, num_bosses=4)
    assert cell.sample_size == 3
    assert cell.boss_splits_ms == [280000, 740000, 1200000, 1742000]
    assert cell.clear_time_ms == 1742000


def test_compute_reference_cell_handles_missing_boss_split() -> None:
    a = _make_details_payload([280000, 740000, 1200000, 1742000])
    b = _make_details_payload([300000, 760000, 1220000, 1760000])
    # In b, simulate a non-success encounter for boss 2
    b["logged_details"]["encounters"][1]["is_success"] = False
    details = [
        RunDetails.model_validate(a),
        RunDetails.model_validate(b),
    ]
    cell = compute_reference_cell(details, num_bosses=4)
    # Boss 2 only has one valid value → median = that single value
    assert cell.sample_size == 2
    assert cell.boss_splits_ms[1] == 740000


def test_compute_reference_cell_empty_returns_none() -> None:
    cell = compute_reference_cell([], num_bosses=4)
    assert cell is None
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v
```

Expected: 3 new tests fail (`compute_reference_cell` not yet exported).

- [ ] **Step 3: Append implementation to `scripts/jit_update/pipeline.py`**

Add at the bottom of `pipeline.py`:

```python
import statistics

from jit_update.models import ReferenceCell, RunDetails


def compute_reference_cell(
    details: list[RunDetails], num_bosses: int
) -> ReferenceCell | None:
    """Aggregate per-boss split medians and clear-time median.

    `num_bosses` is the dungeon's boss count (from static data); used to
    pad/trim per-run splits to a stable length.

    Returns None if no input runs.
    """
    if not details:
        return None

    # collect per-boss split lists, skipping None entries
    per_boss: list[list[int]] = [[] for _ in range(num_bosses)]
    for d in details:
        splits = d.boss_splits_ms()
        for idx in range(num_bosses):
            if idx < len(splits) and splits[idx] is not None:
                per_boss[idx].append(int(splits[idx]))

    # median per boss; skip empty bosses by linear interp from neighbors as last resort
    boss_medians: list[int] = []
    for idx in range(num_bosses):
        values = per_boss[idx]
        if not values:
            # No data for this boss in any run — fall back to interpolation between
            # known neighbors. If there are no neighbors, use clear_time_median * (idx+1)/num_bosses.
            boss_medians.append(0)  # filled in below
        else:
            boss_medians.append(int(statistics.median(values)))

    clear_times = [int(d.clear_time_ms) for d in details]
    clear_time_median = int(statistics.median(clear_times))

    # backfill any zero placeholders by linear interpolation
    for idx in range(num_bosses):
        if boss_medians[idx] != 0:
            continue
        prev_known = next(
            (boss_medians[j] for j in range(idx - 1, -1, -1) if boss_medians[j] > 0),
            0,
        )
        next_known = next(
            (
                boss_medians[j]
                for j in range(idx + 1, num_bosses)
                if boss_medians[j] > 0
            ),
            clear_time_median,
        )
        # linear midpoint
        boss_medians[idx] = (prev_known + next_known) // 2

    return ReferenceCell(
        sample_size=len(details),
        clear_time_ms=clear_time_median,
        boss_splits_ms=boss_medians,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v
```

Expected: 8 tests pass total.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/pipeline.py scripts/tests/test_pipeline.py
git commit -m "✨ feat(scripts): compute_reference_cell median aggregation"
```

---

## Task 8 — Lua renderer

**Files:**
- Create: `scripts/jit_update/lua_renderer.py`
- Create: `scripts/tests/test_lua_renderer.py`
- Create: `scripts/tests/fixtures/expected_minimal.lua`

- [ ] **Step 1: Create the golden fixture**

Create `scripts/tests/fixtures/expected_minimal.lua`:

```lua
-- Generated by jit_update — do not edit by hand
JustInTimeData = {
  meta = {
    generated_at = "2026-04-25T14:30:00Z",
    season = "season-mn-1",
    schema_version = 1,
  },
  affix_id_to_slug = {
    [9] = "tyrannical",
    [10] = "fortified",
    [147] = "xalataths-guile",
  },
  dungeons = {
    ["algethar-academy"] = {
      short_name = "AA",
      challenge_mode_id = 402,
      timer_ms = 1800999,
      num_bosses = 4,
      bosses = {
        { ordinal = 1, slug = "overgrown-ancient", name = "Overgrown Ancient", wow_encounter_id = 2563 },
        { ordinal = 2, slug = "boss2", name = "Boss 2", wow_encounter_id = 2564 },
        { ordinal = 3, slug = "boss3", name = "Boss 3", wow_encounter_id = 2565 },
        { ordinal = 4, slug = "boss4", name = "Boss 4", wow_encounter_id = 2566 },
      },
      levels = {
        [12] = {
          ["fortified-xalataths-guile"] = {
            sample_size = 3,
            clear_time_ms = 1742000,
            boss_splits_ms = { 280000, 740000, 1200000, 1742000 },
          },
        },
      },
    },
  },
}
```

- [ ] **Step 2: Write failing tests**

Create `scripts/tests/test_lua_renderer.py`:

```python
"""Tests for lua_renderer."""
from __future__ import annotations

from pathlib import Path

from jit_update.lua_renderer import render_data_lua


def test_render_minimal_document(fixtures_dir: Path) -> None:
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
                    {"ordinal": 1, "slug": "overgrown-ancient", "name": "Overgrown Ancient", "wow_encounter_id": 2563},
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
                    {"ordinal": 1, "slug": "the-king", "name": 'King "Tharin"', "wow_encounter_id": 100},
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
    # affix_id_to_slug entries appear ordered by id ascending
    assert rendered.index("[9]") < rendered.index("[10]") < rendered.index("[147]")
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_lua_renderer.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement renderer**

Create `scripts/jit_update/lua_renderer.py`:

```python
"""Render a Python document into a deterministic Lua declaration string."""
from __future__ import annotations

from typing import Any

INDENT = "  "
HEADER = "-- Generated by jit_update — do not edit by hand\n"


def render_data_lua(document: dict[str, Any]) -> str:
    """Render the full Data.lua content for a JustInTime document.

    The output is byte-deterministic given the same input (sorted keys, fixed indent).
    Top-level shape:
        {
          "meta": {...},
          "affix_id_to_slug": {<int>: <str>, ...},
          "dungeons": {<slug>: <dungeon dict>, ...},
        }
    """
    parts: list[str] = [HEADER, "JustInTimeData = {\n"]
    parts.append(_render_kv(1, "meta", document.get("meta", {})))
    parts.append(_render_kv(1, "affix_id_to_slug", document.get("affix_id_to_slug", {})))
    parts.append(_render_kv(1, "dungeons", document.get("dungeons", {})))
    parts.append("}\n")
    return "".join(parts)


def _render_kv(level: int, key: str, value: Any) -> str:
    indent = INDENT * level
    return f"{indent}{key} = {_render_value(level, value, key=key)},\n"


def _render_value(level: int, value: Any, key: str | None = None) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _quote(value)
    if value is None:
        return "nil"
    if isinstance(value, list):
        return _render_list(level, value, key=key)
    if isinstance(value, dict):
        return _render_dict(level, value, key=key)
    raise TypeError(f"unsupported value type: {type(value).__name__}")


def _render_list(level: int, items: list[Any], key: str | None) -> str:
    if not items:
        return "{}"
    # Detect "list of ints" → render compactly on one line (boss_splits_ms style)
    if all(isinstance(x, int) for x in items):
        inner = ", ".join(str(x) for x in items)
        return "{ " + inner + " }"
    indent = INDENT * (level + 1)
    closing = INDENT * level
    lines = ["{\n"]
    for item in items:
        lines.append(f"{indent}{_render_value(level + 1, item)},\n")
    lines.append(f"{closing}}}")
    return "".join(lines)


def _render_dict(level: int, items: dict[Any, Any], key: str | None) -> str:
    if not items:
        return "{}"
    indent = INDENT * (level + 1)
    closing = INDENT * level
    lines = ["{\n"]
    for k, v in _sorted_items(items):
        rendered_key = _render_dict_key(k)
        lines.append(f"{indent}{rendered_key} = {_render_value(level + 1, v)},\n")
    lines.append(f"{closing}}}")
    return "".join(lines)


def _sorted_items(items: dict[Any, Any]) -> list[tuple[Any, Any]]:
    """Sort dict items deterministically: ints by numeric, strs alphabetically."""
    return sorted(items.items(), key=lambda kv: (0, kv[0]) if isinstance(kv[0], int) else (1, kv[0]))


def _render_dict_key(k: Any) -> str:
    if isinstance(k, int):
        return f"[{k}]"
    if isinstance(k, str):
        if _is_lua_identifier(k):
            return k
        return f"[{_quote(k)}]"
    raise TypeError(f"unsupported dict key type: {type(k).__name__}")


def _is_lua_identifier(s: str) -> bool:
    if not s:
        return False
    if not (s[0].isalpha() or s[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in s)


def _quote(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'
```

- [ ] **Step 5: Run tests**

```bash
cd scripts && uv run pytest tests/test_lua_renderer.py -v
```

Expected: 3 tests pass.

If the golden test fails on whitespace/format, regenerate `expected_minimal.lua` from actual output (use the test's `rendered` value as the new golden, then re-run).

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/lua_renderer.py scripts/tests/test_lua_renderer.py scripts/tests/fixtures/expected_minimal.lua
git commit -m "✨ feat(scripts): deterministic Lua renderer with golden file test"
```

---

## Task 9 — Config module

**Files:**
- Create: `scripts/jit_update/config.py`
- Create: `scripts/tests/test_config.py`
- Create: `scripts/jit_config.toml`

- [ ] **Step 1: Create the default `jit_config.toml`**

Create `scripts/jit_config.toml`:

```toml
# JustInTime — script config
# Edit as needed. CLI flags override these values.

[raiderio]
api_base = "https://raider.io/api/v1"
expansion_id = 11                 # Midnight = 11 in static-data lookup
season = "season-mn-1"
region = "world"
rate_per_minute = 300
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3

[scope]
levels = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
min_sample = 20
slowest_percentile = 10
max_pages_per_query = 50

[output]
data_lua_path = "../addon/JustInTime/Data.lua"
schema_version = 1
```

- [ ] **Step 2: Write failing tests**

Create `scripts/tests/test_config.py`:

```python
"""Tests for config loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from jit_update.config import Config, load_config


def test_load_default_jit_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "jit_config.toml"
    cfg_path.write_text(
        """
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
"""
    )
    cfg = load_config(cfg_path)
    assert cfg.raiderio.season == "season-mn-1"
    assert cfg.scope.levels == [10, 12, 14]
    assert cfg.output.data_lua_path == "../addon/JustInTime/Data.lua"


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "absent.toml")


def test_config_validates_levels_range(tmp_path: Path) -> None:
    cfg_path = tmp_path / "jit_config.toml"
    cfg_path.write_text(
        """
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
"""
    )
    with pytest.raises(ValueError, match="level"):
        load_config(cfg_path)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_config.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement Config**

Create `scripts/jit_update/config.py`:

```python
"""Configuration loader for jit_update."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RaiderIOConfig:
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
    levels: list[int]
    min_sample: int
    slowest_percentile: int
    max_pages_per_query: int


@dataclass(frozen=True)
class OutputConfig:
    data_lua_path: str
    schema_version: int


@dataclass(frozen=True)
class Config:
    raiderio: RaiderIOConfig
    scope: ScopeConfig
    output: OutputConfig


def load_config(path: Path) -> Config:
    """Load a Config from a TOML file. Validates basic invariants."""
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
```

- [ ] **Step 5: Run tests**

```bash
cd scripts && uv run pytest tests/test_config.py -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/config.py scripts/tests/test_config.py scripts/jit_config.toml
git commit -m "✨ feat(scripts): config loader with TOML + default jit_config.toml"
```

---

## Task 10 — Pipeline orchestration (build full document)

**Files:**
- Modify: `scripts/jit_update/pipeline.py`
- Modify: `scripts/tests/test_pipeline.py`

- [ ] **Step 1: Append failing tests to `scripts/tests/test_pipeline.py`**

```python
from datetime import datetime, timezone

from jit_update.config import Config, OutputConfig, RaiderIOConfig, ScopeConfig
from jit_update.pipeline import build_document


def _make_config() -> Config:
    return Config(
        raiderio=RaiderIOConfig(
            api_base="https://raider.io/api/v1",
            expansion_id=11,
            season="season-mn-1",
            region="world",
            rate_per_minute=600,
            cache_ttl_seconds=60,
            timeout_seconds=5.0,
            max_retries=2,
        ),
        scope=ScopeConfig(
            levels=[12],
            min_sample=2,
            slowest_percentile=50,  # half = at least 1
            max_pages_per_query=1,
        ),
        output=OutputConfig(
            data_lua_path="/tmp/Data.lua",
            schema_version=1,
        ),
    )


def test_build_document_assembles_meta_and_dungeons() -> None:
    static_data = {
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
                    },
                ],
            }
        ]
    }
    runs_page = {
        "rankings": [
            _make_run_payload(1, 12, 1700000),
            _make_run_payload(2, 12, 1750000),
        ]
    }
    details_payload = _make_details_payload([280000, 740000, 1200000, 1742000])

    client = MagicMock()
    client.get_static_data.return_value = static_data
    client.get_runs.return_value = runs_page
    client.get_run_details.return_value = details_payload

    cfg = _make_config()
    doc = build_document(
        client=client,
        config=cfg,
        now=datetime(2026, 4, 25, 14, 30, 0, tzinfo=timezone.utc),
    )

    assert doc["meta"]["season"] == "season-mn-1"
    assert doc["meta"]["schema_version"] == 1
    assert doc["meta"]["generated_at"] == "2026-04-25T14:30:00Z"
    assert "algethar-academy" in doc["dungeons"]
    aa = doc["dungeons"]["algethar-academy"]
    assert aa["short_name"] == "AA"
    assert aa["challenge_mode_id"] == 402
    assert aa["timer_ms"] == 1800000
    assert aa["num_bosses"] == 4
    cell = aa["levels"][12]["fortified-xalataths-guile"]
    assert cell["sample_size"] >= 1
    assert cell["boss_splits_ms"] == [280000, 740000, 1200000, 1742000]
    # bosses present from run-details encounters
    assert {b["ordinal"] for b in aa["bosses"]} == {1, 2, 3, 4}


def test_build_document_skips_cells_with_insufficient_sample() -> None:
    static_data = {
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
                    }
                ],
            }
        ]
    }
    # Page returns no matching runs
    client = MagicMock()
    client.get_static_data.return_value = static_data
    client.get_runs.return_value = {"rankings": []}

    cfg = _make_config()
    doc = build_document(
        client=client,
        config=cfg,
        now=datetime(2026, 4, 25, 14, 30, 0, tzinfo=timezone.utc),
    )

    aa = doc["dungeons"]["algethar-academy"]
    # No level cells emitted (sample insufficient)
    assert aa["levels"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v
```

Expected: 2 new failures (`build_document` not yet implemented).

- [ ] **Step 3: Append `build_document` to `scripts/jit_update/pipeline.py`**

```python
from datetime import datetime
from typing import Iterable

from jit_update.config import Config

# Hardcoded affix mapping (Raider.IO id → slug). Extended as new affixes appear.
DEFAULT_AFFIX_MAP: dict[int, str] = {
    9: "tyrannical",
    10: "fortified",
    147: "xalataths-guile",
}


def _affix_combos_to_query(affix_map: dict[int, str]) -> list[str]:
    """Generate all interesting weekly-affix combos to query.

    For Midnight S1, the rotation is Fortified|Tyrannical × Xal'atath's Guile.
    Returns the alphabetically-sorted combo slugs.
    """
    seasonal = ["xalataths-guile"]
    rotation = ["fortified", "tyrannical"]
    return sorted(["-".join(sorted([r, *seasonal])) for r in rotation])


def build_document(
    client: RaiderIOClientLike,
    config: Config,
    now: datetime,
) -> dict[str, Any]:
    """Run the full pipeline and assemble the Data.lua document dict."""
    static = client.get_static_data(expansion_id=config.raiderio.expansion_id)

    season_obj = next(
        (s for s in static.get("seasons", []) if s.get("slug") == config.raiderio.season),
        None,
    )
    if season_obj is None:
        raise RaiderIOError(f"season {config.raiderio.season!r} not in static data")

    dungeons_static = season_obj.get("dungeons", [])
    affix_combos = _affix_combos_to_query(DEFAULT_AFFIX_MAP)

    document: dict[str, Any] = {
        "meta": {
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "season": config.raiderio.season,
            "schema_version": config.output.schema_version,
        },
        "affix_id_to_slug": dict(DEFAULT_AFFIX_MAP),
        "dungeons": {},
    }

    for dg in dungeons_static:
        slug = dg["slug"]
        timer_ms = int(dg["keystone_timer_seconds"]) * 1000
        levels: dict[int, dict[str, Any]] = {}
        bosses_seen: dict[int, dict[str, Any]] = {}

        for level in config.scope.levels:
            for combo in affix_combos:
                runs = collect_timed_runs(
                    client=client,
                    season=config.raiderio.season,
                    region=config.raiderio.region,
                    dungeon=slug,
                    target_level=level,
                    target_affix_combo=combo,
                    min_sample=config.scope.min_sample,
                    max_pages=config.scope.max_pages_per_query,
                )
                if len(runs) < config.scope.min_sample:
                    continue
                sample = select_slowest_percentile(
                    runs, percentile=config.scope.slowest_percentile, min_count=2
                )
                details_list: list[RunDetails] = []
                for run in sample:
                    raw = client.get_run_details(
                        season=config.raiderio.season, run_id=run.keystone_run_id
                    )
                    rd = RunDetails.model_validate(raw)
                    details_list.append(rd)
                    for enc in rd.encounters:
                        bosses_seen.setdefault(
                            enc.boss.ordinal,
                            {
                                "ordinal": enc.boss.ordinal,
                                "slug": enc.boss.slug,
                                "name": enc.boss.name,
                                "wow_encounter_id": enc.boss.wow_encounter_id,
                            },
                        )
                cell = compute_reference_cell(
                    details_list, num_bosses=int(dg.get("num_bosses", 4))
                )
                if cell is None:
                    continue
                levels.setdefault(level, {})[combo] = {
                    "sample_size": cell.sample_size,
                    "clear_time_ms": cell.clear_time_ms,
                    "boss_splits_ms": list(cell.boss_splits_ms),
                }

        bosses_list = sorted(bosses_seen.values(), key=lambda b: b["ordinal"])
        document["dungeons"][slug] = {
            "short_name": dg.get("short_name", ""),
            "challenge_mode_id": int(dg["challenge_mode_id"]),
            "timer_ms": timer_ms,
            "num_bosses": int(dg.get("num_bosses", len(bosses_list) or 4)),
            "bosses": bosses_list,
            "levels": levels,
        }

    return document
```

(Note: the `num_bosses` field isn't returned by `static-data`; we infer it from observed encounters. If you want to pre-bake it, hardcode in a small map for the 8 MN1 dungeons.)

- [ ] **Step 4: Run all tests**

```bash
cd scripts && uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/pipeline.py scripts/tests/test_pipeline.py
git commit -m "✨ feat(scripts): build_document end-to-end pipeline"
```

---

## Task 11 — CLI entry-point

**Files:**
- Create: `scripts/jit_update/cli.py`
- Create: `scripts/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Create `scripts/tests/test_cli.py`:

```python
"""Tests for the typer CLI."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from jit_update.cli import app


def _write_minimal_config(path: Path) -> Path:
    cfg = path / "jit_config.toml"
    cfg.write_text(
        """
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
""".format(out=str(path / "Data.lua"))
    )
    return cfg


def test_cli_dry_run_does_not_write_file(tmp_path: Path) -> None:
    cfg_path = _write_minimal_config(tmp_path)

    fake_doc = {
        "meta": {"generated_at": "2026-04-25T14:30:00Z", "season": "season-mn-1", "schema_version": 1},
        "affix_id_to_slug": {},
        "dungeons": {},
    }
    with patch("jit_update.cli.build_document", return_value=fake_doc):
        runner = CliRunner()
        result = runner.invoke(app, ["--config", str(cfg_path), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert not (tmp_path / "Data.lua").exists()
    assert "season-mn-1" in result.output


def test_cli_writes_data_lua(tmp_path: Path) -> None:
    cfg_path = _write_minimal_config(tmp_path)
    fake_doc = {
        "meta": {"generated_at": "2026-04-25T14:30:00Z", "season": "season-mn-1", "schema_version": 1},
        "affix_id_to_slug": {},
        "dungeons": {},
    }
    with patch("jit_update.cli.build_document", return_value=fake_doc):
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
    fake_doc = {
        "meta": {"generated_at": "2026-04-25T14:30:00Z", "season": "season-mn-1", "schema_version": 1},
        "affix_id_to_slug": {},
        "dungeons": {},
    }
    with patch("jit_update.cli.build_document", return_value=fake_doc):
        runner = CliRunner()
        result = runner.invoke(app, ["--config", str(cfg_path), "--out", str(target)])

    assert result.exit_code == 0, result.output
    assert target.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scripts && uv run pytest tests/test_cli.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement CLI**

Create `scripts/jit_update/cli.py`:

```python
"""Typer-based CLI for jit_update."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from jit_update.cache import FileCache
from jit_update.config import load_config
from jit_update.lua_renderer import render_data_lua
from jit_update.pipeline import build_document
from jit_update.raiderio import RaiderIOClient
from jit_update.rate_limiter import RateLimiter

app = typer.Typer(add_completion=False, help="Generate JustInTime Data.lua from Raider.IO")
console = Console()


@app.command()
def run(
    config: Path = typer.Option(
        Path("jit_config.toml"),
        "--config",
        "-c",
        help="Path to jit_config.toml",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Override output path (defaults to config.output.data_lua_path)",
    ),
    only: Optional[str] = typer.Option(
        None,
        "--only",
        help="Only fetch this dungeon slug (debug)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute and print stats; do not write Data.lua",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Bypass HTTP cache (does not delete; sets TTL to 0 for this run).",
    ),
) -> None:
    """Run the full data-generation pipeline."""
    cfg = load_config(config)

    cache_root = config.parent / ".cache" / "raiderio"
    cache = FileCache(
        cache_root, ttl_seconds=0 if no_cache else cfg.raiderio.cache_ttl_seconds
    )
    rl = RateLimiter(rate_per_minute=cfg.raiderio.rate_per_minute, capacity=10)
    client = RaiderIOClient(
        base_url=cfg.raiderio.api_base,
        rate_limiter=rl,
        cache=cache,
        timeout_seconds=cfg.raiderio.timeout_seconds,
        max_retries=cfg.raiderio.max_retries,
    )

    try:
        document = build_document(
            client=client, config=cfg, now=datetime.now(tz=timezone.utc)
        )
    finally:
        client.close()

    if only is not None:
        document["dungeons"] = {
            k: v for k, v in document["dungeons"].items() if k == only
        }

    _print_summary(document)

    if dry_run:
        console.print("[yellow]--dry-run: Data.lua not written[/yellow]")
        raise typer.Exit(0)

    target = out if out is not None else (config.parent / cfg.output.data_lua_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_data_lua(document))
    console.print(f"[green]✓ wrote {target}[/green]")


def _print_summary(document: dict) -> None:
    meta = document.get("meta", {})
    dungeons = document.get("dungeons", {})
    console.print(f"[bold]season:[/bold] {meta.get('season')}")
    console.print(f"[bold]generated_at:[/bold] {meta.get('generated_at')}")
    console.print(f"[bold]dungeons:[/bold] {len(dungeons)}")
    for slug, dg in dungeons.items():
        cells = sum(len(combos) for combos in dg.get("levels", {}).values())
        console.print(f"  • {slug}: {len(dg.get('levels', {}))} levels, {cells} cells")
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_cli.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Verify entry-point installs**

```bash
cd scripts && uv sync && uv run jit-update --help
```

Expected: Typer-rendered help text shown, exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/cli.py scripts/tests/test_cli.py
git commit -m "✨ feat(scripts): CLI entry-point with --dry-run / --out / --only / --no-cache"
```

---

## Task 12 — End-to-end integration test

**Files:**
- Create: `scripts/tests/test_integration.py`

- [ ] **Step 1: Write the integration test**

Create `scripts/tests/test_integration.py`:

```python
"""End-to-end integration test with mocked HTTP."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from jit_update.cli import app


def _runs_payload(level: int, run_ids: list[int]) -> dict[str, Any]:
    rankings = []
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
                    "boss": {"slug": "boss1", "name": "Boss 1", "ordinal": 1, "wowEncounterId": 1001},
                },
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 640000,
                    "approximate_relative_ended_at": 740000,
                    "boss": {"slug": "boss2", "name": "Boss 2", "ordinal": 2, "wowEncounterId": 1002},
                },
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 1100000,
                    "approximate_relative_ended_at": 1200000,
                    "boss": {"slug": "boss3", "name": "Boss 3", "ordinal": 3, "wowEncounterId": 1003},
                },
                {
                    "duration_ms": 100000,
                    "is_success": True,
                    "approximate_relative_started_at": 1640000,
                    "approximate_relative_ended_at": 1742000,
                    "boss": {"slug": "boss4", "name": "Boss 4", "ordinal": 4, "wowEncounterId": 1004},
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
    cfg_path.write_text(
        f"""
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
"""
    )

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
```

- [ ] **Step 2: Run integration test**

```bash
cd scripts && uv run pytest tests/test_integration.py -v
```

Expected: 1 test passes.

- [ ] **Step 3: Run full test suite + coverage**

```bash
cd scripts && uv run pytest --cov-report=term-missing
```

Expected: all tests pass, total coverage ≥70%.

- [ ] **Step 4: Run mypy + ruff strict checks**

```bash
cd scripts && uv run mypy jit_update/ && uv run ruff check jit_update/ tests/
```

Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/tests/test_integration.py
git commit -m "✅ test(scripts): end-to-end integration with respx mocked HTTP"
```

---

## Task 13 — README + first real Data.lua generation

**Files:**
- Create: `scripts/README.md`
- Modify: `addon/JustInTime/Data.lua` (generated by running the script)
- Modify: `addon/JustInTime/JustInTime.toc` (to load Data.lua at the right place)

- [ ] **Step 1: Create `scripts/README.md`**

```markdown
# jit_update — JustInTime data generator

Private build-time tool. Generates `addon/JustInTime/Data.lua` from Raider.IO Mythic+ data.

**Not shipped on `master`.** Lives only on `main`.

## Setup

```bash
cd scripts
uv sync
```

## Usage

```bash
# Full generation (writes Data.lua at config-defined path)
uv run jit-update

# Dry-run: print stats, don't write
uv run jit-update --dry-run

# Override output path
uv run jit-update --out ../addon/JustInTime/Data.lua

# Restrict to one dungeon (debug)
uv run jit-update --only algethar-academy

# Bypass HTTP cache
uv run jit-update --no-cache
```

## Tests

```bash
uv run pytest                     # all tests
uv run pytest --cov-report=html   # coverage report → htmlcov/
uv run mypy jit_update/           # strict type-check
uv run ruff check jit_update/ tests/
```

## Configuration

Edit `jit_config.toml` for season slug, levels range, sample threshold, output path.
```

- [ ] **Step 2: Update `addon/JustInTime/JustInTime.toc` to declare `Data.lua` in the load order**

Read the current `.toc` then update. The current `.toc` lists `Locales.lua, Config.lua, Core.lua, UI.lua` (from the scaffold). For Plan A we only add `Data.lua` between `Locales.lua` and `Config.lua` (the addon code that consumes it lands in Plan B).

```bash
cat addon/JustInTime/JustInTime.toc
```

Apply edit so the file body becomes:

```
## Interface: 120001
## Title: JustInTime
## Notes: Lightweight raid timing helper for WoW Retail
## Author: Claralicious_
## Version: 0.1.0
## SavedVariables: JustInTimeDB

Locales.lua
Data.lua
Config.lua
Core.lua
UI.lua
```

- [ ] **Step 3: Generate the real Data.lua (dry-run first)**

```bash
cd scripts && uv run jit-update --dry-run
```

Expected: rich console output listing season `season-mn-1`, the 8 MN1 dungeons, and per-dungeon cell counts. No file written.

- [ ] **Step 4: Generate the real Data.lua**

```bash
cd scripts && uv run jit-update
```

Expected: `✓ wrote /home/tarto/projects/wowAddons/justInTime/addon/JustInTime/Data.lua` and the file exists.

If the run takes >10 minutes, that's expected (paginating low keys is slow). If it errors out (rate limit, timeout, schema), check `.cache/raiderio/` for the raw responses, debug, and re-run (cache will short-circuit).

- [ ] **Step 5: Smoke-validate the generated `Data.lua`**

```bash
lua -e 'dofile("addon/JustInTime/Data.lua"); print("ok schema=" .. JustInTimeData.meta.schema_version .. " season=" .. JustInTimeData.meta.season)'
```

(Requires `lua5.4` or any Lua runtime locally — `apt install lua5.4` if missing.)

Expected: `ok schema=1 season=season-mn-1`.

If Lua is unavailable, instead grep the file:

```bash
head -10 addon/JustInTime/Data.lua && grep -c '^    \["' addon/JustInTime/Data.lua
```

Expected: header line shown, ≥8 dungeon entries counted.

- [ ] **Step 6: Commit Data.lua and README**

```bash
git add scripts/README.md addon/JustInTime/Data.lua addon/JustInTime/JustInTime.toc
git commit -m "🎉 feat(data): generate first real Data.lua for MN1 season"
```

---

## Self-review

After completing all 13 tasks, verify:

- [ ] **Coverage gate** : `uv run pytest --cov-report=term-missing` shows ≥70% per module.
- [ ] **mypy strict clean** : `uv run mypy jit_update/` all green.
- [ ] **ruff clean** : `uv run ruff check jit_update/ tests/` no findings.
- [ ] **All tasks committed atomically** : `git log --oneline scripts/` shows ≥13 commits, each scoped.
- [ ] **Data.lua exists and is valid Lua** : Task 13 step 5 passed.
- [ ] **`.toc` declares Data.lua** : second line in load order.
- [ ] **`main` branch only** : never pushed (`git status` should show no upstream for main).

**Spec coverage check** (mapping plan → spec sections):

| Spec section | Tasks |
|---|---|
| §3 Architecture (Python flow) | 1, 11, 13 |
| §4.1 Data.lua schema | 8, 13 |
| §5.1 Project structure | 1 |
| §5.2 Dependencies | 1 |
| §5.3 Pipeline steps a–e | 6, 7, 10 |
| §5.4 Robustness (rate limit, cache, retry) | 3, 4, 5 |
| §5.5 CLI | 11 |
| §5.6 Tests | 2–12 |
| §10 Hypotheses to validate | 13 (real run surfaces any pagination issues) |

If any task is missing for a spec requirement, add it inline before declaring Plan A done.

---

## Hand-off to Plan B

Once Plan A is executed and `Data.lua` is committed on `main`, **Plan B** (`docs/specs/2026-04-25-jit-plan-lua.md`) will be written to consume that file from the addon side. Plan B doesn't exist yet — invoke writing-plans again after Plan A completes, supplying the real `Data.lua` as a known input.
