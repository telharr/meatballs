# MeatballsSafehouses

Hosting-agnostic panel bridge for vanilla Project Zomboid **SafeHouse** zones (B42).

The control panel cannot mutate `saves/`. This mod runs on the dedicated JVM, reads `Lua/mb_safehouse_cmd.txt`, and calls `SafeHouse.addSafeHouse` / `setOwner` / `addPlayer` / `removeSafeHouse`.

## Files (cachedir `Lua/`)

| File | Role |
|------|------|
| `mb_safehouse_cmd.txt` | Panel writes jobs; mod clears after read |
| `mb_safehouses.json` | Dump: safehouses, factions, online `players` `{name,x,y,z}` (EveryOneMinute) |
| `mb_safehouse_ack.json` | Last job result (`nonce`, `ok`, `error`) |
| `mb_safehouse_bridge.json` | Heartbeat — panel knows the mod is polling |

## Install

1. Copy this folder to `{cachedir}/mods/MeatballsSafehouses` (panel **Приваты → Залить мод**).
2. Add `MeatballsSafehouses` to `Mods=` in the server INI.
3. Restart the dedicated process.

Does not require ServerTweaker, LogExtender, or AdminTools.

## Better Safehouse (optional, official Workshop)

Do **not** merge or repack [Better Safehouse](https://steamcommunity.com/sharedfiles/filedetails/?id=3634569678) — the author forbids redistribution. Run both:

1. FTP official `BetterSafehouse` as-is (`Workshop ID 3634569678`).
2. `Mods=` order: `AdminTools` → `BetterSafehouse` → `MeatballsSafehouses`.
3. Keep vanilla SafeHouse enabled in Better Safehouse sandbox. Custom claim can stay off (their default).

v1.3 finds a house by overlap (so panel update/release still works after their in-place expansion), dumps when `OnSafehouseCreate` fires, and notifies Better Safehouse clients (`BetterSafehouseCC` / `SafehouseReleased`) so the overlay matches the panel. Louisville bans from AdminTools still wrap `SafeHouse.addSafeHouse`.
