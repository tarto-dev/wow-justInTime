# Blizzard Data Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Raider.IO `/runs` as the discovery source for the JustInTime reference data with the Blizzard Battle.net Game Data API, extending keystone level coverage from +18-20 to +15-22, simplifying the `Data.lua` schema (drop affix layer, schema_version=2), and synthesizing boss splits at low levels via observed-ratio extrapolation.

**Architecture:** New `BlizzardClient` (OAuth client_credentials + per-realm `mythic-keystone-leaderboard` calls, EU + US). Raider.IO retained for static metadata, `/run-details` splits enrichment, and `/runs?page=0` ratio collection (cache 7 days). New `splits_synthesis` module owns ratio math. Pipeline rewritten to orchestrate Blizzard discovery → Raider.IO ratio collection → cell aggregation with three-tier splits source (`raiderio` / `synthesized` / `equidistant_fallback`). `lua_renderer` emits schema v2. Three Lua files patched (drop affix-combo lookup, add schema guard, add locale keys). Version bumps to `v0.4.0`.

**Tech Stack:** Python 3.12 (existing), `httpx` for HTTP, `pydantic` v2 for response validation, `respx` for HTTP mocking in tests, `pytest` + `pytest-mock` + `pytest-cov` (70% coverage gate). WoW Retail Lua 5.1 (Interface 120001). Battle.net OAuth `client_credentials` flow (token TTL 24h, cached 23h).

**Spec reference:** [`docs/specs/2026-05-09-blizzard-data-source-design.md`](2026-05-09-blizzard-data-source-design.md)

**Working directory:** `/home/tarto/projects/wowAddons/justInTime`

**Branch:** `main` (per project workflow — never push, master is release-only orphan).

**Commit policy:** Conventional Commits + gitmoji per `CLAUDE.md`. Atomic per task. Use `git add <specific files>`, never `git add -A`.

**Pre-flight env vars:** Set before running `make data*`:
```bash
export BLIZZARD_CLIENT_ID="<your_client_id>"
export BLIZZARD_CLIENT_SECRET="<your_client_secret>"
```

---

## File structure changes

| File | Status | Responsibility |
|---|---|---|
| `scripts/jit_update/blizzard.py` | NEW | OAuth flow, token cache, Battle.net Game Data endpoints, rate limiter |
| `scripts/jit_update/splits_synthesis.py` | NEW | Observed-ratio collection (cache 7d), splits synthesis math |
| `scripts/jit_update/models.py` | MODIFY | Add `BlizzardRun`, `BlizzardLeaderboard*`; update `ReferenceCell` (drop affix_combo, add `splits_source`) |
| `scripts/jit_update/config.py` | MODIFY | Add `BlizzardConfig` dataclass, drop `max_pages_per_query`, update default `levels` |
| `scripts/jit_update/raiderio.py` | UNCHANGED | Keep `get_static_data`, `get_run_details`, `get_runs` (used by ratios) |
| `scripts/jit_update/pipeline.py` | REWRITE | Discovery via Blizzard, aggregation with new splits-source selection |
| `scripts/jit_update/lua_renderer.py` | MODIFY | Emit schema v2 (no affix layer, `splits_source` field, `schema_version=2`) |
| `scripts/jit_update/cli.py` | MODIFY | Load Blizzard env vars, instantiate clients, handle missing-creds error |
| `scripts/jit_config.toml` | MODIFY | Add `[blizzard]` section, drop `max_pages_per_query`, update `levels` |
| `scripts/tests/test_blizzard.py` | NEW | OAuth flow, token cache, endpoint parsing, rate limit, retry |
| `scripts/tests/test_splits_synthesis.py` | NEW | Ratio collection, synthesis, cache, fallback |
| `scripts/tests/test_models.py` | MODIFY | Add `BlizzardRun` validation; update `ReferenceCell` (no affix) |
| `scripts/tests/test_config.py` | MODIFY | Add Blizzard config parsing tests |
| `scripts/tests/test_pipeline.py` | REWRITE | New flow: Blizzard discovery + ratio collection + aggregation |
| `scripts/tests/test_lua_renderer.py` | MODIFY | Schema v2 output assertions |
| `scripts/tests/test_cli.py` | MODIFY | Test missing-creds error handling |
| `scripts/tests/fixtures/blizzard_*.json` | NEW | Sample responses (token, period, dungeon, realm, leaderboard) |
| `addon/JustInTime/Overlay.lua` | MODIFY | Drop `[affixCombo]` lookup at 3 sites |
| `addon/JustInTime/Core.lua` | MODIFY | Add `checkSchema()` guard called from `OnLoad` |
| `addon/JustInTime/Locales.lua` | MODIFY | Add `OUTDATED_DATA`, `MISSING_DATA` keys (FR + EN) |
| `addon/JustInTime/JustInTime.toc` | MODIFY | Bump Version `0.3.4` → `0.4.0` |
| `addon/JustInTime/CHANGELOG.txt` | MODIFY | Add v0.4.0 entry |
| `addon/JustInTime/Data.lua` | REGEN | Output of `make data` after Python pipeline complete |

---

## Task overview

| # | Phase | Task | Test-first | Effort |
|---|---|---|---|---|
| 1 | A | Add `BlizzardConfig` dataclass + TOML parsing | yes | S |
| 2 | A | Update `[scope]` config (drop `max_pages_per_query`, default levels) | yes | XS |
| 3 | A | Add `BlizzardRun` + `BlizzardLeaderboard*` models | yes | S |
| 4 | A | Update `ReferenceCell` (drop `affix_combo`, add `splits_source`) | yes | S |
| 5 | B | `BlizzardClient` OAuth flow with token cache | yes | M |
| 6 | B | `BlizzardClient` Game Data endpoints | yes | M |
| 7 | C | `collect_observed_ratios()` — ratios from Raider.IO | yes | M |
| 8 | C | `synthesize_splits()` — apply ratios, equidistant fallback | yes | S |
| 9 | C | Disk cache for ratios (TTL 7d, key `(season, dungeon)`) | yes | S |
| 10 | D | `discover_runs()` — iterate region/realm/dungeon, accumulate by level | yes | M |
| 11 | D | Index real splits by `(dungeon, level)` from `/runs?page=0` | yes | S |
| 12 | D | `aggregate_cell()` — three-tier splits source selection | yes | M |
| 13 | D | `build_document_from_discovered()` + `merge_discovered()` | yes | M |
| 14 | E | `lua_renderer` schema v2 output | yes | S |
| 15 | F | CLI env-var loading + Blizzard client wiring + error UX | yes | S |
| 16 | G | `Overlay.lua` drop affix-combo lookup at 3 sites | manual | XS |
| 17 | G | `Core.lua` schema guard + `Locales.lua` keys | manual | S |
| 18 | G | `.toc` version bump + `CHANGELOG.txt` entry | manual | XS |
| 19 | H | Run `make data-dry` to validate flow | manual | XS |
| 20 | H | Run `make data` to regen `Data.lua`, verify schema v2 | manual | XS |
| 21 | H | UAT — load addon in WoW, verify pace at +15 (synth) and +18 (real) | manual | M |

Effort: XS = ≤5 min, S = 5-15 min, M = 15-45 min.

---

# Phase A — Configuration & models

### Task 1: Add `BlizzardConfig` dataclass + TOML parsing

**Files:**
- Modify: `scripts/jit_update/config.py`
- Modify: `scripts/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `scripts/tests/test_config.py`:

```python
def test_load_config_parses_blizzard_section(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[raiderio]
api_base = "https://raider.io/api/v1"
expansion_id = 11
season = "season-mn-1"
region = "world"
rate_per_minute = 300
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3

[blizzard]
regions = ["eu", "us"]
rate_per_second = 80
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3

[scope]
levels = [15, 16, 17, 18, 19, 20, 21, 22]
min_sample = 20
slowest_percentile = 10

[output]
data_lua_path = "../addon/JustInTime/Data.lua"
schema_version = 2
""")
    cfg = load_config(cfg_file)
    assert cfg.blizzard.regions == ["eu", "us"]
    assert cfg.blizzard.rate_per_second == 80
    assert cfg.blizzard.cache_ttl_seconds == 3600.0
    assert cfg.blizzard.timeout_seconds == 30.0
    assert cfg.blizzard.max_retries == 3
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd scripts && uv run pytest tests/test_config.py::test_load_config_parses_blizzard_section -v
```
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'blizzard'`.

- [ ] **Step 3: Add `BlizzardConfig` dataclass and wire it into `Config`**

In `scripts/jit_update/config.py`, after the `RaiderIOConfig` dataclass, add:

```python
@dataclass(frozen=True)
class BlizzardConfig:
    """Battle.net Game Data API connection and behaviour settings."""

    regions: list[str]
    rate_per_second: float
    cache_ttl_seconds: float
    timeout_seconds: float
    max_retries: int
```

Update the `Config` dataclass to include the new field:

```python
@dataclass(frozen=True)
class Config:
    """Top-level configuration object."""

    raiderio: RaiderIOConfig
    blizzard: BlizzardConfig
    scope: ScopeConfig
    output: OutputConfig
```

In `load_config()`, parse the `[blizzard]` section. Find the existing `raiderio` parsing block and add right after it:

```python
    blizzard_section = data.get("blizzard")
    if blizzard_section is None:
        raise ValueError(f"missing [blizzard] section in {path}")
    blizzard = BlizzardConfig(
        regions=list(blizzard_section["regions"]),
        rate_per_second=float(blizzard_section["rate_per_second"]),
        cache_ttl_seconds=float(blizzard_section["cache_ttl_seconds"]),
        timeout_seconds=float(blizzard_section["timeout_seconds"]),
        max_retries=int(blizzard_section["max_retries"]),
    )
```

Update the `Config(...)` constructor call at the end of `load_config()`:

```python
    return Config(raiderio=raiderio, blizzard=blizzard, scope=scope, output=output)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd scripts && uv run pytest tests/test_config.py::test_load_config_parses_blizzard_section -v
```
Expected: PASS.

- [ ] **Step 5: Run all config tests to confirm no regression**

```bash
cd scripts && uv run pytest tests/test_config.py -v
```
Expected: existing tests may fail because they predate `BlizzardConfig`. If so, update the existing fixture TOMLs in `tests/test_config.py` to include a `[blizzard]` section with default values matching this task's test, then re-run. Goal: all tests in `test_config.py` PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/config.py scripts/tests/test_config.py
git commit -m "✨ feat(config): add BlizzardConfig dataclass + TOML parsing

Adds a [blizzard] section to jit_config supporting OAuth client behaviour
(regions, rate, cache, timeout, retries). Fixture configs in existing
tests bumped to include the new section."
```

---

### Task 2: Update `[scope]` config — drop `max_pages_per_query`, set new default levels

**Files:**
- Modify: `scripts/jit_update/config.py`
- Modify: `scripts/jit_config.toml`
- Modify: `scripts/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `scripts/tests/test_config.py`:

```python
def test_scope_config_no_longer_has_max_pages_per_query(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[raiderio]
api_base = "https://raider.io/api/v1"
expansion_id = 11
season = "season-mn-1"
region = "world"
rate_per_minute = 300
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3

[blizzard]
regions = ["eu"]
rate_per_second = 80
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3

[scope]
levels = [15, 16, 17, 18, 19, 20, 21, 22]
min_sample = 20
slowest_percentile = 10

[output]
data_lua_path = "x"
schema_version = 2
""")
    cfg = load_config(cfg_file)
    assert cfg.scope.levels == [15, 16, 17, 18, 19, 20, 21, 22]
    assert not hasattr(cfg.scope, "max_pages_per_query")
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd scripts && uv run pytest tests/test_config.py::test_scope_config_no_longer_has_max_pages_per_query -v
```
Expected: FAIL — `ScopeConfig` still has `max_pages_per_query`.

- [ ] **Step 3: Update `ScopeConfig` and parsing**

In `scripts/jit_update/config.py`, modify `ScopeConfig`:

```python
@dataclass(frozen=True)
class ScopeConfig:
    """Keystone-level and sampling settings."""

    levels: list[int]
    min_sample: int
    slowest_percentile: int
```

Find the `scope = ScopeConfig(...)` call in `load_config()` and remove the `max_pages_per_query=...` argument so only the three remaining fields are passed.

- [ ] **Step 4: Update `scripts/jit_config.toml`**

Replace the `[scope]` section with:

```toml
[scope]
levels = [15, 16, 17, 18, 19, 20, 21, 22]
min_sample = 20
slowest_percentile = 10
```

And add a new `[blizzard]` section right after `[raiderio]`:

```toml
[blizzard]
regions = ["eu", "us"]
rate_per_second = 80
cache_ttl_seconds = 3600
timeout_seconds = 30.0
max_retries = 3
```

- [ ] **Step 5: Run tests**

```bash
cd scripts && uv run pytest tests/test_config.py -v
```
Expected: PASS.

If any other test (e.g. `test_pipeline.py`) references `max_pages_per_query` and now fails, leave it for Task 13 (pipeline rewrite). Add `pytestmark = pytest.mark.skip(reason="rewritten in Task 13")` at the top of `test_pipeline.py` if needed to unblock CI temporarily.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/config.py scripts/jit_config.toml scripts/tests/test_config.py
git commit -m "♻️ refactor(config): drop max_pages_per_query, set levels 15-22 default

Pagination is no longer the discovery mechanism (Blizzard returns full
leaderboards per realm/period). Default levels extended to 15-22 per
spec section 5.3."
```

