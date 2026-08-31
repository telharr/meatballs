-- Targeted city loot wipe + container refill (server authority).

if not AdminTools then
    require "AdminTools"
end

AdminCityWipe = AdminCityWipe or {}

AdminCityWipe._jobs = {}
AdminCityWipe.SQUARES_PER_TICK = 80
AdminCityWipe.Z_LEVELS = { 0, 1, 2 }

local function fillContainer(container, player)
    if not container then
        return false
    end
    if ItemPickerJava and ItemPickerJava.fillContainer then
        -- B41/B42: fillContainer(ItemContainer, IsoPlayer)
        pcall(function()
            ItemPickerJava.fillContainer(container, player)
        end)
        return true
    end
    if ItemPicker and ItemPicker.fillContainer then
        pcall(function()
            ItemPicker.fillContainer(container, player)
        end)
        return true
    end
    return false
end

local function clearWorldItems(square)
    if not square then
        return 0
    end
    local removed = 0
    local objects = square:getWorldObjects()
    if objects then
        -- iterate backwards when removing
        for i = objects:size() - 1, 0, -1 do
            local wo = objects:get(i)
            if wo then
                square:transmitRemoveItemFromSquare(wo)
                removed = removed + 1
            end
        end
    end
    -- also clear static moving objects that are items
    local staticList = square:getStaticMovingObjects()
    if staticList then
        for i = staticList:size() - 1, 0, -1 do
            local obj = staticList:get(i)
            if obj and instanceof(obj, "IsoWorldInventoryObject") then
                square:transmitRemoveItemFromSquare(obj)
                removed = removed + 1
            end
        end
    end
    return removed
end

local function processContainerObject(obj, player, resetLoot, reconstruct)
    if not obj then
        return 0, 0
    end
    local container = nil
    if obj.getContainer then
        container = obj:getContainer()
    end
    if not container then
        return 0, 0
    end

    local emptied = 0
    local filled = 0

    if resetLoot then
        if container.clear then
            container:clear()
            emptied = 1
        elseif container.getItems then
            local items = container:getItems()
            if items then
                for i = items:size() - 1, 0, -1 do
                    local item = items:get(i)
                    if item then
                        container:Remove(item)
                    end
                end
                emptied = 1
            end
        end
        if fillContainer(container, player) then
            filled = 1
        end
        if obj.transmitCompleteItemToClients then
            pcall(function()
                obj:transmitCompleteItemToClients()
            end)
        end
    end

    -- "Reconstruct" = ensure container exists and is lootable; we cannot rebuild
    -- destroyed furniture sprites safely without map defs. Refill covers common case.
    if reconstruct and not resetLoot then
        if container:getItems() and container:getItems():size() == 0 then
            if fillContainer(container, player) then
                filled = 1
            end
        end
    end

    return emptied, filled
end

local function processSquare(square, player, opts)
    local stats = { ground = 0, emptied = 0, filled = 0 }
    if not square then
        return stats
    end

    if opts.resetLoot then
        stats.ground = clearWorldItems(square)
    end

    local objects = square:getObjects()
    if objects then
        for i = 0, objects:size() - 1 do
            local obj = objects:get(i)
            local e, f = processContainerObject(obj, player, opts.resetLoot, opts.reconstruct)
            stats.emptied = stats.emptied + e
            stats.filled = stats.filled + f
        end
    end
    return stats
end

local function getSquare(x, y, z)
    local cell = getCell()
    if not cell then
        return nil
    end
    return cell:getGridSquare(x, y, z)
end

function AdminCityWipe.startJob(player, cityId, resetLoot, reconstruct)
    local city = AdminTools.getCityById(cityId)
    if not city then
        return false, "unknown city"
    end
    if not AdminTools.isAdminPlayer(player) then
        return false, "not admin"
    end

    local job = {
        player = player,
        city = city,
        x = city.x1,
        y = city.y1,
        zIndex = 1,
        resetLoot = resetLoot ~= false,
        reconstruct = reconstruct == true,
        ground = 0,
        emptied = 0,
        filled = 0,
        squares = 0,
        missing = 0,
        done = false,
    }
    table.insert(AdminCityWipe._jobs, job)
    AdminTools.debugLog(
        "City wipe queued: " .. city.name
            .. " resetLoot=" .. tostring(job.resetLoot)
            .. " reconstruct=" .. tostring(job.reconstruct)
    )
    if sendServerCommand then
        sendServerCommand(player, AdminTools.MODULE, "WipeStarted", {
            cityId = city.id,
            cityName = city.name,
        })
    end
    return true, nil
end

function AdminCityWipe.tickJobs()
    if #AdminCityWipe._jobs == 0 then
        return
    end
    local job = AdminCityWipe._jobs[1]
    if not job or job.done then
        table.remove(AdminCityWipe._jobs, 1)
        return
    end

    local budget = AdminCityWipe.SQUARES_PER_TICK
    local zLevels = AdminCityWipe.Z_LEVELS

    while budget > 0 and not job.done do
        local z = zLevels[job.zIndex] or 0
        local sq = getSquare(job.x, job.y, z)
        if sq then
            local stats = processSquare(sq, job.player, job)
            job.ground = job.ground + stats.ground
            job.emptied = job.emptied + stats.emptied
            job.filled = job.filled + stats.filled
            job.squares = job.squares + 1
        else
            job.missing = job.missing + 1
        end

        budget = budget - 1
        job.zIndex = job.zIndex + 1
        if job.zIndex > #zLevels then
            job.zIndex = 1
            job.x = job.x + 1
            if job.x > job.city.x2 then
                job.x = job.city.x1
                job.y = job.y + 1
                if job.y > job.city.y2 then
                    job.done = true
                end
            end
        end
    end

    if job.done then
        AdminTools.debugLog(string.format(
            "City wipe done %s: squares=%d missing=%d ground=%d emptied=%d filled=%d",
            job.city.name, job.squares, job.missing, job.ground, job.emptied, job.filled
        ))
        if job.player and sendServerCommand then
            sendServerCommand(job.player, AdminTools.MODULE, "WipeFinished", {
                cityId = job.city.id,
                cityName = job.city.name,
                squares = job.squares,
                missing = job.missing,
                ground = job.ground,
                emptied = job.emptied,
                filled = job.filled,
            })
        end
        table.remove(AdminCityWipe._jobs, 1)
    end
end

Events.OnTick.Add(function()
    if isClient() and not isServer() then
        return
    end
    AdminCityWipe.tickJobs()
end)

AdminTools.debugLog("AdminCityWipe loaded (TriggerCityWipe ready)")
