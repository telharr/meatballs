-- Apply panel/server SafeHouse mutations on clients (vanilla list can lag).

if not MeatballsSafehouses then
    require "MeatballsSafehouses"
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

local function refreshUi()
    if triggerEvent then
        pcall(function()
            triggerEvent("OnSafehousesChanged")
        end)
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
    local owner = tostring(args.owner or "")
    if command == "remove" then
        local house = MeatballsSafehouses.findHouse(x, y, w, h, owner)
        if house and SafeHouse and SafeHouse.removeSafeHouse then
            SafeHouse.removeSafeHouse(house)
        end
        refreshUi()
        return
    end
    if command ~= "apply" then
        return
    end
    if not SafeHouse or not SafeHouse.addSafeHouse then
        return
    end
    local house = MeatballsSafehouses.findHouse(x, y, w, h, owner)
    if not house then
        house = SafeHouse.addSafeHouse(x, y, w, h, owner)
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
    refreshUi()
end

Events.OnServerCommand.Add(onServerCommand)
