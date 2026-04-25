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
    active_session = nil,
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

    -- Schema version mismatch: nuke runs (best-effort migration), keep config.
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
    s.snapshot_at_epoch = time()
end

function State.FinalizeActiveSession(timed, depleted, clear_time_ms)
    local s = _G.JustInTimeDB.active_session
    if not s then return nil end

    -- Convert ordinal-keyed sparse table → array indexed by ordinal+1 (Lua 1-based).
    local boss_splits_ms = {}
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
        completed_at    = date("!%Y-%m-%dT%H:%M:%SZ"),
        dungeon_slug    = s.dungeon_slug,
        level           = s.level,
        affix_combo     = s.affix_combo,
        clear_time_ms   = clear_time_ms,
        timed           = timed,
        depleted        = depleted,
        boss_splits_ms  = boss_splits_ms,
        boss_kills_ord  = s.boss_kills,
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
    local name = UnitName("player")
    local realm = GetRealmName()
    local _, classToken = UnitClass("player")
    return {
        name = name or "?",
        realm = realm or "?",
        class = classToken and classToken:lower() or "?",
    }
end

NS.State = State
