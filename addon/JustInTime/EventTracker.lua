-- EventTracker: hooks M+ lifecycle events and ENCOUNTER_END to drive State.
-- All M+ key state mutations happen here.
local addonName, NS = ...

local EventTracker = {}

local frame = CreateFrame("Frame")
local challengeTimerID = nil

-- LE_WORLD_ELAPSED_TIMER_TYPE_CHALLENGE_MODE = 1. Hardcoded to avoid relying
-- on the global constant, which has been moved/renamed across patches.
local TIMER_TYPE_CHALLENGE_MODE = 1

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

-- Scan active world timers for the challenge-mode one. Used after /reload
-- (WORLD_STATE_TIMER_START already fired before our handler was registered)
-- and as a lazy recovery path inside GetElapsedMs.
local function findActiveChallengeTimer()
    if not GetWorldElapsedTimers then return nil end
    for _, timerID in ipairs({ GetWorldElapsedTimers() }) do
        local _, timerType = GetWorldElapsedTime(timerID)
        if timerType == TIMER_TYPE_CHALLENGE_MODE then
            return timerID
        end
    end
    return nil
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
    -- The official challenge timer hasn't started yet at this point (10s
    -- ready countdown). WORLD_STATE_TIMER_START will hand us the timerID,
    -- and GetElapsedMs() lazy-scans as a fallback.
    challengeTimerID = challengeTimerID or findActiveChallengeTimer()
    State.SetActiveSession(slug, level, combo, time())

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

local function onChallengeModeCompleted()
    local State = NS.State
    if not State then return end
    local s = State.GetActiveSession()
    if not s then return end

    local _, _, time_ms, onTime = C_ChallengeMode.GetCompletionInfo()
    local clear_time_ms = time_ms or EventTracker.GetElapsedMs()
    local timed = onTime == true
    local depleted = not timed

    local run = State.FinalizeActiveSession(timed, depleted, clear_time_ms)
    challengeTimerID = nil

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
    challengeTimerID = nil

    if NS.Overlay and NS.Overlay.Hide then
        NS.Overlay.Hide()
    end
    if NS.Overlay and NS.Overlay.StopPulse then
        NS.Overlay.StopPulse()
    end
end

local function onWorldStateTimerStart(timerID)
    if not timerID then return end
    local _, timerType = GetWorldElapsedTime(timerID)
    if timerType == TIMER_TYPE_CHALLENGE_MODE then
        challengeTimerID = timerID
    end
end

local function onWorldStateTimerStop(timerID)
    if challengeTimerID and timerID == challengeTimerID then
        challengeTimerID = nil
    end
end

local function onPlayerLogin()
    if C_ChallengeMode.IsChallengeModeActive() then
        -- After /reload mid-key, WORLD_STATE_TIMER_START already fired before
        -- our handler was registered, so scan the live timers list directly.
        challengeTimerID = findActiveChallengeTimer()
        if NS.ChatPrinter and NS.ChatPrinter.AnnounceLevelFallbackIfNeeded then
            NS.ChatPrinter.AnnounceLevelFallbackIfNeeded()
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
    elseif event == "WORLD_STATE_TIMER_START" then
        onWorldStateTimerStart(...)
    elseif event == "WORLD_STATE_TIMER_STOP" then
        onWorldStateTimerStop(...)
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
    frame:RegisterEvent("WORLD_STATE_TIMER_START")
    frame:RegisterEvent("WORLD_STATE_TIMER_STOP")
    frame:RegisterEvent("PLAYER_LOGIN")
    frame:RegisterEvent("PLAYER_LOGOUT")
end

-- Read the elapsed seconds straight from Blizzard's official challenge timer
-- (the same one driving the in-game clock). It already accounts for the 10s
-- ready countdown AND the cumulative death penalty, so we don't compose our
-- own value. Returns 0 when no timer is active or the API is unavailable.
function EventTracker.GetElapsedMs()
    if not challengeTimerID then
        challengeTimerID = findActiveChallengeTimer()
    end
    if not challengeTimerID then return 0 end
    local elapsed, timerType = GetWorldElapsedTime(challengeTimerID)
    if not elapsed or timerType ~= TIMER_TYPE_CHALLENGE_MODE then
        challengeTimerID = nil
        return 0
    end
    return math.floor(elapsed * 1000)
end

NS.EventTracker = EventTracker
