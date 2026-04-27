local addonName, NS = ...

local TAG = (NS.Util and NS.Util.TAG_INFO) or "|cffffcc00[JIT]|r"

local function L(key) return NS.L and NS.L[key] or key end

-- ─── Schema validation at load ──────────────────────────────────────────────

local function validateDataLuaSchema()
    local data = _G.JustInTimeData
    if not data then
        print(TAG .. " " .. L("DATA_MISSING"))
        return false
    end
    if type(data.meta) ~= "table" or type(data.dungeons) ~= "table" then
        print(TAG .. " " .. L("DATA_SCHEMA_INVALID"))
        return false
    end
    for _, dg in pairs(data.dungeons) do
        if type(dg.bosses) ~= "table" or type(dg.timer_ms) ~= "number" then
            print(TAG .. " " .. L("DATA_SCHEMA_INVALID"))
            return false
        end
        break
    end
    return true
end

local function checkStaleness()
    local data = _G.JustInTimeData
    if not data or not data.meta or not data.meta.generated_at then return end
    local s = data.meta.generated_at
    local Y, M, D = s:match("^(%d+)-(%d+)-(%d+)")
    if not Y then return end
    local genEpoch = time({ year = tonumber(Y), month = tonumber(M), day = tonumber(D), hour = 0, min = 0, sec = 0 })
    local days = math.floor((time() - genEpoch) / 86400)
    if days > 14 then
        print(TAG .. " " .. string.format(L("DATA_STALE"), days))
    end
end

-- ─── Bootstrap ──────────────────────────────────────────────────────────────

local eventFrame = CreateFrame("Frame")

local function onAddonLoaded(name)
    if name ~= addonName then return end

    if NS.State then NS.State.Init() end
    if NS.Config then NS.Config.BuildPanel() end
    if NS.PaceEngine then NS.PaceEngine.Init() end
    if NS.EventTracker then NS.EventTracker.Init() end
    if NS.Overlay then NS.Overlay.Init() end

    validateDataLuaSchema()
    local brand = (NS.Util and NS.Util.flameText) and NS.Util.flameText("JustInTime") or "JustInTime"
    print(TAG .. " " .. string.format(L("ADDON_LOADED"), brand))
end

local function onPlayerLogin()
    checkStaleness()
end

eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then onAddonLoaded(...) end
    if event == "PLAYER_LOGIN" then onPlayerLogin() end
end)

-- ─── Slash commands ────────────────────────────────────────────────────────

SLASH_JIT1 = "/jit"
SlashCmdList.JIT = function(msg)
    msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    local cmd, rest = msg:match("^(%S+)%s*(.*)$")
    cmd = cmd or ""

    if cmd == "" then
        if NS.Config and NS.Config.OpenPanel then NS.Config.OpenPanel() end
        return
    end

    if cmd == "help" then
        print(TAG .. " " .. L("SLASH_HELP"))
        return
    end

    if cmd == "show" then
        if NS.Overlay and NS.Overlay.Show then NS.Overlay.Show() end
        return
    end
    if cmd == "hide" then
        if NS.Overlay and NS.Overlay.Hide then NS.Overlay.Hide() end
        return
    end

    if cmd == "lock" then
        if NS.State then NS.State.Config().overlay_position.locked = true end
        if NS.Overlay and NS.Overlay.RefreshDraggable then NS.Overlay.RefreshDraggable() end
        return
    end
    if cmd == "unlock" then
        if NS.State then NS.State.Config().overlay_position.locked = false end
        if NS.Overlay and NS.Overlay.RefreshDraggable then NS.Overlay.RefreshDraggable() end
        return
    end

    if cmd == "mode" then
        local valid = { public = true, fastest = true, recent = true, median = true }
        if not valid[rest] then
            print(TAG .. " " .. string.format(L("SLASH_UNKNOWN"), "mode " .. rest))
            return
        end
        local v = rest == "public" and "public" or ("perso_" .. rest)
        if NS.State then NS.State.Config().reference_mode = v end
        return
    end

    if cmd == "reset" then
        StaticPopup_Show("JIT_CONFIRM_RESET_RUNS")
        return
    end

    print(TAG .. " " .. string.format(L("SLASH_UNKNOWN"), cmd))
end
