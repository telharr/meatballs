-- Panel ↔ dedicated SafeHouse bridge. Shared constants (Kahlua2).

MeatballsSafehouses = MeatballsSafehouses or {}

MeatballsSafehouses.MODULE = "MeatballsSafehouses"
MeatballsSafehouses.VERSION = "1.3.0"
MeatballsSafehouses.BETTER_ID = "BetterSafehouse"
MeatballsSafehouses.CMD_FILE = "mb_safehouse_cmd.txt"
MeatballsSafehouses.ACK_FILE = "mb_safehouse_ack.json"
MeatballsSafehouses.DUMP_FILE = "mb_safehouses.json"
MeatballsSafehouses.BRIDGE_FILE = "mb_safehouse_bridge.json"

function MeatballsSafehouses.decode(value)
    local text = tostring(value or "")
    text = string.gsub(text, "+", " ")
    text = string.gsub(text, "%%(%x%x)", function(hex)
        local n = tonumber(hex, 16)
        if not n then
            return ""
        end
        return string.char(n)
    end)
    return text
end

function MeatballsSafehouses.splitCsv(value)
    local names = {}
    local text = tostring(value or "")
    if text == "" then
        return names
    end
    for token in string.gmatch(text, "([^,]+)") do
        local name = MeatballsSafehouses.decode(token)
        name = string.gsub(name, "^%s+", "")
        name = string.gsub(name, "%s+$", "")
        if name ~= "" then
            names[#names + 1] = name
        end
    end
    return names
end

function MeatballsSafehouses.jsonQuote(value)
    local s = tostring(value or "")
    s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", " ")
    return '"' .. s .. '"'
end

function MeatballsSafehouses.log(msg)
    print("[MeatballsSafehouses] " .. tostring(msg))
end

function MeatballsSafehouses.isBetterSafehouseActive()
    if not getActivatedMods then
        return false
    end
    local ok, mods = pcall(getActivatedMods)
    if not ok or not mods or not mods.contains then
        return false
    end
    return mods:contains(MeatballsSafehouses.BETTER_ID) == true
end

function MeatballsSafehouses.rectsOverlap(ax, ay, aw, ah, bx, by, bw, bh)
    ax = tonumber(ax) or 0
    ay = tonumber(ay) or 0
    aw = tonumber(aw) or 0
    ah = tonumber(ah) or 0
    bx = tonumber(bx) or 0
    by = tonumber(by) or 0
    bw = tonumber(bw) or 0
    bh = tonumber(bh) or 0
    return ax < (bx + bw) and (ax + aw) > bx and ay < (by + bh) and (ay + ah) > by
end

function MeatballsSafehouses.houseRect(house)
    if not house then
        return nil
    end
    local x = math.floor(house:getX())
    local y = math.floor(house:getY())
    local w = math.floor(house:getW())
    local h = math.floor(house:getH())
    return x, y, w, h
end

function MeatballsSafehouses.eachSafehouse()
    local out = {}
    if not SafeHouse or not SafeHouse.getSafehouseList then
        return out
    end
    local ok, list = pcall(function()
        return SafeHouse.getSafehouseList()
    end)
    if not ok or not list then
        return out
    end
    local i = 0
    while i < list:size() do
        local house = list:get(i)
        if house then
            out[#out + 1] = house
        end
        i = i + 1
    end
    return out
end

function MeatballsSafehouses.findExact(x, y, w, h)
    x = math.floor(tonumber(x) or 0)
    y = math.floor(tonumber(y) or 0)
    w = math.floor(tonumber(w) or 0)
    h = math.floor(tonumber(h) or 0)
    local list = MeatballsSafehouses.eachSafehouse()
    local i = 1
    while i <= #list do
        local house = list[i]
        local hx, hy, hw, hh = MeatballsSafehouses.houseRect(house)
        if hx == x and hy == y and hw == w and hh == h then
            return house
        end
        i = i + 1
    end
    return nil
end

function MeatballsSafehouses.findOverlapping(x, y, w, h, owner)
    x = math.floor(tonumber(x) or 0)
    y = math.floor(tonumber(y) or 0)
    w = math.floor(tonumber(w) or 0)
    h = math.floor(tonumber(h) or 0)
    owner = tostring(owner or "")
    local hits = {}
    local list = MeatballsSafehouses.eachSafehouse()
    local i = 1
    while i <= #list do
        local house = list[i]
        local hx, hy, hw, hh = MeatballsSafehouses.houseRect(house)
        if MeatballsSafehouses.rectsOverlap(x, y, w, h, hx, hy, hw, hh) then
            hits[#hits + 1] = house
        end
        i = i + 1
    end
    if #hits == 0 then
        return nil
    end
    if #hits == 1 then
        return hits[1]
    end
    if owner ~= "" then
        local j = 1
        while j <= #hits do
            local house = hits[j]
            if house.getOwner and tostring(house:getOwner() or "") == owner then
                return house
            end
            j = j + 1
        end
    end
    return hits[1]
end

function MeatballsSafehouses.findHouse(x, y, w, h, owner)
    return MeatballsSafehouses.findExact(x, y, w, h) or MeatballsSafehouses.findOverlapping(x, y, w, h, owner)
end
