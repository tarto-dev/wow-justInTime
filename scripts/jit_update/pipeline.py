"""Pipeline orchestration: fetch → filter → sample → aggregate."""

from __future__ import annotations

import math
import statistics
from typing import Any, Protocol

from jit_update.models import ReferenceCell, Run, RunDetails


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
    """Paginate /mythic-plus/runs and return matching timed runs.

    Filters client-side on:
      * mythic_level == target_level
      * weekly_modifiers combo == target_affix_combo
      * is_timed (num_chests >= 1)

    Stops *after the page on which* we reach `min_sample` matches, or after
    `max_pages` pages consumed (whichever comes first). The returned list may
    therefore exceed `min_sample` (extra samples are statistically welcome).

    **Production caveat (hypothesis #6 from design spec)**: Raider.IO's /runs
    endpoint sorts globally by score, with high-level keys at the top. For
    *low* target levels (+2..+8), matching runs sit deep in the leaderboard
    behind thousands of high-level runs, and `max_pages` may be exhausted
    before any matches are found. Callers should handle the empty-result case
    by skipping the cell (see jit_update.config.scope.min_sample) and accept
    that very low keys may have insufficient samples in v1.
    """
    matched: list[Run] = []
    for page in range(max_pages):
        payload = client.get_runs(season=season, region=region, dungeon=dungeon, page=page)
        rankings = payload.get("rankings")
        if rankings is None:
            # 200 OK but no rankings key — likely an error envelope.
            raise RuntimeError(
                f"unexpected /runs payload (no 'rankings' key) for {dungeon} page {page}"
            )
        if not isinstance(rankings, list):
            raise RuntimeError(
                f"unexpected /runs payload (rankings not a list) for {dungeon} page {page}"
            )
        if not rankings:
            break  # legitimate end of results
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

    The result count is ``max(min_count, floor(len(runs) * percentile / 100))``
    clamped to ``len(runs)``. So if ``len(runs) < min_count``, the function
    returns all available runs (fewer than ``min_count``) — the floor is a
    target, not a guarantee. Returns ``[]`` if ``runs`` is empty.

    Raises ``ValueError`` if ``percentile`` is outside [0, 100].
    """
    if not 0 <= percentile <= 100:
        raise ValueError(f"percentile must be in [0, 100], got {percentile}")
    if not runs:
        return []
    sorted_desc = sorted(runs, key=lambda r: r.clear_time_ms, reverse=True)
    count = max(min_count, math.floor(len(runs) * percentile / 100))
    count = min(count, len(runs))
    return sorted_desc[:count]


def compute_reference_cell(details: list[RunDetails], num_bosses: int) -> ReferenceCell | None:
    """Aggregate per-boss split medians and clear-time median.

    ``num_bosses`` is the dungeon's boss count (from static data); used to
    pad/trim per-run splits to a stable length.

    Returns ``None`` if no input runs. For bosses with no successful encounter
    in any input run, the median is backfilled by linear interpolation between
    known neighboring bosses (or against ``clear_time_median`` at the end).
    """
    if not details:
        return None

    per_boss: list[list[int]] = [[] for _ in range(num_bosses)]
    for d in details:
        splits = d.boss_splits_ms()
        for idx in range(num_bosses):
            if idx < len(splits) and splits[idx] is not None:
                per_boss[idx].append(int(splits[idx]))  # type: ignore[arg-type]

    boss_medians: list[int] = []
    for idx in range(num_bosses):
        values = per_boss[idx]
        if not values:
            boss_medians.append(0)  # placeholder; backfilled below
        else:
            boss_medians.append(int(statistics.median(values)))

    clear_times = [int(d.clear_time_ms) for d in details]
    clear_time_median = int(statistics.median(clear_times))

    for idx in range(num_bosses):
        if boss_medians[idx] != 0:
            continue
        prev_known = next(
            (boss_medians[j] for j in range(idx - 1, -1, -1) if boss_medians[j] > 0),
            0,
        )
        next_known = next(
            (boss_medians[j] for j in range(idx + 1, num_bosses) if boss_medians[j] > 0),
            clear_time_median,
        )
        boss_medians[idx] = (prev_known + next_known) // 2

    return ReferenceCell(
        sample_size=len(details),
        clear_time_ms=clear_time_median,
        boss_splits_ms=boss_medians,
    )
