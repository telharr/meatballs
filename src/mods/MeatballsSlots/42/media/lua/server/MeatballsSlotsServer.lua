-- Spawn named trainers in their towns. Player-list rows come from ModData.
-- Do not return on isServer() at load: B42 GameServer can parse server Lua before the flag is set.
print("[MeatballsSlots] server script parsed")

local bodies = {}
local lastLogged = -1

local function log(msg)
    print("[MeatballsSlots] " .. tostring(msg))
end

local function readConfig()
    local reader = getFileReader(MeatballsSlots.FILE, false)
    if not reader then
        return MeatballsSlots.parseLine("")
    end
    local line = reader:readLine()
    reader:close()
    return MeatballsSlots.parseLine(line)
end

local function publish(cfg)
    local slots = MeatballsSlots.activeList(cfg.count)
    local state = { count = cfg.count, slots = {} }
    local i = 1
    while i <= #slots do
        local t = slots[i]
        table.insert(state.slots, {
            id = t.id,
            name = t.name,
            role = t.role,
            role_ru = t.role_ru,
            city = t.city,
            teaches = t.teaches,
            kind = "trainer",
        })
        i = i + 1
    end
    ModData.add(MeatballsSlots.DATA_KEY, state)
    ModData.transmit(MeatballsSlots.DATA_KEY)
end

local function isAliveBody(zombie)
    if not zombie then
        return false
    end
    if zombie.isDead and zombie:isDead() then
        return false
    end
    return true
end

local function removeBody(zombie)
    if not zombie then
        return
    end
    if zombie.removeFromWorld then
        zombie:removeFromWorld()
    end
    if zombie.removeFromSquare then
        zombie:removeFromSquare()
    end
end

local function pickPoint(cfg, trainer)
    if cfg.x ~= 0 or cfg.y ~= 0 then
        return cfg.x + (trainer.id - 1), cfg.y, cfg.z
    end
    return trainer.x, trainer.y, trainer.z
end

local function applyIdentity(obj, trainer)
    if not obj or not trainer then
        return
    end
    local md = obj:getModData()
    if md then
        md.MeatballsSlots_id = trainer.id
        md.MeatballsSlots_name = trainer.name
        md.MeatballsSlots_role = trainer.role
        md.MeatballsSlots_city = trainer.city
    end
    if obj.setUseless then
        obj:setUseless(true)
    end
    if obj.setNoDamage then
        obj:setNoDamage(true)
    end
    if obj.setName then
        obj:setName(trainer.name)
    end
    if obj.getDescriptor then
        local desc = obj:getDescriptor()
        if desc then
            if desc.setForename then
                desc:setForename(trainer.name)
            end
            if desc.setSurname then
                desc:setSurname(trainer.role)
            end
        end
    end
end

local function tagOnSquare(sq, trainer)
    if not sq or not sq.getMovingObjects then
        return false
    end
    local moving = sq:getMovingObjects()
    if not moving then
        return false
    end
    local i = 0
    while i < moving:size() do
        local obj = moving:get(i)
        if obj and instanceof(obj, "IsoZombie") then
            local md = obj:getModData()
            if md and not md.MeatballsSlots_id then
                applyIdentity(obj, trainer)
                bodies[trainer.id] = obj
                return true
            end
        end
        i = i + 1
    end
    return false
end

local function spawnOne(cfg, trainer)
    local x, y, z = pickPoint(cfg, trainer)
    local cell = getCell()
    if not cell then
        return false
    end
    local sq = cell:getGridSquare(math.floor(x), math.floor(y), math.floor(z))
    if not sq then
        local players = getOnlinePlayers()
        if players and players:size() > 0 then
            local player = players:get(0)
            if player then
                x = player:getX() + 2 * trainer.id
                y = player:getY() + 1
                z = player:getZ()
                sq = cell:getGridSquare(math.floor(x), math.floor(y), math.floor(z))
            end
        end
    end
    if not sq or not addZombiesInOutfit then
        return false
    end
    local outfit = trainer.outfit or "Generic01"
    addZombiesInOutfit(math.floor(x), math.floor(y), math.floor(z), 1, outfit, trainer.female or 0)
    return tagOnSquare(sq, trainer)
end

local function syncBodies(cfg)
    local wanted = MeatballsSlots.activeList(cfg.count)
    local id = 1
    while id <= MeatballsSlots.MAX do
        local keep = false
        local w = 1
        while w <= #wanted do
            if wanted[w].id == id then
                keep = true
            end
            w = w + 1
        end
        if not keep and bodies[id] then
            removeBody(bodies[id])
            bodies[id] = nil
        end
        id = id + 1
    end
    local i = 1
    while i <= #wanted do
        local trainer = wanted[i]
        if not isAliveBody(bodies[trainer.id]) then
            bodies[trainer.id] = nil
            spawnOne(cfg, trainer)
        end
        i = i + 1
    end
end

local function tick()
    local cfg = readConfig()
    publish(cfg)
    syncBodies(cfg)
    if cfg.count ~= lastLogged then
        lastLogged = cfg.count
        local names = {}
        local slots = MeatballsSlots.activeList(cfg.count)
        local i = 1
        while i <= #slots do
            table.insert(names, slots[i].name)
            i = i + 1
        end
        log("trainers=" .. tostring(cfg.count) .. " " .. table.concat(names, ","))
    end
end

local function safeTick(reason)
    log("tick " .. tostring(reason))
    local ok, err = pcall(tick)
    if not ok then
        log("tick error: " .. tostring(err))
    end
end

if Events.OnGameStart then
    Events.OnGameStart.Add(function()
        log("ready - trainers Rook Otto Sarge Ash Vera")
        safeTick("OnGameStart")
    end)
end

if Events.OnServerStarted then
    Events.OnServerStarted.Add(function()
        safeTick("OnServerStarted")
    end)
end

if Events.OnInitGlobalModData then
    Events.OnInitGlobalModData.Add(function()
        safeTick("OnInitGlobalModData")
    end)
end

Events.EveryOneMinute.Add(function()
    safeTick("EveryOneMinute")
end)

Events.OnZombieUpdate.Add(function(zombie)
    if not zombie then
        return
    end
    local md = zombie:getModData()
    if not md or not md.MeatballsSlots_id then
        return
    end
    if zombie.setUseless then
        zombie:setUseless(true)
    end
end)
