-- EventTracker: hooks M+ lifecycle events and ENCOUNTER_END to drive State.
-- All M+ key state mutations happen here.
local addonName, NS = ...

local EventTracker = {}

local frame = CreateFrame("Frame")
local sessionStartTime = nil  -- GetTime() at CHALLENGE_MODE_START (relative seconds float)

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
    sessionStartTime = GetTime()
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

    local elapsed_ms = math.floor((GetTime() - (sessionStartTime or GetTime())) * 1000)
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
    local clear_time_ms = time_ms or math.floor((GetTime() - (sessionStartTime or GetTime())) * 1000)
    local timed = onTime == true
    local depleted = not timed

    local run = State.FinalizeActiveSession(timed, depleted, clear_time_ms)
    sessionStartTime = nil

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

    if NS.Overlay and NS.Overlay.Hide then
        NS.Overlay.Hide()
    end
    if NS.Overlay and NS.Overlay.StopPulse then
        NS.Overlay.StopPulse()
    end
end

local function onPlayerLogin()
    if C_ChallengeMode.IsChallengeModeActive() then
        local State = NS.State
        if not State then return end
        local s = State.GetActiveSession()
        if s and s.started_epoch then
            local now = time()
            local elapsedSec = now - s.started_epoch
            sessionStartTime = GetTime() - elapsedSec
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