---

### Task 3: Add `BlizzardRun` + `BlizzardLeaderboard*` models

**Files:**
- Modify: `scripts/jit_update/models.py`
- Modify: `scripts/tests/test_models.py`
- Create: `scripts/tests/fixtures/blizzard_leaderboard_sample.json`

- [ ] **Step 1: Create the fixture**

Save a real-shaped sample of the Blizzard leaderboard response. Create `scripts/tests/fixtures/blizzard_leaderboard_sample.json`:

```json
{
  "_links": {"self": {"href": "https://eu.api.blizzard.com/data/wow/connected-realm/1080/mythic-leaderboard/402/period/1062?namespace=dynamic-eu"}},
  "map": {"name": "Algeth'ar Academy", "id": 402},
  "period": 1062,
  "period_start_timestamp": 1778040000000,
  "period_end_timestamp": 1778644799000,
  "connected_realm": {"href": "https://eu.api.blizzard.com/data/wow/connected-realm/1080?namespace=dynamic-eu"},
  "leading_groups": [
    {
      "ranking": 1,
      "duration": 1816344,
      "completed_timestamp": 1778153301000,
      "keystone_level": 19,
      "members": [
        {"profile": {"name": "Alpha", "id": 100, "realm": {"id": 1335, "slug": "ysondre"}}, "faction": {"type": "HORDE"}, "specialization": {"id": 102}}
      ],
      "mythic_rating": {"color": {"r": 1.0, "g": 0.65, "b": 0.0, "a": 1.0}, "rating": 154.7}
    },
    {
      "ranking": 2,
      "duration": 1893221,
      "completed_timestamp": 1778153999000,
      "keystone_level": 16,
      "members": [
        {"profile": {"name": "Beta", "id": 101, "realm": {"id": 1335, "slug": "ysondre"}}, "faction": {"type": "ALLIANCE"}, "specialization": {"id": 252}}
      ]
    },
    {
      "ranking": 3,
      "duration": 2103556,
      "completed_timestamp": 1778160000000,
      "keystone_level": 15,
      "members": [
        {"profile": {"name": "Gamma", "id": 102, "realm": {"id": 1336, "slug": "outland"}}, "faction": {"type": "HORDE"}, "specialization": {"id": 264}}
      ]
    }
  ],
  "keystone_affixes": [{"id": 9, "name": "Tyrannical"}, {"id": 10, "name": "Fortified"}],
  "map_challenge_mode_id": 402,
  "name": "Algeth'ar Academy"
}
```

- [ ] **Step 2: Write the failing test**

Add to `scripts/tests/test_models.py`:

```python
import json
from pathlib import Path

from jit_update.models import BlizzardLeaderboardResponse, BlizzardRun


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_blizzard_leaderboard_response_parses_sample():
    raw = json.loads((FIXTURE_DIR / "blizzard_leaderboard_sample.json").read_text())
    parsed = BlizzardLeaderboardResponse.model_validate(raw)
    assert parsed.map_challenge_mode_id == 402
    assert parsed.period == 1062
    assert len(parsed.leading_groups) == 3


def test_blizzard_run_extracts_keystone_level_and_duration():
    raw = json.loads((FIXTURE_DIR / "blizzard_leaderboard_sample.json").read_text())
    parsed = BlizzardLeaderboardResponse.model_validate(raw)
    runs = [BlizzardRun.from_group(g, dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062) for g in parsed.leading_groups]
    assert {r.keystone_level for r in runs} == {15, 16, 19}
    assert {r.duration_ms for r in runs} == {1816344, 1893221, 2103556}
    assert all(r.dungeon_slug == "algethar-academy" for r in runs)
    assert all(r.region == "eu" for r in runs)
```

- [ ] **Step 3: Run test, expect failure**

```bash
cd scripts && uv run pytest tests/test_models.py::test_blizzard_leaderboard_response_parses_sample tests/test_models.py::test_blizzard_run_extracts_keystone_level_and_duration -v
```
Expected: FAIL — `ImportError: cannot import name 'BlizzardLeaderboardResponse'`.

- [ ] **Step 4: Add the models**

Append to `scripts/jit_update/models.py`:

```python
class BlizzardMember(BaseModel):
    """A single character in a Blizzard mythic-keystone-leaderboard group."""

    model_config = ConfigDict(extra="ignore")

    profile: dict
    faction: dict | None = None
    specialization: dict | None = None


class BlizzardLeadingGroup(BaseModel):
    """One ranked group from /mythic-leaderboard/.../leading_groups."""

    model_config = ConfigDict(extra="ignore")

    ranking: int
    duration: int
    completed_timestamp: int
    keystone_level: int
    members: list[BlizzardMember] = Field(default_factory=list)
    mythic_rating: dict | None = None


class BlizzardLeaderboardResponse(BaseModel):
    """Full payload of a Blizzard mythic-keystone-leaderboard response."""

    model_config = ConfigDict(extra="ignore")

    period: int
    period_start_timestamp: int
    period_end_timestamp: int
    leading_groups: list[BlizzardLeadingGroup] = Field(default_factory=list)
    map_challenge_mode_id: int
    name: str


class BlizzardRun(BaseModel):
    """A normalized Mythic+ run discovered via Blizzard API.

    Decoupled from BlizzardLeadingGroup so the pipeline can carry the dungeon /
    region / realm / period context that the raw payload omits.
    """

    model_config = ConfigDict(extra="ignore")

    dungeon_slug: str
    region: str
    realm_id: int
    period: int
    keystone_level: int
    duration_ms: int
    completed_timestamp: int

    @classmethod
    def from_group(
        cls,
        group: BlizzardLeadingGroup | dict,
        *,
        dungeon_slug: str,
        region: str,
        realm_id: int,
        period: int,
    ) -> "BlizzardRun":
        """Build a BlizzardRun from a leading_groups entry plus context."""
        if isinstance(group, dict):
            group = BlizzardLeadingGroup.model_validate(group)
        return cls(
            dungeon_slug=dungeon_slug,
            region=region,
            realm_id=realm_id,
            period=period,
            keystone_level=group.keystone_level,
            duration_ms=group.duration,
            completed_timestamp=group.completed_timestamp,
        )
```

- [ ] **Step 5: Run tests**

```bash
cd scripts && uv run pytest tests/test_models.py -v
```
Expected: new tests PASS, existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/models.py scripts/tests/test_models.py scripts/tests/fixtures/blizzard_leaderboard_sample.json
git commit -m "✨ feat(models): add BlizzardRun + leaderboard response models

New models cover the Game Data /mythic-leaderboard payload and a
normalized BlizzardRun that carries the dungeon/region/realm/period
context the raw Blizzard JSON omits. Fixture from a real EU/Algeth'ar
period 1062 sample (truncated to 3 groups)."
```

---

### Task 4: Update `ReferenceCell` — drop `affix_combo`, add `splits_source`

**Files:**
- Modify: `scripts/jit_update/models.py`
- Modify: `scripts/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `scripts/tests/test_models.py`:

```python
from jit_update.models import ReferenceCell


def test_reference_cell_has_splits_source_field():
    cell = ReferenceCell(
        sample_size=10,
        clear_time_ms=1700000,
        boss_splits_ms=[425000, 850000, 1275000, 1700000],
        splits_source="raiderio",
    )
    assert cell.splits_source == "raiderio"


def test_reference_cell_accepts_synthesized_source():
    cell = ReferenceCell(
        sample_size=5,
        clear_time_ms=1850000,
        boss_splits_ms=[462500, 925000, 1387500, 1850000],
        splits_source="synthesized",
    )
    assert cell.splits_source == "synthesized"


def test_reference_cell_rejects_unknown_source():
    import pytest
    with pytest.raises(Exception):  # pydantic ValidationError
        ReferenceCell(
            sample_size=5,
            clear_time_ms=1850000,
            boss_splits_ms=[1, 2, 3, 4],
            splits_source="bogus",
        )
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd scripts && uv run pytest tests/test_models.py::test_reference_cell_has_splits_source_field tests/test_models.py::test_reference_cell_accepts_synthesized_source tests/test_models.py::test_reference_cell_rejects_unknown_source -v
```
Expected: FAIL — `ReferenceCell` has no `splits_source` field.

- [ ] **Step 3: Modify `ReferenceCell`**

In `scripts/jit_update/models.py`, find the `ReferenceCell` class and replace it with:

```python
from typing import Literal


class ReferenceCell(BaseModel):
    """One cell of the reference table: (dungeon, level) -> splits.

    This is what gets serialized into Data.lua per (dungeon x level).
    The affix dimension was removed in schema v2 — see spec section 5.
    """

    model_config = ConfigDict(extra="ignore")

    sample_size: int
    clear_time_ms: int
    boss_splits_ms: list[int]
    splits_source: Literal["raiderio", "synthesized", "equidistant_fallback"]
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_models.py -v
```
Expected: PASS for the three new tests. If existing tests use `affix_combo` field on `ReferenceCell`, they will fail — those usages are scoped to `pipeline.py` / `lua_renderer.py` which are rewritten in later tasks. Search the test file:

```bash
cd scripts && grep -n "affix_combo\|ReferenceCell" tests/test_models.py
```

