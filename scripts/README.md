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
