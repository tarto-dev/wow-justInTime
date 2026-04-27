-- EventTracker: hooks M+ lifecycle events and ENCOUNTER_END to drive State.
-- All M+ key state mutations happen here.
local addonName, NS = ...

local EventTracker = {}

local frame = CreateFrame("Frame")

-- Authoritative source: Blizzard pushes the elapsed seconds via
-- ChallengeModeBlock:UpdateTime once per second. By hooking it we get the
-- exact value the in-game tracker displays, includes the 10s ready countdown
-- AND the cumulative death penalty by construction, /reload-safe.
local _blizzElapsed = nil
-- Last-resort fallback start time (used only if both the hook and
-- GetWorldElapsedTime are unavailable). Initialised at CHALLENGE_MODE_START
-- so the timer is never literally zero even in worst-case API failure.
local sessionStartTime = nil
-- Idempotency for the hooksecurefunc install (Blizzard_ObjectiveTracker is
-- load-on-demand, may load before OR after our addon).
local _hookInstalled = false

-- LE_WORLD_ELAPSED_TIMER_TYPE_CHALLENGE_MODE = 1. Hardcoded to avoid relying
-- on the global constant, which has been moved/renamed across patches.
local TIMER_TYPE_CHALLENGE_MODE = 1

-- ENCOUNTER_END fires for every dungeon, raid, and world-boss kill. We only
-- need it inside an active M+ key, so it's registered/unregistered around
-- the run lifecycle instead of being always-on.
local _RUN_EVENTS = { "ENCOUNTER_END" }

-- Resolve the boss ordinal for a given encounter ID by looking up Data.lua.
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

-- GetWorldElapsedTime has shipped with two signatures across patches:
--   2 returns: elapsed, type
--   3 returns: <widget/something>, elapsed, type
-- Probe the 3rd return to disambiguate.
local function readWorldElapsed(timerID)
    if not GetWorldElapsedTime or not timerID then return nil, nil end
    local r1, r2, r3 = GetWorldElapsedTime(timerID)
    if r3 ~= nil then
        return r2, r3
    end
    return r1, r2
end

-- Install hooksecurefunc on ChallengeModeBlock:UpdateTime. Idempotent.
-- Returns true if the hook is in place after the call (was or just became).
local function installChallengeBlockHook()
    if _hookInstalled then return true end
    local block = (ScenarioObjectiveTracker and ScenarioObjectiveTracker.ChallengeModeBlock)
        or (ScenarioBlocksFrame and ScenarioBlocksFrame.ChallengeModeBlock)
    if not (block and block.UpdateTime) then return false end
    hooksecurefunc(block, "UpdateTime", function(_, elapsedTime)
        if elapsedTime and elapsedTime >= 0 then
            _blizzElapsed = elapsedTime
        end
    end)
    _hookInstalled = true
    return true
end

local function registerRunEvents()
    for _, ev in ipairs(_RUN_EVENTS) do frame:RegisterEvent(ev) end
end

local function unregisterRunEvents()
    for _, ev in ipairs(_RUN_EVENTS) do frame:UnregisterEvent(ev) end
end

local function onChallengeModeStart()
    local mapId = C_ChallengeMode.GetActiveChallengeMapID()
    if not mapId then return end
    local level, affixIds = C_ChallengeMode.GetActiveKeystoneInfo()
    if not level or not affixIds then return end

    local PaceEngine = NS.PaceEngine
    local State = NS.State
    if not PaceEngine or not State then return end

    local slug = PaceEngine.MapIdToSlug(mapId) or ("unknown-" .. tostring(mapId))
    local combo = PaceEngine.ResolveAffixCombo(affixIds)
    -- Discard any stale push from the previous run before the new tick lands.
    _blizzElapsed = nil
    sessionStartTime = GetTime()
    -- Last-chance hook install in case Blizzard_ObjectiveTracker loaded
    -- after our Init() but before this event.
    installChallengeBlockHook()
    State.SetActiveSession(slug, level, combo, time())
    registerRunEvents()

    if NS.ChatPrinter and NS.ChatPrinter.AnnounceLevelFallbackIfNeeded then
        NS.ChatPrinter.AnnounceLevelFallbackIfNeeded()
    end
    if NS.Overlay and NS.Overlay.RefreshVisibility then
        NS.Overlay.RefreshVisibility()
    end
end

local function onEncounterEnd(encounterID, _encounterName, _difficultyID, _groupSize, success)
    if not C_ChallengeMode.IsChallengeModeActive() then return end
    if success ~= 1 and success ~= true then return end

    local State = NS.State
    if not State then return end
    local s = State.GetActiveSession()
    if not s then return end

    local elapsed_ms = EventTracker.GetElapsedMs()
    local ord = lookupOrdinalByEncounterId(s.dungeon_slug, encounterID)
    if ord ~= nil then
        State.RecordBossKill(ord, elapsed_ms)
        State.SnapshotActiveSession()
    end

    if NS.ChatPrinter and NS.ChatPrinter.OnBossKill then
        NS.ChatPrinter.OnBossKill(ord, elapsed_ms)
    end
    if NS.ChatPrinter and NS.ChatPrinter.CheckCriticalAlert then
        NS.ChatPrinter.CheckCriticalAlert(elapsed_ms)
    end
    if NS.Overlay and NS.Overlay.OnBossKillTrigger then
        NS.Overlay.OnBossKillTrigger()
    end
end

