-- Louisville safehouse claim restriction (shared helpers + client/server hooks).

if not AdminTools then
    require "AdminTools"
end

SafehouseRestrictions = SafehouseRestrictions or {}

function SafehouseRestrictions.isClaimBlockedAt(x, y)
    return AdminTools.isInLouisville(x, y)
end

function SafehouseRestrictions.notifyBlocked(player)
    local msg = AdminTools.CLAIM_BLOCK_MSG
    if isClient() and player then
        player:setHaloNote(msg, 255, 50, 50, 320)
        if HaloTextHelper and HaloTextHelper.addText then
            HaloTextHelper.addText(player, msg, HaloTextHelper.getColorRed())
        end
    end
    if isServer() and player and sendServerCommand then
        sendServerCommand(player, AdminTools.MODULE, "ClaimBlocked", { message = msg })
    end
    AdminTools.debugLog("Blocked Louisville claim at " .. tostring(x) .. "," .. tostring(y))
end

--- Patch take-safehouse entry points used by vanilla / common UIs.
function SafehouseRestrictions.installClientHooks()
    if not isClient() then
        return
    end

    if ISWorldObjectContextMenu and ISWorldObjectContextMenu.onTakeSafeHouse then
        local original = ISWorldObjectContextMenu.onTakeSafeHouse
        ISWorldObjectContextMenu.onTakeSafeHouse = function(worldobjects, square, playerNum)
            if square and SafehouseRestrictions.isClaimBlockedAt(square:getX(), square:getY()) then
                local player = getSpecificPlayer(playerNum)
                SafehouseRestrictions.notifyBlocked(player)
                return
            end
            return original(worldobjects, square, playerNum)
        end
    end

    if ISSafehouseUI and ISSafehouseUI.onClaim then
        local originalClaim = ISSafehouseUI.onClaim
        ISSafehouseUI.onClaim = function(self, ...)
            local player = getPlayer()
            if player then
                local sq = player:getCurrentSquare()
                if sq and SafehouseRestrictions.isClaimBlockedAt(sq:getX(), sq:getY()) then
                    SafehouseRestrictions.notifyBlocked(player)
                    return
                end
            end
            return originalClaim(self, ...)
        end
    end

    -- Admin zone UI (claim by rectangle)
    if ISAddSafeZoneUI and ISAddSafeZoneUI.onClick then
        local originalClick = ISAddSafeZoneUI.onClick
        ISAddSafeZoneUI.onClick = function(self, button)
            if button and self.ok and button.internal == "OK" then
                local x = self.X1 or self.x1 or 0
                local y = self.Y1 or self.y1 or 0
                if SafehouseRestrictions.isClaimBlockedAt(x, y) then
                    SafehouseRestrictions.notifyBlocked(getPlayer())
                    return
                end
                -- also reject if any corner sits in Louisville
                local x2 = self.X2 or self.x2 or x
                local y2 = self.Y2 or self.y2 or y
                if SafehouseRestrictions.isClaimBlockedAt(x2, y2)
                    or SafehouseRestrictions.isClaimBlockedAt(x, y2)
                    or SafehouseRestrictions.isClaimBlockedAt(x2, y) then
                    SafehouseRestrictions.notifyBlocked(getPlayer())
                    return
                end
            end
            return originalClick(self, button)
        end
    end
end

function SafehouseRestrictions.installServerHooks()
    if not isServer() then
        return
    end
    if SafehouseRestrictions._serverHooksInstalled then
        return
    end
    -- Intercept SafeHouse.addSafeHouse when available (authoritative).
    if SafeHouse and SafeHouse.addSafeHouse then
        local originalAdd = SafeHouse.addSafeHouse
        SafeHouse.addSafeHouse = function(x, y, w, h, owner, ...)
            local x2 = x + (w or 1) - 1
            local y2 = y + (h or 1) - 1
            if AdminTools.isInLouisville(x, y)
                or AdminTools.isInLouisville(x2, y2)
                or AdminTools.isInLouisville(x, y2)
                or AdminTools.isInLouisville(x2, y) then
                AdminTools.debugLog("Server rejected Louisville SafeHouse.addSafeHouse")
                return nil
            end
            return originalAdd(x, y, w, h, owner, ...)
        end
        SafehouseRestrictions._serverHooksInstalled = true
        AdminTools.debugLog("SafehouseRestrictions server hooks installed")
    else
        AdminTools.debugLog("SafehouseRestrictions: SafeHouse.addSafeHouse unavailable at install time")
    end
end

Events.OnGameStart.Add(function()
    if AdminTools.Config and AdminTools.Config.safehouseRestrictions == false then
        AdminTools.debugLog("SafehouseRestrictions client hooks skipped (config)")
        return
    end
    SafehouseRestrictions.installClientHooks()
end)

Events.OnServerStarted.Add(function()
    if AdminTools.Config and AdminTools.Config.safehouseRestrictions == false then
        AdminTools.debugLog("SafehouseRestrictions server hooks skipped (config)")
        return
    end
    SafehouseRestrictions.installServerHooks()
end)

-- Dedicated may not fire OnGameStart for shared; also try OnInitGlobalModData
Events.OnInitGlobalModData.Add(function()
    if isServer() then
        if AdminTools.Config and AdminTools.Config.safehouseRestrictions == false then
            return
        end
        SafehouseRestrictions.installServerHooks()
    end
end)
