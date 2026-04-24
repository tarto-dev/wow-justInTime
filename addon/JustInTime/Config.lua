local addonName, NS = ...
local Config = {}

Config.defaults = {
    enabled = true,
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

function Config.Load()
    _G.JustInTimeDB = _G.JustInTimeDB or {}
    deepMerge(_G.JustInTimeDB, Config.defaults)
end

-- Per-letter tricolor gradient with midpoint forced to the middle color.
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

local BRAND_RED          = { 0xFF, 0x44, 0x44 }
local BRAND_MID_VIOLET   = { 0xB8, 0x60, 0xD0 }
local BRAND_LIGHT_VIOLET = { 0xC8, 0xA0, 0xFF }

-- Chat tag "[JIT]" — green brackets, first letter red, rest light violet.
local TAG_INFO  = "|cff33ff99[|r|cffff3333J|r|cffc8a0ffIT|r|cff33ff99]|r"
local TAG_DEBUG = TAG_INFO .. "|cff888888[debug]|r"

NS.Util = {
    gradientText        = gradientText,
    BRAND_RED           = BRAND_RED,
    BRAND_MID_VIOLET    = BRAND_MID_VIOLET,
    BRAND_LIGHT_VIOLET  = BRAND_LIGHT_VIOLET,
    TAG_INFO            = TAG_INFO,
    TAG_DEBUG           = TAG_DEBUG,
}

local function buildFooter(parent)
    local fs = parent:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    fs:SetPoint("BOTTOMLEFT", parent, "BOTTOMLEFT", 16, 12)
    fs:SetText("By " .. gradientText(AUTHOR_HANDLE, FR_BLEU, FR_BLANC, FR_ROUGE))
end

local panel
function Config.BuildPanel()
    if panel then return panel end
    panel = CreateFrame("Frame")

    local title = panel:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", 16, -16)
    title:SetText("JustInTime")

    buildFooter(panel)

    local displayName = gradientText("JustInTime", BRAND_RED, BRAND_MID_VIOLET, BRAND_LIGHT_VIOLET)
    if Settings and Settings.RegisterCanvasLayoutCategory then
        local category = Settings.RegisterCanvasLayoutCategory(panel, displayName)
        Settings.RegisterAddOnCategory(category)
        Config._category = category
    elseif InterfaceOptions_AddCategory then
        panel.name = displayName
        InterfaceOptions_AddCategory(panel)
    end

    return panel
end

function Config.OpenPanel()
    if not panel then Config.BuildPanel() end
    if Settings and Settings.OpenToCategory and Config._category then
        Settings.OpenToCategory(Config._category.ID)
    elseif InterfaceOptionsFrame_OpenToCategory then
        InterfaceOptionsFrame_OpenToCategory(panel)
        InterfaceOptionsFrame_OpenToCategory(panel)
    end
end

NS.Config = Config
