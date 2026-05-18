"""Boss splits synthesis: observed-ratio collection + extrapolation."""

from __future__ import annotations

import json
import statistics
from typing import Any, Protocol

from jit_update.cache import FileCache
from jit_update.models import RunDetails


class RaiderIOLike(Protocol):
    """Subset of RaiderIOClient used by ratio collection."""

    def get_runs(
        self, season: str, region: str, dungeon: str, page: int, affixes: str = "all"
    ) -> dict[str, Any]: ...

    def get_run_details(self, season: str, run_id: int) -> dict[str, Any]: ...


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
    runs_payload = client.get_runs(
        season=season, region="world", dungeon=dungeon_slug, page=0
    )
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
        # Depleted runs skew the boss-split ratios upward. Skip them.
        if details.num_chests <= 0:
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

    return [
        statistics.median(samples) if samples else None for samples in samples_per_ordinal
    ]


RATIOS_CACHE_TTL_SECONDS = 7 * 24 * 3600  # documented in spec section 7


def collect_observed_ratios_cached(
    client: RaiderIOLike,
    cache: FileCache,
    season: str,
    dungeon_slug: str,
    num_bosses: int,
) -> list[float | None]:
    """Same as :func:`collect_observed_ratios` but caches on disk.

    Cache key: ``ratios/<season>/<dungeon_slug>``. The caller is responsible
    for instantiating ``cache`` with ``ttl_seconds=7*24*3600`` (or whatever
    refresh cadence is desired). Note that ``FileCache`` only supports a
    single global TTL per instance — use a dedicated instance for ratios.
    """
    key = f"ratios/{season}/{dungeon_slug}"
    cached_bytes = cache.get(key)
    if cached_bytes is not None:
        try:
            decoded = json.loads(cached_bytes.decode("utf-8"))
            if isinstance(decoded, list) and len(decoded) == num_bosses:
                # Restore None values (JSON null -> None) and coerce floats
                return [None if v is None else float(v) for v in decoded]
        except (ValueError, TypeError, UnicodeDecodeError):
            pass  # fall through, recompute
    ratios = collect_observed_ratios(client, season, dungeon_slug, num_bosses)
    cache.set(key, json.dumps(ratios).encode("utf-8"))
    return ratios


def synthesize_splits(
    clear_time_ms: int,
    ratios: list[float | None],
    num_bosses: int,
) -> list[int]:
    """Build per-boss cumulative split times from clear_time and observed ratios.

    Args:
        clear_time_ms: Total clear time of the run in milliseconds.
        ratios:        Length ``num_bosses`` list of float ratios in [0, 1] or
                       ``None`` at positions without observed data. Shorter lists
                       are padded with ``None``.
        num_bosses:    Expected number of bosses (caller's authoritative count).

    Returns:
        ``num_bosses`` ints. For positions where ``ratios[i]`` is a float,
        ``round(clear_time_ms * ratios[i])``. For ``None`` positions, equidistant
        fallback ``round(clear_time_ms * (i+1) / num_bosses)``.
    """
    padded: list[float | None] = list(ratios) + [None] * max(0, num_bosses - len(ratios))
    result: list[int] = []
    for i in range(num_bosses):
        r = padded[i]
        if r is None:
            result.append(round(clear_time_ms * (i + 1) / num_bosses))
        else:
            result.append(round(clear_time_ms * r))
    return result
