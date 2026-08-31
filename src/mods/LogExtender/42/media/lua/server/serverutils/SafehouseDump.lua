-- Dump current SafeHouse / Faction list to Lua/mb_safehouses.json (cachedir).
-- Do not early-return on isServer() at file load — GameServer may parse this first.

local function q(value)
    local s = tostring(value or "")
    s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", " ")
    return '"' .. s .. '"'
end

local function membersOf(house)
    local names = {}
    if not house or not house.getPlayers then
        return names
    end
    local players = house:getPlayers()
    if not players then
        return names
    end
    for i = 0, players:size() - 1 do
        names[#names + 1] = tostring(players:get(i))
    end
    return names
end

local function houseObject(house)
    local x = math.floor(house:getX())
    local y = math.floor(house:getY())
    local x2 = math.floor(house:getX2())
    local y2 = math.floor(house:getY2())
    local title = ""
    if house.getTitle then
        title = tostring(house:getTitle() or "")
    end
    local expiry = ""
    if house.getLastVisited then
        expiry = tostring(house:getLastVisited() or "")
    end
    return {
        owner = tostring(house:getOwner() or ""),
        title = title,
        x = x,
        y = y,
        w = math.abs(x2 - x),
        h = math.abs(y2 - y),
        x2 = x2,
        y2 = y2,
        members = membersOf(house),
        expiry = expiry,
    }
end

local function factionObject(faction)
    local name = ""
    if faction.getName then
        name = tostring(faction:getName() or "")
    end
    local owner = ""
    if faction.getOwner then
        owner = tostring(faction:getOwner() or "")
    end
    local tag = ""
    if faction.getTag then
        tag = tostring(faction:getTag() or "")
    end
    local members = {}
    if faction.getPlayers then
        local players = faction:getPlayers()
        if players then
            for i = 0, players:size() - 1 do
                members[#members + 1] = tostring(players:get(i))
            end
        end
    end
    return { name = name, owner = owner, tag = tag, members = members }
end

local function writeJson(houses, factions)
    local writer = getFileWriter("mb_safehouses.json", true, false)
    if not writer then
        return
    end
    writer:write("{\n")
    local stamp = ""
    if getTimestamp then
        stamp = tostring(getTimestamp())
    end
    writer:write('  "updated_at": ' .. q(stamp) .. ",\n")
    writer:write('  "safehouses": [\n')
    for i = 1, #houses do
        local h = houses[i]
        writer:write("    {")
        writer:write("\"owner\":" .. q(h.owner) .. ",")
        writer:write("\"title\":" .. q(h.title) .. ",")
        writer:write("\"x\":" .. tostring(h.x) .. ",")
        writer:write("\"y\":" .. tostring(h.y) .. ",")
        writer:write("\"w\":" .. tostring(h.w) .. ",")
        writer:write("\"h\":" .. tostring(h.h) .. ",")
        writer:write("\"x2\":" .. tostring(h.x2) .. ",")
        writer:write("\"y2\":" .. tostring(h.y2) .. ",")
        writer:write("\"expiry\":" .. q(h.expiry) .. ",")
        writer:write("\"members\":[")
        for j = 1, #h.members do
            if j > 1 then
                writer:write(",")
            end
            writer:write(q(h.members[j]))
        end
        writer:write("]}")
        if i < #houses then
            writer:write(",")
        end
        writer:write("\n")
    end
    writer:write("  ],\n")
    writer:write('  "factions": [\n')
    for i = 1, #factions do
        local f = factions[i]
        writer:write("    {")
        writer:write("\"name\":" .. q(f.name) .. ",")
        writer:write("\"owner\":" .. q(f.owner) .. ",")
        writer:write("\"tag\":" .. q(f.tag) .. ",")
        writer:write("\"members\":[")
        for j = 1, #f.members do
            if j > 1 then
                writer:write(",")
            end
            writer:write(q(f.members[j]))
        end
        writer:write("]}")
        if i < #factions then
            writer:write(",")
        end
        writer:write("\n")
    end
    writer:write("  ]\n")
    writer:write("}\n")
    writer:close()
end

local function dumpSafehouses()
    if isClient() then
        return
    end
    local houses = {}
    if SafeHouse and SafeHouse.getSafehouseList then
        local list = SafeHouse.getSafehouseList()
        if list then
            for i = 0, list:size() - 1 do
                local house = list:get(i)
                if house then
                    houses[#houses + 1] = houseObject(house)
                end
            end
        end
    end
    local factions = {}
    if Faction and Faction.getFactions then
        local list = Faction.getFactions()
        if list then
            for i = 0, list:size() - 1 do
                local faction = list:get(i)
                if faction then
                    factions[#factions + 1] = factionObject(faction)
                end
            end
        end
    end
    writeJson(houses, factions)
end

Events.OnInitGlobalModData.Add(dumpSafehouses)
if Events.OnServerStarted then
    Events.OnServerStarted.Add(dumpSafehouses)
end
if Events.EveryHours then
    Events.EveryHours.Add(dumpSafehouses)
end
