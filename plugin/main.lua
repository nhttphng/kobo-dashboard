-- .adds/koreader/plugins/agenda.koplugin/main.lua
-- Fetch a PNG from your LAN and only repaint on change.

local UIManager    = require("ui/uimanager")
local Dispatcher   = require("dispatcher")
local WidgetCtn    = require("ui/widget/container/widgetcontainer")
local ImageWidget  = require("ui/widget/imagewidget")
local http         = require("socket.http")
local ltn12        = require("ltn12")
local md5          = require("ffi.md5")  -- provides md5.sumFile(filename)
local _            = require("gettext")

-- ==== CONFIG (edit these) ====
local URL         = "http://192.168.1.14:3333/today.png" -- URL to fetch the PNG from. If using a local server, use the device's LAN IP. If using Docker, you might not need to change anything.
local OUT_DIR     = "/mnt/onboard/koreader/screensaver"
local OUT_PATH    = OUT_DIR .. "/today.png"
local INTERVAL_S  = 60    -- check every minute. Change as desired.
local FORCE_FULL  = true       -- "full" refresh wipe on updates
-- =============================

local Agenda = WidgetCtn:extend{
    name = "agenda",
    is_doc_only = false,
}

-- Internal state
Agenda._widget        = nil
Agenda._sched_cb      = nil
Agenda._last_md5      = nil
Agenda._last_img_path = nil

-- Register two simple menu entries: Start / Stop.
function Agenda:onDispatcherRegisterActions()
    Dispatcher:registerAction("agenda_start", {category="none", event="AgendaStart", title=_("Agenda Display: Start"), general=true})
    Dispatcher:registerAction("agenda_stop",  {category="none", event="AgendaStop",  title=_("Agenda Display: Stop"),  general=true})
end

function Agenda:init()
    self:onDispatcherRegisterActions()
    self.ui.menu:registerToMainMenu(self)
end

function Agenda:addToMainMenu(menu_items)
    menu_items.agenda_start = {
        text = _("Agenda Display: Start"),
        sorting_hint = "more_tools",
        callback = function() self:open() end
    }
    menu_items.agenda_stop = {
        text = _("Agenda Display: Stop"),
        sorting_hint = "more_tools",
        callback = function() self:close() end
    }
end

local function ensure_dir(path)
    -- ultra-simple mkdir -p
    os.execute("mkdir -p '" .. path .. "'")
end

local function headers_lc(t)
    local o = {}
    if not t then return o end
    for k,v in pairs(t) do o[string.lower(k)] = v end
    return o
end

-- Download the image. If server supports validators, LuaSocket will pass them back.
-- We do a plain GET & then compare MD5 to avoid stale caches reliably.
function Agenda:_download_png()
    ensure_dir(OUT_DIR)
    local tmp = OUT_PATH .. ".tmp"

    local out = io.open(tmp, "wb")
    if not out then return false, "cannot write tmp" end
    local sink = ltn12.sink.file(out)

    -- cache-bust to avoid any stale caches
    local url = URL .. "?t=" .. tostring(os.time())

    -- Set a 10-second timeout for the HTTP request
    http.TIMEOUT = 10

    local _, code = http.request{
        method  = "GET",
        url     = url,
        sink    = sink,
        headers = { ["Cache-Control"] = "no-cache" },
    }
    if code ~= 200 then
        os.remove(tmp)
        return false, "http "..tostring(code)
    end

    os.remove(OUT_PATH)
    os.rename(tmp, OUT_PATH)
    return true, "updated"
end

function Agenda:_show_widget(img_path)
    -- (Re)show the image full-screen
    if self._widget then
        UIManager:close(self._widget, "full")
        self._widget = nil
    end
    self._widget = ImageWidget:new{
        file  = img_path,
        alpha = false,
    }
    UIManager:show(self._widget, "full", nil, 0, 0, true)
    self._last_img_path = img_path
end

function Agenda:_tick()
    -- Prevent device from dimming or sleeping on every tick
    UIManager:preventStandby()
    local ok, err = self:_download_png()
    if ok then
        -- Check MD5 of the new image
        local new_md5 = md5.sumFile(OUT_PATH)
        if new_md5 ~= self._last_md5 then
            self._last_md5 = new_md5
            -- Copy to a unique filename to avoid cache
            local ts = tostring(os.time())
            local unique_path = OUT_DIR .. "/today_" .. ts .. ".png"
            local src = io.open(OUT_PATH, "rb")
            local dst = io.open(unique_path, "wb")
            if src and dst then
                local data = src:read("*a")
                dst:write(data)
                src:close()
                dst:close()
                -- Remove previous temp image
                if self._last_img_path and self._last_img_path ~= unique_path then
                    os.remove(self._last_img_path)
                end
                self:_show_widget(unique_path)
                if FORCE_FULL and self._widget then
                    UIManager:setDirty(self._widget, "full")
                end
            end
        end
    else
        -- Failsafe: log error, do not crash, try again next interval
        if err then
            print("Agenda: image download failed: " .. tostring(err))
        else
            print("Agenda: image download failed: unknown error")
        end
    end
    UIManager:scheduleIn(INTERVAL_S, self._sched_cb)
end

function Agenda:open()
    if self._widget then return end
    UIManager:preventStandby()        -- keep the device awake while showing
    -- Show the current image with a unique filename
    local ts = tostring(os.time())
    local unique_path = OUT_DIR .. "/today_" .. ts .. ".png"
    local src = io.open(OUT_PATH, "rb")
    local dst = io.open(unique_path, "wb")
    if src and dst then
        local data = src:read("*a")
        dst:write(data)
        src:close()
        dst:close()
        self:_show_widget(unique_path)
    end
    -- one immediate update, then recurrent checks
    self._sched_cb = self._sched_cb or function() self:_tick() end
    self:_tick()
end

function Agenda:close()
    if self._sched_cb then UIManager:unschedule(self._sched_cb) end
    if self._widget   then UIManager:close(self._widget, "full"); self._widget = nil end
    UIManager:allowStandby()
end

return Agenda