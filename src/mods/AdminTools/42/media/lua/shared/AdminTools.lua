-- AdminTools — shared constants and helpers (Kahlua2 / PZ MP).
-- Prefixed ModData / command module: AdminTools

AdminTools = AdminTools or {}

AdminTools.MODULE = "AdminTools"
AdminTools.VERSION = "1.0.0"

-- City AABB (world tile coords). Louisville matches product rule set.
AdminTools.CITIES = {
    {
        id = "muldraugh",
        name = "Muldraugh",
        x1 = 10540, y1 = 9150, x2 = 11020, y2 = 10120,
    },
    {
        id = "westpoint",
        name = "West Point",
        x1 = 11140, y1 = 6600, x2 = 12240, y2 = 7380,
    },
    {
        id = "rosewood",
        name = "Rosewood",
        x1 = 7900, y1 = 11140, x2 = 8700, y2 = 12200,
    },
    {
        id = "riverside",
        name = "Riverside",
        x1 = 5700, y1 = 5100, x2 = 6900, y2 = 6000,
    },
    {
        id = "louisville",
        name = "Louisville",
        x1 = 11700, y1 = 1000, x2 = 14700, y2 = 4500,
    },
    {
        id = "marchridge",
        name = "March Ridge",
        x1 = 9700, y1 = 12600, x2 = 10500, y2 = 13200,
    },
    {
        id = "fallaslake",
        name = "Fallas Lake",
        x1 = 7000, y1 = 8200, x2 = 7800, y2 = 8800,
    },
}

AdminTools.LOUISVILLE = {
    x1 = 11700,
    y1 = 1000,
    x2 = 14700,
    y2 = 4500,
}

AdminTools.CLAIM_BLOCK_MSG = "Приват зданий в Луисвилле запрещен правилами сервера!"

function AdminTools.getCityById(cityId)
    if not cityId then
        return nil
    end
    local i = 1
    while i <= #AdminTools.CITIES do
        local city = AdminTools.CITIES[i]
        if city.id == cityId then
            return city
        end
        i = i + 1
    end
    return nil
end

function AdminTools.pointInBox(x, y, box)
    if not box then
        return false
    end
    return x >= box.x1 and x <= box.x2 and y >= box.y1 and y <= box.y2
end

function AdminTools.isInLouisville(x, y)
    return AdminTools.pointInBox(x, y, AdminTools.LOUISVILLE)
end

--- Admin check compatible with B41 access levels and B42 roles when present.
function AdminTools.isAdminPlayer(player)
    if not player then
        return false
    end
    if isAdmin and isAdmin() then
        return true
    end
    if player.getAccessLevel then
        local level = tostring(player:getAccessLevel() or "")
        local lower = string.lower(level)
        if lower == "admin" or lower == "moderator" or lower == "gm" then
            return true
        end
    end
    if player.getRole then
        local role = player:getRole()
        if role and role.hasCapability and Capability and Capability.CanGoInsideSafehouses then
            -- Capability check alone is not enough for wipe; prefer AccessLevel above.
        end
        if role and role.getName then
            local name = string.lower(tostring(role:getName() or ""))
            if name == "admin" or name == "overseer" then
                return true
            end
        end
    end
    return false
end

function AdminTools.debugLog(msg)
    print("[AdminTools] " .. tostring(msg))
end
