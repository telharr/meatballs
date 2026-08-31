-- In-game admin UI: targeted city wipe.

require "ISUI/ISPanel"
require "ISUI/ISButton"
require "ISUI/ISLabel"
require "ISUI/ISTickBox"

if not AdminTools then
    require "AdminTools"
end

ISCityWipeUI = ISPanel:derive("ISCityWipeUI")

local FONT_HGT_SMALL = getTextManager():getFontHeight(UIFont.Small)
local FONT_HGT_MEDIUM = getTextManager():getFontHeight(UIFont.Medium)

function ISCityWipeUI:initialise()
    ISPanel.initialise(self)
    self:createChildren()
end

function ISCityWipeUI:createChildren()
    local pad = 10
    local y = pad

    self.title = ISLabel:new(pad, y, FONT_HGT_MEDIUM, "Targeted City Wipe", 1, 1, 1, 1, UIFont.Medium, true)
    self:addChild(self.title)
    y = y + FONT_HGT_MEDIUM + pad

    self.hint = ISLabel:new(
        pad,
        y,
        FONT_HGT_SMALL,
        "Reset loot + refill containers (loaded chunks). Admin only.",
        0.8,
        0.8,
        0.8,
        1,
        UIFont.Small,
        true
    )
    self:addChild(self.hint)
    y = y + FONT_HGT_SMALL + pad

    self.cityTicks = ISTickBox:new(pad, y, self.width - pad * 2, FONT_HGT_SMALL, "Cities", self, nil)
    self.cityTicks:initialise()
    self.cityTicks:instantiate()
    self.cityTicks.choicesColor = { r = 1, g = 1, b = 1, a = 1 }
    local i = 1
    while i <= #AdminTools.CITIES do
        local city = AdminTools.CITIES[i]
        self.cityTicks:addOption(city.name, city.id)
        self.cityTicks:setSelected(i, false)
        i = i + 1
    end
    self:addChild(self.cityTicks)
    y = y + (#AdminTools.CITIES * (FONT_HGT_SMALL + 4)) + pad

    self.optTicks = ISTickBox:new(pad, y, self.width - pad * 2, FONT_HGT_SMALL, "Options", self, nil)
    self.optTicks:initialise()
    self.optTicks:instantiate()
    self.optTicks:addOption("Reset Loot (ground + empty containers)", "resetLoot")
    self.optTicks:setSelected(1, true)
    self.optTicks:addOption("Reconstruct / refill vanilla containers", "reconstruct")
    self.optTicks:setSelected(2, true)
    self:addChild(self.optTicks)
    y = y + (FONT_HGT_SMALL + 4) * 2 + pad * 2

    local btnW = 120
    self.runBtn = ISButton:new(pad, y, btnW, FONT_HGT_SMALL + 6, "Run Wipe", self, ISCityWipeUI.onRun)
    self.runBtn:initialise()
    self.runBtn:instantiate()
    self.runBtn.borderColor = { r = 0.9, g = 0.3, b = 0.2, a = 1 }
    self:addChild(self.runBtn)

    self.closeBtn = ISButton:new(pad + btnW + 8, y, btnW, FONT_HGT_SMALL + 6, "Close", self, ISCityWipeUI.onClose)
    self.closeBtn:initialise()
    self.closeBtn:instantiate()
    self:addChild(self.closeBtn)

    self.status = ISLabel:new(pad, y + FONT_HGT_SMALL + 14, FONT_HGT_SMALL, "", 0.7, 1, 0.7, 1, UIFont.Small, true)
    self:addChild(self.status)
end

function ISCityWipeUI:onClose()
    self:setVisible(false)
    self:removeFromUIManager()
    ISCityWipeUI.instance = nil
end

function ISCityWipeUI:onRun()
    if not AdminTools.isAdminPlayer(getPlayer()) then
        self.status:setName("Admin only.")
        return
    end

    local resetLoot = self.optTicks:isSelected(1)
    local reconstruct = self.optTicks:isSelected(2)
    local cities = {}
    local i = 1
    while i <= #AdminTools.CITIES do
        if self.cityTicks:isSelected(i) then
            table.insert(cities, {
                cityId = AdminTools.CITIES[i].id,
                resetLoot = resetLoot,
                reconstruct = reconstruct,
            })
        end
        i = i + 1
    end

    if #cities == 0 then
        self.status:setName("Select at least one city.")
        return
    end

    sendClientCommand(getPlayer(), AdminTools.MODULE, "TriggerCityWipeBatch", {
        cities = cities,
        resetLoot = resetLoot,
        reconstruct = reconstruct,
    })
    self.status:setName("Queued " .. tostring(#cities) .. " city wipe job(s). See server log.")
end

function ISCityWipeUI:prerender()
    ISPanel.prerender(self)
    self:drawRect(0, 0, self.width, self.height, self.backgroundColor.a, self.backgroundColor.r, self.backgroundColor.g, self.backgroundColor.b)
    self:drawRectBorder(0, 0, self.width, self.height, self.borderColor.a, self.borderColor.r, self.borderColor.g, self.borderColor.b)
end

function ISCityWipeUI:new(x, y, width, height)
    local o = ISPanel:new(x, y, width, height)
    setmetatable(o, self)
    self.__index = self
    o.borderColor = { r = 0.4, g = 0.4, b = 0.4, a = 1 }
    o.backgroundColor = { r = 0.1, g = 0.1, b = 0.1, a = 0.9 }
    o.moveWithMouse = true
    return o
end

function ISCityWipeUI.open()
    if ISCityWipeUI.instance then
        ISCityWipeUI.instance:onClose()
    end
    local w, h = 420, 420
    local ui = ISCityWipeUI:new((getCore():getScreenWidth() - w) / 2, (getCore():getScreenHeight() - h) / 2, w, h)
    ui:initialise()
    ui:addToUIManager()
    ISCityWipeUI.instance = ui
    return ui
end
