local addonName, NS = ...

local TAG  = (NS.Util and NS.Util.TAG_INFO)  or "|cffffcc00[JIT]|r"
local TAGD = (NS.Util and NS.Util.TAG_DEBUG) or "|cff33ff99[JIT][debug]|r"

local eventFrame = CreateFrame("Frame")

local function onAddonLoaded(name)
    if name ~= addonName then return end
    NS.Config.Load()
    NS.Config.BuildPanel()
    print(TAG .. " " .. NS.L.ADDON_LOADED)
end

eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then onAddonLoaded(...) end
end)

SLASH_JIT1 = "/jit"
SlashCmdList.JIT = function(msg)
    msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    if msg == "" then
        NS.Config.OpenPanel()
    else
        print(TAG .. " " .. NS.L.SLASH_HELP)
    end
end
