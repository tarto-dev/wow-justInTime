-- ChatPrinter: emit chat messages for boss kills, key end, threshold cross,
-- and critical alerts. All gated by cfg.triggers and cfg.critical_alerts.
local addonName, NS = ...

local ChatPrinter = {}

local lastNormalizedSign = 0
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
        return string.format("Boss %d", (ord or 0) + 1)
    end
    local dg = data.dungeons[dungeon_slug]
    for _, b in ipairs(dg.bosses or {}) do
        if b.ordinal == ord then return b.name or b.slug end
    end
    return string.format("Boss %d", (ord or 0) + 1)
end

-- Announce once per session if the resolved reference is from a different
-- key level than the active session (level fallback hit).
function ChatPrinter.AnnounceLevelFallbackIfNeeded()
    local State = NS.State
    local PaceEngine = NS.PaceEngine
    if not State or not PaceEngine then return end
    local s = State.GetActiveSession()
    if not s then return end
    if s.level_fallback_announced then return end

    local ref = PaceEngine.GetReferenceForActive()
    if not ref or not ref.level_used or ref.level_used == s.level then return end

    print(string.format("%s %s", tag(),
        string.format(L("LEVEL_FALLBACK_INFO"), s.level, ref.level_used)))
    s.level_fallback_announced = true
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
    if not State then return end
    local cfg = State.Config()
    if not cfg.triggers.chat_key_end then return end

    -- Re-resolve reference for the dungeon/level/affix that JUST finished.
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
    criticalFiredThisKey = false
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

    -- Threshold cross trigger: only when sign of normalized delta flips
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
            PlaySound(8959)
        end
        if cfg.critical_alerts.visual and NS.Overlay and NS.Overlay.PulseCritical then
            NS.Overlay.PulseCritical()
        end
    end
end

NS.ChatPrinter = ChatPrinter
