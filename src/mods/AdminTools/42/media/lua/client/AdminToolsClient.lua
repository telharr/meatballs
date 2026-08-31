-- Client entry: context menus, server command feedback.

if not AdminTools then
    require "AdminTools"
end

require "ISCityWipeUI"
require "SafehouseVisualizer"
require "DisableMapShare"

AdminToolsClient = AdminToolsClient or {}

function AdminToolsClient.onServerCommand(module, command, args)
    if module ~= AdminTools.MODULE then
        return
    end
    args = args or {}
    local player = getPlayer()
    if not player then
        return
    end

    if command == "ClaimBlocked" then
        local msg = args.message or AdminTools.CLAIM_BLOCK_MSG
        player:setHaloNote(msg, 255, 50, 50, 320)
        return
    end

    if command == "WipeStarted" then
        player:setHaloNote("City wipe started: " .. tostring(args.cityName or args.cityId), 255, 200, 80, 200)
        return
    end

    if command == "WipeFinished" then
        local msg = string.format(
            "Wipe done %s · sq=%s ground=%s filled=%s",
            tostring(args.cityName or "?"),
            tostring(args.squares or 0),
            tostring(args.ground or 0),
            tostring(args.filled or 0)
        )
        player:setHaloNote(msg, 80, 255, 120, 280)
        return
    end
end

function AdminToolsClient.onFillWorldObjectContextMenu(playerNum, context, worldobjects, test)
    if test then
        return
    end
    local player = getSpecificPlayer(playerNum)
    if not player then
        return
    end

    -- Safehouse visualizer — available to all players
    context:addOption("Подсветка зон привата / Toggle Safehouse Borders", nil, function()
        SafehouseVisualizer.toggle()
    end)

    if not AdminTools.isAdminPlayer(player) then
        return
    end

    local adminMenu = context:addOption("Admin Panel", nil, nil)
    local sub = ISContextMenu:getNew(context)
    context:addSubMenu(adminMenu, sub)
    sub:addOption("Targeted City Wipe", nil, function()
        ISCityWipeUI.open()
    end)
end

function AdminToolsClient.onFillPlayerContextMenu(playerNum, context, players)
    local player = getSpecificPlayer(playerNum)
    if not player then
        return
    end
    context:addOption("Подсветка зон привата / Toggle Safehouse Borders", nil, function()
        SafehouseVisualizer.toggle()
    end)
end

Events.OnServerCommand.Add(AdminToolsClient.onServerCommand)
Events.OnFillWorldObjectContextMenu.Add(AdminToolsClient.onFillWorldObjectContextMenu)
Events.OnFillPlayerContextMenu.Add(AdminToolsClient.onFillPlayerContextMenu)

AdminTools.debugLog("client loaded")
