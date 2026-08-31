-- Safehouse border visualizer (client). Toggle via context menu.

if not AdminTools then
    require "AdminTools"
end

SafehouseVisualizer = SafehouseVisualizer or {}
SafehouseVisualizer.enabled = false
SafehouseVisualizer.MAX_DIST = 70
SafehouseVisualizer.COLOR = nil

local function getHighlightColor()
    if not SafehouseVisualizer.COLOR and ColorInfo then
        SafehouseVisualizer.COLOR = ColorInfo.new(0.15, 0.85, 1.0, 1.0)
    end
    return SafehouseVisualizer.COLOR
end

function SafehouseVisualizer.toggle()
    SafehouseVisualizer.enabled = not SafehouseVisualizer.enabled
    local player = getPlayer()
    if player then
        local msg = SafehouseVisualizer.enabled
            and "Подсветка зон привата: ВКЛ"
            or "Подсветка зон привата: ВЫКЛ"
        player:setHaloNote(msg, 80, 200, 255, 200)
    end
end

function SafehouseVisualizer.drawBorders()
    if not SafehouseVisualizer.enabled then
        return
    end
    local player = getPlayer()
    if not player or player:getZ() < 0 then
        return
    end
    if not SafeHouse or not SafeHouse.getSafehouseList then
        return
    end

    local cell = getCell()
    if not cell then
        return
    end

    local color = getHighlightColor()
    local px = player:getX()
    local py = player:getY()
    local list = SafeHouse.getSafehouseList()
    if not list then
        return
    end

    for i = 0, list:size() - 1 do
        local sh = list:get(i)
        if sh then
            local x1 = sh:getX()
            local y1 = sh:getY()
            local x2 = x1 + sh:getW() - 1
            local y2 = y1 + sh:getH() - 1
            if IsoUtils and IsoUtils.DistanceTo then
                if IsoUtils.DistanceTo(px, py, x1, y1) > SafehouseVisualizer.MAX_DIST then
                    -- still draw if player is inside / near center
                    local cx = (x1 + x2) / 2
                    local cy = (y1 + y2) / 2
                    if IsoUtils.DistanceTo(px, py, cx, cy) > SafehouseVisualizer.MAX_DIST then
                        sh = nil
                    end
                end
            end
            if sh then
                -- perimeter only (cheaper than full fill)
                local function paint(x, y)
                    local sq = cell:getGridSquare(x, y, 0)
                    if sq and sq:getFloor() then
                        local floor = sq:getFloor()
                        floor:setHighlighted(true)
                        if color then
                            floor:setHighlightColor(color)
                        end
                    end
                end
                local x = x1
                while x <= x2 do
                    paint(x, y1)
                    paint(x, y2)
                    x = x + 1
                end
                local y = y1
                while y <= y2 do
                    paint(x1, y)
                    paint(x2, y)
                    y = y + 1
                end
            end
        end
    end
end

Events.OnPostFloorLayerDraw.Add(SafehouseVisualizer.drawBorders)
