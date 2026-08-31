---@meta

---@class IsoObject
IsoObject = {}

---@class IsoGridSquare
---@field x integer
---@field y integer
---@field z integer
IsoGridSquare = {}

---@return IsoObject|nil
function IsoGridSquare:getFloor() end

---@return table
function IsoGridSquare:getObjects() end

---@param obj IsoObject
function IsoGridSquare:AddTileObject(obj) end

---@param obj IsoObject
function IsoGridSquare:transmitRemoveItemFromSquare(obj) end

---@class IsoPlayer : IsoObject
---@field username string|nil
IsoPlayer = {}

---@return string|nil
function IsoPlayer:getUsername() end

---@return number
function IsoPlayer:getX() end

---@return number
function IsoPlayer:getY() end

---@return number
function IsoPlayer:getZ() end

---@return ItemContainer|nil
function IsoPlayer:getInventory() end

---@return boolean
function IsoPlayer:isAlive() end

---@return IsoGridSquare|nil
function IsoPlayer:getCurrentSquare() end

---@class InventoryItem
---@field fullType string
InventoryItem = {}

---@return string
function InventoryItem:getFullType() end

---@class ItemContainer
ItemContainer = {}

---@param item InventoryItem
---@return boolean
function ItemContainer:AddItem(item) end

---@param fullType string
---@return InventoryItem|nil
function ItemContainer:FindAndReturn(fullType) end

---@class IsoCell
IsoCell = {}

---@param x number
---@param y number
---@param z number
---@return IsoGridSquare|nil
function IsoCell:getGridSquare(x, y, z) end
