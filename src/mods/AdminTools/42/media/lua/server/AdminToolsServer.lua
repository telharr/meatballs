-- Server command router for AdminTools.

if not AdminTools then
    require "AdminTools"
end

require "AdminCityWipe"

AdminToolsServer = AdminToolsServer or {}

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

Events.OnClientCommand.Add(AdminToolsServer.onClientCommand)

AdminTools.debugLog("server router loaded")
