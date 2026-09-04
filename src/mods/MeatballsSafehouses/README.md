# MeatballsSafehouses

Hosting-agnostic panel bridge for vanilla Project Zomboid **SafeHouse** zones (B42).

The control panel cannot mutate `saves/`. This mod runs on the dedicated JVM, reads `Lua/mb_safehouse_cmd.txt`, and calls `SafeHouse.addSafeHouse` / `setOwner` / `addPlayer` / `removeSafeHouse`.

## Files (cachedir `Lua/`)

| File | Role |
|------|------|
| `mb_safehouse_cmd.txt` | Panel writes jobs; mod clears after read |
| `mb_safehouses.json` | Current dump (safehouses + factions) |
| `mb_safehouse_ack.json` | Last job result (`nonce`, `ok`, `error`) |
| `mb_safehouse_bridge.json` | Heartbeat — panel knows the mod is polling |

## Install

1. Copy this folder to `{cachedir}/mods/MeatballsSafehouses` (panel **Приваты → Залить мод**).
2. Add `MeatballsSafehouses` to `Mods=` in the server INI.
3. Restart the dedicated process.

Does not require ServerTweaker, LogExtender, or AdminTools.
