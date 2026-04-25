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
        payload = client.get_runs(season=season, region=region, dungeon=dungeon, page=page)
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


def select_slowest_percentile(runs: list[Run], percentile: int, min_count: int = 2) -> list[Run]:
    """Return the slowest ``percentile`` % of runs by ``clear_time_ms``.

    ``min_count`` floors the result so we always have a usable sample.
    """
    if not runs:
        return []
    sorted_desc = sorted(runs, key=lambda r: r.clear_time_ms, reverse=True)
    count = max(min_count, math.floor(len(runs) * percentile / 100))
    count = min(count, len(runs))
    return sorted_desc[:count]