If existing `test_models.py` references `affix_combo` on `ReferenceCell`, delete those lines (they test the v1 schema we're replacing). Re-run.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/models.py scripts/tests/test_models.py
git commit -m "♻️ refactor(models): drop affix_combo from ReferenceCell, add splits_source

Schema v2 removes the per-affix-combo nesting from Data.lua (the addon
ignores the dimension in practice). splits_source documents how the
boss_splits were obtained: raiderio / synthesized / equidistant_fallback."
```

---

# Phase B — Blizzard client

### Task 5: `BlizzardClient` OAuth flow with token cache

**Files:**
- Create: `scripts/jit_update/blizzard.py`
- Create: `scripts/tests/test_blizzard.py`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_blizzard.py`:

```python
"""Tests for BlizzardClient OAuth + Game Data endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from jit_update.blizzard import BlizzardClient, BlizzardError
from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def cache(tmp_path):
    return FileCache(tmp_path / "cache")


@pytest.fixture
def rate_limiter():
    return RateLimiter(rate_per_second=1000.0)  # effectively no limit in tests


@pytest.fixture
def client(cache, rate_limiter):
    return BlizzardClient(
        client_id="test_id",
        client_secret="test_secret",
        region="eu",
        cache=cache,
        rate_limiter=rate_limiter,
    )


@respx.mock
def test_client_obtains_oauth_token_on_first_call(client):
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok_123", "expires_in": 86400, "token_type": "bearer"})
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        return_value=httpx.Response(200, json={"current_period": {"id": 1062}, "periods": []})
    )
    period_id = client.get_current_period_id()
    assert period_id == 1062


@respx.mock
def test_client_caches_token_between_calls(client):
    token_route = respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok_456", "expires_in": 86400, "token_type": "bearer"})
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        return_value=httpx.Response(200, json={"current_period": {"id": 1062}, "periods": []})
    )
    client.get_current_period_id()
    client.get_current_period_id()
    # Token call only once even though we hit two endpoints
    assert token_route.call_count == 1


@respx.mock
def test_client_refreshes_token_on_401(client):
    token_calls = respx.post("https://oauth.battle.net/token").mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "stale", "expires_in": 86400, "token_type": "bearer"}),
            httpx.Response(200, json={"access_token": "fresh", "expires_in": 86400, "token_type": "bearer"}),
        ]
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        side_effect=[
            httpx.Response(401, json={"error": "unauthorized"}),
            httpx.Response(200, json={"current_period": {"id": 1062}, "periods": []}),
        ]
    )
    period_id = client.get_current_period_id()
    assert period_id == 1062
    assert token_calls.call_count == 2


@respx.mock
def test_client_raises_on_repeated_401(client):
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 86400, "token_type": "bearer"})
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/period/index").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    with pytest.raises(BlizzardError, match="unauthorized"):
        client.get_current_period_id()
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_blizzard.py -v
```
Expected: FAIL with `ImportError: No module named 'jit_update.blizzard'`.

- [ ] **Step 3: Create `BlizzardClient` skeleton**

Create `scripts/jit_update/blizzard.py`:

```python
"""HTTP client for Battle.net Game Data API (mythic-keystone-leaderboard)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter


class BlizzardError(RuntimeError):
    """Raised when Battle.net responds with an unrecoverable error."""


REGION_BASE_URLS = {
    "us": "https://us.api.blizzard.com",
    "eu": "https://eu.api.blizzard.com",
    "kr": "https://kr.api.blizzard.com",
    "tw": "https://tw.api.blizzard.com",
}

OAUTH_TOKEN_URL = "https://oauth.battle.net/token"
TOKEN_TTL_BUFFER_SECONDS = 3600  # refresh 1h before stated expiry


class BlizzardClient:
    """Battle.net Game Data API client with OAuth + cache + rate limit + retry.

    Read-only. Token is cached in memory + disk for 23h.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        region: str,
        cache: FileCache,
        rate_limiter: RateLimiter,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        if region not in REGION_BASE_URLS:
            raise ValueError(f"unsupported region {region!r}; expected one of {list(REGION_BASE_URLS)}")
        self._client_id = client_id
        self._client_secret = client_secret
        self._region = region
        self._namespace = f"dynamic-{region}"
        self._base = REGION_BASE_URLS[region]
        self._cache = cache
        self._rl = rate_limiter
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(timeout=timeout_seconds)

    def _ensure_token(self, force_refresh: bool = False) -> str:
        now = time.time()
        if not force_refresh and self._token and now < self._token_expires_at:
            return self._token
        # Cache check (disk)
        cache_key = f"blizzard/oauth_token_{self._client_id}"
        cached = self._cache.get(cache_key) if not force_refresh else None
        if cached and isinstance(cached, dict) and cached.get("expires_at", 0) > now:
            self._token = cached["token"]
            self._token_expires_at = cached["expires_at"]
            return self._token
        # Request new token
        resp = self._http.post(
            OAUTH_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
        )
        if resp.status_code != 200:
            raise BlizzardError(
                f"OAuth token request failed: status={resp.status_code} body={resp.text[:200]}"
            )
        payload = resp.json()
        token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 86400))
        expires_at = now + max(60, expires_in - TOKEN_TTL_BUFFER_SECONDS)
        self._token = token
        self._token_expires_at = expires_at
        self._cache.set(cache_key, {"token": token, "expires_at": expires_at})
        return token

    def _request_json(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """GET a Game Data endpoint with token + namespace + retry on 401."""
        params = dict(params or {})
        params.setdefault("namespace", self._namespace)
        params.setdefault("locale", "en_US")
        url = f"{self._base}{path}"
        attempted_refresh = False
        for attempt in range(self._max_retries + 1):
            self._rl.acquire()
            token = self._ensure_token(force_refresh=False)
            resp = self._http.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401 and not attempted_refresh:
                self._ensure_token(force_refresh=True)
                attempted_refresh = True
                continue
            if resp.status_code in (429, 503):
                if attempt < self._max_retries:
                    time.sleep(2 ** attempt)
                    continue
            raise BlizzardError(
                f"Battle.net request failed: GET {url} status={resp.status_code} body={resp.text[:200]}"
            )
        raise BlizzardError(f"Battle.net request exhausted retries: GET {url}")

    def get_current_period_id(self) -> int:
        """Return the current Mythic+ period ID for the configured region."""
        payload = self._request_json("/data/wow/mythic-keystone/period/index")
        period = payload.get("current_period")
        if not isinstance(period, dict) or "id" not in period:
            raise BlizzardError(f"unexpected /period/index payload: {payload!r}")
        return int(period["id"])

    def close(self) -> None:
        self._http.close()
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_blizzard.py -v
```
Expected: PASS for all four tests in this task.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/blizzard.py scripts/tests/test_blizzard.py
git commit -m "✨ feat(blizzard): add OAuth client_credentials flow with token cache

BlizzardClient.get_current_period_id() exercises the OAuth round-trip
and the GET-with-token wrapper. Token cached in memory + on disk (23h
effective TTL after a 1h safety buffer). 401 triggers a single force-
refresh + retry; further failures surface as BlizzardError."
```

---

### Task 6: `BlizzardClient` Game Data endpoints — dungeons, realms, leaderboard

**Files:**
- Modify: `scripts/jit_update/blizzard.py`
- Modify: `scripts/tests/test_blizzard.py`

- [ ] **Step 1: Write failing tests**

Append to `scripts/tests/test_blizzard.py`:

```python
@respx.mock
def test_get_connected_realms_index_returns_realm_ids(client):
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 86400})
    )
    respx.get("https://eu.api.blizzard.com/data/wow/connected-realm/index").mock(
        return_value=httpx.Response(200, json={
            "connected_realms": [
                {"href": "https://eu.api.blizzard.com/data/wow/connected-realm/1080?namespace=dynamic-eu"},
                {"href": "https://eu.api.blizzard.com/data/wow/connected-realm/1084?namespace=dynamic-eu"},
            ]
        })
    )
    realms = client.get_connected_realms_index()
    assert realms == [1080, 1084]


@respx.mock
def test_get_dungeons_index_returns_id_to_name_mapping(client):
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 86400})
    )
    respx.get("https://eu.api.blizzard.com/data/wow/mythic-keystone/dungeon/index").mock(
        return_value=httpx.Response(200, json={
            "dungeons": [
                {"id": 402, "name": "Algeth'ar Academy"},
                {"id": 499, "name": "Priory of the Sacred Flame"},
                {"id": 500, "name": "The Rookery"},
            ]
        })
    )
    mapping = client.get_dungeons_index()
    assert mapping == {402: "Algeth'ar Academy", 499: "Priory of the Sacred Flame", 500: "The Rookery"}


@respx.mock
def test_get_leaderboard_parses_leading_groups(client):
    sample = json.loads((FIXTURE_DIR / "blizzard_leaderboard_sample.json").read_text())
    respx.post("https://oauth.battle.net/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 86400})
    )
    respx.get("https://eu.api.blizzard.com/data/wow/connected-realm/1080/mythic-leaderboard/402/period/1062").mock(
        return_value=httpx.Response(200, json=sample)
    )
    runs = client.get_leaderboard_runs(realm_id=1080, dungeon_id=402, period_id=1062, dungeon_slug="algethar-academy")
    assert len(runs) == 3
    assert {r.keystone_level for r in runs} == {15, 16, 19}
    assert all(r.realm_id == 1080 and r.region == "eu" for r in runs)
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_blizzard.py -v -k "connected_realms or dungeons_index or leaderboard"
```
Expected: FAIL — those methods are not yet defined.

- [ ] **Step 3: Add the endpoint methods**

In `scripts/jit_update/blizzard.py`, after `get_current_period_id`, add:

```python
    def get_connected_realms_index(self) -> list[int]:
        """Return all connected-realm IDs for the configured region."""
        import re

        payload = self._request_json("/data/wow/connected-realm/index")
        result: list[int] = []
        for item in payload.get("connected_realms", []):
            href = item.get("href", "")
            m = re.search(r"/connected-realm/(\d+)", href)
            if m:
                result.append(int(m.group(1)))
        return result

    def get_dungeons_index(self) -> dict[int, str]:
        """Return mapping dungeon_id -> dungeon name (English)."""
        payload = self._request_json("/data/wow/mythic-keystone/dungeon/index")
        return {int(d["id"]): d["name"] for d in payload.get("dungeons", []) if "id" in d and "name" in d}

    def get_leaderboard_runs(
        self,
        *,
        realm_id: int,
        dungeon_id: int,
        period_id: int,
        dungeon_slug: str,
    ) -> list["BlizzardRun"]:
        """Return normalized BlizzardRun objects from one realm/dungeon/period leaderboard."""
        from jit_update.models import BlizzardLeaderboardResponse, BlizzardRun

        path = f"/data/wow/connected-realm/{realm_id}/mythic-leaderboard/{dungeon_id}/period/{period_id}"
        payload = self._request_json(path)
        parsed = BlizzardLeaderboardResponse.model_validate(payload)
        return [
            BlizzardRun.from_group(g, dungeon_slug=dungeon_slug, region=self._region, realm_id=realm_id, period=period_id)
            for g in parsed.leading_groups
        ]
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_blizzard.py -v
```
Expected: PASS for all tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/blizzard.py scripts/tests/test_blizzard.py
git commit -m "✨ feat(blizzard): add dungeon/realm/leaderboard endpoints

Three Game Data endpoints to drive the discovery flow: connected-realm
index, mythic-keystone dungeon index, and the leaderboard itself which
returns normalized BlizzardRun objects (not raw payloads) so the
pipeline doesn't have to know about response shape."
```

---

# Phase C — Splits synthesis

### Task 7: `collect_observed_ratios()` — ratios from Raider.IO

**Files:**
- Create: `scripts/jit_update/splits_synthesis.py`
- Create: `scripts/tests/test_splits_synthesis.py`
- Create: `scripts/tests/fixtures/raiderio_run_details_with_splits.json`
- Create: `scripts/tests/fixtures/raiderio_run_details_no_splits.json`

- [ ] **Step 1: Create the fixtures**

Create `scripts/tests/fixtures/raiderio_run_details_with_splits.json` (a real-shaped /run-details with logged_details.encounters populated):

```json
{
  "season": "season-mn-1",
  "status": "finished",
  "keystone_run_id": 20945824,
  "mythic_level": 22,
  "clear_time_ms": 1700000,
  "keystone_time_ms": 1860999,
  "completed_at": "2026-05-03T07:33:46.051Z",
  "logged_run_id": 5941968,
  "logged_details": {
    "encounters": [
      {
        "id": 1,
        "status": "finished",
        "duration_ms": 425000,
        "is_success": true,
        "approximate_relative_started_at": 0,
        "approximate_relative_ended_at": 425000,
        "boss": {"encounterId": 1, "wowEncounterId": 2563, "name": "Boss A", "slug": "boss-a", "ordinal": 0}
      },
      {
        "id": 2,
        "status": "finished",
        "duration_ms": 425000,
        "is_success": true,
        "approximate_relative_started_at": 425000,
        "approximate_relative_ended_at": 850000,
        "boss": {"encounterId": 2, "wowEncounterId": 2564, "name": "Boss B", "slug": "boss-b", "ordinal": 1}
      },
      {
        "id": 3,
        "status": "finished",
        "duration_ms": 425000,
        "is_success": true,
        "approximate_relative_started_at": 850000,
        "approximate_relative_ended_at": 1275000,
        "boss": {"encounterId": 3, "wowEncounterId": 2565, "name": "Boss C", "slug": "boss-c", "ordinal": 2}
      },
      {
        "id": 4,
        "status": "finished",
        "duration_ms": 425000,
        "is_success": true,
        "approximate_relative_started_at": 1275000,
        "approximate_relative_ended_at": 1700000,
        "boss": {"encounterId": 4, "wowEncounterId": 2566, "name": "Boss D", "slug": "boss-d", "ordinal": 3}
      }
    ]
  }
}
```

Create `scripts/tests/fixtures/raiderio_run_details_no_splits.json`:

```json
{
  "season": "season-mn-1",
  "status": "finished",
  "keystone_run_id": 22426791,
  "mythic_level": 22,
  "clear_time_ms": 1774898,
  "keystone_time_ms": 1860999,
  "completed_at": "2026-05-06T17:09:31.000Z",
  "logged_run_id": null,
  "logged_details": null
}
```

- [ ] **Step 2: Write failing tests**

Create `scripts/tests/test_splits_synthesis.py`:

```python
"""Tests for collect_observed_ratios + synthesize_splits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jit_update.splits_synthesis import collect_observed_ratios, synthesize_splits


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class StubRaiderIO:
    """Minimal stub matching the methods collect_observed_ratios calls."""

    def __init__(self, runs_payload: dict, details_by_id: dict[int, dict]):
        self._runs_payload = runs_payload
        self._details_by_id = details_by_id

    def get_runs(self, season, region, dungeon, page, affixes="all"):
        return self._runs_payload

    def get_run_details(self, season, run_id):
        return self._details_by_id[run_id]


def test_collect_observed_ratios_returns_per_ordinal_medians():
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    runs_payload = {
        "rankings": [
            {"run": {"keystone_run_id": 20945824}},
            {"run": {"keystone_run_id": 20945825}},
        ]
    }
    # Two identical runs — median = expected ratios
    details_by_id = {
        20945824: splits,
        20945825: splits,
    }
    stub = StubRaiderIO(runs_payload, details_by_id)
    ratios = collect_observed_ratios(stub, "season-mn-1", "algethar-academy", num_bosses=4)
    # clear_time = 1700000, ends at 425k/850k/1.275M/1.7M → ratios 0.25/0.5/0.75/1.0
    assert len(ratios) == 4
    assert ratios[0] == pytest.approx(0.25, abs=0.001)
    assert ratios[1] == pytest.approx(0.5, abs=0.001)
    assert ratios[2] == pytest.approx(0.75, abs=0.001)
    assert ratios[3] == pytest.approx(1.0, abs=0.001)


def test_collect_observed_ratios_skips_runs_without_logged_encounters():
    no_splits = json.loads((FIXTURE_DIR / "raiderio_run_details_no_splits.json").read_text())
    runs_payload = {"rankings": [{"run": {"keystone_run_id": 22426791}}]}
    stub = StubRaiderIO(runs_payload, {22426791: no_splits})
    ratios = collect_observed_ratios(stub, "season-mn-1", "algethar-academy", num_bosses=4)
    assert ratios == [None, None, None, None]


def test_collect_observed_ratios_handles_partial_coverage():
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    no_splits = json.loads((FIXTURE_DIR / "raiderio_run_details_no_splits.json").read_text())
    runs_payload = {
        "rankings": [
            {"run": {"keystone_run_id": 20945824}},
            {"run": {"keystone_run_id": 22426791}},
        ]
    }
    stub = StubRaiderIO(runs_payload, {20945824: splits, 22426791: no_splits})
    ratios = collect_observed_ratios(stub, "season-mn-1", "algethar-academy", num_bosses=4)
    # Only one run with splits, so each ordinal has a single sample
    assert all(r is not None for r in ratios)
```

