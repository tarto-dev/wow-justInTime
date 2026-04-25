# JustInTime — Plan B : Addon Lua

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the JustInTime WoW addon Lua side: load `Data.lua` reference, track player runs live, compute pace deltas at boss kills, render the CD-1 overlay + chat triggers + critical alerts, and expose all configuration via slash commands and Settings panel.

**Architecture:** 9 Lua files in `addon/JustInTime/`, each with one clear responsibility, loaded in dependency order via the `.toc`. Pure-logic modules (`PaceEngine`, `State`) expose API on `NS.<Module>` namespace and are unit-testable via a `/jit test` debug slash command. Event-driven components (`EventTracker`, `Overlay`) are smoke-tested manually in WoW.

**Tech Stack:** WoW Retail Lua 5.1 (12.0 Midnight, Interface 120001). No external libraries (no Ace3, no LibStub). Frame templates: `BackdropTemplate`. SavedVariables per-account.

**Working directory:** `/home/tarto/projects/wowAddons/justInTime`

**Branch:** `main` only. Per Claralicious workflow: never push (master is release-only).

**Commit policy:** Conventional Commits + gitmoji per CLAUDE.md global, atomic per task.

---

## Real-world API discoveries from Plan A (constraints for the addon)

These were validated against the live Raider.IO API and embedded in the generated `Data.lua`. The Lua addon must respect them:

1. **Boss `ordinal` is 0-based** in `Data.lua.dungeons[slug].bosses[i].ordinal` (e.g., values 0, 1, 2, 3 for a 4-boss dungeon). When `ENCOUNTER_END` fires in WoW, we look up the ordinal by `wow_encounter_id` matching.
2. **MN1 has ONE active affix combo per week**: `fortified-tyrannical-xalataths-guile`. `C_MythicPlus.GetCurrentAffixes()` returns 3 affix IDs simultaneously (Fortified=10, Tyrannical=9, Xal'atath's Guile=147). The addon resolves these to slugs via `Data.lua.affix_id_to_slug` and joins alphabetically.
3. **Boss splits are by ordinal, not by kill-order**. The reference `boss_splits_ms` array (Lua 1-indexed) corresponds 1:1 to the `bosses` table by position. Position `i` in both lists is the same boss. The split values may NOT be monotonically increasing — kill order in real runs varies.
4. **Data.lua coverage is sparse**: only levels +18..+20 currently, only one affix combo. The addon must gracefully handle "no reference data for this (level, combo)" and fall back to dungeon-timer-only feedback. (Coverage will improve when the script runs with higher `max_pages_per_query`.)

## File structure

```
addon/JustInTime/
├── JustInTime.toc           # ordre de chargement strict (deps en haut)
├── Locales.lua              # FR + EN, étendu avec ~40 strings
├── Data.lua                 # généré par Python, déclaratif (existe déjà)
├── Config.lua               # SavedVariables defaults + Settings panel étendu
├── State.lua                # NEW: SavedVariables management + session lifecycle
├── PaceEngine.lua           # NEW: affix combo, mapID lookup, ref resolver, delta/ETA
├── EventTracker.lua         # NEW: hook CHALLENGE_MODE_*, ENCOUNTER_END
├── ChatPrinter.lua          # NEW: triggers boss kill / key end / threshold cross
├── Overlay.lua              # NEW: CD-1 frame (gradient bar + pips + delta + rows)
└── Core.lua                 # bootstrap + slash commands étendus + tests dispatch
```

`.toc` final order:
```
Locales.lua
Data.lua
Config.lua
State.lua
PaceEngine.lua
EventTracker.lua
ChatPrinter.lua
Overlay.lua
Core.lua
```

## Test strategy (no pytest in WoW Lua)

- **Pure-logic modules** (`PaceEngine`, `State`, `Config` resolvers) expose deterministic functions on `NS.<Module>`.
- A `/jit test` slash command runs synthetic test cases via inline `assert()` calls. Each test prints `[JIT][test] PASS: <name>` or `[JIT][test] FAIL: <name> expected X, got Y`. Tests run in-game on demand.
- **Event-driven components** (`EventTracker`, `Overlay`, `ChatPrinter`) — smoke-tested manually in-game during a real or test M+ key.
- **Schema validation at load** — `Data.lua` structure validated by `Core.lua` at `ADDON_LOADED`. Mismatch logs `[JIT] ⚠ Data.lua schema invalid` and disables overlay public mode.

## Conventions

- Namespace: `local addonName, NS = ...` at the top of every module file.
- All locals: NEVER assign to `_G` directly except for `JustInTimeDB` (SavedVariables) and slash command globals (`SLASH_JIT1`, `SlashCmdList.JIT`).
- Use `string.format` for formatting, not `..` chains for performance-sensitive code paths (overlay updates).
- `OnUpdate` throttling: register the script only when active (`C_ChallengeMode.IsChallengeModeActive()`); unregister when the key ends. Throttle to 10 Hz.
- Comments: English only (per CLAUDE.md).
- Locales: French default, English fallback per `GetLocale()`.

---

## Task 1 — Extend Locales.lua + .toc declares new modules

**Files:**
- Modify: `addon/JustInTime/Locales.lua`
- Modify: `addon/JustInTime/JustInTime.toc`

- [ ] **Step 1: Replace `addon/JustInTime/Locales.lua` with the extended version**

Use Write tool. Full content:

```lua
local addonName, NS = ...

local locale = GetLocale()
local L = setmetatable({}, { __index = function(_, k) return k end })

-- Affix slug → localized display name (used in chat / overlay tooltips).
-- Falls back to the slug itself when missing.
local AFFIX_DISPLAY_FR = {
    fortified = "Fortifiée",
    tyrannical = "Tyrannique",
    ["xalataths-guile"] = "Ruse de Xal'atath",
}

local AFFIX_DISPLAY_EN = {
    fortified = "Fortified",
    tyrannical = "Tyrannical",
    ["xalataths-guile"] = "Xal'atath's Guile",
}

local fr = {
    ADDON_LOADED          = "%s chargé. /jit pour les options.",
    FRAME_TITLE           = "JustInTime",
    SLASH_HELP            = "Commandes : /jit | /jit show | /jit hide | /jit lock | /jit unlock | /jit mode <public|fastest|recent|median> | /jit reset | /jit help | /jit test",
    SLASH_UNKNOWN         = "Commande inconnue : %s. /jit help",

    REF_NONE              = "réf. indispo",
    REF_PUBLIC_LABEL      = "P10 publique",
    REF_PERSO_FASTEST     = "Mes runs (la + rapide)",
    REF_PERSO_RECENT      = "Mes runs (la + récente)",
    REF_PERSO_MEDIAN      = "Mes runs (médiane)",

    BOSS_KILL_TRIGGER     = "%s tué — %s vs %s",   -- e.g. "Vexamus tué — 1m23 d'avance vs P10"
    KEY_END_TIMED         = "Run terminée %s ✓ timée — %s vs %s",
    KEY_END_DEPLETED      = "Run dépletée %s ✗ — %s vs %s",
    THRESHOLD_AHEAD       = "tu viens de basculer en avance (+%s)",
    THRESHOLD_BEHIND      = "tu viens de basculer en retard (−%s)",
    CRITICAL_DEPLETE      = "⚠ projection : déplate prévue à %s (%s) — envisage un reset",

    DELTA_AHEAD           = "%s d'avance",
    DELTA_BEHIND          = "%s de retard",
    DELTA_ZERO            = "à l'heure",

    OVERLAY_LABEL_ELAPSED = "Écoulé",
    OVERLAY_LABEL_TIMER   = "Timer",
    OVERLAY_LABEL_ETA     = "ETA",
    OVERLAY_LABEL_LAST    = "Last split",
    OVERLAY_LABEL_REF     = "Réf",
    OVERLAY_REF_NONE      = "réf indispo",

    PANEL_REF_HEADER      = "Référence",
    PANEL_REF_PUBLIC      = "Publique (P10 worst-timed)",
    PANEL_REF_FASTEST     = "Mes runs : la plus rapide",
    PANEL_REF_RECENT      = "Mes runs : la plus récente",
    PANEL_REF_MEDIAN      = "Mes runs : médiane",
    PANEL_IGNORE_AFFIXES  = "Ignorer les affixes (élargir le sample)",

    PANEL_OVERLAY_HEADER  = "Overlay graphique",
    PANEL_OVERLAY_ALWAYS  = "Toujours visible",
    PANEL_OVERLAY_POPUP   = "Popup transitoire (6s post-boss kill)",
    PANEL_OVERLAY_LOCK    = "Verrouiller la position",
    PANEL_OVERLAY_RESET   = "Réinitialiser la position",

    PANEL_CHAT_HEADER     = "Mode texte (chat)",
    PANEL_CHAT_BOSS_KILL  = "Print à chaque boss kill",
    PANEL_CHAT_KEY_END    = "Récap en fin de clé",
    PANEL_CHAT_THRESHOLD  = "Alerte au passage de seuil (vert ↔ rouge)",

    PANEL_CRIT_HEADER     = "Alerte « tu vas déplate »",
    PANEL_CRIT_VISUAL     = "Visuel (pulsation rouge)",
    PANEL_CRIT_CHAT       = "Chat warning",
    PANEL_CRIT_SOUND      = "Son d'alerte",

    PANEL_DATA_HEADER     = "Données",
    PANEL_DATA_GENERATED  = "Référence générée le : %s (il y a %d jours) %s",
    PANEL_DATA_RESET_RUNS = "Effacer mes runs (confirmation)",
    PANEL_DATA_NONE       = "Pas de Data.lua",

    DATA_STALE            = "⚠ données vieilles de %d jours, considère relancer le script",
    DATA_MISSING          = "⚠ Data.lua manquant — lance le script Python",
    DATA_SCHEMA_INVALID   = "⚠ Data.lua schéma invalide — overlay public désactivé",

    NO_PERSO_RUNS         = "pas encore de run perso ici, fallback sur public",
    NO_REF_AT_ALL         = "réf indispo (cellule vide)",

    CONFIRM_RESET_RUNS    = "Effacer toutes tes runs perso ? (impossible à annuler)",
    BTN_YES               = "Oui",
    BTN_NO                = "Non",
    RESET_DONE            = "Runs perso effacées (%d entrées)",

    TEST_HEADER           = "JustInTime self-tests",
    TEST_PASS             = "PASS: %s",
    TEST_FAIL             = "FAIL: %s — attendu %s, obtenu %s",
    TEST_SUMMARY          = "%d/%d tests passent",
}

local en = {
    ADDON_LOADED          = "%s loaded. Type /jit for options.",
    FRAME_TITLE           = "JustInTime",
    SLASH_HELP            = "Commands: /jit | /jit show | /jit hide | /jit lock | /jit unlock | /jit mode <public|fastest|recent|median> | /jit reset | /jit help | /jit test",
    SLASH_UNKNOWN         = "Unknown command: %s. /jit help",

    REF_NONE              = "ref unavailable",
    REF_PUBLIC_LABEL      = "P10 public",
    REF_PERSO_FASTEST     = "My runs (fastest)",
    REF_PERSO_RECENT      = "My runs (most recent)",
    REF_PERSO_MEDIAN      = "My runs (median)",

    BOSS_KILL_TRIGGER     = "%s killed — %s vs %s",
    KEY_END_TIMED         = "Run timed %s ✓ — %s vs %s",
    KEY_END_DEPLETED      = "Run depleted %s ✗ — %s vs %s",
    THRESHOLD_AHEAD       = "you just moved ahead (+%s)",
    THRESHOLD_BEHIND      = "you just fell behind (−%s)",
    CRITICAL_DEPLETE      = "⚠ projection: deplete predicted at %s (%s) — consider reset",

    DELTA_AHEAD           = "%s ahead",
    DELTA_BEHIND          = "%s behind",
    DELTA_ZERO            = "on pace",

    OVERLAY_LABEL_ELAPSED = "Elapsed",
    OVERLAY_LABEL_TIMER   = "Timer",
    OVERLAY_LABEL_ETA     = "ETA",
    OVERLAY_LABEL_LAST    = "Last split",
    OVERLAY_LABEL_REF     = "Ref",
    OVERLAY_REF_NONE      = "ref unavailable",

    PANEL_REF_HEADER      = "Reference",
    PANEL_REF_PUBLIC      = "Public (P10 worst-timed)",
    PANEL_REF_FASTEST     = "My runs: fastest",
    PANEL_REF_RECENT      = "My runs: most recent",
    PANEL_REF_MEDIAN      = "My runs: median",
    PANEL_IGNORE_AFFIXES  = "Ignore affixes (widen sample)",

    PANEL_OVERLAY_HEADER  = "Graphic overlay",
    PANEL_OVERLAY_ALWAYS  = "Always visible",
    PANEL_OVERLAY_POPUP   = "Popup transient (6s after boss kill)",
    PANEL_OVERLAY_LOCK    = "Lock position",
    PANEL_OVERLAY_RESET   = "Reset position",

    PANEL_CHAT_HEADER     = "Text mode (chat)",
    PANEL_CHAT_BOSS_KILL  = "Print on each boss kill",
    PANEL_CHAT_KEY_END    = "Key end recap",
    PANEL_CHAT_THRESHOLD  = "Alert on threshold cross (green ↔ red)",

    PANEL_CRIT_HEADER     = "Deplete-imminent alerts",
    PANEL_CRIT_VISUAL     = "Visual (red pulse)",
    PANEL_CRIT_CHAT       = "Chat warning",
    PANEL_CRIT_SOUND      = "Sound alert",

    PANEL_DATA_HEADER     = "Data",
    PANEL_DATA_GENERATED  = "Reference generated at: %s (%d days ago) %s",
    PANEL_DATA_RESET_RUNS = "Erase my runs (confirmation)",
    PANEL_DATA_NONE       = "No Data.lua",

    DATA_STALE            = "⚠ data is %d days old, consider regenerating",
    DATA_MISSING          = "⚠ Data.lua missing — run the Python script",
    DATA_SCHEMA_INVALID   = "⚠ Data.lua schema invalid — public overlay disabled",

    NO_PERSO_RUNS         = "no personal runs here yet, falling back to public",
    NO_REF_AT_ALL         = "ref unavailable (empty cell)",

    CONFIRM_RESET_RUNS    = "Erase all your personal runs? (cannot be undone)",
    BTN_YES               = "Yes",
    BTN_NO                = "No",
    RESET_DONE            = "Personal runs erased (%d entries)",

    TEST_HEADER           = "JustInTime self-tests",
    TEST_PASS             = "PASS: %s",
    TEST_FAIL             = "FAIL: %s — expected %s, got %s",
    TEST_SUMMARY          = "%d/%d tests pass",
}

local active = (locale == "enUS" or locale == "enGB") and en or fr
for k, v in pairs(active) do L[k] = v end

NS.L = L
NS.AffixDisplayFR = AFFIX_DISPLAY_FR
NS.AffixDisplayEN = AFFIX_DISPLAY_EN

function NS.AffixDisplayName(slug)
    local map = (locale == "enUS" or locale == "enGB") and AFFIX_DISPLAY_EN or AFFIX_DISPLAY_FR
    return map[slug] or slug
end
```

