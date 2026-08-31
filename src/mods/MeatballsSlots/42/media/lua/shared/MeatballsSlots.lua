-- Named trainer NPCs. Count 0-5 from Lua/mb_slots.txt. Teaching comes later.
print("[MeatballsSlots] shared roster loaded")
MeatballsSlots = MeatballsSlots or {}
MeatballsSlots.MODULE = "MeatballsSlots"
MeatballsSlots.DATA_KEY = "MeatballsSlots_State"
MeatballsSlots.FILE = "mb_slots.txt"
MeatballsSlots.MAX = 5

-- id, name, role, city, spawn, outfit, later: teach skill for cash/items
MeatballsSlots.ROSTER = {
    {
        id = 1,
        name = "Rook",
        role = "Burglar",
        role_ru = "Взломщик",
        city = "West Point",
        teaches = "Lockpicking",
        x = 11920,
        y = 6880,
        z = 0,
        outfit = "Generic01",
        female = 0,
    },
    {
        id = 2,
        name = "Otto",
        role = "Mechanic",
        role_ru = "Автомеханик",
        city = "Riverside",
        teaches = "Mechanics",
        x = 6435,
        y = 5260,
        z = 0,
        outfit = "Mechanic",
        female = 0,
    },
    {
        id = 3,
        name = "Sarge",
        role = "Veteran",
        role_ru = "Военный",
        city = "March Ridge",
        teaches = "Aiming",
        x = 10120,
        y = 12730,
        z = 0,
        outfit = "ArmyCamoGreen",
        female = 0,
    },
    {
        id = 4,
        name = "Ash",
        role = "Carpenter",
        role_ru = "Плотник",
        city = "Rosewood",
        teaches = "Carpentry",
        x = 8080,
        y = 11750,
        z = 0,
        outfit = "ConstructionWorker",
        female = 0,
    },
    {
        id = 5,
        name = "Vera",
        role = "Doctor",
        role_ru = "Доктор",
        city = "Brandenburg",
        teaches = "Doctor",
        x = 2040,
        y = 6180,
        z = 0,
        outfit = "Doctor",
        female = 100,
    },
}

-- Next slot (not spawned yet): Anvil / Blacksmith / Muldraugh / Metalworking

function MeatballsSlots.parseLine(line)
    local cfg = { count = 0, x = 0, y = 0, z = 0 }
    if not line or line == "" then
        return cfg
    end
    for pair in string.gmatch(line, "[^;]+") do
        local key, value = string.match(pair, "^%s*([%w_]+)%s*=%s*(.-)%s*$")
        if key == "count" then
            cfg.count = tonumber(value) or 0
        elseif key == "x" then
            cfg.x = tonumber(value) or 0
        elseif key == "y" then
            cfg.y = tonumber(value) or 0
        elseif key == "z" then
            cfg.z = tonumber(value) or 0
        end
    end
    if cfg.count < 0 then
        cfg.count = 0
    end
    if cfg.count > MeatballsSlots.MAX then
        cfg.count = MeatballsSlots.MAX
    end
    return cfg
end

function MeatballsSlots.trainer(id)
    return MeatballsSlots.ROSTER[id]
end

function MeatballsSlots.activeList(count)
    local out = {}
    local n = tonumber(count) or 0
    if n > MeatballsSlots.MAX then
        n = MeatballsSlots.MAX
    end
    local i = 1
    while i <= n do
        table.insert(out, MeatballsSlots.ROSTER[i])
        i = i + 1
    end
    return out
end

function MeatballsSlots.isTrainerName(name)
    if not name then
        return false
    end
    local i = 1
    while i <= #MeatballsSlots.ROSTER do
        if MeatballsSlots.ROSTER[i].name == name then
            return true
        end
        i = i + 1
    end
    return false
end

function MeatballsSlots.fromModData()
    local data = ModData.get(MeatballsSlots.DATA_KEY)
    if data and data.slots then
        return data.slots
    end
    return {}
end
