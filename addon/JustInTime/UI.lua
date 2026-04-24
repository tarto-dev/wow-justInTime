local addonName, NS = ...
local UI = {}

local mainFrame

local function ensureFrame()
    if mainFrame then return end
    mainFrame = CreateFrame("Frame", "JustInTimeFrame", UIParent, "BackdropTemplate")
    mainFrame:SetSize(320, 60)
    mainFrame:SetFrameStrata("MEDIUM")
    mainFrame:SetPoint("CENTER")
    if mainFrame.SetBackdrop then
        mainFrame:SetBackdrop({
            bgFile   = "Interface\\Buttons\\WHITE8x8",
            edgeFile = "Interface\\Buttons\\WHITE8x8",
            edgeSize = 1,
        })
        mainFrame:SetBackdropColor(0, 0, 0, 0.6)
        mainFrame:SetBackdropBorderColor(0.2, 0.2, 0.2, 1)
    end

    local title = mainFrame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    title:SetPoint("TOPLEFT", 8, -4)
    local U = NS.Util
    if U and U.gradientText then
        title:SetText(U.gradientText(NS.L.FRAME_TITLE, U.BRAND_RED, U.BRAND_MID_VIOLET, U.BRAND_LIGHT_VIOLET))
    else
        title:SetText(NS.L.FRAME_TITLE)
    end

    mainFrame:Hide()
    UI.mainFrame = mainFrame
end

function UI.Show() ensureFrame(); mainFrame:Show() end
function UI.Hide() if mainFrame then mainFrame:Hide() end end

NS.UI = UI