- [ ] **Step 2: Update `addon/JustInTime/JustInTime.toc` to declare new modules + flame Title + Icon**

Use Edit tool. Replace the file contents with:

```
## Interface: 120001
## Title: |cFFFFCC66J|r|cFFFFBB60u|r|cFFFFAA5As|r|cFFFF9955t|r|cFFFF884FI|r|cFFFF7749n|r|cFFFF6644T|r|cFFFF553Ei|r|cFFFF4439m|r|cFFFF3333e|r
## IconTexture: Interface\Icons\Spell_Nature_LightningBolt
## Notes: Lightweight raid timing helper for WoW Retail
## Notes-frFR: Tracker de tempo pour clés mythique+
## Author: Claralicious_
## Version: 0.1.0
## X-Category: Mythic+
## SavedVariables: JustInTimeDB

Locales.lua
Data.lua
Config.lua
State.lua
PaceEngine.lua
EventTracker.lua
ChatPrinter.lua
Overlay.lua
Core.lua
```

The Title uses per-letter color codes interpolated from `#FFCC66` (light orange) to `#FF3333` (bright red) to produce a flame effect across "JustInTime" — visible in the AddOns list and in the chat when WoW prints the addon name.

The icon (`Interface\Icons\Spell_Nature_LightningBolt`) is a stock yellow lightning bolt — fits the "just in time" / fast / electric theme. The user can later swap to a custom 64×64 BLP/TGA at `Interface\AddOns\JustInTime\icon.tga` and update the path; not v1.

