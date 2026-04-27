local addonName, NS = ...

local TAG  = (NS.Util and NS.Util.TAG_INFO)  or "|cffffcc00[JIT]|r"
local TAGD = (NS.Util and NS.Util.TAG_DEBUG) or "|cff33ff99[JIT][debug]|r"

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

-- ─── Self-tests (PaceEngine smoke) ─────────────────────────────────────────

local function runSelfTests()
    print(TAGD .. " " .. L("TEST_HEADER"))
    local PaceEngine = NS.PaceEngine
    if not PaceEngine then
        print(TAGD .. " PaceEngine not loaded")
        return
    end

    local tests = {}
    local function record(name, ok, expected, got)
        tests[#tests + 1] = { name = name, ok = ok, expected = tostring(expected), got = tostring(got) }
    end

    -- Test 1: ResolveAffixCombo sorts alphabetically
    local got = PaceEngine.ResolveAffixCombo({ 10, 9, 147 })
    local expected = "fortified-tyrannical-xalataths-guile"
    record("affix_combo_sort", got == expected, expected, got)

    -- Test 2: ComputePace returns zero delta with no kills
    local pace = PaceEngine.ComputePace(0, {}, { boss_splits_ms = { 280000, 740000, 1200000, 1742000 }, clear_time_ms = 1742000 })
    record("pace_no_kills", pace.delta_ms == 0, 0, pace.delta_ms)

    -- Test 3: ComputePace anchors to last killed boss
    local pace2 = PaceEngine.ComputePace(
        750000,
        { [0] = 280000, [1] = 740000 },
        { boss_splits_ms = { 280000, 740000, 1200000, 1742000 }, clear_time_ms = 1742000 }
    )
    record("pace_at_anchor", pace2.delta_ms == 0, 0, pace2.delta_ms)

    -- Test 4: ComputePace drifts past nextRefKill
    local pace3 = PaceEngine.ComputePace(
        1300000,
        { [0] = 280000, [1] = 740000 },
        { boss_splits_ms = { 280000, 740000, 1200000, 1742000 }, clear_time_ms = 1742000 }
    )
    record("pace_drift_past_ref", pace3.delta_ms == 100000, 100000, pace3.delta_ms)

    -- Test 5: SortedRefSplits returns ascending
    local sorted = PaceEngine.SortedRefSplits({ 1200000, 280000, 1742000, 740000 })
    local correct = sorted[1].split == 280000 and sorted[2].split == 740000 and sorted[3].split == 1200000 and sorted[4].split == 1742000
    record("sorted_ref_splits", correct, "asc", correct and "asc" or "wrong")

    -- Test 6: FindNearestLevel — exact match wins
    local lvls = { [18] = {}, [19] = {}, [20] = {} }
    record("nearest_level_exact", PaceEngine.FindNearestLevel(lvls, 19, 7) == 19, 19, PaceEngine.FindNearestLevel(lvls, 19, 7))

    -- Test 7: FindNearestLevel — picks closest within cap (15 → 18)
    record("nearest_level_below", PaceEngine.FindNearestLevel(lvls, 15, 7) == 18, 18, PaceEngine.FindNearestLevel(lvls, 15, 7))

    -- Test 8: FindNearestLevel — picks closest above (25 → 20)
    record("nearest_level_above", PaceEngine.FindNearestLevel(lvls, 25, 7) == 20, 20, PaceEngine.FindNearestLevel(lvls, 25, 7))

    -- Test 9: FindNearestLevel — beyond cap returns nil
    local nearest9 = PaceEngine.FindNearestLevel(lvls, 30, 7)
    record("nearest_level_capped", nearest9 == nil, "nil", tostring(nearest9))

    -- Test 10: FindNearestLevel — tie prefers lower level
    local lvls10 = { [12] = {}, [18] = {} }
    record("nearest_level_tie_lower", PaceEngine.FindNearestLevel(lvls10, 15, 7) == 12, 12, PaceEngine.FindNearestLevel(lvls10, 15, 7))

    local pass = 0
    for _, t in ipairs(tests) do
        if t.ok then
            pass = pass + 1
            print(TAGD .. " " .. string.format(L("TEST_PASS"), t.name))
        else
            print(TAGD .. " " .. string.format(L("TEST_FAIL"), t.name, t.expected, t.got))
        end
    end
    print(TAGD .. " " .. string.format(L("TEST_SUMMARY"), pass, #tests))
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

    if cmd == "test" then
        runSelfTests()
        return
    end

    print(TAG .. " " .. string.format(L("SLASH_UNKNOWN"), cmd))
end
