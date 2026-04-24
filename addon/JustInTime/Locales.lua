local addonName, NS = ...

local locale = GetLocale()
local L = setmetatable({}, { __index = function(_, k) return k end })

local fr = {
    ADDON_LOADED = "JustInTime chargé. /jit pour les options.",
    FRAME_TITLE  = "JustInTime",
    SLASH_HELP   = "Commandes : /jit",
}

local en = {
    ADDON_LOADED = "JustInTime loaded. Type /jit for options.",
    FRAME_TITLE  = "JustInTime",
    SLASH_HELP   = "Commands: /jit",
}

local active = (locale == "enUS" or locale == "enGB") and en or fr
for k, v in pairs(active) do L[k] = v end

NS.L = L