(`UI.lua` from the scaffold is removed — it's replaced by `Overlay.lua`. Don't delete the file from disk yet; we'll do that explicitly in the commit.)

- [ ] **Step 3: Delete the old scaffold `UI.lua`** (replaced by `Overlay.lua` later in this plan)

```bash
git rm addon/JustInTime/UI.lua
```

- [ ] **Step 4: Commit**

```bash
git add addon/JustInTime/Locales.lua addon/JustInTime/JustInTime.toc
git commit -m "🌐 i18n(addon): extend Locales FR+EN, declare new modules in toc, drop UI.lua"
```

---

## Task 2 — State.lua: SavedVariables management + session lifecycle

**Files:**
- Create: `addon/JustInTime/State.lua`

The State module owns `JustInTimeDB`. It exposes:
- `State.Init()` — called at `ADDON_LOADED`, ensures defaults and schema migration
- `State.Config()` → returns `JustInTimeDB.config` (live reference)
- `State.SetActiveSession(dungeon_slug, level, affix_combo, started_epoch)` — start a key
- `State.RecordBossKill(ordinal, elapsed_ms)` — append a boss split to the active session
- `State.SnapshotActiveSession()` — flushes current session state (called after each boss kill)
- `State.FinalizeActiveSession(timed, depleted, clear_time_ms)` — archive into `runs[]` with full metadata
- `State.DiscardActiveSession()` — clear without archiving (abandon)
- `State.GetActiveSession()` → table or nil
- `State.GetPersonalRuns(dungeon_slug, level, affix_combo)` → list of runs (for perso reference modes)
- `State.ClearAllRuns()` — wipes the runs list (for /jit reset)
- `State.GetCharacterDescriptor()` — returns `{ name, realm, class }` of the player

- [ ] **Step 1: Create `addon/JustInTime/State.lua`**

Use Write tool. Full content:

```lua
-- State module: owns JustInTimeDB (SavedVariables).
-- Manages per-account persistence, active session lifecycle, and run archive.
local addonName, NS = ...

local State = {}

local SCHEMA_VERSION = 1

-- Defaults; deep-merged into JustInTimeDB at Init() so new fields appear in
-- existing saves without wiping user data.
local DEFAULTS = {
    schema_version = SCHEMA_VERSION,
    config = {
        reference_mode    = "public",        -- public | perso_fastest | perso_recent | perso_median
        ignore_affixes    = false,
        overlay_visibility = "always",       -- always | popup
        overlay_position  = { x = 0, y = 0, locked = false, anchor = "TOPRIGHT", relAnchor = "TOPRIGHT" },
        triggers = {
            chat_boss_kill        = true,
            chat_key_end          = true,
            chat_threshold_cross  = false,
        },
        critical_alerts = {
            visual = true,
            chat   = true,
            sound  = false,
        },
    },
    runs = {},
    active_session = nil,  -- { dungeon_slug, level, affix_combo, started_epoch, boss_kills = { [ord] = ms }, snapshot_at_epoch }
}

local function deepMerge(target, defaults)
    for k, v in pairs(defaults) do
        if target[k] == nil then
            if type(v) == "table" then
                target[k] = {}
                deepMerge(target[k], v)
            else
                target[k] = v
            end
        elseif type(v) == "table" and type(target[k]) == "table" then
            deepMerge(target[k], v)
        end
    end
end

function State.Init()
    _G.JustInTimeDB = _G.JustInTimeDB or {}
    local db = _G.JustInTimeDB

    -- Schema version check (best-effort migration: nuke runs if mismatch, keep config)
    if db.schema_version and db.schema_version ~= SCHEMA_VERSION then
        db.runs = {}
        db.active_session = nil
    end

    deepMerge(db, DEFAULTS)
    db.schema_version = SCHEMA_VERSION
end

function State.Config()
    return _G.JustInTimeDB.config
end

function State.SetActiveSession(dungeon_slug, level, affix_combo, started_epoch)
    _G.JustInTimeDB.active_session = {
        dungeon_slug      = dungeon_slug,
        level             = level,
        affix_combo       = affix_combo,
        started_epoch     = started_epoch,
        boss_kills        = {},
        snapshot_at_epoch = started_epoch,
    }
end

function State.RecordBossKill(ordinal, elapsed_ms)
    local s = _G.JustInTimeDB.active_session
    if not s then return end
    s.boss_kills[ordinal] = elapsed_ms
end

function State.SnapshotActiveSession()
    local s = _G.JustInTimeDB.active_session
    if not s then return end
    s.snapshot_at_epoch = time()  -- WoW global: epoch seconds
end

function State.FinalizeActiveSession(timed, depleted, clear_time_ms)
    local s = _G.JustInTimeDB.active_session
    if not s then return nil end

    local boss_splits_ms = {}
    -- Convert ordinal-keyed sparse table to array indexed by ordinal+1 (Lua 1-based)
    -- Walk by sorted ordinal so result array preserves "by-ordinal" indexing.
    local ordinals = {}
    for ord, _ in pairs(s.boss_kills) do
        ordinals[#ordinals + 1] = ord
    end
    table.sort(ordinals)
    for _, ord in ipairs(ordinals) do
        boss_splits_ms[ord + 1] = s.boss_kills[ord]
    end

    local char = State.GetCharacterDescriptor()
    local run = {
        run_id          = string.format("%d-%s-%d", s.started_epoch, s.dungeon_slug, s.level),
        completed_at    = date("!%Y-%m-%dT%H:%M:%SZ"),  -- WoW global, UTC ISO
        dungeon_slug    = s.dungeon_slug,
        level           = s.level,
        affix_combo     = s.affix_combo,
        clear_time_ms   = clear_time_ms,
        timed           = timed,
        depleted        = depleted,
        boss_splits_ms  = boss_splits_ms,
        boss_kills_ord  = s.boss_kills,  -- preserve ordinal map for debugging
        character       = char,
    }
    table.insert(_G.JustInTimeDB.runs, run)
    _G.JustInTimeDB.active_session = nil
    return run
end

function State.DiscardActiveSession()
    _G.JustInTimeDB.active_session = nil
end

function State.GetActiveSession()
    return _G.JustInTimeDB.active_session
end

function State.GetPersonalRuns(dungeon_slug, level, affix_combo)
    local matches = {}
    for _, r in ipairs(_G.JustInTimeDB.runs) do
        if r.dungeon_slug == dungeon_slug and r.level == level then
            if affix_combo == nil or r.affix_combo == affix_combo then
                if r.timed then
                    matches[#matches + 1] = r
                end
            end
        end
    end
    return matches
end

function State.ClearAllRuns()
    local n = #_G.JustInTimeDB.runs
    _G.JustInTimeDB.runs = {}
    return n
end

function State.GetCharacterDescriptor()
    local name = UnitName("player")  -- WoW global
    local realm = GetRealmName()      -- WoW global
    local _, classToken = UnitClass("player")  -- WoW global
    return {
        name = name or "?",
        realm = realm or "?",
        class = classToken and classToken:lower() or "?",
    }
end

NS.State = State
```

- [ ] **Step 2: Verify the file is valid Lua**

```bash
lua5.4 -e 'loadfile("addon/JustInTime/State.lua")()' 2>&1 || echo "(no lua interpreter, skipping syntactic check)"
```

If a Lua interpreter isn't available locally, do a basic grep sanity check:

```bash
grep -E "^(function State\.|NS\.State)" addon/JustInTime/State.lua | wc -l
```

Expected: 11 (10 functions + the namespace export).

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/State.lua
git commit -m "✨ feat(addon): State module — SavedVariables + session lifecycle"
```

---

## Task 3 — PaceEngine.lua: affix combo, mapID, ref resolver, delta/ETA

**Files:**
- Create: `addon/JustInTime/PaceEngine.lua`

The PaceEngine has two phases of API:
1. **Resolvers** — pure lookups against `Data.lua` (sync, no state mutation)
2. **Pace computation** — anchor-based delta with linear drift (per design spec §4.4)

API:
- `PaceEngine.Init()` — builds `mapIdToSlug` lookup once at load
- `PaceEngine.MapIdToSlug(map_id)` → slug or nil
- `PaceEngine.ResolveAffixCombo(affix_ids)` → string slug (e.g., `"fortified-tyrannical-xalataths-guile"`)
- `PaceEngine.GetReferenceForActive()` → `{ boss_splits_ms, clear_time_ms, num_bosses, source_label, affix_combo_used }` or `nil`
- `PaceEngine.ComputePace(elapsed_ms, your_kills_by_ord, ref)` → `{ delta_ms, projected_finish_ms, last_anchor_ord, deplete_projected, normalized }`
- `PaceEngine.SortedRefSplits(ref_splits)` → table `{ {ord=K, split=T}, ... }` sorted ascending by `T`
- `PaceEngine.AggregatePersonalRuns(runs, mode)` → synthetic ref `{ boss_splits_ms, clear_time_ms, num_bosses }` from a list of `runs` according to mode (`fastest`|`recent`|`median`)

- [ ] **Step 1: Create `addon/JustInTime/PaceEngine.lua`**

Use Write tool. Full content:

```lua
-- PaceEngine: pure-logic module for pace computation against Data.lua reference.
-- All functions are deterministic given inputs; no global side-effects beyond the
-- mapIdToSlug lookup populated once at Init().
local addonName, NS = ...

local PaceEngine = {}

local mapIdToSlug = {}
local affixIdToSlug = {}

function PaceEngine.Init()
    if not _G.JustInTimeData then return end
    local data = _G.JustInTimeData

    if data.affix_id_to_slug then
        for id, slug in pairs(data.affix_id_to_slug) do
            affixIdToSlug[id] = slug
        end
    end

    if data.dungeons then
        for slug, dg in pairs(data.dungeons) do
            if dg.challenge_mode_id then
                mapIdToSlug[dg.challenge_mode_id] = slug
            end
        end
    end
end

function PaceEngine.MapIdToSlug(map_id)
    return mapIdToSlug[map_id]
end

-- Given a list of WoW affix IDs, returns the alphabetically-sorted combo slug.
-- E.g., {10, 9, 147} → "fortified-tyrannical-xalataths-guile".
function PaceEngine.ResolveAffixCombo(affix_ids)
    local slugs = {}
    for _, id in ipairs(affix_ids) do
        local s = affixIdToSlug[id]
        if s then slugs[#slugs + 1] = s end
    end
    table.sort(slugs)
    return table.concat(slugs, "-")
end

-- Aggregate a pool of personal runs into a synthetic reference cell.
-- mode: "fastest" | "recent" | "median"
function PaceEngine.AggregatePersonalRuns(runs, mode)
    if not runs or #runs == 0 then return nil end

    local pickedRun
    if mode == "fastest" then
        for _, r in ipairs(runs) do
            if not pickedRun or r.clear_time_ms < pickedRun.clear_time_ms then
                pickedRun = r
            end
        end
    elseif mode == "recent" then
        for _, r in ipairs(runs) do
            if not pickedRun or (r.completed_at or "") > (pickedRun.completed_at or "") then
                pickedRun = r
            end
        end
    elseif mode == "median" then
        -- median across runs: per-position split is the median of all runs' split[i]
        -- and clear_time_ms is the median of all clear times.
        local maxLen = 0
        for _, r in ipairs(runs) do
            if r.boss_splits_ms and #r.boss_splits_ms > maxLen then
                maxLen = #r.boss_splits_ms
            end
        end
        local medianSplits = {}
        for i = 1, maxLen do
            local values = {}
            for _, r in ipairs(runs) do
                if r.boss_splits_ms and r.boss_splits_ms[i] then
                    values[#values + 1] = r.boss_splits_ms[i]
                end
            end
            if #values > 0 then
                table.sort(values)
                medianSplits[i] = values[math.ceil(#values / 2)]
            end
        end
        local clearTimes = {}
        for _, r in ipairs(runs) do
            if r.clear_time_ms then clearTimes[#clearTimes + 1] = r.clear_time_ms end
        end
        table.sort(clearTimes)
        local medianClear = clearTimes[math.ceil(#clearTimes / 2)] or 0

        return {
            boss_splits_ms = medianSplits,
            clear_time_ms  = medianClear,
            num_bosses     = maxLen,
            source_label   = "perso_median",
            sample_size    = #runs,
        }
    else
        return nil
    end

    if not pickedRun then return nil end
    return {
        boss_splits_ms = pickedRun.boss_splits_ms or {},
        clear_time_ms  = pickedRun.clear_time_ms,
        num_bosses     = #(pickedRun.boss_splits_ms or {}),
        source_label   = "perso_" .. mode,
        sample_size    = 1,
    }
end

-- Look up the active reference cell based on State.GetActiveSession() + State.Config().
-- Returns nil if no session, no Data.lua, or no matching cell (and no fallback hits).
function PaceEngine.GetReferenceForActive()
    local State = NS.State
    if not State then return nil end
    local s = State.GetActiveSession()
    if not s then return nil end
    local cfg = State.Config()
    local data = _G.JustInTimeData

    if cfg.reference_mode == "public" then
        if not data or not data.dungeons or not data.dungeons[s.dungeon_slug] then
            return nil
        end
        local dg = data.dungeons[s.dungeon_slug]
        local levelEntry = dg.levels and dg.levels[s.level]
        if not levelEntry then return nil end
        local cell = levelEntry[s.affix_combo]
        if not cell and cfg.ignore_affixes then
            -- Fallback: pick any cell at this level, prefer the first encountered
            for combo, c in pairs(levelEntry) do
                cell = c
                cell.__combo_used = combo
                break
            end
        end
        if not cell then return nil end
        return {
            boss_splits_ms     = cell.boss_splits_ms,
            clear_time_ms      = cell.clear_time_ms,
            num_bosses         = dg.num_bosses,
            source_label       = "public",
            affix_combo_used   = cell.__combo_used or s.affix_combo,
            sample_size        = cell.sample_size,
        }
    else
        local subtype = cfg.reference_mode:match("^perso_(.+)$")
        if not subtype then return nil end
        local pool = State.GetPersonalRuns(
            s.dungeon_slug,
            s.level,
            cfg.ignore_affixes and nil or s.affix_combo
        )
        local agg = PaceEngine.AggregatePersonalRuns(pool, subtype)
        if agg then return agg end
        -- Fallback to public if no perso data
        local data = _G.JustInTimeData
        if data and data.dungeons and data.dungeons[s.dungeon_slug] then
            local dg = data.dungeons[s.dungeon_slug]
            local levelEntry = dg.levels and dg.levels[s.level]
            if levelEntry then
                local cell = levelEntry[s.affix_combo]
                if cell then
                    return {
                        boss_splits_ms     = cell.boss_splits_ms,
                        clear_time_ms      = cell.clear_time_ms,
                        num_bosses         = dg.num_bosses,
                        source_label       = "public_fallback",
                        affix_combo_used   = s.affix_combo,
                        sample_size        = cell.sample_size,
                    }
                end
            end
        end
        return nil
    end
end

-- Helper: returns ref splits as { {ord=K, split=T}, ... } sorted ascending by T.
-- Skips zero/nil splits. ord is the 0-based ordinal (boss_splits_ms[i] corresponds to ordinal i-1).
function PaceEngine.SortedRefSplits(ref_splits_ms)
    local list = {}
    for i, t in ipairs(ref_splits_ms) do
        if t and t > 0 then
            list[#list + 1] = { ord = i - 1, split = t }
        end
    end
    table.sort(list, function(a, b) return a.split < b.split end)
    return list
end

-- Anchor-based pace computation per design spec §4.4.
--   elapsed_ms: current run elapsed (from CHALLENGE_MODE_START)
--   your_kills_by_ord: { [ord] = elapsed_at_kill_ms } sparse table
--   ref: { boss_splits_ms, clear_time_ms, num_bosses }
-- Returns:
--   {
--     delta_ms        = signed (>0 behind, <0 ahead) at elapsed_ms
--     projected_finish_ms,
--     deplete_projected = bool (projected > timer requires caller to compare)
--     normalized      = clamp(delta_ms / clear_time_ms, -0.10, +0.10) for color mapping
--     last_anchor_ord = ord of the last killed boss, or nil if none
--   }
function PaceEngine.ComputePace(elapsed_ms, your_kills_by_ord, ref)
    if not ref or not ref.boss_splits_ms then
        return {
            delta_ms = 0,
            projected_finish_ms = 0,
            deplete_projected = false,
            normalized = 0,
            last_anchor_ord = nil,
        }
    end
    local refClear = ref.clear_time_ms or 0

    -- Find the last anchor (your most recent kill in time order)
    local lastYourSplit = 0
    local lastYourOrd = nil
    for ord, t in pairs(your_kills_by_ord) do
        if t > lastYourSplit then
            lastYourSplit = t
            lastYourOrd = ord
        end
    end

    -- delta_at_anchor = your_split[ord] - ref.boss_splits_ms[ord+1]
    local deltaAtAnchor = 0
    if lastYourOrd ~= nil then
        local refTLast = ref.boss_splits_ms[lastYourOrd + 1] or 0
        if refTLast > 0 then
            deltaAtAnchor = lastYourSplit - refTLast
        end
    end

    -- Sorted ref kills (chronological) → find next ref kill after lastYourSplit
    local sortedRef = PaceEngine.SortedRefSplits(ref.boss_splits_ms)
    local nextRefKill = refClear  -- fallback: end of dungeon
    for _, entry in ipairs(sortedRef) do
        if entry.split > lastYourSplit then
            nextRefKill = entry.split
            break
        end
    end

    -- Conservative drift: if elapsed > nextRefKill, we're past where ref would be by now
    local drift = 0
    if elapsed_ms > nextRefKill then
        drift = elapsed_ms - nextRefKill
    end
    local deltaContinuous = deltaAtAnchor + drift

    -- Projection: ratio of last-anchor pace, applied to ref total
    local projectedFinish = refClear
    if lastYourSplit > 0 and lastYourOrd ~= nil then
        local refTLast = ref.boss_splits_ms[lastYourOrd + 1] or 0
        if refTLast > 0 then
            local ratio = lastYourSplit / refTLast
            projectedFinish = math.floor(refClear * ratio)
        end
    end
    -- Drift past nextRefKill also moves projection forward
    if drift > 0 then
        projectedFinish = projectedFinish + drift
    end

    local normalized = 0
    if refClear > 0 then
        normalized = deltaContinuous / refClear
        if normalized > 0.10 then normalized = 0.10 end
        if normalized < -0.10 then normalized = -0.10 end
    end

    return {
        delta_ms            = deltaContinuous,
        projected_finish_ms = projectedFinish,
        deplete_projected   = false,  -- caller checks against timer
        normalized          = normalized,
        last_anchor_ord     = lastYourOrd,
    }
end

NS.PaceEngine = PaceEngine
```

- [ ] **Step 2: Sanity check the file**

```bash
grep -E "^function PaceEngine\.|^NS\.PaceEngine" addon/JustInTime/PaceEngine.lua | wc -l
```

Expected: 8 (7 functions + namespace export).

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/PaceEngine.lua
git commit -m "✨ feat(addon): PaceEngine — affix combo + mapID + ref resolver + delta/ETA"
```

---

## Task 4 — EventTracker.lua: hook M+ events, drive State + PaceEngine

**Files:**
- Create: `addon/JustInTime/EventTracker.lua`

The EventTracker is a single hidden frame with `OnEvent` script handling:
- `CHALLENGE_MODE_START` — new key; resolve mapID + level + affixes → set active session
- `ENCOUNTER_END` — boss kill (in M+ context); record split + snapshot + fire ChatPrinter trigger A + fire critical-alert check
- `CHALLENGE_MODE_COMPLETED` — key ended (success or fail); finalize run, fire trigger C
- `CHALLENGE_MODE_RESET` — key reset/abandon; discard session
- `PLAYER_LOGIN` — restore active session if `IsChallengeModeActive()` (recovery from /reload)
- `PLAYER_LOGOUT` — flush snapshot

API:
- `EventTracker.Init()` — register events
- `EventTracker.GetElapsedMs()` → current elapsed ms based on session start (used by Overlay's OnUpdate)

- [ ] **Step 1: Create `addon/JustInTime/EventTracker.lua`**

Use Write tool. Full content:

```lua
-- EventTracker: hooks M+ lifecycle events and ENCOUNTER_END to drive State.
-- All M+ key state mutations happen here.
local addonName, NS = ...

local EventTracker = {}

local frame = CreateFrame("Frame")
local sessionStartTime = nil  -- GetTime() at CHALLENGE_MODE_START (relative seconds float)

-- Resolve the boss ordinal for a given encounter ID by looking up Data.lua's bosses.
local function lookupOrdinalByEncounterId(dungeon_slug, encounterID)
    local data = _G.JustInTimeData
    if not data or not data.dungeons then return nil end
    local dg = data.dungeons[dungeon_slug]
    if not dg or not dg.bosses then return nil end
    for _, b in ipairs(dg.bosses) do
        if b.wow_encounter_id == encounterID then
            return b.ordinal
        end
    end
    return nil
end

local function onChallengeModeStart()
    local mapId = C_ChallengeMode.GetActiveChallengeMapID()  -- WoW global
    if not mapId then return end
    local level, affixIds = C_ChallengeMode.GetActiveKeystoneInfo()  -- WoW global
    if not level or not affixIds then return end

    local PaceEngine = NS.PaceEngine
    local State = NS.State
    if not PaceEngine or not State then return end

    local slug = PaceEngine.MapIdToSlug(mapId)
    if not slug then
        -- Unknown dungeon — record session anyway so we still track elapsed,
        -- but ref resolution will return nil.
        slug = "unknown-" .. tostring(mapId)
    end
    local combo = PaceEngine.ResolveAffixCombo(affixIds)
    sessionStartTime = GetTime()  -- WoW global, monotonic seconds float
    State.SetActiveSession(slug, level, combo, time())  -- time() = epoch
end

local function onEncounterEnd(encounterID, _encounterName, _difficultyID, _groupSize, success)
    if not C_ChallengeMode.IsChallengeModeActive() then return end  -- ignore non-M+ encounters
    if success ~= 1 and success ~= true then return end  -- only successful kills count

    local State = NS.State
    if not State then return end
    local s = State.GetActiveSession()
    if not s then return end

    local elapsed_ms = math.floor((GetTime() - (sessionStartTime or GetTime())) * 1000)
    local ord = lookupOrdinalByEncounterId(s.dungeon_slug, encounterID)
    if ord ~= nil then
        State.RecordBossKill(ord, elapsed_ms)
        State.SnapshotActiveSession()
    end

    -- Fire the chat printer trigger (boss kill) and critical alert check.
    if NS.ChatPrinter and NS.ChatPrinter.OnBossKill then
        NS.ChatPrinter.OnBossKill(ord, elapsed_ms)
    end
    if NS.ChatPrinter and NS.ChatPrinter.CheckCriticalAlert then
        NS.ChatPrinter.CheckCriticalAlert(elapsed_ms)
    end
end

local function onChallengeModeCompleted()
    local State = NS.State
    if not State then return end
    local s = State.GetActiveSession()
    if not s then return end

    local _, _, time_ms, onTime = C_ChallengeMode.GetCompletionInfo()  -- WoW global
    -- time_ms is the elapsed at completion (ms). onTime = bool, true if timed.
    local clear_time_ms = time_ms or math.floor((GetTime() - (sessionStartTime or GetTime())) * 1000)
    local timed = onTime == true
    local depleted = not timed

    local run = State.FinalizeActiveSession(timed, depleted, clear_time_ms)
    sessionStartTime = nil

    if NS.ChatPrinter and NS.ChatPrinter.OnKeyEnd and run then
        NS.ChatPrinter.OnKeyEnd(run)
    end
end

local function onChallengeModeReset()
    local State = NS.State
    if not State then return end
    State.DiscardActiveSession()
    sessionStartTime = nil
end

local function onPlayerLogin()
    if C_ChallengeMode.IsChallengeModeActive() then
        -- Recovery path: a /reload happened mid-key. The active_session in
        -- SavedVariables is our best guess. We can't recompute sessionStartTime
        -- exactly (GetTime() is process-relative). Use snapshot_at_epoch as a
        -- heuristic: assume started_epoch maps to GetTime() = 0 + (now - started_epoch).
        local State = NS.State
        if not State then return end
        local s = State.GetActiveSession()
        if s and s.started_epoch then
            local now = time()
            local elapsedSec = now - s.started_epoch
            sessionStartTime = GetTime() - elapsedSec
        end
    end
end

local function onPlayerLogout()
    if NS.State then NS.State.SnapshotActiveSession() end
end

frame:SetScript("OnEvent", function(_, event, ...)
    if event == "CHALLENGE_MODE_START" then
        onChallengeModeStart()
    elseif event == "ENCOUNTER_END" then
        onEncounterEnd(...)
    elseif event == "CHALLENGE_MODE_COMPLETED" then
        onChallengeModeCompleted()
    elseif event == "CHALLENGE_MODE_RESET" then
        onChallengeModeReset()
    elseif event == "PLAYER_LOGIN" then
        onPlayerLogin()
    elseif event == "PLAYER_LOGOUT" then
        onPlayerLogout()
    end
end)

function EventTracker.Init()
    frame:RegisterEvent("CHALLENGE_MODE_START")
    frame:RegisterEvent("ENCOUNTER_END")
    frame:RegisterEvent("CHALLENGE_MODE_COMPLETED")
    frame:RegisterEvent("CHALLENGE_MODE_RESET")
    frame:RegisterEvent("PLAYER_LOGIN")
    frame:RegisterEvent("PLAYER_LOGOUT")
end

function EventTracker.GetElapsedMs()
    if not sessionStartTime then return 0 end
    return math.floor((GetTime() - sessionStartTime) * 1000)
end

NS.EventTracker = EventTracker
```

- [ ] **Step 2: Sanity check**

```bash
grep -E "^function|^NS\." addon/JustInTime/EventTracker.lua | wc -l
```

Expected: 9 (helpers + 2 public API + namespace export, approximately).

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/EventTracker.lua
git commit -m "✨ feat(addon): EventTracker — hook M+ events to State + PaceEngine"
```

---

## Task 5 — ChatPrinter.lua: triggers (boss kill / key end / threshold / critical)

**Files:**
- Create: `addon/JustInTime/ChatPrinter.lua`

API:
- `ChatPrinter.OnBossKill(ord, elapsed_ms)` — fires trigger A if cfg.triggers.chat_boss_kill
- `ChatPrinter.OnKeyEnd(run)` — fires trigger C if cfg.triggers.chat_key_end
- `ChatPrinter.CheckCriticalAlert(elapsed_ms)` — fires alerts (visual/chat/sound) if pace projection > timer; also fires threshold-cross trigger B
- `ChatPrinter.FormatDelta(delta_ms)` → e.g., `"1m23 d'avance"` / `"42s de retard"`
- `ChatPrinter.FormatTime(ms)` → `"M:SS"` style

Brand tag is reused from Config.lua (`NS.Util.TAG_INFO`).

- [ ] **Step 1: Create `addon/JustInTime/ChatPrinter.lua`**

Use Write tool. Full content:

```lua
-- ChatPrinter: emit chat messages for boss kills, key end, threshold cross,
-- and critical alerts. All gated by cfg.triggers and cfg.critical_alerts.
local addonName, NS = ...

local ChatPrinter = {}

local lastNormalizedSign = 0  -- track sign change for threshold-cross trigger
local criticalFiredThisKey = false

local function tag()
    return (NS.Util and NS.Util.TAG_INFO) or "|cffffcc00[JIT]|r"
end

local function L(key) return NS.L and NS.L[key] or key end

-- Format milliseconds as "M:SS" or "Hh M:SS" if hours involved.
function ChatPrinter.FormatTime(ms)
    if not ms or ms < 0 then return "0:00" end
    local total_s = math.floor(ms / 1000)
    local h = math.floor(total_s / 3600)
    local m = math.floor((total_s % 3600) / 60)
    local s = total_s % 60
    if h > 0 then
        return string.format("%dh%02d:%02d", h, m, s)
    end
    return string.format("%d:%02d", m, s)
end

-- "1m23 d'avance" / "42s de retard" / "à l'heure"
function ChatPrinter.FormatDelta(delta_ms)
    if not delta_ms or math.abs(delta_ms) < 1000 then
        return L("DELTA_ZERO")
    end
    local abs_s = math.floor(math.abs(delta_ms) / 1000)
    local m = math.floor(abs_s / 60)
    local s = abs_s % 60
    local human
    if m > 0 then
        human = string.format("%dm%02d", m, s)
    else
        human = string.format("%ds", s)
    end
    if delta_ms < 0 then
        return string.format(L("DELTA_AHEAD"), human)
    else
        return string.format(L("DELTA_BEHIND"), human)
    end
end

local function refLabel(ref)
    if not ref then return L("OVERLAY_REF_NONE") end
    local sl = ref.source_label
    if sl == "public" or sl == "public_fallback" then return L("REF_PUBLIC_LABEL") end
    if sl == "perso_fastest" then return L("REF_PERSO_FASTEST") end
    if sl == "perso_recent"  then return L("REF_PERSO_RECENT") end
    if sl == "perso_median"  then return L("REF_PERSO_MEDIAN") end
    return sl or L("OVERLAY_REF_NONE")
end

local function bossNameByOrdinal(dungeon_slug, ord)
    local data = _G.JustInTimeData
    if not data or not data.dungeons or not data.dungeons[dungeon_slug] then
        return string.format("Boss %d", ord + 1)
    end
    local dg = data.dungeons[dungeon_slug]
    for _, b in ipairs(dg.bosses or {}) do
        if b.ordinal == ord then return b.name or b.slug end
    end
    return string.format("Boss %d", ord + 1)
end

function ChatPrinter.OnBossKill(ord, elapsed_ms)
    local State = NS.State
    local PaceEngine = NS.PaceEngine
    if not State or not PaceEngine then return end
    local cfg = State.Config()
    if not cfg.triggers.chat_boss_kill then return end

    local s = State.GetActiveSession()
    if not s then return end
    local ref = PaceEngine.GetReferenceForActive()
    local pace = PaceEngine.ComputePace(elapsed_ms, s.boss_kills, ref)
    local bossName = ord and bossNameByOrdinal(s.dungeon_slug, ord) or "?"
    local deltaStr = ChatPrinter.FormatDelta(pace.delta_ms)
    local refStr = refLabel(ref)
    print(string.format("%s %s", tag(), string.format(L("BOSS_KILL_TRIGGER"), bossName, deltaStr, refStr)))
end

function ChatPrinter.OnKeyEnd(run)
    local State = NS.State
    local PaceEngine = NS.PaceEngine
    if not State or not PaceEngine then return end
    local cfg = State.Config()
    if not cfg.triggers.chat_key_end then return end

    -- Re-resolve reference for the dungeon/level/affix that JUST finished.
    -- The session is already finalized; build a synthetic active context.
    local data = _G.JustInTimeData
    local refClear = nil
    local refLabelStr = L("OVERLAY_REF_NONE")
    if data and data.dungeons and data.dungeons[run.dungeon_slug] then
        local dg = data.dungeons[run.dungeon_slug]
        local levelEntry = dg.levels and dg.levels[run.level]
        if levelEntry then
            local cell = levelEntry[run.affix_combo]
            if cell then
                refClear = cell.clear_time_ms
                refLabelStr = L("REF_PUBLIC_LABEL")
            end
        end
    end

    local clearStr = ChatPrinter.FormatTime(run.clear_time_ms)
    local deltaStr = "—"
    if refClear then
        deltaStr = ChatPrinter.FormatDelta(run.clear_time_ms - refClear)
    end
    local fmt = run.timed and L("KEY_END_TIMED") or L("KEY_END_DEPLETED")
    print(string.format("%s %s", tag(), string.format(fmt, clearStr, deltaStr, refLabelStr)))
    criticalFiredThisKey = false  -- reset for next key
    lastNormalizedSign = 0
end

function ChatPrinter.CheckCriticalAlert(elapsed_ms)
    local State = NS.State
    local PaceEngine = NS.PaceEngine
    if not State or not PaceEngine then return end
    local cfg = State.Config()
    local s = State.GetActiveSession()
    if not s then return end
    local ref = PaceEngine.GetReferenceForActive()
    local pace = PaceEngine.ComputePace(elapsed_ms, s.boss_kills, ref)

    -- Threshold cross trigger (B): only when sign of normalized delta flips
    if cfg.triggers.chat_threshold_cross then
        local sign = 0
        if pace.normalized > 0.005 then sign = 1
        elseif pace.normalized < -0.005 then sign = -1 end
        if lastNormalizedSign ~= 0 and sign ~= 0 and sign ~= lastNormalizedSign then
            local deltaStr = ChatPrinter.FormatDelta(pace.delta_ms)
            local fmt = sign < 0 and L("THRESHOLD_AHEAD") or L("THRESHOLD_BEHIND")
            print(string.format("%s %s", tag(), string.format(fmt, deltaStr)))
        end
        if sign ~= 0 then lastNormalizedSign = sign end
    end

    -- Critical alert: projection exceeds timer
    local data = _G.JustInTimeData
    local timer_ms = nil
    if data and data.dungeons and data.dungeons[s.dungeon_slug] then
        timer_ms = data.dungeons[s.dungeon_slug].timer_ms
    end
    if not timer_ms then return end

    if pace.projected_finish_ms > timer_ms and not criticalFiredThisKey then
        criticalFiredThisKey = true
        if cfg.critical_alerts.chat then
            local etaStr = ChatPrinter.FormatTime(pace.projected_finish_ms)
            local overStr = ChatPrinter.FormatDelta(pace.projected_finish_ms - timer_ms)
            print(string.format("%s %s", tag(), string.format(L("CRITICAL_DEPLETE"), etaStr, overStr)))
        end
        if cfg.critical_alerts.sound then
            PlaySound(8959)  -- WoW global; "RaidWarning" sound
        end
        if cfg.critical_alerts.visual and NS.Overlay and NS.Overlay.PulseCritical then
            NS.Overlay.PulseCritical()
        end
    end
end

NS.ChatPrinter = ChatPrinter
```

- [ ] **Step 2: Sanity check**

```bash
grep -E "^function ChatPrinter\.|^NS\.ChatPrinter" addon/JustInTime/ChatPrinter.lua | wc -l
```

Expected: 6 (5 functions + namespace export).

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/ChatPrinter.lua
git commit -m "✨ feat(addon): ChatPrinter — boss kill / key end / threshold / critical alerts"
```

---

## Task 6 — Overlay.lua: CD-1 frame skeleton (no color logic yet)

**Files:**
- Create: `addon/JustInTime/Overlay.lua`

The Overlay creates a `BackdropTemplate` frame with the CD-1 layout: gradient brand title + delta numeric + gradient bar + boss pips + 3 info rows. This task creates the **skeleton** only — color gradient mapping comes in Task 7, visibility modes in Task 8, drag/lock in Task 9, critical pulse in Task 10.

API:
- `Overlay.Init()` — create the frame, hidden by default
- `Overlay.Show()` / `Overlay.Hide()`
- `Overlay.SetData(elapsed_ms, pace, num_bosses, kills_count, last_kill_split, ref)` — refresh content
- `Overlay.GetFrame()` → frame ref (for drag, etc., in later tasks)

The `OnUpdate` script ticks at 10 Hz and calls `SetData` with current pace data. Active only when `IsChallengeModeActive()`.

- [ ] **Step 1: Create `addon/JustInTime/Overlay.lua`**

Use Write tool. Full content:

```lua
-- Overlay: CD-1 layout. Gradient brand title + delta + gradient bar + pips + 3 rows.
-- This task creates the skeleton; color mapping / visibility modes / drag / pulse
-- are layered in subsequent tasks.
local addonName, NS = ...

local Overlay = {}

local frame
local titleFS, deltaFS
local barTrack, barFill, barMarker
local pips = {}
local rowElapsed, rowETA, rowLast, rowRef

local UPDATE_INTERVAL = 0.1  -- seconds

local function L(key) return NS.L and NS.L[key] or key end

local function formatTime(ms)
    return NS.ChatPrinter and NS.ChatPrinter.FormatTime(ms) or "0:00"
end

local function buildFrame()
    frame = CreateFrame("Frame", "JustInTimeOverlay", UIParent, "BackdropTemplate")
    frame:SetSize(300, 140)
    frame:SetFrameStrata("MEDIUM")
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)

    if frame.SetBackdrop then
        frame:SetBackdrop({
            bgFile   = "Interface\\Buttons\\WHITE8x8",
            edgeFile = "Interface\\Buttons\\WHITE8x8",
            edgeSize = 1,
        })
        frame:SetBackdropColor(0.05, 0.05, 0.07, 0.85)
        frame:SetBackdropBorderColor(0.18, 0.18, 0.22, 1)
    end

    -- Title (flame brand gradient — light orange → red across letters)
    titleFS = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    titleFS:SetPoint("TOPLEFT", 10, -8)
    if NS.Util and NS.Util.flameText then
        titleFS:SetText(NS.Util.flameText("JustInTime"))
    else
        titleFS:SetText("JustInTime")
    end

    -- Delta (top right, large)
    deltaFS = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    deltaFS:SetPoint("TOPRIGHT", -10, -6)
    deltaFS:SetText("—")

    -- Bar track
    barTrack = CreateFrame("Frame", nil, frame, "BackdropTemplate")
    barTrack:SetSize(280, 8)
    barTrack:SetPoint("TOPLEFT", 10, -32)
    if barTrack.SetBackdrop then
        barTrack:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8x8" })
        barTrack:SetBackdropColor(0.10, 0.10, 0.12, 1)
    end

    barFill = barTrack:CreateTexture(nil, "ARTWORK")
    barFill:SetTexture("Interface\\Buttons\\WHITE8x8")
    barFill:SetPoint("TOPLEFT", 0, 0)
    barFill:SetPoint("BOTTOMLEFT", 0, 0)
    barFill:SetVertexColor(0.78, 0.62, 1.0, 1)  -- neutral light violet by default
    barFill:SetWidth(0)

    barMarker = barTrack:CreateTexture(nil, "OVERLAY")
    barMarker:SetTexture("Interface\\Buttons\\WHITE8x8")
    barMarker:SetVertexColor(1, 0.92, 0.23, 1)  -- yellow
    barMarker:SetSize(2, 12)
    barMarker:SetPoint("TOP", barTrack, "TOPLEFT", 0, 2)

    -- Pips (variable count; create up to 6, hide unused)
    for i = 1, 6 do
        local pip = barTrack:CreateTexture(nil, "BORDER")
        pip:SetTexture("Interface\\Buttons\\WHITE8x8")
        pip:SetSize(40, 6)
        pip:SetVertexColor(0.18, 0.18, 0.20, 1)
        pip:Hide()
        pips[i] = pip
    end

    -- Info rows
    local function makeRow(yoff)
        local labelFS = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        labelFS:SetPoint("TOPLEFT", 10, yoff)
        local valueFS = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        valueFS:SetPoint("TOPRIGHT", -10, yoff)
        return labelFS, valueFS
    end

    local le, ve = makeRow(-58)
    rowElapsed = { label = le, value = ve }

    local lt, vt = makeRow(-74)
    rowETA = { label = lt, value = vt }

    local ll, vl = makeRow(-90)
    rowLast = { label = ll, value = vl }

    local lr, vr = makeRow(-106)
    rowRef = { label = lr, value = vr }

    rowElapsed.label:SetText(L("OVERLAY_LABEL_ELAPSED"))
    rowETA.label:SetText(L("OVERLAY_LABEL_ETA"))
    rowLast.label:SetText(L("OVERLAY_LABEL_LAST"))
    rowRef.label:SetText(L("OVERLAY_LABEL_REF"))

    -- OnUpdate ticker (driven by Init/Hide externally)
    frame.elapsedAccum = 0
    frame:SetScript("OnUpdate", function(self, elapsed)
        self.elapsedAccum = (self.elapsedAccum or 0) + elapsed
        if self.elapsedAccum < UPDATE_INTERVAL then return end
        self.elapsedAccum = 0
        if not C_ChallengeMode.IsChallengeModeActive() then
            Overlay.Hide()
            return
        end
        Overlay.Tick()
    end)

    frame:Hide()  -- hidden by default; Init may show based on visibility config
end

function Overlay.Tick()
    local State = NS.State
    local PaceEngine = NS.PaceEngine
    local ET = NS.EventTracker
    if not State or not PaceEngine or not ET then return end
    local s = State.GetActiveSession()
    if not s then return end
    local elapsed_ms = ET.GetElapsedMs()
    local ref = PaceEngine.GetReferenceForActive()
    local pace = PaceEngine.ComputePace(elapsed_ms, s.boss_kills, ref)

    local data = _G.JustInTimeData
    local num_bosses = 4
    local timer_ms = 1800000
    if data and data.dungeons and data.dungeons[s.dungeon_slug] then
        local dg = data.dungeons[s.dungeon_slug]
        num_bosses = dg.num_bosses or 4
        timer_ms = dg.timer_ms or 1800000
    end

    local kills_count = 0
    local last_split_ms = 0
    for _, t in pairs(s.boss_kills) do
        kills_count = kills_count + 1
        if t > last_split_ms then last_split_ms = t end
    end

    Overlay.SetData(elapsed_ms, pace, num_bosses, kills_count, last_split_ms, ref, timer_ms)
end

function Overlay.SetData(elapsed_ms, pace, num_bosses, kills_count, last_split_ms, ref, timer_ms)
    if not frame then return end

    -- Delta
    if NS.ChatPrinter and pace then
        local s = NS.ChatPrinter.FormatDelta(pace.delta_ms)
        deltaFS:SetText(s)
    end

    -- Bar fill: width = elapsed / projected_finish (or timer if no ref)
    local projected = (pace and pace.projected_finish_ms) or timer_ms or 1
    if projected < 1 then projected = 1 end
    local progress = math.min(1, elapsed_ms / projected)
    barFill:SetWidth(280 * progress)
    barMarker:SetPoint("TOP", barTrack, "TOPLEFT", 280 * progress, 2)

    -- Pips: spread evenly over the bar; mark 'done' for each kill
    local n = math.min(6, num_bosses or 4)
    for i = 1, 6 do
        if i <= n then
            local pip = pips[i]
            local x = (280 / n) * (i - 0.5) - 20  -- center each pip in its slot
            pip:ClearAllPoints()
            pip:SetPoint("TOP", barTrack, "TOPLEFT", x, -10)
            if i <= (kills_count or 0) then
                pip:SetVertexColor(0.19, 0.78, 0.39, 1)  -- green = done
            else
                pip:SetVertexColor(0.18, 0.18, 0.20, 1)  -- gray = pending
            end
            pip:Show()
        else
            pips[i]:Hide()
        end
    end

    rowElapsed.value:SetText(formatTime(elapsed_ms))
    rowETA.value:SetText(pace and formatTime(pace.projected_finish_ms) or "—")
    rowLast.value:SetText(last_split_ms > 0 and formatTime(last_split_ms) or "—")
    rowRef.value:SetText(ref and formatTime(ref.clear_time_ms) or L("OVERLAY_REF_NONE"))
end

function Overlay.Init()
    if frame then return end
    buildFrame()
    -- Apply position from saved config if available
    local State = NS.State
    if State then
        local cfg = State.Config()
        local pos = cfg.overlay_position or {}
        frame:ClearAllPoints()
        frame:SetPoint(pos.anchor or "TOPRIGHT", UIParent, pos.relAnchor or "TOPRIGHT", pos.x or -180, pos.y or -200)
    end
end

function Overlay.Show()
    if frame then frame:Show() end
end

function Overlay.Hide()
    if frame then frame:Hide() end
end

function Overlay.GetFrame()
    return frame
end

NS.Overlay = Overlay
```

- [ ] **Step 2: Sanity check**

```bash
grep -E "^function Overlay\.|^NS\.Overlay" addon/JustInTime/Overlay.lua | wc -l
```

Expected: 7 (Init, Show, Hide, Tick, SetData, GetFrame + namespace export = 7).

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/Overlay.lua
git commit -m "✨ feat(addon): Overlay skeleton — CD-1 frame structure (no colors yet)"
```

---

## Task 7 — Overlay color gradient (HSL interp by normalized delta)

**Files:**
- Modify: `addon/JustInTime/Overlay.lua`

Add a `mapDeltaToColor(normalized)` function that interpolates between brand anchors:
- ≤ −0.05: vert vif (0x30C864)
- −0.025: vert pâle (0x7ED87A)
- 0: violet pâle (0xC8A0FF)
- +0.025: violet rosé (0xD878A0)
- ≥ +0.05: rouge (0xFF5050)

Apply the result to `barFill:SetVertexColor(r, g, b, 1)` in `SetData`.

- [ ] **Step 1: Add the color helper at the top of `Overlay.lua` (after the `local frame, titleFS...` block, before `buildFrame()`)**

Use Edit tool. Insert this before the `buildFrame()` function definition:

```lua
-- Brand color anchors for delta-driven gradient mapping.
-- All in 0..1 RGB.
local COLOR_AHEAD_STRONG  = { 0.19, 0.78, 0.39 }  -- 30C864 vert vif
local COLOR_AHEAD_LIGHT   = { 0.49, 0.85, 0.48 }  -- 7ED87A vert pâle
local COLOR_NEUTRAL       = { 0.78, 0.62, 1.00 }  -- C8A0FF violet pâle
local COLOR_BEHIND_LIGHT  = { 0.85, 0.47, 0.62 }  -- D878A0 violet rosé
local COLOR_BEHIND_STRONG = { 1.00, 0.31, 0.31 }  -- FF5050 rouge

-- Linear RGB interpolation (good enough; HSL adds complexity for a marginal gain).
local function lerpRGB(a, b, t)
    return {
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
        a[3] + (b[3] - a[3]) * t,
    }
end

-- Map normalized delta in [-0.10, +0.10] to a brand color.
-- Inputs outside the range clamp to the strong anchors.
local function mapDeltaToColor(normalized)
    local n = normalized or 0
    if n <= -0.05 then return COLOR_AHEAD_STRONG end
    if n <= -0.025 then
        return lerpRGB(COLOR_AHEAD_LIGHT, COLOR_AHEAD_STRONG, (-0.025 - n) / 0.025)
    end
    if n <= 0 then
        return lerpRGB(COLOR_NEUTRAL, COLOR_AHEAD_LIGHT, -n / 0.025)
    end
    if n <= 0.025 then
        return lerpRGB(COLOR_NEUTRAL, COLOR_BEHIND_LIGHT, n / 0.025)
    end
    if n <= 0.05 then
        return lerpRGB(COLOR_BEHIND_LIGHT, COLOR_BEHIND_STRONG, (n - 0.025) / 0.025)
    end
    return COLOR_BEHIND_STRONG
end
```

- [ ] **Step 2: Modify `SetData` to apply the color**

Find the line `local progress = math.min(1, elapsed_ms / projected)` in `SetData`. After the `barFill:SetWidth(...)` line, add:

```lua
    local color = mapDeltaToColor(pace and pace.normalized or 0)
    barFill:SetVertexColor(color[1], color[2], color[3], 1)
```

- [ ] **Step 3: Sanity check the file is still valid**

```bash
grep -E "^local function (lerpRGB|mapDeltaToColor)" addon/JustInTime/Overlay.lua | wc -l
```

Expected: 2.

- [ ] **Step 4: Commit**

```bash
git add addon/JustInTime/Overlay.lua
git commit -m "🎨 feat(addon): Overlay color gradient mapping for normalized delta"
```

---

## Task 8 — Overlay visibility modes (always vs popup)

**Files:**
- Modify: `addon/JustInTime/Overlay.lua`

Add `Overlay.OnBossKillTrigger()` that, in popup mode, shows the frame for 6 seconds with fade-in and fade-out, then re-hides. In always mode, no-op (the frame stays visible whenever a key is active).

ChatPrinter already calls `NS.ChatPrinter.OnBossKill` — we'll thread Overlay's hook through EventTracker (modify Task 4 wiring) but keep this task self-contained: the function exists; whether it's invoked depends on EventTracker being amended.

- [ ] **Step 1: Add visibility helpers to `Overlay.lua`**

Use Edit tool. Append to the end of `Overlay.lua` (just before `NS.Overlay = Overlay`):

```lua
local POPUP_HOLD_SECONDS = 6
local FADE_IN_SECONDS    = 0.3
local FADE_OUT_SECONDS   = 0.5

local popupHideTimer

local function fadeOutThenHide()
    if not frame then return end
    UIFrameFadeOut(frame, FADE_OUT_SECONDS, frame:GetAlpha(), 0)  -- WoW global animation helper
    C_Timer.After(FADE_OUT_SECONDS, function()  -- WoW global
        if frame then frame:Hide() end
    end)
end

function Overlay.RefreshVisibility()
    if not frame then return end
    local State = NS.State
    if not State then return end
    local cfg = State.Config()
    local active = C_ChallengeMode.IsChallengeModeActive()
    if not active then
        frame:Hide()
        return
    end
    if cfg.overlay_visibility == "always" then
        frame:SetAlpha(1)
        frame:Show()
    else
        -- popup mode: only show in response to triggers
    end
end

function Overlay.OnBossKillTrigger()
    if not frame then return end
    local State = NS.State
    if not State then return end
    local cfg = State.Config()
    if cfg.overlay_visibility ~= "popup" then return end
    if popupHideTimer then popupHideTimer:Cancel() end

    frame:SetAlpha(0)
    frame:Show()
    UIFrameFadeIn(frame, FADE_IN_SECONDS, 0, 1)
    popupHideTimer = C_Timer.NewTimer(POPUP_HOLD_SECONDS, fadeOutThenHide)
end
```

- [ ] **Step 2: Wire Overlay.OnBossKillTrigger from EventTracker**

In `addon/JustInTime/EventTracker.lua`, find the `onEncounterEnd` function. After the existing `if NS.ChatPrinter and NS.ChatPrinter.OnBossKill then ... end` block, add:

```lua
    if NS.Overlay and NS.Overlay.OnBossKillTrigger then
        NS.Overlay.OnBossKillTrigger()
    end
```

Use Edit tool to apply this change.

- [ ] **Step 3: Wire Overlay.RefreshVisibility on key start (always mode)**

In `EventTracker.lua`, at the end of `onChallengeModeStart`, add:

```lua
    if NS.Overlay and NS.Overlay.RefreshVisibility then
        NS.Overlay.RefreshVisibility()
    end
```

And in `onChallengeModeCompleted`, after `sessionStartTime = nil`:

```lua
    if NS.Overlay and NS.Overlay.Hide then
        NS.Overlay.Hide()
    end
```

And in `onChallengeModeReset`:

```lua
    if NS.Overlay and NS.Overlay.Hide then
        NS.Overlay.Hide()
    end
```

- [ ] **Step 4: Commit**

```bash
git add addon/JustInTime/Overlay.lua addon/JustInTime/EventTracker.lua
git commit -m "✨ feat(addon): Overlay visibility modes — always vs popup with fade"
```

---

## Task 9 — Overlay drag + lock + position persistence

**Files:**
- Modify: `addon/JustInTime/Overlay.lua`

Make the frame draggable when `cfg.overlay_position.locked` is false. Persist position into SavedVariables on drag stop.

- [ ] **Step 1: Append drag/lock helpers at end of `Overlay.lua` before `NS.Overlay = Overlay`**

Use Edit tool. Append:

```lua
local function persistPosition()
    if not frame then return end
    local State = NS.State
    if not State then return end
    local point, _, relPoint, x, y = frame:GetPoint(1)
    local cfg = State.Config()
    cfg.overlay_position.anchor = point
    cfg.overlay_position.relAnchor = relPoint
    cfg.overlay_position.x = x
    cfg.overlay_position.y = y
end

function Overlay.RefreshDraggable()
    if not frame then return end
    local State = NS.State
    if not State then return end
    local cfg = State.Config()
    local locked = cfg.overlay_position.locked
    frame:EnableMouse(not locked)
    if locked then
        frame:SetScript("OnDragStart", nil)
        frame:SetScript("OnDragStop", nil)
        frame:RegisterForDrag()
    else
        frame:RegisterForDrag("LeftButton")
        frame:SetScript("OnDragStart", function(self) self:StartMoving() end)
        frame:SetScript("OnDragStop", function(self)
            self:StopMovingOrSizing()
            persistPosition()
        end)
    end
end

function Overlay.ResetPosition()
    local State = NS.State
    if not State then return end
    local cfg = State.Config()
    cfg.overlay_position.anchor = "TOPRIGHT"
    cfg.overlay_position.relAnchor = "TOPRIGHT"
    cfg.overlay_position.x = -180
    cfg.overlay_position.y = -200
    if frame then
        frame:ClearAllPoints()
        frame:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -180, -200)
    end
end
```

- [ ] **Step 2: Call `Overlay.RefreshDraggable()` at end of `Overlay.Init()`**

Use Edit tool. Find:

```lua
function Overlay.Init()
    if frame then return end
    buildFrame()
    -- Apply position from saved config if available
    local State = NS.State
    if State then
        local cfg = State.Config()
        local pos = cfg.overlay_position or {}
        frame:ClearAllPoints()
        frame:SetPoint(pos.anchor or "TOPRIGHT", UIParent, pos.relAnchor or "TOPRIGHT", pos.x or -180, pos.y or -200)
    end
end
```

Replace with:

```lua
function Overlay.Init()
    if frame then return end
    buildFrame()
    local State = NS.State
    if State then
        local cfg = State.Config()
        local pos = cfg.overlay_position or {}
        frame:ClearAllPoints()
        frame:SetPoint(pos.anchor or "TOPRIGHT", UIParent, pos.relAnchor or "TOPRIGHT", pos.x or -180, pos.y or -200)
    end
    Overlay.RefreshDraggable()
end
```

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/Overlay.lua
git commit -m "✨ feat(addon): Overlay drag + lock + position persistence"
```

---

## Task 10 — Overlay critical pulse animation

**Files:**
- Modify: `addon/JustInTime/Overlay.lua`

Add `Overlay.PulseCritical()` that fades the bar fill between bright red and dark red repeatedly while the run is in critical state. Stop pulsing on key end / reset.

- [ ] **Step 1: Append pulse helpers to `Overlay.lua` before `NS.Overlay = Overlay`**

Use Edit tool. Append:

```lua
local pulseAnimation
local pulsing = false

function Overlay.PulseCritical()
    if not frame or pulsing then return end
    pulsing = true

    if not pulseAnimation then
        pulseAnimation = barFill:CreateAnimationGroup()
        pulseAnimation:SetLooping("REPEAT")
        local fadeOut = pulseAnimation:CreateAnimation("Alpha")
        fadeOut:SetFromAlpha(1)
        fadeOut:SetToAlpha(0.4)
        fadeOut:SetDuration(0.5)
        fadeOut:SetOrder(1)
        local fadeIn = pulseAnimation:CreateAnimation("Alpha")
        fadeIn:SetFromAlpha(0.4)
        fadeIn:SetToAlpha(1)
        fadeIn:SetDuration(0.5)
        fadeIn:SetOrder(2)
    end

    barFill:SetVertexColor(1.0, 0.31, 0.31, 1)  -- force red while pulsing
    pulseAnimation:Play()
end

function Overlay.StopPulse()
    if pulseAnimation and pulsing then
        pulseAnimation:Stop()
        barFill:SetAlpha(1)
    end
    pulsing = false
end
```

- [ ] **Step 2: Wire `Overlay.StopPulse()` from EventTracker on key end / reset**

In `EventTracker.lua`, find `onChallengeModeCompleted` and `onChallengeModeReset`. Add at the end of each (just after `Overlay.Hide()` if present, or as standalone):

```lua
    if NS.Overlay and NS.Overlay.StopPulse then
        NS.Overlay.StopPulse()
    end
```

(Use Edit tool — it's the same block for both event handlers.)

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/Overlay.lua addon/JustInTime/EventTracker.lua
git commit -m "✨ feat(addon): Overlay critical pulse animation"
```

---

## Task 11 — Settings panel: replace minimal Config.lua with full panel

**Files:**
- Modify: `addon/JustInTime/Config.lua`

Replace the existing `Config.lua` (which has the brand utilities + minimal panel) with a full Settings panel containing all toggle widgets per spec §6.6. Keep the brand utilities (`gradientText`, `BRAND_*`, `TAG_*` constants) — they're used by Overlay and ChatPrinter.

- [ ] **Step 1: Read the current `Config.lua`**

```bash
cat addon/JustInTime/Config.lua
```

We need to **preserve**: the `gradientText` function, `NS.Util` exports (BRAND_*, TAG_INFO, TAG_DEBUG), `Config.Load` (delegated to `State.Init()`), `Config.OpenPanel`. We're replacing the panel UI with full widgets and reading config from `JustInTimeDB` (managed by State).

- [ ] **Step 2: Replace `addon/JustInTime/Config.lua` entirely**

Use Write tool. Full content:

```lua
local addonName, NS = ...
local Config = {}

-- Config defaults / SavedVariables init are owned by State.Init() in State.lua.
-- This file owns the Settings panel and the brand utilities (gradient + tag).

-- ─── Brand utilities ────────────────────────────────────────────────────────

local function gradientText(text, c1, c2, c3)
    local n = #text
    if n == 0 then return "" end
    local mid = (n + 1) / 2
    local out = {}
    for i = 1, n do
        local t, ca, cb
        if i <= mid then
            t = (mid > 1) and ((i - 1) / (mid - 1)) or 0
            ca, cb = c1, c2
        else
            t = (i - mid) / (n - mid)
            ca, cb = c2, c3
        end
        local r = math.floor(ca[1] + (cb[1] - ca[1]) * t + 0.5)
        local g = math.floor(ca[2] + (cb[2] - ca[2]) * t + 0.5)
        local b = math.floor(ca[3] + (cb[3] - ca[3]) * t + 0.5)
        out[#out + 1] = ("|cFF%02X%02X%02X%s|r"):format(r, g, b, text:sub(i, i))
    end
    return table.concat(out)
end

local AUTHOR_HANDLE = "Claralicious_"
local FR_BLEU  = { 0x00, 0x55, 0xA4 }
local FR_BLANC = { 0xFF, 0xFF, 0xFF }
local FR_ROUGE = { 0xEF, 0x41, 0x35 }

-- Flame brand identity (addon name everywhere): light orange → mid orange → bright red.
local FLAME_LIGHT_ORANGE = { 0xFF, 0xCC, 0x66 }
local FLAME_MID_ORANGE   = { 0xFF, 0x88, 0x44 }
local FLAME_RED          = { 0xFF, 0x33, 0x33 }

-- Pace status palette (used by Overlay color-mapping; not the brand identity).
local BRAND_RED          = { 0xFF, 0x44, 0x44 }
local BRAND_MID_VIOLET   = { 0xB8, 0x60, 0xD0 }
local BRAND_LIGHT_VIOLET = { 0xC8, 0xA0, 0xFF }

local TAG_INFO  = "|cff33ff99[|r|cffff3333J|r|cffc8a0ffIT|r|cff33ff99]|r"
local TAG_DEBUG = TAG_INFO .. "|cff888888[debug]|r"

local function flameText(text)
    return gradientText(text, FLAME_LIGHT_ORANGE, FLAME_MID_ORANGE, FLAME_RED)
end

NS.Util = {
    gradientText        = gradientText,
    flameText           = flameText,
    FLAME_LIGHT_ORANGE  = FLAME_LIGHT_ORANGE,
    FLAME_MID_ORANGE    = FLAME_MID_ORANGE,
    FLAME_RED           = FLAME_RED,
    BRAND_RED           = BRAND_RED,
    BRAND_MID_VIOLET    = BRAND_MID_VIOLET,
    BRAND_LIGHT_VIOLET  = BRAND_LIGHT_VIOLET,
    TAG_INFO            = TAG_INFO,
    TAG_DEBUG           = TAG_DEBUG,
}

local function L(key) return NS.L and NS.L[key] or key end

local function buildFooter(parent)
    local fs = parent:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    fs:SetPoint("BOTTOMLEFT", parent, "BOTTOMLEFT", 16, 12)
    fs:SetText("By " .. gradientText(AUTHOR_HANDLE, FR_BLEU, FR_BLANC, FR_ROUGE))
end

-- ─── Panel ──────────────────────────────────────────────────────────────────

local panel
local widgets = {}

local function setConfig(path_chain, value)
    local State = NS.State
    if not State then return end
    local cfg = State.Config()
    -- path_chain: array of keys like {"triggers", "chat_boss_kill"}
    local target = cfg
    for i = 1, #path_chain - 1 do
        target = target[path_chain[i]]
        if not target then return end
    end
    target[path_chain[#path_chain]] = value
end

local function getConfig(path_chain)
    local State = NS.State
    if not State then return nil end
    local cfg = State.Config()
    local target = cfg
    for _, k in ipairs(path_chain) do
        if target == nil then return nil end
        target = target[k]
    end
    return target
end

local function makeCheckbox(parent, label, x, y, path_chain)
    local cb = CreateFrame("CheckButton", nil, parent, "InterfaceOptionsCheckButtonTemplate")
    cb:SetPoint("TOPLEFT", x, y)
    cb.Text:SetText(label)
    cb:SetScript("OnShow", function(self) self:SetChecked(getConfig(path_chain) and true or false) end)
    cb:SetScript("OnClick", function(self) setConfig(path_chain, self:GetChecked() and true or false) end)
    return cb
end

local function makeRadioGroup(parent, options, x, y, path_chain)
    -- options: list of { value=string, label=string }
    local radios = {}
    for i, opt in ipairs(options) do
        local r = CreateFrame("CheckButton", nil, parent, "InterfaceOptionsCheckButtonTemplate")
        r:SetPoint("TOPLEFT", x, y - (i - 1) * 22)
        r.Text:SetText(opt.label)
        r.value = opt.value
        r:SetScript("OnShow", function(self) self:SetChecked(getConfig(path_chain) == self.value) end)
        r:SetScript("OnClick", function(self)
            setConfig(path_chain, self.value)
            for _, peer in ipairs(radios) do peer:SetChecked(peer == self) end
        end)
        radios[i] = r
    end
    return radios
end

local function makeButton(parent, label, x, y, w, onClick)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetSize(w or 180, 22)
    b:SetPoint("TOPLEFT", x, y)
    b:SetText(label)
    b:SetScript("OnClick", onClick)
    return b
end

local function makeHeader(parent, text, x, y)
    local fs = parent:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
    fs:SetPoint("TOPLEFT", x, y)
    fs:SetText("── " .. text .. " ──")
    return fs
end

local function dataAgeDays()
    if not _G.JustInTimeData or not _G.JustInTimeData.meta then return nil end
    local s = _G.JustInTimeData.meta.generated_at
    if not s then return nil end
    -- Parse "YYYY-MM-DDTHH:MM:SSZ"
    local Y, M, D = s:match("^(%d+)-(%d+)-(%d+)")
    if not Y then return nil end
    -- Compute days using time() and a synthetic table
    local genEpoch = time({ year = tonumber(Y), month = tonumber(M), day = tonumber(D), hour = 0, min = 0, sec = 0 })
    local nowEpoch = time()
    return math.floor((nowEpoch - genEpoch) / 86400), s:sub(1, 10)
end

local function buildPanel()
    if panel then return panel end
    panel = CreateFrame("Frame")
    panel.name = NS.Util.flameText("JustInTime")

    -- Title (flame gradient, big)
    local title = panel:CreateFontString(nil, "ARTWORK", "GameFontNormalHuge")
    title:SetPoint("TOPLEFT", 16, -16)
    title:SetText(NS.Util.flameText("JustInTime"))

    buildFooter(panel)

    local Y_TOP = -50
    -- ── Reference ──
    makeHeader(panel, L("PANEL_REF_HEADER"), 16, Y_TOP)
    local refRadios = makeRadioGroup(panel, {
        { value = "public",          label = L("PANEL_REF_PUBLIC") },
        { value = "perso_fastest",   label = L("PANEL_REF_FASTEST") },
        { value = "perso_recent",    label = L("PANEL_REF_RECENT") },
        { value = "perso_median",    label = L("PANEL_REF_MEDIAN") },
    }, 32, Y_TOP - 22, { "reference_mode" })
    widgets.refRadios = refRadios

    local cbIgnoreAffixes = makeCheckbox(panel, L("PANEL_IGNORE_AFFIXES"), 32, Y_TOP - 22 * 5, { "ignore_affixes" })
    widgets.cbIgnoreAffixes = cbIgnoreAffixes

    -- ── Overlay ──
    local Y_OVL = Y_TOP - 22 * 7
    makeHeader(panel, L("PANEL_OVERLAY_HEADER"), 16, Y_OVL)
    local visRadios = makeRadioGroup(panel, {
        { value = "always", label = L("PANEL_OVERLAY_ALWAYS") },
        { value = "popup",  label = L("PANEL_OVERLAY_POPUP") },
    }, 32, Y_OVL - 22, { "overlay_visibility" })
    widgets.visRadios = visRadios

    local cbLock = makeCheckbox(panel, L("PANEL_OVERLAY_LOCK"), 32, Y_OVL - 22 * 3, { "overlay_position", "locked" })
    cbLock:HookScript("OnClick", function()
        if NS.Overlay and NS.Overlay.RefreshDraggable then NS.Overlay.RefreshDraggable() end
    end)
    widgets.cbLock = cbLock

    makeButton(panel, L("PANEL_OVERLAY_RESET"), 32, Y_OVL - 22 * 4, 200, function()
        if NS.Overlay and NS.Overlay.ResetPosition then NS.Overlay.ResetPosition() end
    end)

    -- ── Chat triggers ──
    local Y_CHAT = Y_OVL - 22 * 6
    makeHeader(panel, L("PANEL_CHAT_HEADER"), 16, Y_CHAT)
    widgets.cbBossKill = makeCheckbox(panel, L("PANEL_CHAT_BOSS_KILL"), 32, Y_CHAT - 22, { "triggers", "chat_boss_kill" })
    widgets.cbKeyEnd   = makeCheckbox(panel, L("PANEL_CHAT_KEY_END"),   32, Y_CHAT - 22 * 2, { "triggers", "chat_key_end" })
    widgets.cbThreshold = makeCheckbox(panel, L("PANEL_CHAT_THRESHOLD"), 32, Y_CHAT - 22 * 3, { "triggers", "chat_threshold_cross" })

    -- ── Critical alerts ──
    local Y_CRIT = Y_CHAT - 22 * 5
    makeHeader(panel, L("PANEL_CRIT_HEADER"), 16, Y_CRIT)
    widgets.cbCritVisual = makeCheckbox(panel, L("PANEL_CRIT_VISUAL"), 32, Y_CRIT - 22, { "critical_alerts", "visual" })
    widgets.cbCritChat   = makeCheckbox(panel, L("PANEL_CRIT_CHAT"),   32, Y_CRIT - 22 * 2, { "critical_alerts", "chat" })
    widgets.cbCritSound  = makeCheckbox(panel, L("PANEL_CRIT_SOUND"),  32, Y_CRIT - 22 * 3, { "critical_alerts", "sound" })

    -- ── Data ──
    local Y_DATA = Y_CRIT - 22 * 5
    makeHeader(panel, L("PANEL_DATA_HEADER"), 16, Y_DATA)
    local dataLabel = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    dataLabel:SetPoint("TOPLEFT", 32, Y_DATA - 22)
    dataLabel:SetWidth(500)
    dataLabel:SetJustifyH("LEFT")
    panel.dataLabel = dataLabel

    makeButton(panel, L("PANEL_DATA_RESET_RUNS"), 32, Y_DATA - 22 * 3, 240, function()
        StaticPopup_Show("JIT_CONFIRM_RESET_RUNS")  -- WoW global
    end)

    -- Refresh dynamic content on show
    panel:SetScript("OnShow", function()
        local days, dateStr = dataAgeDays()
        if days then
            local mark = days <= 14 and "✓" or "⚠"
            dataLabel:SetText(string.format(L("PANEL_DATA_GENERATED"), dateStr or "?", days, mark))
        else
            dataLabel:SetText(L("PANEL_DATA_NONE"))
        end
    end)

    -- Register the panel with Settings UI
    if Settings and Settings.RegisterCanvasLayoutCategory then
        local category = Settings.RegisterCanvasLayoutCategory(panel, panel.name)
        Settings.RegisterAddOnCategory(category)
        Config._category = category
    elseif InterfaceOptions_AddCategory then
        InterfaceOptions_AddCategory(panel)
    end

    -- StaticPopup for reset confirmation
    StaticPopupDialogs["JIT_CONFIRM_RESET_RUNS"] = {  -- WoW global
        text = L("CONFIRM_RESET_RUNS"),
        button1 = L("BTN_YES"),
        button2 = L("BTN_NO"),
        OnAccept = function()
            local State = NS.State
            if State and State.ClearAllRuns then
                local n = State.ClearAllRuns()
                print(string.format("%s %s", NS.Util.TAG_INFO, string.format(L("RESET_DONE"), n)))
            end
        end,
        timeout = 0,
        whileDead = true,
        hideOnEscape = true,
        preferredIndex = 3,
    }

    return panel
end

function Config.Load()
    -- Defaults are managed by State.Init(); kept here for backward compat.
    if NS.State and NS.State.Init then NS.State.Init() end
    Config.BuildPanel()
end

function Config.BuildPanel()
    return buildPanel()
end

function Config.OpenPanel()
    if not panel then buildPanel() end
    if Settings and Settings.OpenToCategory and Config._category then
        Settings.OpenToCategory(Config._category.ID)
    elseif InterfaceOptionsFrame_OpenToCategory then
        InterfaceOptionsFrame_OpenToCategory(panel)
        InterfaceOptionsFrame_OpenToCategory(panel)
    end
end

NS.Config = Config
```

- [ ] **Step 3: Sanity check**

```bash
grep -E "^function (Config\.|local function)" addon/JustInTime/Config.lua | wc -l
```

Expected: at least 12 (helper + Config public functions).

- [ ] **Step 4: Commit**

```bash
git add addon/JustInTime/Config.lua
git commit -m "✨ feat(addon): full Settings panel with all toggle widgets"
```

---

## Task 12 — Slash commands extension (Core.lua)

**Files:**
- Modify: `addon/JustInTime/Core.lua`

Replace the minimal `Core.lua` with the full bootstrap + extended slash commands. Per spec §6.5:

```
/jit                        → ouvre Settings panel
/jit help                   → liste les commandes
/jit show / /jit hide       → overlay visibility runtime
/jit lock / /jit unlock     → overlay drag
/jit mode <public|fastest|recent|median>  → switch reference mode
/jit reset                  → vide JustInTimeDB.runs (avec confirmation)
/jit test                   → run debug self-tests (PaceEngine etc.)
```

- [ ] **Step 1: Replace `addon/JustInTime/Core.lua`**

Use Write tool. Full content:

```lua
local addonName, NS = ...

local TAG  = (NS.Util and NS.Util.TAG_INFO)  or "|cffffcc00[JIT]|r"
local TAGD = (NS.Util and NS.Util.TAG_DEBUG) or "|cff33ff99[JIT][debug]|r"

local function L(key) return NS.L and NS.L[key] or key end

-- ─── Schema validation at load ──────────────────────────────────────────────

local function validateDataLuaSchema()
    local data = _G.JustInTimeData
    if not data then
        print(TAG .. " " .. L("DATA_MISSING"))
        return false
    end
    if type(data.meta) ~= "table" or type(data.dungeons) ~= "table" then
        print(TAG .. " " .. L("DATA_SCHEMA_INVALID"))
        return false
    end
    -- spot-check one dungeon for bosses + levels structure
    for _, dg in pairs(data.dungeons) do
        if type(dg.bosses) ~= "table" or type(dg.timer_ms) ~= "number" then
            print(TAG .. " " .. L("DATA_SCHEMA_INVALID"))
            return false
        end
        break
    end
    return true
end

local function checkStaleness()
    local data = _G.JustInTimeData
    if not data or not data.meta or not data.meta.generated_at then return end
    local s = data.meta.generated_at
    local Y, M, D = s:match("^(%d+)-(%d+)-(%d+)")
    if not Y then return end
    local genEpoch = time({ year = tonumber(Y), month = tonumber(M), day = tonumber(D), hour = 0, min = 0, sec = 0 })
    local days = math.floor((time() - genEpoch) / 86400)
    if days > 14 then
        print(TAG .. " " .. string.format(L("DATA_STALE"), days))
    end
end

-- ─── Self-tests (PaceEngine smoke) ─────────────────────────────────────────

local function runSelfTests()
    print(TAGD .. " " .. L("TEST_HEADER"))
    local PaceEngine = NS.PaceEngine
    if not PaceEngine then
        print(TAGD .. " PaceEngine not loaded")
        return
    end

    local tests = {}
    local function record(name, ok, expected, got)
        tests[#tests + 1] = { name = name, ok = ok, expected = tostring(expected), got = tostring(got) }
    end

    -- Test 1: ResolveAffixCombo sorts alphabetically
    local got = PaceEngine.ResolveAffixCombo({ 10, 9, 147 })
    local expected = "fortified-tyrannical-xalataths-guile"
    record("affix_combo_sort", got == expected, expected, got)

    -- Test 2: ComputePace returns zero delta with no kills
    local pace = PaceEngine.ComputePace(0, {}, { boss_splits_ms = { 280000, 740000, 1200000, 1742000 }, clear_time_ms = 1742000 })
    record("pace_no_kills", pace.delta_ms == 0, 0, pace.delta_ms)

    -- Test 3: ComputePace anchors to last killed boss
    local pace2 = PaceEngine.ComputePace(
        750000,
        { [0] = 280000, [1] = 740000 },
        { boss_splits_ms = { 280000, 740000, 1200000, 1742000 }, clear_time_ms = 1742000 }
    )
    -- Last anchor is ord=1, your_split=740000, ref=740000 → delta_at_anchor = 0
    -- elapsed=750000 < nextRefKill=1200000 → no drift → delta = 0
    record("pace_at_anchor", pace2.delta_ms == 0, 0, pace2.delta_ms)

    -- Test 4: ComputePace drifts past nextRefKill
    local pace3 = PaceEngine.ComputePace(
        1300000,  -- elapsed past ref's boss-3 kill (1200000)
        { [0] = 280000, [1] = 740000 },
        { boss_splits_ms = { 280000, 740000, 1200000, 1742000 }, clear_time_ms = 1742000 }
    )
    -- delta = 0 (anchor) + (1300000 - 1200000) = 100000
    record("pace_drift_past_ref", pace3.delta_ms == 100000, 100000, pace3.delta_ms)

    -- Test 5: SortedRefSplits returns ascending
    local sorted = PaceEngine.SortedRefSplits({ 1200000, 280000, 1742000, 740000 })
    -- Expected: ord 1 (280000), ord 3 (740000), ord 0 (1200000), ord 2 (1742000)
    local correct = sorted[1].split == 280000 and sorted[2].split == 740000 and sorted[3].split == 1200000 and sorted[4].split == 1742000
    record("sorted_ref_splits", correct, "asc", correct and "asc" or "wrong")

    local pass = 0
    for _, t in ipairs(tests) do
        if t.ok then
            pass = pass + 1
            print(TAGD .. " " .. string.format(L("TEST_PASS"), t.name))
        else
            print(TAGD .. " " .. string.format(L("TEST_FAIL"), t.name, t.expected, t.got))
        end
    end
    print(TAGD .. " " .. string.format(L("TEST_SUMMARY"), pass, #tests))
end

-- ─── Bootstrap ──────────────────────────────────────────────────────────────

local eventFrame = CreateFrame("Frame")

local function onAddonLoaded(name)
    if name ~= addonName then return end

    if NS.State then NS.State.Init() end
    if NS.Config then NS.Config.BuildPanel() end
    if NS.PaceEngine then NS.PaceEngine.Init() end
    if NS.EventTracker then NS.EventTracker.Init() end
    if NS.Overlay then NS.Overlay.Init() end

    validateDataLuaSchema()
    local brand = (NS.Util and NS.Util.flameText) and NS.Util.flameText("JustInTime") or "JustInTime"
    print(TAG .. " " .. string.format(L("ADDON_LOADED"), brand))
end

local function onPlayerLogin()
    checkStaleness()
end

eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then onAddonLoaded(...) end
    if event == "PLAYER_LOGIN" then onPlayerLogin() end
end)

-- ─── Slash commands ────────────────────────────────────────────────────────

SLASH_JIT1 = "/jit"
SlashCmdList.JIT = function(msg)
    msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    local cmd, rest = msg:match("^(%S+)%s*(.*)$")
    cmd = cmd or ""

    if cmd == "" then
        if NS.Config and NS.Config.OpenPanel then NS.Config.OpenPanel() end
        return
    end

    if cmd == "help" then
        print(TAG .. " " .. L("SLASH_HELP"))
        return
    end

    if cmd == "show" then
        if NS.Overlay and NS.Overlay.Show then NS.Overlay.Show() end
        return
    end
    if cmd == "hide" then
        if NS.Overlay and NS.Overlay.Hide then NS.Overlay.Hide() end
        return
    end

    if cmd == "lock" then
        if NS.State then NS.State.Config().overlay_position.locked = true end
        if NS.Overlay and NS.Overlay.RefreshDraggable then NS.Overlay.RefreshDraggable() end
        return
    end
    if cmd == "unlock" then
        if NS.State then NS.State.Config().overlay_position.locked = false end
        if NS.Overlay and NS.Overlay.RefreshDraggable then NS.Overlay.RefreshDraggable() end
        return
    end

    if cmd == "mode" then
        local valid = { public = true, fastest = true, recent = true, median = true }
        if not valid[rest] then
            print(TAG .. " " .. string.format(L("SLASH_UNKNOWN"), "mode " .. rest))
            return
        end
        local v = rest == "public" and "public" or ("perso_" .. rest)
        if NS.State then NS.State.Config().reference_mode = v end
        return
    end

    if cmd == "reset" then
        StaticPopup_Show("JIT_CONFIRM_RESET_RUNS")
        return
    end

    if cmd == "test" then
        runSelfTests()
        return
    end

    print(TAG .. " " .. string.format(L("SLASH_UNKNOWN"), cmd))
end
```

- [ ] **Step 2: Sanity check**

```bash
grep -E "^(SLASH_JIT|SlashCmdList\.JIT)" addon/JustInTime/Core.lua | wc -l
```

Expected: 2.

```bash
grep -E "^local function (validateDataLuaSchema|checkStaleness|runSelfTests|onAddonLoaded|onPlayerLogin)" addon/JustInTime/Core.lua | wc -l
```

Expected: 5.

- [ ] **Step 3: Commit**

```bash
git add addon/JustInTime/Core.lua
git commit -m "✨ feat(addon): Core slash commands + schema validation + staleness + selftests"
```

---

## Task 13 — In-game smoke test instructions

**Files:**
- Create: `docs/specs/2026-04-25-jit-smoketest.md`

The addon is feature-complete. Since WoW Lua has no automated test harness, we document the manual smoke test procedure for the user to execute.

- [ ] **Step 1: Create `docs/specs/2026-04-25-jit-smoketest.md`**

Use Write tool. Full content:

```markdown
# JustInTime — In-game smoke test procedure

After each meaningful Plan B change, verify in WoW:

## Setup

1. Symlink the addon into WoW: `ln -s /path/to/justInTime/addon/JustInTime ~/Games/wow/_retail_/Interface/AddOns/JustInTime`
2. Launch WoW Retail (Midnight, Interface 120001).
3. At the character select / main screen, confirm JustInTime is enabled in `/AddOns`.

## Boot tests (no key required)

1. **Login boot**: log in. Expected: `[JIT] JustInTime loaded. Type /jit for options.` in chat.
2. **Schema validation**: if `Data.lua` is corrupt, expected: `[JIT] ⚠ Data.lua schéma invalide`. Otherwise nothing.
3. **Staleness**: if `Data.lua` is >14 days old, expected: `[JIT] ⚠ données vieilles de N jours`.
4. **Self-tests**: `/jit test` → expected: 5 PASS lines + summary `5/5 tests passent`.

## Settings panel

1. `/jit` → Settings panel opens with title "JustInTime" in gradient (rouge → violet).
2. Verify all sections present: Référence (4 radios + 1 checkbox), Overlay graphique (2 radios + 1 checkbox + 1 button), Mode texte (3 checkboxes), Alerte critique (3 checkboxes), Données (1 line + 1 button).
3. Toggle each checkbox/radio → reload UI (`/reload`) → verify state persists.
4. `/jit show` → overlay appears (assuming popup mode disabled or in-key).
5. `/jit lock` then drag → overlay does not move. `/jit unlock` then drag → moves and persists.

## In-key tests

1. Start a Mythic+ key (any dungeon).
2. Verify overlay shows (in always mode) or appears at boss kill (in popup mode).
3. Kill a boss → expected:
   - Chat: `[JIT] <BossName> tué — <delta> vs <ref>` (if `chat_boss_kill` enabled)
   - Overlay updates: delta number, bar color shifts toward green/red, pip turns green for that boss.
4. Continue keying. If pace falls behind enough that ETA > timer:
   - Chat: `[JIT] ⚠ projection: déplate prévue à <ETA> (<over>)` (once)
   - Overlay: bar pulses red.
5. End the key (timed or depleted). Expected:
   - Chat: `[JIT] Run terminée <time> ✓ timée — <delta> vs <ref>` (or `Run dépletée`).
   - Overlay hides (always mode) or stays in popup state until next key.
6. Next key: reset behavior reproduces.

## /reload mid-key

1. Start a key, kill boss 1, kill boss 2.
2. `/reload` mid-run.
3. Expected: addon recovers active session (boss kills 1+2 still in `JustInTimeDB.active_session.boss_kills`); overlay resumes; subsequent kills append correctly.

## Reset confirmation

1. `/jit reset` → confirmation popup with FR text "Effacer toutes tes runs perso ? (impossible à annuler)".
2. Click "Oui" → expected: `[JIT] Runs perso effacées (N entrées)`.
3. `/jit reset` again → "Non" → no change.

## Edge cases

- **Unknown dungeon** (e.g., a Delve or Mythic 0 outside the 8 MN1 keystones): no crash; ref resolves to nil; overlay shows elapsed but "réf indispo" in row.
- **Key abandonned** (party leaves, leave instance): `CHALLENGE_MODE_RESET` fires; `active_session` cleared; overlay hides.
- **Deplete crossed mid-run**: overlay continues to track; after completion, recap chat says "dépletée".
- **Mode switch during key**: `/jit mode fastest` while a key is active → next overlay tick uses the new reference.

## Done

If all sections pass with no errors in chat (other than the expected info/warning lines), Plan B is verified. Report any anomaly with the chat log + relevant `JustInTimeDB` snapshot.
```

- [ ] **Step 2: Commit**

```bash
git add docs/specs/2026-04-25-jit-smoketest.md
git commit -m "📝 docs(addon): in-game smoke test procedure for Plan B"
```

---

## Self-review

After completing all 13 tasks, verify:

- [ ] **Module count** : `ls addon/JustInTime/*.lua` shows 9 files (Locales, Data, Config, State, PaceEngine, EventTracker, ChatPrinter, Overlay, Core).
- [ ] **`.toc` order** : matches the documented order; loads dependencies first.
- [ ] **No globals beyond `JustInTimeDB`, `JustInTimeData`, `SLASH_JIT1`, `SlashCmdList.JIT`** : `grep -E "^[A-Z][A-Za-z_]+ ?=" addon/JustInTime/*.lua | grep -v "^.*:--" | grep -v "^.*:local"` should only show those four.
- [ ] **`/jit test` self-tests pass in WoW** : 5/5.
- [ ] **In-game smoke test** : all sections of `docs/specs/2026-04-25-jit-smoketest.md` pass.
- [ ] **All commits atomic on `main`** : `git log --oneline addon/JustInTime/` shows 13+ commits, each scoped.
- [ ] **`main` branch only** : never pushed.

**Spec coverage check** (mapping plan → spec sections):

| Spec section | Tasks |
|---|---|
| §3 Architecture (Lua addon) | 1, 12 |
| §4.2 SavedVariables schema | 2 |
| §4.3 Lookup logic | 3 |
| §4.4 Pace model | 3 |
| §6.1 File structure | 1, 12 |
| §6.2 .toc | 1 |
| §6.3 Events | 4 |
| §6.4 PaceEngine API | 3 |
| §6.5 Slash commands | 12 |
| §6.6 Settings panel | 11 |
| §7.1 Overlay layout | 6 |
| §7.2 Color gradient | 7 |
| §7.3 Temporal behavior | 8, 10 |
| §7.4 Branding | 11 (NS.Util) |
| §7.5 Localization | 1 |
| §8 Edge cases & robustness | 4, 12 (schema validation, staleness) |
| §9.2 Lua test strategy | 12 (/jit test) |

If any spec requirement isn't covered, add a follow-up task before declaring Plan B done.

---

## Hand-off

Once Plan B is complete, the JustInTime addon is feature-complete for v1. The user (Claralicious_) installs it into WoW, runs through the smoke-test doc, and reports any issues. Subsequent iterations:

- Improve `Data.lua` coverage by raising `max_pages_per_query` in `jit_config.toml` and re-running `uv run jit-update`.
- Polish UI based on real in-key feedback.
- v2 candidates per spec §10.2: trash %, multi-language, per-character configs, cross-account sync, etc.
