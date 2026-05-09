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


# ─── v2 (Blizzard-driven) ──────────────────────────────────────────────────
# Below: rewritten pipeline that consumes BlizzardRun directly. The old
# build_document / select_slowest_percentile (Run-typed) above stay for now;
# Task 13 will remove them once the new flow is fully wired in cli.py.

from collections import defaultdict

from jit_update.models import BlizzardRun


class BlizzardClientLike(Protocol):
    """Protocol matching what the pipeline needs from the Blizzard client."""

    def get_current_period_id(self) -> int: ...

    def get_connected_realms_index(self) -> list[int]: ...

    def get_leaderboard_runs(
        self,
        *,
        realm_id: int,
        dungeon_id: int,
        period_id: int,
        dungeon_slug: str,
    ) -> list[BlizzardRun]: ...


def discover_runs(
    blizz: BlizzardClientLike,
    *,
    dungeons: list[dict[str, Any]],
    levels: list[int],
) -> dict[str, dict[int, list[BlizzardRun]]]:
    """Iterate (realm, dungeon) for the current period, accumulate runs by (dungeon, level).

    Args:
        blizz: BlizzardClient (real or fake).
        dungeons: Dungeon descriptors with at least 'slug' and 'challenge_mode_id'.
        levels: Allowed keystone levels; runs outside this set are dropped.

    Returns:
        ``{dungeon_slug: {keystone_level: [BlizzardRun, ...]}}``
    """
    period_id = blizz.get_current_period_id()
    realm_ids = blizz.get_connected_realms_index()
    levels_set = set(levels)
    accumulator: dict[str, dict[int, list[BlizzardRun]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for dungeon in dungeons:
        slug = dungeon["slug"]
        dungeon_id = int(dungeon["challenge_mode_id"])
        for realm_id in realm_ids:
            runs = blizz.get_leaderboard_runs(
                realm_id=realm_id,
                dungeon_id=dungeon_id,
                period_id=period_id,
                dungeon_slug=slug,
            )
            for run in runs:
                if run.keystone_level not in levels_set:
                    continue
                accumulator[slug][run.keystone_level].append(run)

    return {slug: dict(levels_dict) for slug, levels_dict in accumulator.items()}


def select_slowest_percentile(  # type: ignore[misc]
    runs: list[BlizzardRun],
    percentile: int,
    min_count: int = 2,
) -> list[BlizzardRun]:
    """Return the slowest ``percentile`` % of runs by ``duration_ms``.

    Result count is ``max(min_count, floor(len(runs) * percentile / 100))``
    capped at ``len(runs)``. Runs are sorted by ``duration_ms`` descending
    (slowest first); the returned list is the first N entries of that sort.

    Raises:
        ValueError: if ``percentile`` is outside [0, 100].
    """
    if not 0 <= percentile <= 100:
        raise ValueError(f"percentile must be in [0, 100], got {percentile}")
    if not runs:
        return []
    count = max(min_count, math.floor(len(runs) * percentile / 100))
    count = min(count, len(runs))
    return sorted(runs, key=lambda r: r.duration_ms, reverse=True)[:count]


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
    Splits are normalized to length ``num_bosses`` (truncate or pad with 0).
    Runs whose splits are entirely zeros (no successful encounters at all) are
    skipped entirely.

    Args:
        raiderio: Raider.IO client implementing :class:`RaiderIOClientLike`.
        season: Season slug (e.g. ``"season-mn-1"``).
        dungeon_slug: Dungeon slug (e.g. ``"algethar-academy"``).
        levels_in_scope: Keystone levels to collect data for; runs outside this
            set are skipped without fetching their details.
        num_bosses: Expected number of bosses; splits are padded/truncated to
            this length.

    Returns:
        A dict mapping each keystone level that had qualifying runs to a list
        of per-run boss-split arrays.
    """
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
            details = RunDetails.model_validate(
                raiderio.get_run_details(season=season, run_id=run_id)
            )
        except Exception:
            continue
        if not details.encounters:
            continue
        splits = details.boss_splits_ms()
        normalized = [int(s) if s is not None else 0 for s in splits[:num_bosses]]
        while len(normalized) < num_bosses:
            normalized.append(0)
        if all(v == 0 for v in normalized):
            continue
        by_level[level].append(normalized)

    return dict(by_level)


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
        prev_known = next(
            (medians[j] for j in range(i - 1, -1, -1) if medians[j] > 0), 0
        )
        next_known = next(
            (medians[j] for j in range(i + 1, num_bosses) if medians[j] > 0),
            clear_time_median,
        )
        medians[i] = (prev_known + next_known) // 2
    return medians


def aggregate_cell(
    blizzard_runs: list[BlizzardRun],
    real_splits_at_level: list[list[int]],
    observed_ratios: list[float | None],
    num_bosses: int,
) -> ReferenceCell:
    """Build a ReferenceCell for one (dungeon, level) using three-tier splits source.

    Tier 1: real Raider.IO splits at this level → median per position
            (source="raiderio"). Falls through if the list is empty.
    Tier 2: synthesize from observed_ratios + clear_time_median
            (source="synthesized"). Falls through if all ratios are None.
    Tier 3: equidistant fallback (source="equidistant_fallback").

    Raises:
        ValueError: if ``blizzard_runs`` is empty.
    """
    from jit_update.splits_synthesis import synthesize_splits

    if not blizzard_runs:
        raise ValueError("aggregate_cell requires at least one BlizzardRun")
    clear_time_median = int(statistics.median(r.duration_ms for r in blizzard_runs))

    if real_splits_at_level:
        boss_splits = _median_per_position_with_backfill(
            real_splits_at_level, num_bosses, clear_time_median
        )
        source: str = "raiderio"
    elif any(r is not None for r in observed_ratios):
        boss_splits = synthesize_splits(clear_time_median, observed_ratios, num_bosses)
        source = "synthesized"
    else:
        boss_splits = [
            round(clear_time_median * (i + 1) / num_bosses) for i in range(num_bosses)
        ]
        source = "equidistant_fallback"

    return ReferenceCell(
        sample_size=len(blizzard_runs),
        clear_time_ms=clear_time_median,
        boss_splits_ms=boss_splits,
        splits_source=source,  # type: ignore[arg-type]
    )


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


def _bosses_block_from_static(dungeon: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the bosses array (Lua 1-indexed) from static data.

    Each entry: ``{ordinal: 0..n-1, slug, name}``. Ordinal is 0-indexed so
    the addon's existing access pattern (``boss_splits_ms[ord+1]``) keeps
    working.

    Falls back to placeholder entries if static data lacks a bosses array but
    declares ``num_bosses`` (so renderer output is at least non-empty).
    """
    bosses_in = dungeon.get("bosses") or []
    out: list[dict[str, Any]] = []
    for b in bosses_in:
        out.append({
            "ordinal": int(b.get("ordinal", 0)),
            "slug": b.get("slug", ""),
            "name": b.get("name", ""),
        })
    if not out and dungeon.get("num_bosses"):
        for i in range(int(dungeon["num_bosses"])):
            out.append({"ordinal": i, "slug": f"boss-{i+1}", "name": f"Boss {i+1}"})
    return out


def _extract_bosses_from_raiderio_runs(
    raiderio: RaiderIOClientLike,
    *,
    season: str,
    dungeon_slug: str,
) -> tuple[int, list[dict[str, Any]]]:
    """Extract num_bosses + bosses metadata from Raider.IO RunDetails.

    Hits ``/runs?page=0`` and walks the encounters of the first run with
    a populated ``logged_details.encounters`` list. Returns ``(num_bosses,
    bosses_list)`` where each boss is ``{ordinal, slug, name}`` (0-indexed
    ordinal) sorted by ordinal.

    If no run has logged encounters, returns ``(0, [])`` and the caller
    must fall back to a placeholder. The dungeon's static data does NOT
    expose num_bosses or bosses, so this enrichment is the only reliable
    source short of hard-coding per-dungeon defaults.
    """
    payload = raiderio.get_runs(season=season, region="world", dungeon=dungeon_slug, page=0)
    bosses_by_ordinal: dict[int, dict[str, Any]] = {}
    for r in payload.get("rankings", []):
        run = r.get("run", {})
        run_id = run.get("keystone_run_id")
        if run_id is None:
            continue
        try:
            details = RunDetails.model_validate(
                raiderio.get_run_details(season=season, run_id=run_id)
            )
        except Exception:
            continue
        if not details.encounters:
            continue
        for enc in details.encounters:
            ord_val = int(enc.boss.ordinal)
            if ord_val not in bosses_by_ordinal:
                bosses_by_ordinal[ord_val] = {
                    "ordinal": ord_val,
                    "slug": enc.boss.slug,
                    "name": enc.boss.name,
                }
        # Once we have a stable set of bosses, we can stop. But keep going if
        # different runs have different boss sets (some routes skip optionals).
        if bosses_by_ordinal and len(bosses_by_ordinal) >= 4:
            # Most M+ dungeons cap at 4 bosses; bail early to save calls.
            break
    bosses_list = sorted(bosses_by_ordinal.values(), key=lambda b: b["ordinal"])
    return len(bosses_list), bosses_list


def build_document_from_discovered(
    discovered: dict[str, dict[int, list[BlizzardRun]]],
    raiderio: RaiderIOClientLike,
    cache: Any,  # FileCache; typed Any to avoid circular import at type-check time
    config: Any,
    now: datetime,
) -> dict[str, Any]:
    """Assemble a Data.lua document dict (schema v2) from pre-discovered Blizzard runs.

    Multi-region merging is the caller's job (use ``merge_discovered``).

    Args:
        discovered: ``{dungeon_slug: {level: [BlizzardRun]}}`` (post-merge).
        raiderio:   Raider.IO client used for static data + ratio collection
                    + real-splits indexing.
        cache:      FileCache instance for the ratios cache (caller controls
                    its TTL, recommended 7 days per spec).
        config:     A jit_update Config (or duck-compatible) exposing
                    ``raiderio.expansion_id``, ``raiderio.season``,
                    ``scope.levels``, ``scope.min_sample``,
                    ``scope.slowest_percentile``.
        now:        Timestamp embedded in ``meta.generated_at``.

    Returns:
        A dict matching Data.lua schema v2:
        ``{"meta": {...}, "dungeons": {slug: {keystone_timer_ms, bosses, levels: {L: cell}}}}``
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
        timer_ms = int(dungeon["keystone_timer_seconds"]) * 1000

        # Extract num_bosses + bosses metadata (static_data doesn't expose them)
        num_bosses, bosses_block = _extract_bosses_from_raiderio_runs(
            raiderio, season=config.raiderio.season, dungeon_slug=slug,
        )
        if num_bosses == 0:
            # Fallback: 4 bosses with placeholder names (matches v1 fallback)
            num_bosses = 4
            bosses_block = [
                {"ordinal": i, "slug": f"boss-{i+1}", "name": f"Boss {i+1}"}
                for i in range(num_bosses)
            ]

        observed_ratios = collect_observed_ratios_cached(
            raiderio, cache, season=config.raiderio.season, dungeon_slug=slug,
            num_bosses=num_bosses,
        )

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
            sample = select_slowest_percentile(
                runs,
                percentile=config.scope.slowest_percentile,
                min_count=2,
            )
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
            "challenge_mode_id": int(dungeon.get("challenge_mode_id", 0)),
            "num_bosses": num_bosses,
            "short_name": dungeon.get("short_name", ""),
            "timer_ms": timer_ms,
            "bosses": bosses_block,
            "levels": levels_block,
        }

    return document