-- Authoritative completion time. The struct API is the modern path and
-- reportedly more reliable around depletion than GetWorldElapsedTime. Fall
-- back to the older GetCompletionInfo() shape if the struct API isn't there.
local function fetchCompletionInfo()
    if C_ChallengeMode.GetChallengeCompletionInfo then
        local info = C_ChallengeMode.GetChallengeCompletionInfo()
        if info and info.time and info.time > 0 then
            return info.time, info.onTime == true
        end
    end
    local _, _, time_ms, onTime = C_ChallengeMode.GetCompletionInfo()
    return time_ms, onTime == true
end

local function onChallengeModeCompleted()
    local State = NS.State
    if not State then return end
    local s = State.GetActiveSession()
    if not s then return end

    local clear_time_ms, timed = fetchCompletionInfo()
    clear_time_ms = clear_time_ms or EventTracker.GetElapsedMs()
    local depleted = not timed

    local run = State.FinalizeActiveSession(timed, depleted, clear_time_ms)
    _blizzElapsed = nil
    sessionStartTime = nil
    unregisterRunEvents()

    if NS.ChatPrinter and NS.ChatPrinter.OnKeyEnd and run then
        NS.ChatPrinter.OnKeyEnd(run)
    end
    if NS.Overlay and NS.Overlay.Hide then
        NS.Overlay.Hide()
    end
    if NS.Overlay and NS.Overlay.StopPulse then
        NS.Overlay.StopPulse()
    end
end

local function onChallengeModeReset()
    local State = NS.State
    if not State then return end
    State.DiscardActiveSession()
    _blizzElapsed = nil
    sessionStartTime = nil
    unregisterRunEvents()

    if NS.Overlay and NS.Overlay.Hide then
        NS.Overlay.Hide()
    end
    if NS.Overlay and NS.Overlay.StopPulse then
        NS.Overlay.StopPulse()
    end
end

-- Re-attach to a key in progress (fresh login or /reload mid-key). Idempotent
-- so the PEW delayed retry can fire it again safely.
local function recoverActiveSession()
    if not C_ChallengeMode.IsChallengeModeActive() then return end
    local State = NS.State
    if not State then return end
    local s = State.GetActiveSession()
    if not s or not s.started_epoch then return end
    -- Wall-clock fallback first; the next push from the hook (≤1s away)
    -- will overwrite _blizzElapsed with the precise value.
    sessionStartTime = GetTime() - (time() - s.started_epoch)
    installChallengeBlockHook()
    registerRunEvents()
end

local function onPlayerLogin()
    recoverActiveSession()
    if NS.ChatPrinter and NS.ChatPrinter.AnnounceLevelFallbackIfNeeded
       and C_ChallengeMode.IsChallengeModeActive() then
        NS.ChatPrinter.AnnounceLevelFallbackIfNeeded()
    end
end

local function onPlayerEnteringWorld()
    -- API state isn't fully populated at PEW; retry once after a delay so
    -- /reload mid-key picks up the live ChallengeModeBlock once Blizzard's
    -- own tracker has rebuilt itself.
    if C_Timer and C_Timer.After then
        C_Timer.After(10, recoverActiveSession)
    end
end

local function onPlayerLogout()
    if NS.State then NS.State.SnapshotActiveSession() end
end

local function onAddonLoaded(name)
    if name == "Blizzard_ObjectiveTracker" then
        installChallengeBlockHook()
    end
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
    elseif event == "PLAYER_ENTERING_WORLD" then
        onPlayerEnteringWorld()
    elseif event == "PLAYER_LOGOUT" then
        onPlayerLogout()
    elseif event == "ADDON_LOADED" then
        onAddonLoaded(...)
    end
end)

function EventTracker.Init()
    frame:RegisterEvent("CHALLENGE_MODE_START")
    frame:RegisterEvent("CHALLENGE_MODE_COMPLETED")
    frame:RegisterEvent("CHALLENGE_MODE_RESET")
    frame:RegisterEvent("PLAYER_LOGIN")
    frame:RegisterEvent("PLAYER_ENTERING_WORLD")
    frame:RegisterEvent("PLAYER_LOGOUT")
    frame:RegisterEvent("ADDON_LOADED")
    -- ENCOUNTER_END is registered/unregistered around the run lifecycle.
    -- Try installing the hook now in case Blizzard_ObjectiveTracker has
    -- already loaded (its ADDON_LOADED would not fire again for us).
    installChallengeBlockHook()
end

-- Three-tier elapsed source chain:
--   1. _blizzElapsed: cached push from ChallengeModeBlock:UpdateTime hook.
--      Same value the in-game tracker shows. Includes ready-countdown and
--      death penalty by construction.
--   2. select(2, GetWorldElapsedTime(1)) via readWorldElapsed: used while
--      the hook hasn't pushed yet (fresh login, before first tick).
--   3. (GetTime() - sessionStartTime) + GetDeathCount(): last-resort
--      fallback when both upstream sources are unavailable. Carries the
--      ~+10s start-of-key bias of the original v0.3.0 path.
function EventTracker.GetElapsedMs()
    if _blizzElapsed and _blizzElapsed > 0 then
        return math.floor(_blizzElapsed * 1000)
    end
    local elapsed, timerType = readWorldElapsed(1)
    if elapsed and elapsed > 0 and timerType == TIMER_TYPE_CHALLENGE_MODE then
        return math.floor(elapsed * 1000)
    end
    if not sessionStartTime then return 0 end
    local raw = math.floor((GetTime() - sessionStartTime) * 1000)
    if C_ChallengeMode and C_ChallengeMode.GetDeathCount then
        local _, timeLost = C_ChallengeMode.GetDeathCount()
        if timeLost and timeLost > 0 then
            raw = raw + math.floor(timeLost * 1000)
        end
    end
    return raw
end

NS.EventTracker = EventTracker