- [ ] **Step 3: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_splits_synthesis.py -v
```
Expected: FAIL with `ImportError: No module named 'jit_update.splits_synthesis'`.

- [ ] **Step 4: Implement `collect_observed_ratios`**

Create `scripts/jit_update/splits_synthesis.py`:

```python
"""Boss splits synthesis: observed-ratio collection + extrapolation."""

from __future__ import annotations

import statistics
from typing import Protocol

from jit_update.models import RunDetails


class RaiderIOLike(Protocol):
    """Subset of RaiderIOClient used by ratio collection."""

    def get_runs(self, season: str, region: str, dungeon: str, page: int, affixes: str = "all") -> dict: ...
    def get_run_details(self, season: str, run_id: int) -> dict: ...


def collect_observed_ratios(
    client: RaiderIOLike,
    season: str,
    dungeon_slug: str,
    num_bosses: int,
) -> list[float | None]:
    """Compute median boss-split ratios for one dungeon from Raider.IO top-page runs.

    Returns a list of length ``num_bosses``. Each element is the median value of
    ``boss_splits_ms[i] / clear_time_ms`` across runs whose ``logged_details``
    contains successful encounter timings, or ``None`` if no run yielded a value
    at that ordinal.
    """
    runs_payload = client.get_runs(season=season, region="world", dungeon=dungeon_slug, page=0)
    samples_per_ordinal: list[list[float]] = [[] for _ in range(num_bosses)]

    for r in runs_payload.get("rankings", []):
        run = r.get("run", {})
        run_id = run.get("keystone_run_id")
        if run_id is None:
            continue
        details_raw = client.get_run_details(season=season, run_id=run_id)
        try:
            details = RunDetails.model_validate(details_raw)
        except Exception:
            continue
        if not details.encounters:
            continue
        clear_time = details.clear_time_ms
        if clear_time <= 0:
            continue
        for i, split in enumerate(details.boss_splits_ms()):
            if i >= num_bosses:
                break
            if split is None:
                continue
            if split <= 0 or split > clear_time * 1.05:  # tolerance 5 %
                continue
            samples_per_ordinal[i].append(split / clear_time)

    return [statistics.median(samples) if samples else None for samples in samples_per_ordinal]
```

- [ ] **Step 5: Run tests**

```bash
cd scripts && uv run pytest tests/test_splits_synthesis.py -v
```
Expected: PASS for the three tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/splits_synthesis.py scripts/tests/test_splits_synthesis.py scripts/tests/fixtures/raiderio_run_details_with_splits.json scripts/tests/fixtures/raiderio_run_details_no_splits.json
git commit -m "✨ feat(splits): collect_observed_ratios from Raider.IO logged runs

For each dungeon, query /runs?page=0 (top 20 ranked runs), call
/run-details, and median the boss_splits_ms / clear_time ratios per
boss ordinal. Returns None at ordinals with no observed data so the
caller can fall back to equidistant splits."
```

---

### Task 8: `synthesize_splits()` — apply ratios, equidistant fallback

**Files:**
- Modify: `scripts/jit_update/splits_synthesis.py`
- Modify: `scripts/tests/test_splits_synthesis.py`

- [ ] **Step 1: Write failing tests**

Append to `scripts/tests/test_splits_synthesis.py`:

```python
def test_synthesize_splits_applies_ratios():
    ratios = [0.25, 0.5, 0.75, 1.0]
    result = synthesize_splits(clear_time_ms=1850000, ratios=ratios, num_bosses=4)
    assert result == [462500, 925000, 1387500, 1850000]


def test_synthesize_splits_falls_back_to_equidistant_when_all_none():
    result = synthesize_splits(clear_time_ms=1800000, ratios=[None, None, None, None], num_bosses=4)
    # Equidistant: 1/4, 2/4, 3/4, 4/4 of clear_time
    assert result == [450000, 900000, 1350000, 1800000]


def test_synthesize_splits_uses_equidistant_for_missing_ordinals_when_some_present():
    ratios = [0.25, None, 0.75, 1.0]
    result = synthesize_splits(clear_time_ms=1800000, ratios=ratios, num_bosses=4)
    assert result[0] == 450000  # 0.25 * 1.8M
    assert result[1] == 900000  # equidistant: 2/4 * 1.8M
    assert result[2] == 1350000  # 0.75 * 1.8M
    assert result[3] == 1800000  # 1.0 * 1.8M


def test_synthesize_splits_rounds_to_int():
    ratios = [0.333, 0.666, 1.0]
    result = synthesize_splits(clear_time_ms=1000000, ratios=ratios, num_bosses=3)
    assert all(isinstance(v, int) for v in result)
    assert result == [333000, 666000, 1000000]
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_splits_synthesis.py -v -k "synthesize"
```
Expected: FAIL — `synthesize_splits` not defined.

- [ ] **Step 3: Implement `synthesize_splits`**

Append to `scripts/jit_update/splits_synthesis.py`:

```python
def synthesize_splits(
    clear_time_ms: int,
    ratios: list[float | None],
    num_bosses: int,
) -> list[int]:
    """Build per-boss cumulative split times from clear_time and observed ratios.

    Args:
        clear_time_ms: Total clear time of the run in milliseconds.
        ratios:        Length ``num_bosses`` list of float ratios in [0, 1] or
                       ``None`` at positions without observed data.
        num_bosses:    Expected number of bosses (in case ``ratios`` is shorter).

    Returns:
        ``num_bosses`` ints. For positions where ``ratios[i]`` is a float,
        ``round(clear_time_ms * ratios[i])``. For ``None`` positions,
        equidistant fallback ``round(clear_time_ms * (i+1) / num_bosses)``.
    """
    padded = list(ratios) + [None] * max(0, num_bosses - len(ratios))
    result: list[int] = []
    for i in range(num_bosses):
        r = padded[i]
        if r is None:
            result.append(round(clear_time_ms * (i + 1) / num_bosses))
        else:
            result.append(round(clear_time_ms * r))
    return result
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_splits_synthesis.py -v
```
Expected: PASS for all `synthesize_splits` tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/splits_synthesis.py scripts/tests/test_splits_synthesis.py
git commit -m "✨ feat(splits): synthesize_splits applies ratios with equidistant fallback

Per-ordinal: round(clear_time * ratio) where ratio is observed; else
equidistant round(clear_time * (i+1) / num_bosses). All-None ratios
list yields a fully equidistant ladder anchored to clear_time."
```

---

### Task 9: Disk cache for ratios — TTL 7 days, key `(season, dungeon)`

**Files:**
- Modify: `scripts/jit_update/splits_synthesis.py`
- Modify: `scripts/tests/test_splits_synthesis.py`

- [ ] **Step 1: Write failing tests**

Append to `scripts/tests/test_splits_synthesis.py`:

```python
from jit_update.cache import FileCache
from jit_update.splits_synthesis import collect_observed_ratios_cached


def test_collect_observed_ratios_cached_serves_cache_on_second_call(tmp_path):
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    runs_payload = {"rankings": [{"run": {"keystone_run_id": 20945824}}]}
    stub = StubRaiderIO(runs_payload, {20945824: splits})
    # Track call count via subclass
    calls = {"runs": 0, "details": 0}

    class CountingStub(StubRaiderIO):
        def get_runs(self, *a, **kw):
            calls["runs"] += 1
            return super().get_runs(*a, **kw)

        def get_run_details(self, *a, **kw):
            calls["details"] += 1
            return super().get_run_details(*a, **kw)

    counting = CountingStub(runs_payload, {20945824: splits})
    cache = FileCache(tmp_path / "cache")

    ratios_1 = collect_observed_ratios_cached(counting, cache, "season-mn-1", "algethar-academy", num_bosses=4)
    ratios_2 = collect_observed_ratios_cached(counting, cache, "season-mn-1", "algethar-academy", num_bosses=4)

    assert ratios_1 == ratios_2
    assert calls["runs"] == 1
    assert calls["details"] == 1


def test_collect_observed_ratios_cached_uses_separate_keys_per_dungeon(tmp_path):
    splits = json.loads((FIXTURE_DIR / "raiderio_run_details_with_splits.json").read_text())
    runs_payload = {"rankings": [{"run": {"keystone_run_id": 20945824}}]}
    cache = FileCache(tmp_path / "cache")
    stub = StubRaiderIO(runs_payload, {20945824: splits})

    r1 = collect_observed_ratios_cached(stub, cache, "season-mn-1", "algethar-academy", num_bosses=4)
    r2 = collect_observed_ratios_cached(stub, cache, "season-mn-1", "the-rookery", num_bosses=4)

    # Both compute, both cached, no cross-contamination
    assert r1 == r2  # same data in stub
    # Sanity: cache has two keys
    assert len(list((tmp_path / "cache").rglob("*"))) >= 2
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_splits_synthesis.py -v -k "cached"
```
Expected: FAIL — `collect_observed_ratios_cached` not defined.

- [ ] **Step 3: Implement cached wrapper**

Append to `scripts/jit_update/splits_synthesis.py`:

```python
RATIOS_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def collect_observed_ratios_cached(
    client: RaiderIOLike,
    cache,  # FileCache, kept generic to avoid circular import
    season: str,
    dungeon_slug: str,
    num_bosses: int,
) -> list[float | None]:
    """Same as ``collect_observed_ratios`` but caches the result on disk for 7 days.

    Cache key: ``ratios/<season>/<dungeon_slug>``. Hit returns the cached list
    untouched. Miss recomputes and writes through.
    """
    key = f"ratios/{season}/{dungeon_slug}"
    cached = cache.get(key)
    if cached is not None and isinstance(cached, list):
        return cached
    ratios = collect_observed_ratios(client, season, dungeon_slug, num_bosses)
    cache.set(key, ratios, ttl_seconds=RATIOS_CACHE_TTL_SECONDS)
    return ratios
```

If the existing `FileCache.set()` doesn't accept a `ttl_seconds` argument, check the existing API:

```bash
grep -n "def set\|ttl_seconds\|expires" scripts/jit_update/cache.py
```

If `FileCache` does not support per-key TTL, **add it** as a separate task — but for now, assume it does. If the existing implementation only supports a single global TTL, replace the `cache.set(key, ratios, ttl_seconds=...)` line with `cache.set(key, ratios)` and document the limitation in a code comment:

```python
    # FileCache uses the global TTL configured at construction. The pipeline
    # passes a 7-day TTL FileCache instance for ratios; see pipeline.py.
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_splits_synthesis.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/splits_synthesis.py scripts/tests/test_splits_synthesis.py
git commit -m "✨ feat(splits): disk-cached observed ratios with 7-day TTL

Routes within a season don't change, so ratio collection happens at
most once per week per (season, dungeon). Cache key namespaced under
ratios/ to avoid colliding with HTTP cache."
```

---

# Phase D — Pipeline refactor

### Task 10: `discover_runs()` — iterate region/realm/dungeon, accumulate by level

**Files:**
- Modify: `scripts/jit_update/pipeline.py`
- Modify: `scripts/tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

If `test_pipeline.py` is currently skipped (per Task 2 step 5), unskip it and replace its content with this new file:

