"""Typer-based CLI for jit_update."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from jit_update.cache import FileCache
from jit_update.config import load_config
from jit_update.lua_renderer import render_data_lua
from jit_update.pipeline import build_document
from jit_update.raiderio import RaiderIOClient
from jit_update.rate_limiter import RateLimiter

app = typer.Typer(
    add_completion=False,
    help="Generate JustInTime Data.lua from Raider.IO",
    invoke_without_command=False,
)
console = Console()


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

    cache_root = config.parent / ".cache" / "raiderio"
    cache = FileCache(
        cache_root,
        ttl_seconds=0 if no_cache else cfg.raiderio.cache_ttl_seconds,
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
        document = build_document(client=client, config=cfg, now=datetime.now(tz=UTC))
    finally:
        client.close()

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
        document: The document dict produced by build_document.
    """
    meta = document.get("meta", {})
    dungeons = document.get("dungeons", {})
    console.print(f"[bold]season:[/bold] {meta.get('season')}")
    console.print(f"[bold]generated_at:[/bold] {meta.get('generated_at')}")
    console.print(f"[bold]dungeons:[/bold] {len(dungeons)}")
    for slug, dg in dungeons.items():
        cells = sum(len(combos) for combos in dg.get("levels", {}).values())
        console.print(f"  • {slug}: {len(dg.get('levels', {}))} levels, {cells} cells")
