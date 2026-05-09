"""Typer-based CLI for jit_update."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from jit_update.blizzard import BlizzardClient
from jit_update.cache import FileCache
from jit_update.config import load_config
from jit_update.lua_renderer import render_data_lua
from jit_update.pipeline import (
    BlizzardClientLike,
    build_document_from_discovered,
    discover_runs,
    merge_discovered,
)
from jit_update.raiderio import RaiderIOClient
from jit_update.rate_limiter import RateLimiter

app = typer.Typer(
    add_completion=False,
    help="Generate JustInTime Data.lua from Raider.IO",
    invoke_without_command=False,
)
console = Console()


def build_blizzard_clients_from_env(
    *,
    regions: list[str],
    rate_per_second: float,
    cache: FileCache | None,
    timeout: float,
    max_retries: int,
) -> dict[str, BlizzardClient]:
    """Construct one BlizzardClient per region using env vars for OAuth.

    Args:
        regions: List of Battle.net regions (e.g. ``["eu", "us"]``).
        rate_per_second: Requests per second limit (converted to per-minute
            for :class:`~jit_update.rate_limiter.RateLimiter`).
        cache: Shared :class:`~jit_update.cache.FileCache` instance, or
            ``None`` to create a per-client fallback cache at ``.cache/blizzard``.
        timeout: HTTP timeout in seconds.
        max_retries: Maximum number of retry attempts per request.

    Returns:
        A dict mapping each region string to its :class:`BlizzardClient`.

    Raises:
        SystemExit(2): If ``BLIZZARD_CLIENT_ID`` or ``BLIZZARD_CLIENT_SECRET``
            is not set in the environment, printing a pointer to
            ``develop.battle.net``.
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
        rl = RateLimiter(
            rate_per_minute=rate_per_second * 60,
            capacity=int(rate_per_second * 2),
        )
        clients[region] = BlizzardClient(
            client_id=client_id,
            client_secret=client_secret,
            region=region,
            cache=cache or FileCache(Path(".cache/blizzard"), ttl_seconds=3600.0),
            rate_limiter=rl,
            timeout_seconds=timeout,
            max_retries=max_retries,
        )
    return clients


@app.command()
def run(
    config: Path = typer.Option(  # noqa: B008
        Path("jit_config.toml"),
        "--config",
        "-c",
        help="Path to jit_config.toml",
    ),
    out: Path | None = typer.Option(  # noqa: B008
        None,
        "--out",
        "-o",
        help="Override output path (defaults to config.output.data_lua_path).",
    ),
    only: str | None = typer.Option(
        None,
        "--only",
        help="Only emit this dungeon slug in the document (debug).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute and print stats; do not write Data.lua.",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Bypass HTTP cache (sets TTL to 0 for this run).",
    ),
) -> None:
    """Run the full data-generation pipeline."""
    cfg = load_config(config)

    cache_ttl = 0.0 if no_cache else cfg.raiderio.cache_ttl_seconds
    blizzard_cache_ttl = 0.0 if no_cache else cfg.blizzard.cache_ttl_seconds

    cache_root = config.parent / ".cache"
    http_cache = FileCache(cache_root / "raiderio", ttl_seconds=cache_ttl)
    ratios_cache = FileCache(
        cache_root / "ratios",
        ttl_seconds=0.0 if no_cache else 7 * 24 * 3600.0,
    )
    blizzard_cache = FileCache(cache_root / "blizzard", ttl_seconds=blizzard_cache_ttl)

    rl = RateLimiter(rate_per_minute=cfg.raiderio.rate_per_minute, capacity=10)
    raiderio = RaiderIOClient(
        base_url=cfg.raiderio.api_base,
        rate_limiter=rl,
        cache=http_cache,
        timeout_seconds=cfg.raiderio.timeout_seconds,
        max_retries=cfg.raiderio.max_retries,
    )

    blizzard_clients = build_blizzard_clients_from_env(
        regions=cfg.blizzard.regions,
        rate_per_second=cfg.blizzard.rate_per_second,
        cache=blizzard_cache,
        timeout=cfg.blizzard.timeout_seconds,
        max_retries=cfg.blizzard.max_retries,
    )

    try:
        # Discover runs per region, then merge
        partials: list[dict[str, dict[int, Any]]] = []
        static = raiderio.get_static_data(expansion_id=cfg.raiderio.expansion_id)
        season_obj = next(
            (s for s in static.get("seasons", []) if s.get("slug") == cfg.raiderio.season),
            None,
        )
        if season_obj is None:
            console.print(
                f"[red]ERROR: season {cfg.raiderio.season!r} not in Raider.IO static data[/red]"
            )
            raise typer.Exit(3)

        season_dungeons: list[dict[str, Any]] = season_obj["dungeons"]

        for region, blizz in blizzard_clients.items():
            console.print(f"[dim]Discovering runs for region: {region}[/dim]")
            partial = discover_runs(
                blizz,
                dungeons=season_dungeons,
                levels=list(cfg.scope.levels),
            )
            partials.append(partial)

        discovered = merge_discovered(*partials)

        document = build_document_from_discovered(
            discovered,
            raiderio,
            ratios_cache,
            cfg,
            datetime.now(tz=UTC),
        )
    finally:
        raiderio.close()

    if only is not None:
        document["dungeons"] = {k: v for k, v in document["dungeons"].items() if k == only}

    _print_summary(document)

    if dry_run:
        console.print("[yellow]--dry-run: Data.lua not written[/yellow]")
        raise typer.Exit(0)

    target = out if out is not None else (config.parent / cfg.output.data_lua_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_data_lua(document))
    console.print(f"[green]✓ wrote {target}[/green]")


def _print_summary(document: dict[str, Any]) -> None:
    """Print a human-readable summary of the generated document.

    Args:
        document: The document dict produced by build_document_from_discovered.
    """
    meta = document.get("meta", {})
    dungeons = document.get("dungeons", {})
    console.print(f"[bold]season:[/bold] {meta.get('season')}")
    console.print(f"[bold]generated_at:[/bold] {meta.get('generated_at')}")
    console.print(f"[bold]source:[/bold] {meta.get('source', 'unknown')}")
    console.print(f"[bold]dungeons:[/bold] {len(dungeons)}")
    for slug, dg in dungeons.items():
        cells = len(dg.get("levels", {}))
        console.print(f"  • {slug}: {cells} levels")
