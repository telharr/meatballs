---@meta

---@class Perks
Perks = {}

---@class Traits
Traits = {}

---@param trait string
---@return boolean
function Traits.isTrait(trait) end

---@class WorldDictionary
WorldDictionary = {}

--- Registers a mod-scoped world object to prevent ID collisions.
---@param modID string
---@param type string
---@param id string
function WorldDictionary.register(modID, type, id) end

---@param modID string
---@param type string
---@param id string
---@return boolean
function WorldDictionary.exists(modID, type, id) end
