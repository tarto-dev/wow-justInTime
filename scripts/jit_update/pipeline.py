"""Pipeline orchestration: fetch → filter → sample → aggregate."""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Any, Protocol

from jit_update.config import Config
from jit_update.models import ReferenceCell, Run, RunDetails
from jit_update.raiderio import RaiderIOError


class RaiderIOClientLike(Protocol):
    """Protocol matching what the pipeline needs from the HTTP client."""

    def get_static_data(self, expansion_id: int) -> dict[str, Any]: ...

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

    If every boss has no successful encounter across all runs, the backfill
    produces a synthetic monotonically increasing ladder anchored to
    ``clear_time_median``. This is plausible filler rather than meaningful
    data; callers should treat extremely-uncovered cells with skepticism.
    """
    if not details:
        return None

    per_boss: list[list[int]] = [[] for _ in range(num_bosses)]
    for d in details:
        splits = d.boss_splits_ms()
        for idx in range(num_bosses):
            if idx >= len(splits):
                continue
            val = splits[idx]
            if val is not None:
                per_boss[idx].append(int(val))

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


DEFAULT_AFFIX_MAP: dict[int, str] = {
    9: "tyrannical",
    10: "fortified",
    147: "xalataths-guile",
}


def _affix_combos_to_query(affix_map: dict[int, str]) -> list[str]:
    """Generate the affix combos to query for Midnight Season 1.

    MN1 activates Fortified, Tyrannical, and Xal'atath's Guile simultaneously
    every week (no alternation). There is only one combo.

    Returns the alphabetically-sorted combo slugs.
    """
    all_slugs = sorted(affix_map.values())
    return ["-".join(all_slugs)]


def build_document(
    client: RaiderIOClientLike,
    config: Config,
    now: datetime,
) -> dict[str, Any]:
    """Run the full pipeline and assemble the Data.lua document dict.

    Fetches static data + runs + run details, aggregates per
    (dungeon x level x affix_combo), and returns a dict ready for the Lua renderer.

    Args:
        client: Raider.IO client implementing :class:`RaiderIOClientLike`.
        config: Fully-validated pipeline configuration.
        now: Timestamp to embed in the document's ``generated_at`` field.

    Returns:
        A nested dict with ``meta``, ``affix_id_to_slug``, and ``dungeons`` keys.

    Raises:
        RaiderIOError: If the configured season is absent from static data.
    """
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
                cell = compute_reference_cell(details_list, num_bosses=int(dg.get("num_bosses", 4)))
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
