-- Hide / disable map symbol sharing between players.

if not AdminTools then
    require "AdminTools"
end

DisableMapShare = DisableMapShare or {}
DisableMapShare._patched = false
DisableMapShare._tick = 0

local function hideButton(btn)
    if not btn then
        return
    end
    if btn.setVisible then
        btn:setVisible(false)
    end
    if btn.setEnable then
        btn:setEnable(false)
    end
    btn.enable = false
end

local function patchWorldMapInstance(map)
    if not map then
        return
    end
    local names = {
        "shareBtn",
        "btnShare",
        "shareSymbolsBtn",
        "buttonShare",
        "shareButton",
    }
    local i = 1
    while i <= #names do
        hideButton(map[names[i]])
        i = i + 1
    end
    if map.symbolsUI then
        hideButton(map.symbolsUI.shareBtn)
        hideButton(map.symbolsUI.btnShare)
        hideButton(map.symbolsUI.shareSymbolsBtn)
    end
end

function DisableMapShare.patchUIClasses()
    if DisableMapShare._patched then
        return
    end
    DisableMapShare._patched = true

    if ISWorldMap and ISWorldMap.createChildren then
        local original = ISWorldMap.createChildren
        ISWorldMap.createChildren = function(self, ...)
            original(self, ...)
            patchWorldMapInstance(self)
        end
    end

    if ISWorldMap and ISWorldMap.prerender then
        local originalPre = ISWorldMap.prerender
        ISWorldMap.prerender = function(self, ...)
            patchWorldMapInstance(self)
            return originalPre(self, ...)
        end
    end

    if ISMiniMapOuter and ISMiniMapOuter.createChildren then
        local originalMini = ISMiniMapOuter.createChildren
        ISMiniMapOuter.createChildren = function(self, ...)
            originalMini(self, ...)
            patchWorldMapInstance(self)
            if self.inner then
                patchWorldMapInstance(self.inner)
            end
        end
    end

    if ISWorldMapSymbols and ISWorldMapSymbols.onShareClick then
        ISWorldMapSymbols.onShareClick = function()
            AdminTools.debugLog("Blocked ISWorldMapSymbols.onShareClick")
        end
    end

    AdminTools.debugLog("DisableMapShare hooks installed")
end

Events.OnGameStart.Add(function()
    if AdminTools.Config and AdminTools.Config.disableMapShare == false then
        AdminTools.debugLog("DisableMapShare skipped (config)")
        return
    end
    DisableMapShare.patchUIClasses()
end)

Events.OnTick.Add(function()
    if not isClient() then
        return
    end
    if AdminTools.Config and AdminTools.Config.disableMapShare == false then
        return
    end
    DisableMapShare._tick = (DisableMapShare._tick or 0) + 1
    if DisableMapShare._tick % 30 ~= 0 then
        return
    end
    if ISWorldMap and ISWorldMap.instance then
        patchWorldMapInstance(ISWorldMap.instance)
    end
end)
