-- Panel ↔ dedicated SafeHouse bridge. Shared constants (Kahlua2).

MeatballsSafehouses = MeatballsSafehouses or {}

MeatballsSafehouses.MODULE = "MeatballsSafehouses"
MeatballsSafehouses.VERSION = "1.1.1"
MeatballsSafehouses.CMD_FILE = "mb_safehouse_cmd.txt"
MeatballsSafehouses.ACK_FILE = "mb_safehouse_ack.json"
MeatballsSafehouses.DUMP_FILE = "mb_safehouses.json"
MeatballsSafehouses.BRIDGE_FILE = "mb_safehouse_bridge.json"

function MeatballsSafehouses.decode(value)
    local text = tostring(value or "")
    text = string.gsub(text, "+", " ")
    text = string.gsub(text, "%%(%x%x)", function(hex)
        local n = tonumber(hex, 16)
        if not n then
            return ""
        end
        return string.char(n)
    end)
    return text
end

function MeatballsSafehouses.splitCsv(value)
    local names = {}
    local text = tostring(value or "")
    if text == "" then
        return names
    end
    for token in string.gmatch(text, "([^,]+)") do
        local name = MeatballsSafehouses.decode(token)
        name = string.gsub(name, "^%s+", "")
        name = string.gsub(name, "%s+$", "")
        if name ~= "" then
            names[#names + 1] = name
        end
    end
    return names
end

function MeatballsSafehouses.jsonQuote(value)
    local s = tostring(value or "")
    s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", " ")
    return '"' .. s .. '"'
end

function MeatballsSafehouses.log(msg)
    print("[MeatballsSafehouses] " .. tostring(msg))
end