```python
"""Tests for the rewritten pipeline (Blizzard discovery + synthesis)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from jit_update.models import BlizzardRun


class StubBlizzardClient:
    """Fakes BlizzardClient for pipeline testing."""

    def __init__(self, period_id: int, realm_ids: list[int], runs_by_realm_dungeon: dict[tuple[int, int], list[BlizzardRun]]):
        self._period_id = period_id
        self._realm_ids = realm_ids
        self._runs = runs_by_realm_dungeon
        self.calls: list[tuple[int, int]] = []

    def get_current_period_id(self) -> int:
        return self._period_id

    def get_connected_realms_index(self) -> list[int]:
        return self._realm_ids

    def get_leaderboard_runs(self, *, realm_id, dungeon_id, period_id, dungeon_slug):
        self.calls.append((realm_id, dungeon_id))
        return self._runs.get((realm_id, dungeon_id), [])


def test_discover_runs_aggregates_by_dungeon_and_level():
    from jit_update.pipeline import discover_runs

    run_a_19 = BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062, keystone_level=19, duration_ms=1816344, completed_timestamp=1)
    run_a_15 = BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062, keystone_level=15, duration_ms=2103556, completed_timestamp=2)
    run_a_15_b = BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1084, period=1062, keystone_level=15, duration_ms=2200000, completed_timestamp=3)
    runs_by_realm = {
        (1080, 402): [run_a_19, run_a_15],
        (1084, 402): [run_a_15_b],
    }
    blizz = StubBlizzardClient(period_id=1062, realm_ids=[1080, 1084], runs_by_realm_dungeon=runs_by_realm)
    dungeons = [{"slug": "algethar-academy", "map_challenge_mode_id": 402}]

    result = discover_runs(blizz, dungeons=dungeons, levels=[15, 19])

    assert set(result.keys()) == {"algethar-academy"}
    assert sorted(result["algethar-academy"].keys()) == [15, 19]
    assert len(result["algethar-academy"][15]) == 2
    assert len(result["algethar-academy"][19]) == 1


def test_discover_runs_filters_levels_outside_scope():
    from jit_update.pipeline import discover_runs

    run_2 = BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062, keystone_level=2, duration_ms=999, completed_timestamp=1)
    run_15 = BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1080, period=1062, keystone_level=15, duration_ms=2103556, completed_timestamp=2)
    runs_by_realm = {(1080, 402): [run_2, run_15]}
    blizz = StubBlizzardClient(period_id=1062, realm_ids=[1080], runs_by_realm_dungeon=runs_by_realm)
    dungeons = [{"slug": "algethar-academy", "map_challenge_mode_id": 402}]

    result = discover_runs(blizz, dungeons=dungeons, levels=[15, 16, 17])

    assert 2 not in result["algethar-academy"]
    assert 15 in result["algethar-academy"]
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_pipeline.py::test_discover_runs_aggregates_by_dungeon_and_level tests/test_pipeline.py::test_discover_runs_filters_levels_outside_scope -v
```
Expected: FAIL — `discover_runs` does not exist.

- [ ] **Step 3: Implement `discover_runs`**

Replace the contents of `scripts/jit_update/pipeline.py` (or add at top, keeping any unchanged helpers like `select_slowest_percentile`):

```python
"""Pipeline orchestration: Blizzard discovery + Raider.IO enrichment + synthesis."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Protocol

from jit_update.config import Config
from jit_update.models import BlizzardRun, ReferenceCell


class BlizzardClientLike(Protocol):
    def get_current_period_id(self) -> int: ...
    def get_connected_realms_index(self) -> list[int]: ...
    def get_leaderboard_runs(self, *, realm_id: int, dungeon_id: int, period_id: int, dungeon_slug: str) -> list[BlizzardRun]: ...


class RaiderIOClientLike(Protocol):
    def get_static_data(self, expansion_id: int) -> dict: ...
    def get_runs(self, season: str, region: str, dungeon: str, page: int, affixes: str = "all") -> dict: ...
    def get_run_details(self, season: str, run_id: int) -> dict: ...


def discover_runs(
    blizz: BlizzardClientLike,
    *,
    dungeons: list[dict[str, Any]],
    levels: list[int],
) -> dict[str, dict[int, list[BlizzardRun]]]:
    """Iterate (realm, dungeon) for the current period, accumulate runs by (dungeon, level).

    Args:
        blizz: BlizzardClient (real or fake).
        dungeons: List of dungeon descriptors with at least 'slug' and 'map_challenge_mode_id'.
        levels: Allowed keystone levels; runs outside this set are dropped.

    Returns:
        ``{dungeon_slug: {keystone_level: [BlizzardRun, ...]}}``
    """
    period_id = blizz.get_current_period_id()
    realm_ids = blizz.get_connected_realms_index()
    levels_set = set(levels)
    accumulator: dict[str, dict[int, list[BlizzardRun]]] = defaultdict(lambda: defaultdict(list))

    for dungeon in dungeons:
        slug = dungeon["slug"]
        dungeon_id = int(dungeon["map_challenge_mode_id"])
        for realm_id in realm_ids:
            runs = blizz.get_leaderboard_runs(realm_id=realm_id, dungeon_id=dungeon_id, period_id=period_id, dungeon_slug=slug)
            for run in runs:
                if run.keystone_level not in levels_set:
                    continue
                accumulator[slug][run.keystone_level].append(run)

    # Convert defaultdicts to plain dicts for cleanliness
    return {slug: dict(levels_dict) for slug, levels_dict in accumulator.items()}


def select_slowest_percentile(runs: list[BlizzardRun], percentile: int, min_count: int = 2) -> list[BlizzardRun]:
    """Return the slowest ``percentile`` % of runs by ``duration_ms``.

    Result count is ``max(min_count, floor(len(runs) * percentile / 100))``
    capped at ``len(runs)``. Runs are sorted by ``duration_ms`` descending
    (slowest first); the returned list is the first N entries of that sort.

    Raises ``ValueError`` if ``percentile`` is outside [0, 100].
    """
    if not 0 <= percentile <= 100:
        raise ValueError(f"percentile must be in [0, 100], got {percentile}")
    if not runs:
        return []
    count = max(min_count, math.floor(len(runs) * percentile / 100))
    count = min(count, len(runs))
    return sorted(runs, key=lambda r: r.duration_ms, reverse=True)[:count]
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_pipeline.py::test_discover_runs_aggregates_by_dungeon_and_level tests/test_pipeline.py::test_discover_runs_filters_levels_outside_scope -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/pipeline.py scripts/tests/test_pipeline.py
git commit -m "✨ feat(pipeline): discover_runs aggregates Blizzard runs by dungeon/level

Walks (region, realm, dungeon) for the current period and groups every
in-scope run by (dungeon_slug, keystone_level). select_slowest_percentile
preserved from v1 logic but operates on BlizzardRun.duration_ms now."
```

---

### Task 11: Index real splits by `(dungeon, level)` from `/runs?page=0`

**Files:**
- Modify: `scripts/jit_update/pipeline.py`
- Modify: `scripts/tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

Append to `scripts/tests/test_pipeline.py`:

```python
def test_index_real_splits_by_level_groups_by_keystone_level():
    from jit_update.pipeline import index_real_splits_by_level

    splits_22 = [425000, 850000, 1275000, 1700000]
    splits_18 = [500000, 1000000, 1500000, 2000000]

    class StubRaider:
        def get_runs(self, season, region, dungeon, page, affixes="all"):
            return {
                "rankings": [
                    {"run": {"keystone_run_id": 1, "mythic_level": 22}},
                    {"run": {"keystone_run_id": 2, "mythic_level": 18}},
                    {"run": {"keystone_run_id": 3, "mythic_level": 14}},  # outside scope
                ]
            }

        def get_run_details(self, season, run_id):
            return {
                1: {
                    "season": season, "status": "finished", "keystone_run_id": 1, "mythic_level": 22,
                    "clear_time_ms": 1700000, "keystone_time_ms": 1860999,
                    "completed_at": "2026-05-03T07:33:46.051Z", "logged_run_id": 99,
                    "logged_details": {"encounters": [
                        {"id": 1, "status": "finished", "duration_ms": 1, "is_success": True,
                         "approximate_relative_started_at": 0, "approximate_relative_ended_at": s,
                         "boss": {"name": f"B{i}", "slug": f"b{i}", "ordinal": i, "wowEncounterId": 1000 + i}}
                        for i, s in enumerate(splits_22)
                    ]},
                },
                2: {
                    "season": season, "status": "finished", "keystone_run_id": 2, "mythic_level": 18,
                    "clear_time_ms": 2000000, "keystone_time_ms": 2200000,
                    "completed_at": "2026-05-03T07:33:46.051Z", "logged_run_id": 100,
                    "logged_details": {"encounters": [
                        {"id": 1, "status": "finished", "duration_ms": 1, "is_success": True,
                         "approximate_relative_started_at": 0, "approximate_relative_ended_at": s,
                         "boss": {"name": f"B{i}", "slug": f"b{i}", "ordinal": i, "wowEncounterId": 1000 + i}}
                        for i, s in enumerate(splits_18)
                    ]},
                },
                3: {
                    "season": season, "status": "finished", "keystone_run_id": 3, "mythic_level": 14,
                    "clear_time_ms": 2500000, "keystone_time_ms": 2700000,
                    "completed_at": "2026-05-03T07:33:46.051Z", "logged_run_id": None,
                    "logged_details": None,  # no encounters → skipped
                },
            }[run_id]

    result = index_real_splits_by_level(
        StubRaider(),
        season="season-mn-1",
        dungeon_slug="algethar-academy",
        levels_in_scope=[18, 19, 20, 21, 22],
        num_bosses=4,
    )
    assert sorted(result.keys()) == [18, 22]
    assert result[22] == [splits_22]
    assert result[18] == [splits_18]
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd scripts && uv run pytest tests/test_pipeline.py::test_index_real_splits_by_level_groups_by_keystone_level -v
```
Expected: FAIL — `index_real_splits_by_level` not defined.

- [ ] **Step 3: Implement `index_real_splits_by_level`**

Append to `scripts/jit_update/pipeline.py`:

```python
def index_real_splits_by_level(
    raiderio: RaiderIOClientLike,
    *,
    season: str,
    dungeon_slug: str,
    levels_in_scope: list[int],
    num_bosses: int,
) -> dict[int, list[list[int]]]:
    """Index Raider.IO top-page runs that have logged encounters, by keystone level.

    Returns ``{level: [[boss_split_ms, ...], ...]}`` where each inner list is
    one run's per-ordinal cumulative split. Only includes runs whose level is
    in ``levels_in_scope`` AND whose ``logged_details.encounters`` is populated.
    """
    from jit_update.models import RunDetails

    levels_set = set(levels_in_scope)
    by_level: dict[int, list[list[int]]] = defaultdict(list)

    payload = raiderio.get_runs(season=season, region="world", dungeon=dungeon_slug, page=0)
    for r in payload.get("rankings", []):
        run = r.get("run", {})
        run_id = run.get("keystone_run_id")
        level = run.get("mythic_level")
        if run_id is None or level not in levels_set:
            continue
        try:
            details = RunDetails.model_validate(raiderio.get_run_details(season=season, run_id=run_id))
        except Exception:
            continue
        if not details.encounters:
            continue
        splits = details.boss_splits_ms()
        # Pad/trim to num_bosses, replacing None with 0 (caller will backfill via clear_time)
        normalized = [int(s) if s is not None else 0 for s in splits[:num_bosses]]
        while len(normalized) < num_bosses:
            normalized.append(0)
        if all(v == 0 for v in normalized):
            continue
        by_level[level].append(normalized)

    return dict(by_level)
```

- [ ] **Step 4: Run test**

```bash
cd scripts && uv run pytest tests/test_pipeline.py::test_index_real_splits_by_level_groups_by_keystone_level -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/pipeline.py scripts/tests/test_pipeline.py
git commit -m "✨ feat(pipeline): index_real_splits_by_level groups Raider.IO splits

For each top-page Raider.IO run with logged encounters, normalize the
boss_splits_ms array to length num_bosses and bucket it under the
run's mythic_level. Used by aggregate_cell to source 'real' splits
where they exist in the same one-call discovery sweep."
```

---

### Task 12: `aggregate_cell()` — three-tier splits source selection

**Files:**
- Modify: `scripts/jit_update/pipeline.py`
- Modify: `scripts/tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Append to `scripts/tests/test_pipeline.py`:

```python
def test_aggregate_cell_uses_raiderio_when_real_splits_present():
    from jit_update.pipeline import aggregate_cell

    runs = [
        BlizzardRun(dungeon_slug="d", region="eu", realm_id=1, period=1, keystone_level=20, duration_ms=1700000, completed_timestamp=1),
        BlizzardRun(dungeon_slug="d", region="eu", realm_id=1, period=1, keystone_level=20, duration_ms=1750000, completed_timestamp=2),
    ]
    real_splits_at_level = [[425000, 850000, 1275000, 1700000]]
    observed_ratios = [0.5, 0.5, 0.5, 0.5]  # would be wrong if used

    cell = aggregate_cell(runs, real_splits_at_level, observed_ratios, num_bosses=4)
    assert cell.splits_source == "raiderio"
    # Median clear_time of [1700000, 1750000] = 1725000
    assert cell.clear_time_ms == 1725000
    # Median of one input list = the input itself
    assert cell.boss_splits_ms == [425000, 850000, 1275000, 1700000]
    assert cell.sample_size == 2


def test_aggregate_cell_synthesizes_when_no_real_splits():
    from jit_update.pipeline import aggregate_cell

    runs = [
        BlizzardRun(dungeon_slug="d", region="eu", realm_id=1, period=1, keystone_level=15, duration_ms=2000000, completed_timestamp=1),
    ]
    real_splits_at_level: list[list[int]] = []
    observed_ratios = [0.25, 0.5, 0.75, 1.0]

    cell = aggregate_cell(runs, real_splits_at_level, observed_ratios, num_bosses=4)
    assert cell.splits_source == "synthesized"
    assert cell.clear_time_ms == 2000000
    assert cell.boss_splits_ms == [500000, 1000000, 1500000, 2000000]


def test_aggregate_cell_falls_back_to_equidistant_when_no_ratios():
    from jit_update.pipeline import aggregate_cell

    runs = [
        BlizzardRun(dungeon_slug="d", region="eu", realm_id=1, period=1, keystone_level=15, duration_ms=2000000, completed_timestamp=1),
    ]
    cell = aggregate_cell(runs, [], [None, None, None, None], num_bosses=4)
    assert cell.splits_source == "equidistant_fallback"
    assert cell.boss_splits_ms == [500000, 1000000, 1500000, 2000000]
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v -k "aggregate_cell"
```
Expected: FAIL — `aggregate_cell` not defined.

