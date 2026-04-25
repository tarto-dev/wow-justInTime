-- PaceEngine: pure-logic module for pace computation against Data.lua reference.
-- All functions are deterministic given inputs; no global side-effects beyond the
-- mapIdToSlug lookup populated once at Init().
local addonName, NS = ...

local PaceEngine = {}

local mapIdToSlug = {}
local affixIdToSlug = {}

function PaceEngine.Init()
    if not _G.JustInTimeData then return end
    local data = _G.JustInTimeData

    if data.affix_id_to_slug then
        for id, slug in pairs(data.affix_id_to_slug) do
            affixIdToSlug[id] = slug
        end
    end

    if data.dungeons then
        for slug, dg in pairs(data.dungeons) do
            if dg.challenge_mode_id then
                mapIdToSlug[dg.challenge_mode_id] = slug
            end
        end
    end
end

function PaceEngine.MapIdToSlug(map_id)
    return mapIdToSlug[map_id]
end

-- Given a list of WoW affix IDs, returns the alphabetically-sorted combo slug.
-- E.g., {10, 9, 147} → "fortified-tyrannical-xalataths-guile".
function PaceEngine.ResolveAffixCombo(affix_ids)
    local slugs = {}
    for _, id in ipairs(affix_ids) do
        local s = affixIdToSlug[id]
        if s then slugs[#slugs + 1] = s end
    end
    table.sort(slugs)
    return table.concat(slugs, "-")
end

-- Aggregate a pool of personal runs into a synthetic reference cell.
-- mode: "fastest" | "recent" | "median"
function PaceEngine.AggregatePersonalRuns(runs, mode)
    if not runs or #runs == 0 then return nil end

    local pickedRun
    if mode == "fastest" then
        for _, r in ipairs(runs) do
            if not pickedRun or r.clear_time_ms < pickedRun.clear_time_ms then
                pickedRun = r
            end
        end
    elseif mode == "recent" then
        for _, r in ipairs(runs) do
            if not pickedRun or (r.completed_at or "") > (pickedRun.completed_at or "") then
                pickedRun = r
            end
        end
    elseif mode == "median" then
        local maxLen = 0
        for _, r in ipairs(runs) do
            if r.boss_splits_ms and #r.boss_splits_ms > maxLen then
                maxLen = #r.boss_splits_ms
            end
        end
        local medianSplits = {}
        for i = 1, maxLen do
            local values = {}
            for _, r in ipairs(runs) do
                if r.boss_splits_ms and r.boss_splits_ms[i] then
                    values[#values + 1] = r.boss_splits_ms[i]
                end
            end
            if #values > 0 then
                table.sort(values)
                medianSplits[i] = values[math.ceil(#values / 2)]
            end
        end
        local clearTimes = {}
        for _, r in ipairs(runs) do
            if r.clear_time_ms then clearTimes[#clearTimes + 1] = r.clear_time_ms end
        end
        table.sort(clearTimes)
        local medianClear = clearTimes[math.ceil(#clearTimes / 2)] or 0

        return {
            boss_splits_ms = medianSplits,
            clear_time_ms  = medianClear,
            num_bosses     = maxLen,
            source_label   = "perso_median",
            sample_size    = #runs,
        }
    else
        return nil
    end

    if not pickedRun then return nil end
    return {
        boss_splits_ms = pickedRun.boss_splits_ms or {},
        clear_time_ms  = pickedRun.clear_time_ms,
        num_bosses     = #(pickedRun.boss_splits_ms or {}),
        source_label   = "perso_" .. mode,
        sample_size    = 1,
    }
end

-- Look up the active reference cell based on State.GetActiveSession() + State.Config().
-- Returns nil if no session, no Data.lua, or no matching cell (and no fallback hits).
function PaceEngine.GetReferenceForActive()
    local State = NS.State
    if not State then return nil end
    local s = State.GetActiveSession()
    if not s then return nil end
    local cfg = State.Config()
    local data = _G.JustInTimeData

    if cfg.reference_mode == "public" then
        if not data or not data.dungeons or not data.dungeons[s.dungeon_slug] then
            return nil
        end
        local dg = data.dungeons[s.dungeon_slug]
        local levelEntry = dg.levels and dg.levels[s.level]
        if not levelEntry then return nil end
        local cell = levelEntry[s.affix_combo]
        local comboUsed = s.affix_combo
        if not cell and cfg.ignore_affixes then
            for combo, c in pairs(levelEntry) do
                cell = c
                comboUsed = combo
                break
            end
        end
        if not cell then return nil end
        return {
            boss_splits_ms     = cell.boss_splits_ms,
            clear_time_ms      = cell.clear_time_ms,
            num_bosses         = dg.num_bosses,
            source_label       = "public",
            affix_combo_used   = comboUsed,
            sample_size        = cell.sample_size,
        }
    else
        local subtype = cfg.reference_mode:match("^perso_(.+)$")
        if not subtype then return nil end
        local pool = State.GetPersonalRuns(
            s.dungeon_slug,
            s.level,
            cfg.ignore_affixes and nil or s.affix_combo
        )
        local agg = PaceEngine.AggregatePersonalRuns(pool, subtype)
        if agg then return agg end
        -- Fallback to public if no perso data
        if data and data.dungeons and data.dungeons[s.dungeon_slug] then
            local dg = data.dungeons[s.dungeon_slug]
            local levelEntry = dg.levels and dg.levels[s.level]
            if levelEntry then
                local cell = levelEntry[s.affix_combo]
                if cell then
                    return {
                        boss_splits_ms     = cell.boss_splits_ms,
                        clear_time_ms      = cell.clear_time_ms,
                        num_bosses         = dg.num_bosses,
                        source_label       = "public_fallback",
                        affix_combo_used   = s.affix_combo,
                        sample_size        = cell.sample_size,
                    }
                end
            end
        end
        return nil
    end
end

-- Helper: returns ref splits as { {ord=K, split=T}, ... } sorted ascending by T.
-- Skips zero/nil splits. ord is the 0-based ordinal (boss_splits_ms[i] corresponds to ordinal i-1).
function PaceEngine.SortedRefSplits(ref_splits_ms)
    local list = {}
    for i, t in ipairs(ref_splits_ms) do
        if t and t > 0 then
            list[#list + 1] = { ord = i - 1, split = t }
        end
    end
    table.sort(list, function(a, b) return a.split < b.split end)
    return list
end

-- Anchor-based pace computation per design spec §4.4.
function PaceEngine.ComputePace(elapsed_ms, your_kills_by_ord, ref)
    if not ref or not ref.boss_splits_ms then
        return {
            delta_ms = 0,
            projected_finish_ms = 0,
            deplete_projected = false,
            normalized = 0,
            last_anchor_ord = nil,
        }
    end
    local refClear = ref.clear_time_ms or 0

    -- Find the last anchor (your most recent kill in time order)
    local lastYourSplit = 0
    local lastYourOrd = nil
    for ord, t in pairs(your_kills_by_ord) do
        if t > lastYourSplit then
            lastYourSplit = t
            lastYourOrd = ord
        end
    end

    -- delta_at_anchor = your_split[ord] - ref.boss_splits_ms[ord+1]
    local deltaAtAnchor = 0
    if lastYourOrd ~= nil then
        local refTLast = ref.boss_splits_ms[lastYourOrd + 1] or 0
        if refTLast > 0 then
            deltaAtAnchor = lastYourSplit - refTLast
        end
    end

    -- Sorted ref kills (chronological) → find next ref kill after lastYourSplit
    local sortedRef = PaceEngine.SortedRefSplits(ref.boss_splits_ms)
    local nextRefKill = refClear
    for _, entry in ipairs(sortedRef) do
        if entry.split > lastYourSplit then
            nextRefKill = entry.split
            break
        end
    end

    -- Conservative drift: if elapsed > nextRefKill, ref would have killed by now.
    local drift = 0
    if elapsed_ms > nextRefKill then
        drift = elapsed_ms - nextRefKill
    end
    local deltaContinuous = deltaAtAnchor + drift

    -- Projection: ratio of last-anchor pace, applied to ref total
    local projectedFinish = refClear
    if lastYourSplit > 0 and lastYourOrd ~= nil then
        local refTLast = ref.boss_splits_ms[lastYourOrd + 1] or 0
        if refTLast > 0 then
            local ratio = lastYourSplit / refTLast
            projectedFinish = math.floor(refClear * ratio)
        end
    end
    if drift > 0 then
        projectedFinish = projectedFinish + drift
    end

    local normalized = 0
    if refClear > 0 then
        normalized = deltaContinuous / refClear
        if normalized > 0.10 then normalized = 0.10 end
        if normalized < -0.10 then normalized = -0.10 end
    end

    return {
        delta_ms            = deltaContinuous,
        projected_finish_ms = projectedFinish,
        deplete_projected   = false,
        normalized          = normalized,
        last_anchor_ord     = lastYourOrd,
    }
end

NS.PaceEngine = PaceEngine
