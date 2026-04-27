-- Overlay: CD-1 layout. Flame brand title + delta + gradient bar + pips + info rows.
-- This task creates the skeleton; color mapping / visibility modes / drag / pulse
-- are layered in subsequent tasks.
local addonName, NS = ...

local Overlay = {}

local frame
local titleFS, deltaFS
local barTrack, barFill, barMarker
local pips = {}
local rowElapsed, rowETA, rowLast, rowRef
local bossRows = {}  -- { [i] = { name, my, ref } } — boss table

local MAX_BOSS_ROWS = 6

local UPDATE_INTERVAL = 0.1

-- Brand color anchors for delta-driven gradient mapping.
local COLOR_AHEAD_STRONG  = { 0.19, 0.78, 0.39 }  -- 30C864 vert vif
local COLOR_AHEAD_LIGHT   = { 0.49, 0.85, 0.48 }  -- 7ED87A vert pâle
local COLOR_NEUTRAL       = { 0.78, 0.62, 1.00 }  -- C8A0FF violet pâle
local COLOR_BEHIND_LIGHT  = { 0.85, 0.47, 0.62 }  -- D878A0 violet rosé
local COLOR_BEHIND_STRONG = { 1.00, 0.31, 0.31 }  -- FF5050 rouge

local function lerpRGB(a, b, t)
    return {
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
        a[3] + (b[3] - a[3]) * t,
    }
end

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

local function L(key) return NS.L and NS.L[key] or key end

local function formatTime(ms)
    return NS.ChatPrinter and NS.ChatPrinter.FormatTime(ms) or "0:00"
end

local function buildFrame()
    frame = CreateFrame("Frame", "JustInTimeOverlay", UIParent, "BackdropTemplate")
    frame:SetSize(300, 234)
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
    barFill:SetVertexColor(0.78, 0.62, 1.0, 1)
    barFill:SetWidth(0)

    barMarker = barTrack:CreateTexture(nil, "OVERLAY")
    barMarker:SetTexture("Interface\\Buttons\\WHITE8x8")
    barMarker:SetVertexColor(1, 0.92, 0.23, 1)
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

    -- Boss table (per-boss splits: name | your time | ref time)
    -- Separator line above the table for visual cleanliness.
    local sep = frame:CreateTexture(nil, "ARTWORK")
    sep:SetTexture("Interface\\Buttons\\WHITE8x8")
    sep:SetVertexColor(0.3, 0.3, 0.35, 0.7)
    sep:SetSize(280, 1)
    sep:SetPoint("TOPLEFT", 10, -124)

    for i = 1, MAX_BOSS_ROWS do
        local y = -130 - (i - 1) * 14
        local nameFS = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        nameFS:SetPoint("TOPLEFT", 10, y)
        nameFS:SetWidth(160)
        nameFS:SetJustifyH("LEFT")
        nameFS:SetWordWrap(false)

        local myFS = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        myFS:SetPoint("TOPRIGHT", -60, y)
        myFS:SetJustifyH("RIGHT")

        local refFS = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        refFS:SetPoint("TOPRIGHT", -10, y)
        refFS:SetJustifyH("RIGHT")

        nameFS:Hide()
        myFS:Hide()
        refFS:Hide()

        bossRows[i] = { name = nameFS, my = myFS, ref = refFS }
    end

    frame.elapsedAccum = 0
    frame:SetScript("OnUpdate", function(self, elapsed)
        self.elapsedAccum = (self.elapsedAccum or 0) + elapsed
        if self.elapsedAccum < UPDATE_INTERVAL then return end
        self.elapsedAccum = 0
        if Overlay.anchorMode then return end
        if not C_ChallengeMode.IsChallengeModeActive() then
            Overlay.Hide()
            return
        end
        Overlay.Tick()
    end)

    frame:Hide()
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
    local bosses = nil
    if data and data.dungeons and data.dungeons[s.dungeon_slug] then
        local dg = data.dungeons[s.dungeon_slug]
        num_bosses = dg.num_bosses or 4
        timer_ms = dg.timer_ms or 1800000
        bosses = dg.bosses
    end

    local kills_count = 0
    local last_split_ms = 0
    for _, t in pairs(s.boss_kills) do
        kills_count = kills_count + 1
        if t > last_split_ms then last_split_ms = t end
    end

    Overlay.SetData(elapsed_ms, pace, num_bosses, kills_count, last_split_ms, ref, timer_ms, bosses, s.boss_kills)
end

local function updateBossTable(elapsed_ms, num_bosses, ref, bosses, your_kills_by_ord)
    local n = math.min(MAX_BOSS_ROWS, num_bosses or 0)
    local refClear = (ref and ref.clear_time_ms and ref.clear_time_ms > 0) and ref.clear_time_ms or 0

    -- Find next-up boss = smallest unkilled ordinal in [0, n-1].
    local nextOrd = nil
    if your_kills_by_ord then
        for ord = 0, n - 1 do
            if not your_kills_by_ord[ord] then
                nextOrd = ord
                break
            end
        end
    else
        nextOrd = 0
    end

    for i = 1, MAX_BOSS_ROWS do
        local row = bossRows[i]
        if not row then break end
        local boss = bosses and bosses[i]
        if i <= n and boss then
            local ord = boss.ordinal or (i - 1)
            local refSplit = ref and ref.boss_splits_ms and ref.boss_splits_ms[ord + 1]
            local yourSplit = your_kills_by_ord and your_kills_by_ord[ord]

            row.name:SetText(boss.name or ("Boss " .. tostring(ord + 1)))
            row.ref:SetText((refSplit and refSplit > 0) and formatTime(refSplit) or "—")

            if yourSplit then
                row.my:SetText(formatTime(yourSplit))
                local delta = (refSplit and refSplit > 0) and (yourSplit - refSplit) or 0
                local norm = (refClear > 0) and (delta / refClear) or 0
                local c = mapDeltaToColor(norm)
                row.my:SetTextColor(c[1], c[2], c[3])
            elseif ord == nextOrd then
                row.my:SetText(formatTime(elapsed_ms))
                local delta = (refSplit and refSplit > 0) and (elapsed_ms - refSplit) or 0
                local norm = (refClear > 0) and (delta / refClear) or 0
                local c = mapDeltaToColor(norm)
                row.my:SetTextColor(c[1], c[2], c[3])
            else
                row.my:SetText("—")
                row.my:SetTextColor(0.5, 0.5, 0.5)
            end

            row.name:Show()
            row.my:Show()
            row.ref:Show()
        else
            row.name:Hide()
            row.my:Hide()
            row.ref:Hide()
        end
    end
