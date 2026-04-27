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
    -- Extend hit area over the label so clicking the text toggles the box.
    cb:SetHitRectInsets(0, -260, 0, 0)
    cb:SetScript("OnShow", function(self) self:SetChecked(getConfig(path_chain) and true or false) end)
    cb:SetScript("OnClick", function(self) setConfig(path_chain, self:GetChecked() and true or false) end)
    return cb
end

local function makeRadioGroup(parent, options, x, y, path_chain)
    local radios = {}
    for i, opt in ipairs(options) do
        local r = CreateFrame("CheckButton", nil, parent, "UIRadioButtonTemplate")
        r:SetPoint("TOPLEFT", x, y - (i - 1) * 22)
        local txt = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        txt:SetPoint("LEFT", r, "RIGHT", 4, 1)
        txt:SetText(opt.label)
        -- Extend hit area over the label so clicking the text selects the radio.
        r:SetHitRectInsets(0, -260, 0, 0)
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
    fs:SetText(text)
    -- Underline rule for visual separation (the box-drawing chars used before
    -- weren't in GameFontNormalLarge and rendered as missing-glyph squares).
    local rule = parent:CreateTexture(nil, "ARTWORK")
    rule:SetTexture("Interface\\Buttons\\WHITE8x8")
    rule:SetVertexColor(0.6, 0.45, 0.15, 0.6)
    rule:SetSize(560, 1)
    rule:SetPoint("TOPLEFT", fs, "BOTTOMLEFT", 0, -2)
    return fs
end

local function dataAgeDays()
    if not _G.JustInTimeData or not _G.JustInTimeData.meta then return nil end
    local s = _G.JustInTimeData.meta.generated_at
    if not s then return nil end
    local Y, M, D = s:match("^(%d+)-(%d+)-(%d+)")
    if not Y then return nil end
    local genEpoch = time({ year = tonumber(Y), month = tonumber(M), day = tonumber(D), hour = 0, min = 0, sec = 0 })
    local nowEpoch = time()
    return math.floor((nowEpoch - genEpoch) / 86400), s:sub(1, 10)
end

local function buildPanel()
    if panel then return panel end
    panel = CreateFrame("Frame")
    panel.name = flameText("JustInTime")

    -- Footer stays anchored to the (non-scrolling) panel.
    buildFooter(panel)

    -- Scrollable content host. The Settings canvas does not scroll on its own,
    -- so wrap everything (except the footer) in a UIPanelScrollFrameTemplate.
    local scroll = CreateFrame("ScrollFrame", "JustInTimeOptionsScroll", panel, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", panel, "TOPLEFT", 0, 0)
    scroll:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -28, 28)

    local content = CreateFrame("Frame", "JustInTimeOptionsContent", scroll)
    content:SetSize(620, 720)
    scroll:SetScrollChild(content)
    panel.scroll = scroll
    panel.content = content

    -- Title (flame gradient, big) — lives inside scroll content
    local title = content:CreateFontString(nil, "ARTWORK", "GameFontNormalHuge")
    title:SetPoint("TOPLEFT", 16, -16)
    title:SetText(flameText("JustInTime"))

    local Y_TOP = -50
    -- ── Reference ──
    makeHeader(content, L("PANEL_REF_HEADER"), 16, Y_TOP)
    widgets.refRadios = makeRadioGroup(content, {
        { value = "public",          label = L("PANEL_REF_PUBLIC") },
        { value = "perso_fastest",   label = L("PANEL_REF_FASTEST") },
        { value = "perso_recent",    label = L("PANEL_REF_RECENT") },
        { value = "perso_median",    label = L("PANEL_REF_MEDIAN") },
    }, 32, Y_TOP - 22, { "reference_mode" })

    widgets.cbIgnoreAffixes = makeCheckbox(content, L("PANEL_IGNORE_AFFIXES"), 32, Y_TOP - 22 * 5, { "ignore_affixes" })

    -- ── Overlay ──
    local Y_OVL = Y_TOP - 22 * 7
    makeHeader(content, L("PANEL_OVERLAY_HEADER"), 16, Y_OVL)
    widgets.visRadios = makeRadioGroup(content, {
        { value = "always", label = L("PANEL_OVERLAY_ALWAYS") },
        { value = "popup",  label = L("PANEL_OVERLAY_POPUP") },
    }, 32, Y_OVL - 22, { "overlay_visibility" })

    widgets.cbLock = makeCheckbox(content, L("PANEL_OVERLAY_LOCK"), 32, Y_OVL - 22 * 3, { "overlay_position", "locked" })
    widgets.cbLock:HookScript("OnClick", function()
        if NS.Overlay and NS.Overlay.RefreshDraggable then NS.Overlay.RefreshDraggable() end
    end)

    makeButton(content, L("PANEL_OVERLAY_RESET"), 32, Y_OVL - 22 * 4, 200, function()
        if NS.Overlay and NS.Overlay.ResetPosition then NS.Overlay.ResetPosition() end
    end)

    widgets.btnAnchor = makeButton(content, L("PANEL_OVERLAY_ANCHOR_SHOW"), 32, Y_OVL - 22 * 5, 240, function() end)
    widgets.btnAnchor:SetScript("OnClick", function(self)
        if not (NS.Overlay and NS.Overlay.ToggleAnchor) then return end
        NS.Overlay.ToggleAnchor()
        local on = NS.Overlay.IsAnchorMode and NS.Overlay.IsAnchorMode()
        self:SetText(L(on and "PANEL_OVERLAY_ANCHOR_HIDE" or "PANEL_OVERLAY_ANCHOR_SHOW"))
    end)
    widgets.btnAnchor:HookScript("OnShow", function(self)
        local on = NS.Overlay and NS.Overlay.IsAnchorMode and NS.Overlay.IsAnchorMode()
        self:SetText(L(on and "PANEL_OVERLAY_ANCHOR_HIDE" or "PANEL_OVERLAY_ANCHOR_SHOW"))
    end)

    -- ── Chat triggers ──
    local Y_CHAT = Y_OVL - 22 * 7
    makeHeader(content, L("PANEL_CHAT_HEADER"), 16, Y_CHAT)
    widgets.cbBossKill = makeCheckbox(content, L("PANEL_CHAT_BOSS_KILL"), 32, Y_CHAT - 22, { "triggers", "chat_boss_kill" })
    widgets.cbKeyEnd   = makeCheckbox(content, L("PANEL_CHAT_KEY_END"),   32, Y_CHAT - 22 * 2, { "triggers", "chat_key_end" })
    widgets.cbThreshold = makeCheckbox(content, L("PANEL_CHAT_THRESHOLD"), 32, Y_CHAT - 22 * 3, { "triggers", "chat_threshold_cross" })

    -- ── Critical alerts ──
    local Y_CRIT = Y_CHAT - 22 * 5
    makeHeader(content, L("PANEL_CRIT_HEADER"), 16, Y_CRIT)
    widgets.cbCritVisual = makeCheckbox(content, L("PANEL_CRIT_VISUAL"), 32, Y_CRIT - 22, { "critical_alerts", "visual" })
    widgets.cbCritChat   = makeCheckbox(content, L("PANEL_CRIT_CHAT"),   32, Y_CRIT - 22 * 2, { "critical_alerts", "chat" })
    widgets.cbCritSound  = makeCheckbox(content, L("PANEL_CRIT_SOUND"),  32, Y_CRIT - 22 * 3, { "critical_alerts", "sound" })

    -- ── Data ──
    local Y_DATA = Y_CRIT - 22 * 5
    makeHeader(content, L("PANEL_DATA_HEADER"), 16, Y_DATA)
    local dataLabel = content:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    dataLabel:SetPoint("TOPLEFT", 32, Y_DATA - 22)
    dataLabel:SetWidth(500)
    dataLabel:SetJustifyH("LEFT")
    panel.dataLabel = dataLabel

    makeButton(content, L("PANEL_DATA_RESET_RUNS"), 32, Y_DATA - 22 * 3, 240, function()
        StaticPopup_Show("JIT_CONFIRM_RESET_RUNS")
    end)

    panel:SetScript("OnShow", function()
        local days, dateStr = dataAgeDays()
        if days then
            local mark = days <= 14 and "✓" or "⚠"
            dataLabel:SetText(string.format(L("PANEL_DATA_GENERATED"), dateStr or "?", days, mark))
        else
            dataLabel:SetText(L("PANEL_DATA_NONE"))
        end
    end)

    if Settings and Settings.RegisterCanvasLayoutCategory then
        local category = Settings.RegisterCanvasLayoutCategory(panel, panel.name)
        Settings.RegisterAddOnCategory(category)
        Config._category = category
    elseif InterfaceOptions_AddCategory then
        InterfaceOptions_AddCategory(panel)
    end

    StaticPopupDialogs["JIT_CONFIRM_RESET_RUNS"] = {
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
