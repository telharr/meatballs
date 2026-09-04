-- Apply panel/server SafeHouse mutations on clients (vanilla list can lag).

if not MeatballsSafehouses then
    require "MeatballsSafehouses"
end

local function findExact(x, y, w, h)
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

local function addMembers(house, csv)
    if not house or not house.addPlayer then
        return
    end
    local names = MeatballsSafehouses.splitCsv(csv or "")
    local owner = tostring(house:getOwner() or "")
    local i = 1
    while i <= #names do
        if names[i] ~= "" and names[i] ~= owner then
            house:addPlayer(names[i])
        end
        i = i + 1
    end
end

local function onServerCommand(module, command, args)
    if module ~= MeatballsSafehouses.MODULE then
        return
    end
    args = args or {}
    local x = tonumber(args.x) or 0
    local y = tonumber(args.y) or 0
    local w = tonumber(args.w) or 1
    local h = tonumber(args.h) or 1
    if command == "remove" then
        local house = findExact(x, y, w, h)
        if house and SafeHouse and SafeHouse.removeSafeHouse then
            SafeHouse.removeSafeHouse(house)
        end
        return
    end
    if command ~= "apply" then
        return
    end
    if not SafeHouse or not SafeHouse.addSafeHouse then
        return
    end
    local house = findExact(x, y, w, h)
    if not house then
        house = SafeHouse.addSafeHouse(x, y, w, h, tostring(args.owner or ""))
    end
    if not house then
        return
    end
    if house.setTitle and args.title then
        house:setTitle(tostring(args.title))
    end
    if house.setOwner and args.owner then
        house:setOwner(tostring(args.owner))
    end
    addMembers(house, args.members)
end

Events.OnServerCommand.Add(onServerCommand)
