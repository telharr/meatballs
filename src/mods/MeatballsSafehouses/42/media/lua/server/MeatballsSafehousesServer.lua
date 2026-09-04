-- Server authority: poll panel commands, mutate SafeHouse list, dump JSON.

if not MeatballsSafehouses then
    require "MeatballsSafehouses"
end

MeatballsSafehousesServer = MeatballsSafehousesServer or {}
MeatballsSafehousesServer._pollTick = 0
MeatballsSafehousesServer._bridgeTick = 0
MeatballsSafehousesServer._seenNonces = {}

local function jsonQuote(value)
    return MeatballsSafehouses.jsonQuote(value)
end

local function stamp()
    if getTimestamp then
        return tostring(getTimestamp())
    end
    return ""
end

local function writeFile(name, body)
    local writer = getFileWriter(name, true, false)
    if not writer then
        return false
    end
    writer:write(body or "")
    writer:close()
    return true
end

local function readAll(name)
    local reader = getFileReader(name, false)
    if not reader then
        return nil
    end
    local chunks = {}
    local line = reader:readLine()
    while line do
        chunks[#chunks + 1] = string.gsub(line, "[\r\n]", "")
        line = reader:readLine()
    end
    reader:close()
    return table.concat(chunks, "\n")
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
    local i = 0
    while i < players:size() do
        names[#names + 1] = tostring(players:get(i))
        i = i + 1
    end
    return names
end

local function houseObject(house)
    local x = math.floor(house:getX())
    local y = math.floor(house:getY())
    local w = math.floor(house:getW())
    local h = math.floor(house:getH())
    local x2 = x + w
    local y2 = y + h
    if house.getX2 then
        x2 = math.floor(house:getX2())
    end
    if house.getY2 then
        y2 = math.floor(house:getY2())
    end
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
        w = w,
        h = h,
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
            local i = 0
            while i < players:size() do
                members[#members + 1] = tostring(players:get(i))
                i = i + 1
            end
        end
    end
    return { name = name, owner = owner, tag = tag, members = members }
end

local function writeMembersJson(names)
    local parts = {}
    local i = 1
    while i <= #names do
        if i > 1 then
            parts[#parts + 1] = ","
        end
        parts[#parts + 1] = jsonQuote(names[i])
        i = i + 1
    end
    return table.concat(parts)
end

function MeatballsSafehousesServer.dump()
    local houses = {}
    if SafeHouse and SafeHouse.getSafehouseList then
        local list = SafeHouse.getSafehouseList()
        if list then
            local i = 0
            while i < list:size() do
                local house = list:get(i)
                if house then
                    houses[#houses + 1] = houseObject(house)
                end
                i = i + 1
            end
        end
    end
    local factions = {}
    if Faction and Faction.getFactions then
        local list = Faction.getFactions()
        if list then
            local i = 0
            while i < list:size() do
                local faction = list:get(i)
                if faction then
                    factions[#factions + 1] = factionObject(faction)
                end
                i = i + 1
            end
        end
    end
    local buf = {}
    buf[#buf + 1] = "{\n"
    buf[#buf + 1] = '  "updated_at": ' .. jsonQuote(stamp()) .. ",\n"
    buf[#buf + 1] = '  "mod": ' .. jsonQuote(MeatballsSafehouses.MODULE) .. ",\n"
    buf[#buf + 1] = '  "safehouses": [\n'
    local hi = 1
    while hi <= #houses do
        local h = houses[hi]
        buf[#buf + 1] = "    {"
        buf[#buf + 1] = '"owner":' .. jsonQuote(h.owner) .. ","
        buf[#buf + 1] = '"title":' .. jsonQuote(h.title) .. ","
        buf[#buf + 1] = '"x":' .. tostring(h.x) .. ","
        buf[#buf + 1] = '"y":' .. tostring(h.y) .. ","
        buf[#buf + 1] = '"w":' .. tostring(h.w) .. ","
        buf[#buf + 1] = '"h":' .. tostring(h.h) .. ","
        buf[#buf + 1] = '"x2":' .. tostring(h.x2) .. ","
        buf[#buf + 1] = '"y2":' .. tostring(h.y2) .. ","
        buf[#buf + 1] = '"expiry":' .. jsonQuote(h.expiry) .. ","
        buf[#buf + 1] = '"members":[' .. writeMembersJson(h.members) .. "]}"
        if hi < #houses then
            buf[#buf + 1] = ","
        end
        buf[#buf + 1] = "\n"
        hi = hi + 1
    end
    buf[#buf + 1] = "  ],\n"
    buf[#buf + 1] = '  "factions": [\n'
    local fi = 1
    while fi <= #factions do
        local f = factions[fi]
        buf[#buf + 1] = "    {"
        buf[#buf + 1] = '"name":' .. jsonQuote(f.name) .. ","
        buf[#buf + 1] = '"owner":' .. jsonQuote(f.owner) .. ","
        buf[#buf + 1] = '"tag":' .. jsonQuote(f.tag) .. ","
        buf[#buf + 1] = '"members":[' .. writeMembersJson(f.members) .. "]}"
        if fi < #factions then
            buf[#buf + 1] = ","
        end
        buf[#buf + 1] = "\n"
        fi = fi + 1
    end
    buf[#buf + 1] = "  ]\n}\n"
    writeFile(MeatballsSafehouses.DUMP_FILE, table.concat(buf))
    return #houses
end

function MeatballsSafehousesServer.writeBridge()
    local body = "{\n"
        .. '  "ok": true,\n'
        .. '  "mod": ' .. jsonQuote(MeatballsSafehouses.MODULE) .. ",\n"
        .. '  "version": ' .. jsonQuote(MeatballsSafehouses.VERSION) .. ",\n"
        .. '  "polled_at": ' .. jsonQuote(stamp()) .. "\n"
        .. "}\n"
    writeFile(MeatballsSafehouses.BRIDGE_FILE, body)
end

function MeatballsSafehousesServer.writeAck(ok, nonce, op, err, extra)
    extra = extra or {}
    local body = "{\n"
        .. '  "ok": ' .. (ok and "true" or "false") .. ",\n"
        .. '  "nonce": ' .. jsonQuote(nonce or "") .. ",\n"
        .. '  "op": ' .. jsonQuote(op or "") .. ",\n"
        .. '  "error": ' .. jsonQuote(err or "") .. ",\n"
        .. '  "x": ' .. tostring(extra.x or 0) .. ",\n"
        .. '  "y": ' .. tostring(extra.y or 0) .. ",\n"
        .. '  "w": ' .. tostring(extra.w or 0) .. ",\n"
        .. '  "h": ' .. tostring(extra.h or 0) .. ",\n"
        .. '  "updated_at": ' .. jsonQuote(stamp()) .. "\n"
        .. "}\n"
    writeFile(MeatballsSafehouses.ACK_FILE, body)
end

local function parseBlocks(text)
    local blocks = {}
    if not text or text == "" then
        return blocks
    end
    local cur = {}
    local has = false
    for line in string.gmatch(text .. "\n", "([^\n]*)\n") do
        line = string.gsub(line, "[\r\n]", "")
        if line == "---" then
            if has then
                blocks[#blocks + 1] = cur
            end
            cur = {}
            has = false
        elseif line ~= "" then
            local key, value = string.match(line, "^([^=]+)=(.*)$")
            if key then
                key = string.gsub(key, "%s+$", "")
                value = string.gsub(value, "[\r\n]", "")
                cur[key] = value
                has = true
            end
        end
    end
    if has then
        blocks[#blocks + 1] = cur
    end
    return blocks
end

local function toInt(value, fallback)
    local n = tonumber(value)
    if not n then
        return fallback or 0
    end
    return math.floor(n)
end

function MeatballsSafehousesServer.findHouse(x, y, w, h)
    if not SafeHouse or not SafeHouse.getSafehouseList then
        return nil
    end
    local list = SafeHouse.getSafehouseList()
    if not list then
        return nil
    end
    local i = 0
    while i < list:size() do
        local house = list:get(i)
        if house
            and house:getX() == x
            and house:getY() == y
            and house:getW() == w
            and house:getH() == h then
            return house
        end
        i = i + 1
    end
    return nil
end

function MeatballsSafehousesServer.overlapping(x, y, w, h, ignore)
    local x2 = x + w
    local y2 = y + h
    if SafeHouse and SafeHouse.getSafehouseOverlapping then
        if ignore then
            return SafeHouse.getSafehouseOverlapping(x, y, x2, y2, ignore)
        end
        return SafeHouse.getSafehouseOverlapping(x, y, x2, y2)
    end
    local existing = MeatballsSafehousesServer.findHouse(x, y, w, h)
    if existing and existing ~= ignore then
        return existing
    end
    return nil
end

local function broadcast(command, args)
    local ok, players = pcall(function()
        if not sendServerCommand or not getOnlinePlayers then
            return nil
        end
        return getOnlinePlayers()
    end)
    if not ok or not players then
        return
    end
    local i = 0
    while i < players:size() do
        local player = players:get(i)
        if player then
            pcall(function()
                sendServerCommand(player, MeatballsSafehouses.MODULE, command, args)
            end)
        end
        i = i + 1
    end
end

local function addMembers(house, names)
    if not house or not house.addPlayer then
        return
    end
    local owner = ""
    if house.getOwner then
        owner = tostring(house:getOwner() or "")
    end
    local i = 1
    while i <= #names do
        local name = names[i]
        if name ~= "" and name ~= owner then
            house:addPlayer(name)
        end
        i = i + 1
    end
end

local function kickMembers(house, names)
    if not house then
        return
    end
    local i = 1
    while i <= #names do
        local name = names[i]
        if name ~= "" then
            if SafeHouse and SafeHouse.kickUserFromSafehouse then
                SafeHouse.kickUserFromSafehouse(house, name)
            elseif house.removePlayer then
                house:removePlayer(name)
            end
        end
        i = i + 1
    end
end

local function payloadFromHouse(house, extra)
    extra = extra or {}
    extra.x = math.floor(house:getX())
    extra.y = math.floor(house:getY())
    extra.w = math.floor(house:getW())
    extra.h = math.floor(house:getH())
    extra.owner = tostring(house:getOwner() or "")
    extra.title = ""
    if house.getTitle then
        extra.title = tostring(house:getTitle() or "")
    end
    extra.members = table.concat(membersOf(house), ",")
    return extra
end

function MeatballsSafehousesServer.applyCreate(cmd)
    local x = toInt(cmd.x)
    local y = toInt(cmd.y)
    local w = toInt(cmd.w)
    local h = toInt(cmd.h)
    local owner = MeatballsSafehouses.decode(cmd.owner or "")
    local title = MeatballsSafehouses.decode(cmd.title or "")
    local members = MeatballsSafehouses.splitCsv(cmd.members or "")
    if w < 1 or h < 1 then
        return false, "size must be at least 1x1", { x = x, y = y, w = w, h = h }
    end
    if owner == "" then
        return false, "owner required", { x = x, y = y, w = w, h = h }
    end
    if title == "" then
        title = owner
    end
    if not SafeHouse or not SafeHouse.addSafeHouse then
        return false, "SafeHouse API missing", { x = x, y = y, w = w, h = h }
    end
    local clash = MeatballsSafehousesServer.overlapping(x, y, w, h, nil)
    if clash then
        return false, "intersects another safehouse", { x = x, y = y, w = w, h = h }
    end
    local house = SafeHouse.addSafeHouse(x, y, w, h, owner)
    if not house then
        return false, "addSafeHouse returned nil", { x = x, y = y, w = w, h = h }
    end
    if house.setTitle then
        house:setTitle(title)
    end
    if house.setOwner then
        house:setOwner(owner)
    end
    addMembers(house, members)
    local args = payloadFromHouse(house, { op = "create" })
    broadcast("apply", args)
    return true, "", args
end

function MeatballsSafehousesServer.applyUpdate(cmd)
    local x = toInt(cmd.x)
    local y = toInt(cmd.y)
    local w = toInt(cmd.w)
    local h = toInt(cmd.h)
    local house = MeatballsSafehousesServer.findHouse(x, y, w, h)
    if not house then
        return false, "safehouse not found", { x = x, y = y, w = w, h = h }
    end
    if cmd.title ~= nil then
        local title = MeatballsSafehouses.decode(cmd.title)
        if house.setTitle then
            house:setTitle(title)
        end
    end
    if cmd.owner ~= nil and cmd.owner ~= "" then
        local owner = MeatballsSafehouses.decode(cmd.owner)
        if house.setOwner then
            house:setOwner(owner)
        end
    end
    addMembers(house, MeatballsSafehouses.splitCsv(cmd.add or ""))
    kickMembers(house, MeatballsSafehouses.splitCsv(cmd.kick or ""))
    if cmd.members ~= nil and cmd.members ~= "" then
        addMembers(house, MeatballsSafehouses.splitCsv(cmd.members))
    end
    local args = payloadFromHouse(house, { op = "update" })
    broadcast("apply", args)
    return true, "", args
end

function MeatballsSafehousesServer.applyRelease(cmd)
    local x = toInt(cmd.x)
    local y = toInt(cmd.y)
    local w = toInt(cmd.w)
    local h = toInt(cmd.h)
    local house = MeatballsSafehousesServer.findHouse(x, y, w, h)
    if not house then
        return false, "safehouse not found", { x = x, y = y, w = w, h = h }
    end
    local args = payloadFromHouse(house, { op = "release" })
    if SafeHouse and SafeHouse.removeSafeHouse then
        SafeHouse.removeSafeHouse(house)
    else
        return false, "removeSafeHouse missing", args
    end
    broadcast("remove", args)
    return true, "", args
end

function MeatballsSafehousesServer.applyCmd(cmd)
    local nonce = tostring(cmd.nonce or "")
    local op = tostring(cmd.op or "")
    if nonce == "" or op == "" then
        return false
    end
    MeatballsSafehousesServer._seenNonces = MeatballsSafehousesServer._seenNonces or {}
    if MeatballsSafehousesServer._seenNonces[nonce] then
        return false
    end
    MeatballsSafehousesServer._seenNonces[nonce] = true
    local ok, err, extra
    if op == "create" then
        ok, err, extra = MeatballsSafehousesServer.applyCreate(cmd)
    elseif op == "update" then
        ok, err, extra = MeatballsSafehousesServer.applyUpdate(cmd)
    elseif op == "release" then
        ok, err, extra = MeatballsSafehousesServer.applyRelease(cmd)
    else
        ok, err, extra = false, "unknown op", {}
    end
    MeatballsSafehousesServer.writeAck(ok, nonce, op, err, extra)
    MeatballsSafehousesServer.dump()
    MeatballsSafehousesServer.writeBridge()
    if ok then
        MeatballsSafehouses.log("ok " .. op .. " nonce=" .. nonce)
    else
        MeatballsSafehouses.log("fail " .. op .. " " .. tostring(err))
    end
    return ok
end

function MeatballsSafehousesServer.poll()
    if isClient() and not isServer() then
        return
    end
    local text = readAll(MeatballsSafehouses.CMD_FILE)
    if not text or text == "" then
        return
    end
    writeFile(MeatballsSafehouses.CMD_FILE, "")
    local blocks = parseBlocks(text)
    local i = 1
    while i <= #blocks do
        MeatballsSafehousesServer.applyCmd(blocks[i])
        i = i + 1
    end
end

local function onTick()
    if isClient() and not isServer() then
        return
    end
    MeatballsSafehousesServer._pollTick = (MeatballsSafehousesServer._pollTick or 0) + 1
    MeatballsSafehousesServer._bridgeTick = (MeatballsSafehousesServer._bridgeTick or 0) + 1
    if MeatballsSafehousesServer._pollTick % 60 == 0 then
        MeatballsSafehousesServer.poll()
    end
    if MeatballsSafehousesServer._bridgeTick % 300 == 0 then
        MeatballsSafehousesServer.writeBridge()
    end
end

local function pulse()
    if isClient() and not isServer() then
        return
    end
    MeatballsSafehousesServer.poll()
    MeatballsSafehousesServer.writeBridge()
end

local function onWorldReady()
    if isClient() and not isServer() then
        return
    end
    MeatballsSafehouses.log("world ready " .. MeatballsSafehouses.VERSION)
    MeatballsSafehousesServer.dump()
    MeatballsSafehousesServer.writeBridge()
    MeatballsSafehousesServer.poll()
end

Events.OnTick.Add(onTick)
if Events.OnTickEvenPaused then
    Events.OnTickEvenPaused.Add(onTick)
end
if Events.EveryOneMinute then
    Events.EveryOneMinute.Add(pulse)
end
if Events.EveryTenMinutes then
    Events.EveryTenMinutes.Add(pulse)
end

if Events.OnServerStarted then
    Events.OnServerStarted.Add(onWorldReady)
end
if Events.OnInitGlobalModData then
    Events.OnInitGlobalModData.Add(function()
        if isClient() and not isServer() then
            return
        end
        MeatballsSafehouses.log("moddata " .. MeatballsSafehouses.VERSION)
    end)
end
if Events.EveryHours then
    Events.EveryHours.Add(function()
        if isClient() and not isServer() then
            return
        end
        MeatballsSafehousesServer.poll()
        MeatballsSafehousesServer.dump()
        MeatballsSafehousesServer.writeBridge()
    end)
end

MeatballsSafehouses.log("server parser loaded")
