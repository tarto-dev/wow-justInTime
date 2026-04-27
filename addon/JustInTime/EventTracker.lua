-- EventTracker: hooks M+ lifecycle events and ENCOUNTER_END to drive State.
-- All M+ key state mutations happen here.
local addonName, NS = ...

local EventTracker = {}

local frame = CreateFrame("Frame")

-- Primary clock: GetTime() snapshot at CHALLENGE_MODE_START. Always set during
-- an active key, so the elapsed value is never zero.
local sessionStartTime = nil
-- Optional: official Blizzard challenge timer ID (from WORLD_STATE_TIMER_START
-- or scanned via GetWorldElapsedTimers). Used solely to re-align sessionStartTime
-- to the precise t0 (post 10s countdown), since CHALLENGE_MODE_START fires too
-- early. If the world-timer events never arrive we still have a working clock.
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

-- GetWorldElapsedTime has shipped with two signatures across patches:
--   2 returns: elapsed, type
--   3 returns: <widget/something>, elapsed, type
-- We probe the 3rd return to disambiguate.
local function readWorldElapsed(timerID)
    if not GetWorldElapsedTime or not timerID then return nil, nil end
    local r1, r2, r3 = GetWorldElapsedTime(timerID)
    if r3 ~= nil then
        return r2, r3
    end
    return r1, r2
end

-- Scan active world timers for the challenge-mode one. Used after /reload
-- (WORLD_STATE_TIMER_START already fired before our handler was registered)
-- and as a lazy recovery path.
local function findActiveChallengeTimer()
    if not GetWorldElapsedTimers then return nil end
    for _, timerID in ipairs({ GetWorldElapsedTimers() }) do
        local _, timerType = readWorldElapsed(timerID)
        if timerType == TIMER_TYPE_CHALLENGE_MODE then
            return timerID
        end
    end
    return nil
end

-- Pull the official timer's elapsed and shift sessionStartTime so our
-- (GetTime() - sessionStartTime) matches Blizzard's clock to the ms.
local function realignFromOfficialTimer()
    if not challengeTimerID then return end
    local elapsed, timerType = readWorldElapsed(challengeTimerID)
    if not elapsed or timerType ~= TIMER_TYPE_CHALLENGE_MODE then return end
    sessionStartTime = GetTime() - elapsed
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
    -- Provisional t0. Captured at keystone insertion, before the 10s ready
    -- countdown ends — so this is ~10s too early. WORLD_STATE_TIMER_START
    -- (or a lazy scan via findActiveChallengeTimer) will realign it shortly.
    sessionStartTime = GetTime()
    challengeTimerID = challengeTimerID or findActiveChallengeTimer()
    if challengeTimerID then
        realignFromOfficialTimer()
    end
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
    sessionStartTime = nil
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
    sessionStartTime = nil
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
    local _, timerType = readWorldElapsed(timerID)
    if timerType == TIMER_TYPE_CHALLENGE_MODE then
        challengeTimerID = timerID
        realignFromOfficialTimer()
    end
end

local function onWorldStateTimerStop(timerID)
    if challengeTimerID and timerID == challengeTimerID then
        challengeTimerID = nil
    end
end

local function onPlayerLogin()
    if C_ChallengeMode.IsChallengeModeActive() then
        local State = NS.State
        if not State then return end
        local s = State.GetActiveSession()
        if s and s.started_epoch then
            -- Reload mid-key: best initial estimate is wall-clock since the
            -- recorded start. Will be replaced by realignFromOfficialTimer()
            -- if we can find the live world timer.
            local elapsedSec = time() - s.started_epoch
            sessionStartTime = GetTime() - elapsedSec
            challengeTimerID = findActiveChallengeTimer()
            if challengeTimerID then
                realignFromOfficialTimer()
            end
        end
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

-- Compose the elapsed value from two sources:
--   1. (GetTime() - sessionStartTime): always available; sessionStartTime is
--      realigned to Blizzard's t0 whenever WORLD_STATE_TIMER_START is heard,
--      so the displayed clock matches the in-game one to the ms.
--   2. C_ChallengeMode.GetDeathCount() timeLost: cumulative death penalty,
--      which scales with affixes/level (5s → 15s on +12+ with Xal'atath's
--      Guile). We re-attempt a realignment opportunistically in case the
--      world timer event arrives after our handler is registered.
function EventTracker.GetElapsedMs()
    if not sessionStartTime then return 0 end
    if not challengeTimerID then
        challengeTimerID = findActiveChallengeTimer()
        if challengeTimerID then realignFromOfficialTimer() end
    end
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
