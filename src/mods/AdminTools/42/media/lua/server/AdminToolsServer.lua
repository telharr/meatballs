-- Server command router for AdminTools + panel file trigger.

if not AdminTools then
    require "AdminTools"
end

require "AdminCityWipe"

AdminToolsServer = AdminToolsServer or {}
AdminToolsServer._lastCmdLine = nil
AdminToolsServer._pollTick = 0

function AdminToolsServer.onClientCommand(module, command, player, args)
    if module ~= AdminTools.MODULE then
        return
    end
    if not player or not player:isAlive() then
        return
    end
    args = args or {}

    if command == "TriggerCityWipe" then
        if not AdminTools.isAdminPlayer(player) then
            AdminTools.debugLog("Rejected TriggerCityWipe from non-admin")
            return
        end
        if AdminTools.Config and AdminTools.Config.cityWipe == false then
            AdminTools.debugLog("City wipe disabled by Config")
            return
        end
        local cityId = args.cityId
        local resetLoot = args.resetLoot ~= false
        local reconstruct = args.reconstruct == true
        if AdminCityWipe and AdminCityWipe.startJob then
            AdminCityWipe.startJob(player, cityId, resetLoot, reconstruct)
        end
        return
    end

    if command == "TriggerCityWipeBatch" then
        if not AdminTools.isAdminPlayer(player) then
            return
        end
        local cities = args.cities
        if type(cities) ~= "table" then
            return
        end
        local i = 1
        while i <= #cities do
            local entry = cities[i]
            if type(entry) == "table" and entry.cityId then
                AdminCityWipe.startJob(
                    player,
                    entry.cityId,
                    entry.resetLoot ~= false,
                    entry.reconstruct == true
                )
            elseif type(entry) == "string" then
                AdminCityWipe.startJob(player, entry, args.resetLoot ~= false, args.reconstruct == true)
            end
            i = i + 1
        end
        return
    end
end

--- Panel drops Lua/mb_admintools_cmd.txt:
--- v1|citywipe|<cityId>|<refill 0/1>|<reconstruct 0/1>|<nonce>|panel
function AdminToolsServer.pollPanelCommand()
    if AdminTools.Config and AdminTools.Config.cityWipe == false then
        return
    end
    local fileName = "mb_admintools_cmd.txt"
    if AdminTools.Config and AdminTools.Config.panelCmdFile then
        fileName = AdminTools.Config.panelCmdFile
    end
    local reader = getFileReader(fileName, false)
    if not reader then
        return
    end
    local line = reader:readLine()
    reader:close()
    if not line or line == "" then
        return
    end
    line = string.gsub(line, "[\r\n]", "")
    if line == AdminToolsServer._lastCmdLine then
        return
    end
    AdminToolsServer._lastCmdLine = line

    -- clear file so we do not re-run
    local writer = getFileWriter(fileName, true, false)
    if writer then
        writer:write("")
        writer:close()
    end

    local parts = {}
    for token in string.gmatch(line, "([^|]+)") do
        table.insert(parts, token)
    end
    if #parts < 5 then
        AdminTools.debugLog("Bad panel cmd line: " .. tostring(line))
        return
    end
    if parts[1] ~= "v1" or parts[2] ~= "citywipe" then
        AdminTools.debugLog("Ignored panel cmd: " .. tostring(parts[2]))
        return
    end
    local cityId = parts[3]
    local refill = parts[4] ~= "0"
    local reconstruct = parts[5] == "1"
    AdminTools.debugLog("Panel citywipe " .. tostring(cityId) .. " refill=" .. tostring(refill))
    AdminCityWipe.startJob(nil, cityId, refill, reconstruct)
end

Events.OnClientCommand.Add(AdminToolsServer.onClientCommand)

Events.OnTick.Add(function()
    if isClient() and not isServer() then
        return
    end
    AdminToolsServer._pollTick = (AdminToolsServer._pollTick or 0) + 1
    if AdminToolsServer._pollTick % 60 ~= 0 then
        return
    end
    AdminToolsServer.pollPanelCommand()
end)

AdminTools.debugLog("server router loaded")
