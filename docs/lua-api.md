# Lua API & Hook Quick Reference

Companion to [architecture.md](architecture.md). Stubs for the language server live in `definitions/pz/`.

## Environments

| Path under `media/lua/` | When it loads |
|-------------------------|---------------|
| `shared/` | Client and dedicated server |
| `client/` | Client only (UI, local FX) |
| `server/` | Dedicated / host authority |

## Core events

| Event | Typical use |
|-------|-------------|
| `OnLoadedTileDefinitions` | Custom tiles / tiledef-related setup |
| `OnGameStart` | Session init, read `SandboxVars` |
| `OnCreatePlayer` | Per-player spawn gear / traits |
| `OnHourly` | Periodic server logic |
| `OnServerCommand` | Server handles client RPC |
| `OnClientCommand` | Client handles server RPC |
| `OnReceiveGlobalModData` | Client sync of `ModData.transmit` |

Register with `Events.<Name>.Add(function ... end)`.

## Networking helpers

```lua
-- Client → server
sendClientCommand(module, command, args)

-- Server → one client (API shape may vary by build; prefer documented overloads)
sendServerCommand(module, command, player, args)
```

Always validate on the server: player alive, permissions, argument ranges.

## ModData

```lua
ModData.add(key, table)
ModData.get(key)
ModData.transmit(key)
```

Prefix keys with your mod id (`MyMod_State`).

## Safety rules (enforced by @pz-coder)

1. World mutations only on server.
2. Nil-check `IsoPlayer`, `IsoGridSquare`, containers/items.
3. Do not trust client coordinates or item counts.
4. Avoid colliding `tiledef` numbers and `WorldDictionary` entity ids.

## Extending stubs

Add new `@meta` files under `definitions/pz/` and keep `.luarc.json` / `.vscode/settings.json` library path pointing at that folder. Stubs are **not** shipped inside mods.
