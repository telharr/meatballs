std = "lua51"
max_line_length = 120
ignore = {"212", "213", "611", "612", "631"}

globals = {
    "Events",
    "getPlayer",
    "getSpecificPlayer",
    "getCell",
    "getWorld",
    "getGameTime",
    "getServerOptions",
    "sendClientCommand",
    "sendServerCommand",
    "ModData",
    "SandboxVars",
    "ZombRand",
    "isClient",
    "isServer",
    "isAdmin",
    "isDebugEnabled",
    "MeatballsSafehouses",
    "MeatballsSafehousesServer",
    "SafeHouse",
    "Faction",
    "getFileReader",
    "getFileWriter",
    "getOnlinePlayers",
    "getTimestamp",
}

read_globals = {
    "IsoPlayer",
    "IsoGridSquare",
    "InventoryItem",
    "ItemContainer",
}
