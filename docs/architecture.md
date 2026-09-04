# Project Zomboid Modding Architecture

Reference guide for Lua mod development, multiplayer safety, and modpack distribution in this workspace.

## Runtime Overview

Project Zomboid mods run on a **Kahlua2** (Lua 5.1-compatible) VM embedded in a **Java 17** game runtime. Mods are loaded from `mods/` directories and Workshop content folders, declared via `mod.info`.

```
mod/
├── mod.info
├── media/
│   ├── lua/
│   │   ├── client/     # Client-only scripts (UI, rendering, local effects)
│   │   ├── server/     # Dedicated server authority (validation, persistence)
│   │   └── shared/     # Loaded on both sides (definitions, tables, constants)
│   ├── scripts/        # Item/recipe/entity definitions (*.txt)
│   └── textures/       # Sprites, tilesets
└── poster.png
```

## Execution Lifecycle

### Environment Split

| Directory | Runs On | Purpose |
|-----------|---------|---------|
| `shared/` | Client + Server | Constants, item tables, shared utilities |
| `client/` | Client only | UI panels, local animations, client event handlers |
| `server/` | Server only | Authority logic, anti-cheat validation, world mutations |

Never mutate world state from `client/` in multiplayer. Use network commands.

### Event Hook Order

Typical mod initialization sequence:

1. **Mod load** — `mod.info` parsed, Lua files required in dependency order.
2. **`Events.OnLoadedTileDefinitions`** — Custom tiles registered. Tiledef numbers must not collide across mods.
3. **`Events.OnGameStart`** — Session begins; safe to read `SandboxVars`, spawn logic.
4. **`Events.OnCreatePlayer`** — Per-player setup (give starting items, apply traits).
5. **`Events.OnHourly`** — Periodic server ticks (decay, respawn timers).
6. **`Events.OnServerCommand` / `Events.OnClientCommand`** — Custom network RPC layer.

### Network Commands (Multiplayer-Safe Pattern)

```lua
-- shared/NetCommands.lua
MyMod = MyMod or {}
MyMod.MODULE = "MyMod"

if isServer() then
    Events.OnServerCommand.Add(function(module, command, player, args)
        if module ~= MyMod.MODULE then return end
        if command == "RequestAction" then
            -- Validate player, args, permissions
            if not player or not player:isAlive() then return end
            -- Apply server-side change
            sendServerCommand(player, MyMod.MODULE, "ActionResult", { ok = true })
        end
    end)
end

if isClient() then
    Events.OnClientCommand.Add(function(module, command, args)
        if module ~= MyMod.MODULE then return end
        if command == "ActionResult" then
            -- Update local UI only
        end
    end)
end
```

Rules:
- Server is authoritative for inventory, health, world objects.
- Always nil-check `IsoPlayer` and `IsoGridSquare` before use.
- Never trust client-sent coordinates or item counts without server validation.

## Data Persistence

### GlobalModData

Synchronized key-value store for server-wide state:

```lua
if isServer() then
    ModData.add("MyMod_State", { counter = 0 })
    ModData.transmit("MyMod_State")
end

Events.OnReceiveGlobalModData.Add(function(key, data)
    if key == "MyMod_State" then
        -- Client receives updated state
    end
end)
```

### Chunk / Safehouse Serialization

Per-chunk data uses `ModData` attached to `IsoGridSquare` or custom `GlobalModData` keys scoped by coordinates. Safehouse data is managed by the vanilla `SafeHouse` system — avoid overwriting safehouse ModData keys.

Панель создаёт зоны только через мод + `Lua/mb_safehouse_cmd.txt`. Карта вкладки Приваты: `docs/privates-map.md` (атлас из `worldmap.xml` + оверлей зон). Headless dedicated может не слать `Events.OnTick`; поллер 1.1.1 сидит на `OnServerStarted` / `EveryOneMinute`.

### WorldDictionary Collision Prevention

When registering custom world entities, prefix IDs with your mod ID:

```lua
WorldDictionary.register("MyMod", "Item", "MyMod.SpecialItem")
```

Duplicate registrations cause `illegalArgumentException: Entity is already registered` at runtime.

## Tiledef & Script Merging

### Item Scripts (`media/scripts/*.txt`)

Multiple mods can define items with unique `item` type names. Collisions occur when two mods define the same item ID. The `pack_merger.py` tool scans `mod.info` IDs; manual review is required for script-level item name clashes.

### Tiledef Numbers

Each custom tileset claims a `tiledef` number in its definition file:

```
tiledef = 5000
```

Two mods using the same number cause `duplicate texture` errors. Run:

```bash
python tools/pack_merger.py --fail-on-conflict
```

before distributing a modpack.

## Modpack Distribution Flow

```
Workshop mods ──► workshop_downloader.py ──► .cache/workshop/
                                                    │
Custom mods ──► src/mods/ ──────────────────────────┤
                                                    ▼
                                          pack_merger.py
                                                    │
                                                    ▼
                                    src/modpacks/<name>/ (locked manifest)
                                                    │
                                                    ▼
                                          uploader.py ──► Steam Workshop
```

## CI/CD Integration

- **Lint:** `luacheck` validates all Lua in `src/mods/`.
- **Pack:** `pack_merger.py` produces release artifacts.
- **Release:** Tagged builds upload `.zip` bundles to GitHub Releases; optional Steam publish via secrets.

## Further Reading

- [PZ Modding Wiki](https://pzwiki.net/wiki/Modding)
- [Lua Events Reference](https://pzwiki.net/wiki/Lua_events)
- Tool docs: `tools/README.md`