- [ ] **Step 3: Implement `aggregate_cell`**

Append to `scripts/jit_update/pipeline.py`:

```python
def _median_per_position_with_backfill(
    splits_lists: list[list[int]],
    num_bosses: int,
    clear_time_median: int,
) -> list[int]:
    """Median per-ordinal across runs, with simple backfill for gaps.

    For each ordinal i, gather non-zero values across runs and take the median.
    If all runs are zero at ordinal i, backfill from neighbours: average of the
    closest known earlier and later medians (using clear_time_median as the
    end anchor when no later value exists, 0 when no earlier value exists).
    """
    medians: list[int] = []
    for i in range(num_bosses):
        values = [s[i] for s in splits_lists if i < len(s) and s[i] > 0]
        medians.append(int(statistics.median(values)) if values else 0)
    # Backfill zeros
    for i in range(num_bosses):
        if medians[i] != 0:
            continue
        prev_known = next((medians[j] for j in range(i - 1, -1, -1) if medians[j] > 0), 0)
        next_known = next((medians[j] for j in range(i + 1, num_bosses) if medians[j] > 0), clear_time_median)
        medians[i] = (prev_known + next_known) // 2
    return medians


def aggregate_cell(
    blizzard_runs: list[BlizzardRun],
    real_splits_at_level: list[list[int]],
    observed_ratios: list[float | None],
    num_bosses: int,
) -> ReferenceCell:
    """Build a ReferenceCell for one (dungeon, level) using three-tier splits source.

    Tier 1: real Raider.IO splits at this level → median per position (source="raiderio").
    Tier 2: synthesize from observed_ratios + clear_time_median (source="synthesized").
    Tier 3: equidistant fallback (source="equidistant_fallback").
    """
    from jit_update.splits_synthesis import synthesize_splits

    if not blizzard_runs:
        raise ValueError("aggregate_cell requires at least one BlizzardRun")
    clear_time_median = int(statistics.median(r.duration_ms for r in blizzard_runs))

    if real_splits_at_level:
        boss_splits = _median_per_position_with_backfill(real_splits_at_level, num_bosses, clear_time_median)
        source = "raiderio"
    elif any(r is not None for r in observed_ratios):
        boss_splits = synthesize_splits(clear_time_median, observed_ratios, num_bosses)
        source = "synthesized"
    else:
        boss_splits = [round(clear_time_median * (i + 1) / num_bosses) for i in range(num_bosses)]
        source = "equidistant_fallback"

    return ReferenceCell(
        sample_size=len(blizzard_runs),
        clear_time_ms=clear_time_median,
        boss_splits_ms=boss_splits,
        splits_source=source,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v -k "aggregate_cell"
```
Expected: PASS for the three tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/pipeline.py scripts/tests/test_pipeline.py
git commit -m "✨ feat(pipeline): aggregate_cell with three-tier splits source

Builds a ReferenceCell using clear_time_median from Blizzard runs and
boss_splits_ms from one of: real Raider.IO splits at the same level
(median per position), synthesized via observed ratios, or equidistant
fallback. Source recorded in cell.splits_source for transparency."
```

---

### Task 13: `build_document_from_discovered()` orchestration

**Files:**
- Modify: `scripts/jit_update/pipeline.py`
- Modify: `scripts/tests/test_pipeline.py`

The function takes a pre-discovered runs dict (so multi-region merging is the CLI's job in Task 15) and orchestrates Raider.IO ratio collection, real-splits indexing, and cell aggregation.

- [ ] **Step 1: Write failing test**

Append to `scripts/tests/test_pipeline.py`:

```python
def test_build_document_from_discovered_assembles_meta_and_dungeons_with_v2_schema():
    from jit_update.pipeline import build_document_from_discovered

    # Static data with one season, one dungeon
    static = {
        "seasons": [
            {
                "slug": "season-mn-1",
                "dungeons": [
                    {
                        "slug": "algethar-academy",
                        "id": 14032,
                        "name": "Algeth'ar Academy",
                        "short_name": "AA",
                        "map_challenge_mode_id": 402,
                        "keystone_timer_seconds": 1861,
                        "num_bosses": 4,
                    }
                ],
            }
        ]
    }

    runs_at_15 = [
        BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1, period=1062, keystone_level=15, duration_ms=2000000, completed_timestamp=1),
        BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1, period=1062, keystone_level=15, duration_ms=2050000, completed_timestamp=2),
    ] * 15  # 30 runs to clear min_sample
    runs_at_22 = [
        BlizzardRun(dungeon_slug="algethar-academy", region="eu", realm_id=1, period=1062, keystone_level=22, duration_ms=1700000, completed_timestamp=3),
    ] * 30
    discovered = {"algethar-academy": {15: runs_at_15, 22: runs_at_22}}

    class StubRaider:
        def get_static_data(self, expansion_id):
            return static
        def get_runs(self, season, region, dungeon, page, affixes="all"):
            return {"rankings": [
                {"run": {"keystone_run_id": 1, "mythic_level": 22}},
            ]}
        def get_run_details(self, season, run_id):
            return {
                "season": season, "status": "finished", "keystone_run_id": run_id, "mythic_level": 22,
                "clear_time_ms": 1700000, "keystone_time_ms": 1860999,
                "completed_at": "2026-05-03T07:33:46.051Z", "logged_run_id": 99,
                "logged_details": {"encounters": [
                    {"id": i, "status": "finished", "duration_ms": 1, "is_success": True,
                     "approximate_relative_started_at": 0, "approximate_relative_ended_at": v,
                     "boss": {"name": f"B{i}", "slug": f"b{i}", "ordinal": i, "wowEncounterId": 1000+i}}
                    for i, v in enumerate([425000, 850000, 1275000, 1700000])
                ]},
            }

    from jit_update.cache import FileCache
    import tempfile
    cache = FileCache(tempfile.mkdtemp())

    cfg = type("Cfg", (), {})()
    cfg.raiderio = type("R", (), {"expansion_id": 11, "season": "season-mn-1", "region": "world"})()
    cfg.scope = type("S", (), {"levels": [15, 16, 17, 18, 19, 20, 21, 22], "min_sample": 20, "slowest_percentile": 10})()
    cfg.output = type("O", (), {"schema_version": 2})()

    doc = build_document_from_discovered(discovered, StubRaider(), cache, cfg, datetime(2026, 5, 9, 18, 30, 0))

    assert doc["meta"]["schema_version"] == 2
    assert doc["meta"]["season"] == "season-mn-1"
    assert doc["meta"]["source"] == "blizzard+raiderio"
    assert "algethar-academy" in doc["dungeons"]
    aa = doc["dungeons"]["algethar-academy"]
    assert aa["keystone_timer_ms"] == 1861000
    # Levels 15 and 22 present (min_sample met both)
    assert 15 in aa["levels"]
    assert 22 in aa["levels"]
    # No affix sub-key
    assert isinstance(aa["levels"][15], dict)
    assert "boss_splits_ms" in aa["levels"][15]
    assert aa["levels"][15]["splits_source"] == "synthesized"
    assert aa["levels"][22]["splits_source"] == "raiderio"
```

Add the import at the top of the test file:

```python
from datetime import datetime
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd scripts && uv run pytest tests/test_pipeline.py::test_build_document_from_discovered_assembles_meta_and_dungeons_with_v2_schema -v
```
Expected: FAIL — `build_document_from_discovered` not defined or signature mismatch.

- [ ] **Step 3: Implement `build_document_from_discovered` and `merge_discovered`**

Append to `scripts/jit_update/pipeline.py`:

```python
def merge_discovered(
    *partials: dict[str, dict[int, list[BlizzardRun]]],
) -> dict[str, dict[int, list[BlizzardRun]]]:
    """Merge multiple discovered-runs dicts (one per region) into one.

    Concatenates run lists at each (dungeon_slug, level) coordinate.
    """
    merged: dict[str, dict[int, list[BlizzardRun]]] = {}
    for partial in partials:
        for slug, levels_dict in partial.items():
            target = merged.setdefault(slug, {})
            for level, runs in levels_dict.items():
                target.setdefault(level, []).extend(runs)
    return merged


def build_document_from_discovered(
    discovered: dict[str, dict[int, list[BlizzardRun]]],
    raiderio: RaiderIOClientLike,
    cache,  # FileCache used for ratios
    config: Config | Any,
    now: datetime,
) -> dict[str, Any]:
    """Assemble a Data.lua document dict (schema v2) from pre-discovered Blizzard runs.

    Multi-region merging is the caller's job (use ``merge_discovered``).
    """
    from jit_update.splits_synthesis import collect_observed_ratios_cached

    static = raiderio.get_static_data(expansion_id=config.raiderio.expansion_id)
    season_obj = next(
        (s for s in static.get("seasons", []) if s.get("slug") == config.raiderio.season),
        None,
    )
    if season_obj is None:
        raise RuntimeError(f"season {config.raiderio.season!r} not in static data")
    season_dungeons = season_obj["dungeons"]

    document: dict[str, Any] = {
        "meta": {
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "season": config.raiderio.season,
            "schema_version": 2,
            "source": "blizzard+raiderio",
        },
        "dungeons": {},
    }

    for dungeon in season_dungeons:
        slug = dungeon["slug"]
        num_bosses = int(dungeon.get("num_bosses", 0))
        timer_ms = int(dungeon["keystone_timer_seconds"]) * 1000

        # Per-dungeon ratio collection (cached 7 days)
        observed_ratios = collect_observed_ratios_cached(
            raiderio, cache, season=config.raiderio.season, dungeon_slug=slug, num_bosses=num_bosses,
        )

        # Per-dungeon Raider.IO real splits indexed by level (one /runs?page=0 + N /run-details)
        real_splits_by_level = index_real_splits_by_level(
            raiderio,
            season=config.raiderio.season,
            dungeon_slug=slug,
            levels_in_scope=list(config.scope.levels),
            num_bosses=num_bosses,
        )

        levels_block: dict[int, dict[str, Any]] = {}
        for level, runs in discovered.get(slug, {}).items():
            if len(runs) < config.scope.min_sample:
                continue
            sample = select_slowest_percentile(runs, percentile=config.scope.slowest_percentile, min_count=2)
            cell = aggregate_cell(
                blizzard_runs=sample,
                real_splits_at_level=real_splits_by_level.get(level, []),
                observed_ratios=observed_ratios,
                num_bosses=num_bosses,
            )
            levels_block[level] = {
                "clear_time_ms": cell.clear_time_ms,
                "boss_splits_ms": list(cell.boss_splits_ms),
                "sample_size": cell.sample_size,
                "splits_source": cell.splits_source,
            }

        document["dungeons"][slug] = {
            "keystone_timer_ms": timer_ms,
            "bosses": _bosses_block_from_static(dungeon),
            "levels": levels_block,
        }

    return document


