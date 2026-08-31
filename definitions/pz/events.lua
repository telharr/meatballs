---@meta

--- Project Zomboid Global Events API (Kahlua2)
---@class Events
Events = {}

--- Fired when the game session starts (client and server).
---@param callback fun()
function Events.OnGameStart.Add(callback) end

--- Fired after tile definitions are loaded from mods.
---@param callback fun()
function Events.OnLoadedTileDefinitions.Add(callback) end

--- Server receives a command from a client.
---@param module string
---@param command string
---@param player IsoPlayer
---@param args table|nil
function Events.OnServerCommand.Add(callback) end

--- Client receives a command from the server.
---@param module string
---@param command string
---@param args table|nil
function Events.OnClientCommand.Add(callback) end

--- Fired when a player connects.
---@param callback fun(player: IsoPlayer)
function Events.OnCreatePlayer.Add(callback) end

--- Fired every in-game hour.
---@param callback fun()
function Events.OnHourly.Add(callback) end

--- Fired when mod data is received from server.
---@param callback fun(key: string, data: table)
function Events.OnReceiveGlobalModData.Add(callback) end

--- Runtime helpers
---@return IsoPlayer|nil
function getPlayer() end

---@param index integer
---@return IsoPlayer|nil
function getSpecificPlayer(index) end

---@return IsoCell|nil
function getCell() end

---@return GameTime|nil
function getGameTime() end

---@return boolean
function isClient() end

---@return boolean
function isServer() end

---@return boolean
function isAdmin() end

---@param module string
---@param command string
---@param player IsoPlayer
---@param args table|nil
function sendServerCommand(module, command, player, args) end

---@param module string
---@param command string
---@param args table|nil
function sendClientCommand(module, command, args) end

---@class ModData
ModData = {}

---@param key string
---@param data table|nil
function ModData.transmit(key, data) end

---@param key string
---@return table|nil
function ModData.get(key) end

---@param key string
---@param data table
function ModData.add(key, data) end

---@class SandboxVars
SandboxVars = {}

---@class ZombRand
---@param max integer
---@return integer
function ZombRand(max) end