end

function Overlay.SetData(elapsed_ms, pace, num_bosses, kills_count, last_split_ms, ref, timer_ms, bosses, your_kills_by_ord)
    if not frame then return end

    if NS.ChatPrinter and pace then
        local s = NS.ChatPrinter.FormatDelta(pace.delta_ms)
        deltaFS:SetText(s)
    end

    local projected = (pace and pace.projected_finish_ms) or timer_ms or 1
    if projected < 1 then projected = 1 end
    local progress = math.min(1, elapsed_ms / projected)
    barFill:SetWidth(280 * progress)
    barMarker:SetPoint("TOP", barTrack, "TOPLEFT", 280 * progress, 2)
    local color = mapDeltaToColor(pace and pace.normalized or 0)
    barFill:SetVertexColor(color[1], color[2], color[3], 1)

    local n = math.min(6, num_bosses or 4)
    for i = 1, 6 do
        if i <= n then
            local pip = pips[i]
            -- "TOP" anchors at the top-center of the pip; center on the segment midpoint.
            local x = (280 / n) * (i - 0.5)
            pip:ClearAllPoints()
            pip:SetPoint("TOP", barTrack, "TOPLEFT", x, -10)
            if i <= (kills_count or 0) then
                pip:SetVertexColor(0.19, 0.78, 0.39, 1)
            else
                pip:SetVertexColor(0.18, 0.18, 0.20, 1)
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

    updateBossTable(elapsed_ms, num_bosses, ref, bosses, your_kills_by_ord)
end

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

function Overlay.Show()
    if frame then frame:Show() end
end

function Overlay.Hide()
    if frame then frame:Hide() end
end

function Overlay.GetFrame()
    return frame
end

-- ─── Visibility modes (Task 8) ─────────────────────────────────────────────

local POPUP_HOLD_SECONDS = 6
local FADE_IN_SECONDS    = 0.3
local FADE_OUT_SECONDS   = 0.5

local popupHideTimer

local function fadeOutThenHide()
    if not frame then return end
    UIFrameFadeOut(frame, FADE_OUT_SECONDS, frame:GetAlpha(), 0)
    C_Timer.After(FADE_OUT_SECONDS, function()
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
    end
    -- popup mode: only show in response to triggers
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

-- ─── Drag + lock (Task 9) ──────────────────────────────────────────────────

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

-- ─── Anchor / placement mode ───────────────────────────────────────────────
-- Renders the overlay outside of any active challenge so the user can drag it
-- to a chosen spot from the Settings panel. Transient (not persisted).

Overlay.anchorMode = false

function Overlay.IsAnchorMode()
    return Overlay.anchorMode == true
end

function Overlay.ShowAnchor()
    if not frame then Overlay.Init() end
    if not frame then return end
    Overlay.anchorMode = true

    -- Force-enable drag, regardless of the saved "locked" preference.
    frame:EnableMouse(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", function(self) self:StartMoving() end)
    frame:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
        persistPosition()
    end)

    -- Populate placeholder values so the frame doesn't look empty.
    local dummyPace = {
        delta_ms = 0,
        normalized = 0,
        projected_finish_ms = 1700000,
    }
    local dummyBosses = {
        { name = "Boss 1", ordinal = 0 },
        { name = "Boss 2", ordinal = 1 },
        { name = "Boss 3", ordinal = 2 },
        { name = "Boss 4", ordinal = 3 },
    }
    local dummyRef = {
        clear_time_ms  = 1700000,
        boss_splits_ms = { 425000, 850000, 1275000, 1700000 },
    }
    local dummyKills = { [0] = 410000, [1] = 845000 }
    Overlay.SetData(900000, dummyPace, 4, 2, 845000, dummyRef, 1800000, dummyBosses, dummyKills)

    frame:SetAlpha(1)
    frame:Show()
end

function Overlay.HideAnchor()
    Overlay.anchorMode = false
    Overlay.RefreshDraggable()
    Overlay.RefreshVisibility()
end

function Overlay.ToggleAnchor()
    if Overlay.anchorMode then
        Overlay.HideAnchor()
    else
        Overlay.ShowAnchor()
    end
end

-- ─── Critical pulse (Task 10) ──────────────────────────────────────────────

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

    barFill:SetVertexColor(1.0, 0.31, 0.31, 1)
    pulseAnimation:Play()
end

function Overlay.StopPulse()
    if pulseAnimation and pulsing then
        pulseAnimation:Stop()
        barFill:SetAlpha(1)
    end
    pulsing = false
end

NS.Overlay = Overlay