def _bosses_block_from_static(dungeon: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Build the bosses sub-table from static data, 1-indexed by ordinal."""
    bosses_in = dungeon.get("bosses") or []
    out: dict[int, dict[str, Any]] = {}
    for b in bosses_in:
        ordinal = int(b.get("ordinal", 0))
        out[ordinal + 1] = {
            "ordinal": ordinal + 1,
            "slug": b.get("slug", ""),
            "name": b.get("name", ""),
        }
    if not out and dungeon.get("num_bosses"):
        # Fallback: synthesize placeholder bosses if static data lacks them
        for i in range(int(dungeon["num_bosses"])):
            out[i + 1] = {"ordinal": i + 1, "slug": f"boss-{i+1}", "name": f"Boss {i+1}"}
    return out
```

- [ ] **Step 4: Run test**

```bash
cd scripts && uv run pytest tests/test_pipeline.py::test_build_document_from_discovered_assembles_meta_and_dungeons_with_v2_schema -v
```
Expected: PASS.

- [ ] **Step 5: Run full pipeline test suite**

```bash
cd scripts && uv run pytest tests/test_pipeline.py -v
```
Expected: all tests in this file PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/jit_update/pipeline.py scripts/tests/test_pipeline.py
git commit -m "✨ feat(pipeline): build_document_from_discovered + merge_discovered

build_document_from_discovered consumes a pre-discovered runs dict
(produced by discover_runs and merged across regions by the CLI) and
assembles the Data.lua document via Raider.IO ratio collection + cell
aggregation. merge_discovered concatenates per-region run lists.
Output matches schema v2."
```

---

# Phase E — Renderer

### Task 14: `lua_renderer` — emit schema v2

**Files:**
- Modify: `scripts/jit_update/lua_renderer.py`
- Modify: `scripts/tests/test_lua_renderer.py`

- [ ] **Step 1: Write failing tests**

Replace the contents of `scripts/tests/test_lua_renderer.py` (or add new tests if the file has unrelated content):

```python
"""Tests for lua_renderer schema v2 output."""

from __future__ import annotations

from jit_update.lua_renderer import render_data_lua


def test_render_emits_schema_version_2():
    doc = {
        "meta": {"generated_at": "2026-05-09T18:30:00Z", "schema_version": 2, "season": "season-mn-1", "source": "blizzard+raiderio"},
        "dungeons": {},
    }
    out = render_data_lua(doc)
    assert "schema_version = 2" in out
    assert 'source         = "blizzard+raiderio"' in out or 'source = "blizzard+raiderio"' in out


def test_render_drops_affix_id_to_slug_table():
    doc = {
        "meta": {"generated_at": "2026-05-09T18:30:00Z", "schema_version": 2, "season": "season-mn-1", "source": "blizzard+raiderio"},
        "dungeons": {},
    }
    out = render_data_lua(doc)
    assert "affix_id_to_slug" not in out


def test_render_levels_have_no_affix_subkey():
    doc = {
        "meta": {"generated_at": "2026-05-09T18:30:00Z", "schema_version": 2, "season": "season-mn-1", "source": "blizzard+raiderio"},
        "dungeons": {
            "algethar-academy": {
                "keystone_timer_ms": 1861000,
                "bosses": {1: {"ordinal": 1, "slug": "boss-1", "name": "Boss 1"}},
                "levels": {
                    15: {"clear_time_ms": 2000000, "boss_splits_ms": [500000, 1000000, 1500000, 2000000], "sample_size": 30, "splits_source": "synthesized"},
                },
            }
        },
    }
    out = render_data_lua(doc)
    # Ensure the level entry is a direct map, not nested under an affix key
    assert "[15] = {" in out
    assert 'splits_source  = "synthesized"' in out or 'splits_source = "synthesized"' in out
    assert "[\"fortified" not in out  # no affix combo string anywhere


def test_render_includes_all_three_splits_sources():
    doc = {
        "meta": {"generated_at": "2026-05-09T18:30:00Z", "schema_version": 2, "season": "season-mn-1", "source": "blizzard+raiderio"},
        "dungeons": {
            "d": {
                "keystone_timer_ms": 1861000,
                "bosses": {1: {"ordinal": 1, "slug": "b1", "name": "B1"}},
                "levels": {
                    15: {"clear_time_ms": 2000000, "boss_splits_ms": [500000, 1000000, 1500000, 2000000], "sample_size": 30, "splits_source": "synthesized"},
                    18: {"clear_time_ms": 1800000, "boss_splits_ms": [450000, 900000, 1350000, 1800000], "sample_size": 50, "splits_source": "raiderio"},
                    22: {"clear_time_ms": 1700000, "boss_splits_ms": [425000, 850000, 1275000, 1700000], "sample_size": 25, "splits_source": "equidistant_fallback"},
                },
            }
        },
    }
    out = render_data_lua(doc)
    assert "synthesized" in out
    assert "raiderio" in out
    assert "equidistant_fallback" in out
```

- [ ] **Step 2: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_lua_renderer.py -v
```
Expected: FAIL on at least the v2 / affix-drop / splits_source tests because the existing renderer emits v1 schema.

- [ ] **Step 3: Update `lua_renderer.py`**

Open `scripts/jit_update/lua_renderer.py` and rewrite `render_data_lua` to emit schema v2. The existing function likely loops over `dungeons[d].levels[L][affix_combo]`; replace that nesting with direct level-keyed entries. Reference structure:

```python
def render_data_lua(doc: dict) -> str:
    """Render a document dict to a Data.lua text body (schema v2)."""
    lines: list[str] = []
    lines.append("-- Auto-generated by scripts/jit_update. Do not edit by hand.")
    lines.append("JustInTimeData = {")

    meta = doc.get("meta", {})
    lines.append("  meta = {")
    lines.append(f'    generated_at   = "{meta.get("generated_at", "")}",')
    lines.append(f"    schema_version = {int(meta.get('schema_version', 2))},")
    lines.append(f'    season         = "{meta.get("season", "")}",')
    lines.append(f'    source         = "{meta.get("source", "blizzard+raiderio")}",')
    lines.append("  },")
    lines.append("")
    lines.append("  dungeons = {")

    for slug, dungeon in sorted(doc.get("dungeons", {}).items()):
        lines.append(f'    ["{slug}"] = {{')
        lines.append(f"      keystone_timer_ms = {int(dungeon.get('keystone_timer_ms', 0))},")
        # Bosses sub-table
        lines.append("      bosses = {")
        for ord_key in sorted(dungeon.get("bosses", {}).keys()):
            b = dungeon["bosses"][ord_key]
            lines.append(
                f'        [{int(ord_key)}] = {{ ordinal = {int(b.get("ordinal", ord_key))}, '
                f'slug = "{b.get("slug","")}", name = "{b.get("name","")}" }},'
            )
        lines.append("      },")
        # Levels sub-table — direct, no affix nesting
        lines.append("      levels = {")
        for level in sorted(dungeon.get("levels", {}).keys()):
            cell = dungeon["levels"][level]
            splits_lua = "{" + ", ".join(str(int(v)) for v in cell.get("boss_splits_ms", [])) + "}"
            lines.append(f"        [{int(level)}] = {{")
            lines.append(f"          clear_time_ms  = {int(cell.get('clear_time_ms', 0))},")
            lines.append(f"          boss_splits_ms = {splits_lua},")
            lines.append(f"          sample_size    = {int(cell.get('sample_size', 0))},")
            lines.append(f'          splits_source  = "{cell.get("splits_source", "")}",')
            lines.append("        },")
        lines.append("      },")
        lines.append("    },")

    lines.append("  },")
    lines.append("}")
    return "\n".join(lines) + "\n"
```

If the existing module exposes a different public name (e.g. `render_document`), keep that name and adjust the test imports — pick whichever requires fewer changes outside the scope of this task.

- [ ] **Step 4: Run tests**

```bash
cd scripts && uv run pytest tests/test_lua_renderer.py -v
```
Expected: PASS for all tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/jit_update/lua_renderer.py scripts/tests/test_lua_renderer.py
git commit -m "✨ feat(renderer): emit Data.lua schema v2 (no affix layer)

schema_version = 2, drops affix_id_to_slug, drops the [affix_combo]
sub-key under levels[L]. Adds splits_source per cell. Output stays
deterministic (sorted keys) so diffs stay readable."
```

---

# Phase F — CLI

### Task 15: CLI env-var loading + Blizzard client wiring + error UX

**Files:**
- Modify: `scripts/jit_update/cli.py`
- Modify: `scripts/tests/test_cli.py`

- [ ] **Step 1: Inspect existing CLI shape**

```bash
cd scripts && cat jit_update/cli.py | head -120
```

Note the existing `main()` entrypoint, the way it loads config, and how it constructs `RaiderIOClient`. The next steps assume the CLI uses a top-level function (e.g. `main()` or a Typer command) that already reads `jit_config.toml` and calls `build_document(...)`. Adapt the patches below to the actual function signature you find.

- [ ] **Step 2: Write failing test**

Add to `scripts/tests/test_cli.py`:

```python
import os
import pytest


def test_cli_fails_loudly_when_blizzard_creds_missing(monkeypatch, capsys):
    from jit_update.cli import build_blizzard_clients_from_env

    monkeypatch.delenv("BLIZZARD_CLIENT_ID", raising=False)
    monkeypatch.delenv("BLIZZARD_CLIENT_SECRET", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        build_blizzard_clients_from_env(regions=["eu"], rate_per_second=80, cache=None, timeout=30, max_retries=3)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "BLIZZARD_CLIENT_ID" in captured.err
    assert "develop.battle.net" in captured.err


def test_cli_builds_one_client_per_region(monkeypatch, tmp_path):
    from jit_update.cli import build_blizzard_clients_from_env
    from jit_update.cache import FileCache

    monkeypatch.setenv("BLIZZARD_CLIENT_ID", "id")
    monkeypatch.setenv("BLIZZARD_CLIENT_SECRET", "secret")
    cache = FileCache(tmp_path / "cache")

    clients = build_blizzard_clients_from_env(regions=["eu", "us"], rate_per_second=80, cache=cache, timeout=30, max_retries=3)

    assert set(clients.keys()) == {"eu", "us"}
    assert clients["eu"]._region == "eu"
    assert clients["us"]._region == "us"
```

- [ ] **Step 3: Run tests, expect failure**

```bash
cd scripts && uv run pytest tests/test_cli.py -v -k "blizzard"
```
Expected: FAIL — `build_blizzard_clients_from_env` not defined.

- [ ] **Step 4: Add the helper to CLI**

Add to `scripts/jit_update/cli.py` (top-level, near the existing client construction code):

```python
import os
import sys

from jit_update.blizzard import BlizzardClient
from jit_update.cache import FileCache
from jit_update.rate_limiter import RateLimiter


def build_blizzard_clients_from_env(
    *,
    regions: list[str],
    rate_per_second: float,
    cache: FileCache | None,
    timeout: float,
    max_retries: int,
) -> dict[str, BlizzardClient]:
    """Construct one BlizzardClient per region using env vars for OAuth.

    Exits with code 2 and a helpful error if BLIZZARD_CLIENT_ID or
    BLIZZARD_CLIENT_SECRET is missing.
    """
    client_id = os.environ.get("BLIZZARD_CLIENT_ID")
    client_secret = os.environ.get("BLIZZARD_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "ERROR: BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET must be set in the environment.\n"
            "  Get a client at https://develop.battle.net/access/clients (free, OAuth2 client_credentials).\n"
            "  Then export the values:\n"
            "    export BLIZZARD_CLIENT_ID=...\n"
            "    export BLIZZARD_CLIENT_SECRET=...",
            file=sys.stderr,
        )
        sys.exit(2)
    clients: dict[str, BlizzardClient] = {}
    for region in regions:
        # One rate limiter shared across all regions (Blizzard rate-limits per
        # client_id, not per region).
        clients[region] = BlizzardClient(
            client_id=client_id,
            client_secret=client_secret,
            region=region,
            cache=cache,
            rate_limiter=RateLimiter(rate_per_second=rate_per_second),
            timeout_seconds=timeout,
            max_retries=max_retries,
        )
    return clients
```

- [ ] **Step 5: Wire into existing `main()`**

Find the existing `main()` (or Typer command) function and replace the document-building section with the multi-region flow. The orchestration looks like:

```python
from datetime import datetime, timezone

from jit_update.pipeline import discover_runs, merge_discovered, build_document_from_discovered


def main(...):
    config = load_config(CONFIG_PATH)
    cache = FileCache(...)
    raiderio = RaiderIOClient(...)
    blizzard_clients = build_blizzard_clients_from_env(
        regions=config.blizzard.regions,
        rate_per_second=config.blizzard.rate_per_second,
        cache=cache,
        timeout=config.blizzard.timeout_seconds,
        max_retries=config.blizzard.max_retries,
    )

    # Resolve season dungeons once via Raider.IO static_data
    static = raiderio.get_static_data(expansion_id=config.raiderio.expansion_id)
    season_obj = next(
        (s for s in static.get("seasons", []) if s.get("slug") == config.raiderio.season),
        None,
    )
    if season_obj is None:
        raise RuntimeError(f"season {config.raiderio.season!r} not in static data")
    season_dungeons = season_obj["dungeons"]

    # Discover runs per region, then merge
    partials = [
        discover_runs(blizz, dungeons=season_dungeons, levels=list(config.scope.levels))
        for blizz in blizzard_clients.values()
    ]
    discovered = merge_discovered(*partials)

    doc = build_document_from_discovered(discovered, raiderio, cache, config, datetime.now(timezone.utc))
    # ... existing render + write code stays the same
```

Keep the existing `--dry-run` / `--no-cache` flag handling. The dry-run path renders the document but skips the file write — adapt accordingly.

- [ ] **Step 6: Run tests**

```bash
cd scripts && uv run pytest tests/test_cli.py tests/test_pipeline.py -v
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/jit_update/cli.py scripts/tests/test_cli.py
git commit -m "✨ feat(cli): wire Blizzard credentials from env, multi-region merge

build_blizzard_clients_from_env constructs one BlizzardClient per
configured region from BLIZZARD_CLIENT_ID/SECRET env vars. Missing
creds → exit code 2 with a pointer to develop.battle.net. CLI then
merges per-region discovered runs before invoking build_document."
```

---

# Phase G — Lua addon

### Task 16: `Overlay.lua` — drop `[affixCombo]` lookup at 3 sites

**Files:**
- Modify: `addon/JustInTime/Overlay.lua`

- [ ] **Step 1: Locate the three sites**

```bash
grep -n "affixCombo\|affix_combo\|levels\[level\]\[" addon/JustInTime/Overlay.lua
```

Expected output: three lines around 228, 249, 326 (per spec section 8.1).

- [ ] **Step 2: Patch each lookup**

For each occurrence of the pattern below, edit it:

Before:
```lua
local ref = data.dungeons[slug] and data.dungeons[slug].levels[level]
            and data.dungeons[slug].levels[level][affixCombo]
```

After:
```lua
local ref = data.dungeons[slug] and data.dungeons[slug].levels[level]
```

If the surrounding code references the variable `affixCombo` for non-lookup purposes, leave those references — the `local affixCombo = ...` definition can stay; we are just dropping its use in the indexing. If `affixCombo` becomes entirely unused in the function after the edit, also remove the `local affixCombo = ...` line.

- [ ] **Step 3: Sanity-check via grep**

```bash
grep -n "levels\[level\]\[" addon/JustInTime/Overlay.lua
```
Expected: 0 matches.

```bash
grep -n "affixCombo" addon/JustInTime/Overlay.lua
```
Expected: 0 matches (or only inside comments/log lines that you can leave).

- [ ] **Step 4: Commit**

```bash
git add addon/JustInTime/Overlay.lua
git commit -m "♻️ refactor(addon): drop affix-combo lookup, levels[L] is direct now

Schema v2 inlines levels[L] directly without an affix-combo sub-key.
Three lookup sites in Overlay.lua patched. The downstream nil checks
on ref.boss_splits_ms / ref.clear_time_ms are unchanged and still
guard against missing cells."
```

---

### Task 17: `Core.lua` schema guard + `Locales.lua` keys

**Files:**
- Modify: `addon/JustInTime/Core.lua`
- Modify: `addon/JustInTime/Locales.lua`

- [ ] **Step 1: Add locale keys**

Open `addon/JustInTime/Locales.lua`. Find the FR table block (likely a `local L_frFR = { ... }` or similar) and add:

```lua
L.OUTDATED_DATA = "Données de référence obsolètes. Mets à jour l'addon ou regenère Data.lua."
L.MISSING_DATA  = "Données de référence introuvables. L'addon est peut-être mal installé."
```

In the EN fallback block, add:

```lua
L.OUTDATED_DATA = "Reference data is outdated. Update the addon or regenerate Data.lua."
L.MISSING_DATA  = "Reference data missing. The addon may be incorrectly installed."
```

The exact namespace path (`L.X` vs `Locales.frFR.X`) follows whatever pattern exists in the file. Match the convention used by neighbouring keys.

- [ ] **Step 2: Add `checkSchema` to Core.lua**

Open `addon/JustInTime/Core.lua`. Find the `OnLoad` function (or the equivalent — search for `EVENTS_HANDLER`, `OnEvent`, or `frame:RegisterEvent`):

```bash
grep -n "OnLoad\|RegisterEvent\|ADDON_LOADED" addon/JustInTime/Core.lua
```

Inside the `OnLoad` (or first-invocation handler), add at the very top:

```lua
local function checkSchema()
    if not (JustInTimeData and JustInTimeData.meta) then
        if ChatPrinter and ChatPrinter.warn then ChatPrinter.warn(L.MISSING_DATA) end
        return false
    end
    if JustInTimeData.meta.schema_version ~= 2 then
        if ChatPrinter and ChatPrinter.warn then ChatPrinter.warn(L.OUTDATED_DATA) end
        return false
    end
    return true
end

if not checkSchema() then
    return
end
```

Place `checkSchema` definition above its first call site. The exact `ChatPrinter` namespace may differ — match existing usage in the file.

- [ ] **Step 3: Smoke-check load order**

`Locales.lua` must be in the `.toc` before `Core.lua` so `L` is defined when Core uses it. Verify:

```bash
grep -n "Locales\.lua\|Core\.lua" addon/JustInTime/JustInTime.toc
```

Expected: `Locales.lua` listed before `Core.lua`. If not, fix the ordering in `JustInTime.toc`.

- [ ] **Step 4: Commit**

```bash
git add addon/JustInTime/Core.lua addon/JustInTime/Locales.lua addon/JustInTime/JustInTime.toc
git commit -m "✨ feat(addon): add Data.lua schema_version guard + locale keys

Core.lua refuses to register events if JustInTimeData is missing or
on schema_version != 2. User-facing error via ChatPrinter using two
new locale keys (FR + EN): OUTDATED_DATA, MISSING_DATA."
```

---

### Task 18: `.toc` version bump + `CHANGELOG.txt` entry

**Files:**
- Modify: `addon/JustInTime/JustInTime.toc`
- Modify: `addon/JustInTime/CHANGELOG.txt`

- [ ] **Step 1: Bump TOC version**

In `addon/JustInTime/JustInTime.toc`, find:

```toc
## Version: 0.3.4
```

Replace with:

```toc
## Version: 0.4.0
```

- [ ] **Step 2: Add CHANGELOG entry**

Prepend to `addon/JustInTime/CHANGELOG.txt`:

```
v0.4.0 — 2026-05-09
  - Reference data now covers Mythic+ keystone levels +15 to +22 (previously +18 to +20).
  - Data.lua schema v2: drops the per-affix-combo nesting under each level (the addon
    didn't use it). Old Data.lua files (schema_version=1) are detected and rejected with
    an explicit error message; reinstall or regenerate to fix.
  - Reference timers now sourced from the Battle.net mythic-keystone-leaderboard API
    for full level coverage. Boss splits at low levels are synthesized from observed
    ratios at higher levels where real per-encounter data is available.

```

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/JustInTime.toc addon/JustInTime/CHANGELOG.txt
git commit -m "🔖 chore(release): bump toc to v0.4.0, document keystone +15-22 coverage"
```

---

# Phase H — Validation

### Task 19: Run `make data-dry` to validate the flow

**Files:** none (validation step)

- [ ] **Step 1: Set credentials**

```bash
export BLIZZARD_CLIENT_ID="<your_client_id>"
export BLIZZARD_CLIENT_SECRET="<your_client_secret>"
```

If you don't yet have credentials, register a free client at https://develop.battle.net/access/clients (Battle.net account required, no fee).

- [ ] **Step 2: Run dry-run**

```bash
cd /home/tarto/projects/wowAddons/justInTime && make data-dry
```

Expected output (ballpark):
- Token obtained successfully
- Discovery progresses through realms and dungeons (~1-2 min total)
- Final stats: `total_runs_discovered`, `runs_per_level` (15-22), `splits_source_distribution`
- No `Data.lua` written

- [ ] **Step 3: Sanity-check stats**

The summary should show:
- All 9 saison-mn-1 dungeons covered
- Each dungeon has at least one cell at level 18-22 with `splits_source = "raiderio"`
- No more than ~1 cell with `splits_source = "equidistant_fallback"` across the whole document (if ratios collection succeeds for every dungeon, this should be zero)

If the run fails:
- Auth error (HTTP 401): re-check env vars; rotate credentials at develop.battle.net.
- Rate-limit error (HTTP 429): lower `[blizzard].rate_per_second` in `jit_config.toml` to e.g. 50.
- Missing dungeon: confirm the saison-mn-1 dungeons in `static_data.seasons[].dungeons` match what Blizzard returns (`map_challenge_mode_id` mismatch).

- [ ] **Step 4: Commit any config tweaks**

If you adjusted `jit_config.toml` (e.g. lowered rate), commit it:

```bash
git add scripts/jit_config.toml
git commit -m "🔧 chore(config): tune Blizzard rate limit after smoke test"
```

If no config tweak was needed, no commit.

---

### Task 20: Run `make data` to regen `Data.lua`, verify schema v2

**Files:**
- Regenerate: `addon/JustInTime/Data.lua`

- [ ] **Step 1: Regenerate Data.lua**

```bash
cd /home/tarto/projects/wowAddons/justInTime && make data
```

Expected: `addon/JustInTime/Data.lua` written successfully.

- [ ] **Step 2: Spot-check the generated file**

```bash
head -60 addon/JustInTime/Data.lua
```

Verify:
- `schema_version = 2`
- `source = "blizzard+raiderio"`
- No `affix_id_to_slug` table at top level
- For at least one dungeon, the `levels` block contains entries 15 through 22

```bash
grep -c '\[15\] = {\|\[22\] = {' addon/JustInTime/Data.lua
```
Expected: at least 9 of each (one per dungeon).

```bash
grep -c 'splits_source' addon/JustInTime/Data.lua
```
Expected: roughly 9 dungeons × 8 levels = ~72 matches.

```bash
grep -c 'equidistant_fallback' addon/JustInTime/Data.lua
```
Expected: 0 (or as close to 0 as possible — every dungeon should yield at least one observed-ratio).

- [ ] **Step 3: Commit the regenerated data**

```bash
git add addon/JustInTime/Data.lua
git commit -m "📦 chore(data): regenerate Data.lua v2 with +15-22 coverage"
```

---

### Task 21: UAT — load addon in WoW, verify pace at +15 (synth) and +18 (real)

**Files:** none (manual user task)

- [ ] **Step 1: Build and install the addon zip**

```bash
cd /home/tarto/projects/wowAddons/justInTime && make package
```

Expected: `addon/JustInTime-v0.4.0.zip` produced. Extract its contents into `Interface/AddOns/JustInTime/` of your WoW Retail install (replacing any previous version).

- [ ] **Step 2: Launch WoW, enable the addon**

`/reload` in-game after enabling at the character select screen. No errors should appear in the chat. If you see a yellow `Données de référence obsolètes...` message, it means the schema guard tripped — re-check that `Data.lua` shipped with the zip (it should be inside `JustInTime/` at the root of the zip).

- [ ] **Step 3: Run a +18 key (or use the test simulation)**

If `Overlay.lua:497` exposes a test mode (per the `boss_splits_ms = { 425000, 850000, 1275000, 1700000 }` snippet from the original grep), trigger it. Otherwise queue a +18 in any season-mn-1 dungeon.

Expected: the overlay shows `boss_splits` per kill, with deltas relative to the pace from the new `Data.lua`. The `splits_source` field is not exposed to the user (per spec hors-scope).

- [ ] **Step 4: Run a +15 key**

Either pug a +15 or solo a previous-week's +15 keystone. Expected: overlay still shows pace per boss kill — the splits will be the synthesized ones, but the user shouldn't notice unless the synthesis is grossly wrong.

- [ ] **Step 5: Sanity check on +21/+22 if available**

If the season has +21/+22 timed runs (likely true late in the season, possibly not at start), queue one. Expected: overlay shows pace with `splits_source = "raiderio"` cells.

- [ ] **Step 6: Report findings**

If everything works, commit nothing further; the work is shippable. If anomalies show:
- Overlay flickers / shows wrong values → file a debug session, run `/jit dump ref` (if such a command exists) or inspect via WoW Lua console.
- Specific dungeon has no entries → check `Data.lua` for that slug; if missing, the dungeon's `min_sample` was unmet; lower it temporarily in `jit_config.toml` and re-run `make data`.

This is the terminal acceptance gate. Once UAT passes, the feature is done.

---

## Self-review checklist

After implementation, verify the plan covered the spec by spot-checking each spec section:

- [ ] **Spec §3 decision 1** (Blizzard discovery) → Tasks 5, 6, 10
- [ ] **Spec §3 decision 2** (Raider.IO splits) → Tasks 11, 12
- [ ] **Spec §3 decision 3** (synthesis) → Tasks 7, 8, 9, 12
- [ ] **Spec §3 decision 4** (EU + US) → Task 15
- [ ] **Spec §3 decision 5** (current period) → Task 5 (`get_current_period_id`), Task 10 (called from `discover_runs`)
- [ ] **Spec §3 decision 6** (schema v2) → Tasks 4, 14
- [ ] **Spec §3 decision 7** (env vars) → Task 15
- [ ] **Spec §3 decision 8** (cache 7d) → Task 9
- [ ] **Spec §3 decision 9** (refonte complète) → Tasks 10-13 rewrite the pipeline
- [ ] **Spec §8 addon impact** → Tasks 16, 17, 18
- [ ] **Spec §9 acceptance criteria** → Tasks 19, 20, 21

If any decision lacks a task, add it before starting execution.
