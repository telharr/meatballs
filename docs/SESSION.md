# Agent session log

**Сначала** `docs/PRODUCT.md` (цели панели, профиль сервера), **потом** этот файл. Спринты: `docs/SPRINTS.md`.

Last updated: 2026-09-01 (panel 3.15.0 SteamCMD bootstrap + ModPack deploy)

## Host (do not commit secrets)

Fill this section **locally only**. Do not put real passwords, tokens, or private FTP users in commits.

- Dedicated host: `(set locally)`
- FTP / SFTP: port + user under hoster paths (e.g. `/ServerWorld`)
- Live INI name: e.g. `world.ini`
- RCON / Query / game ports: from hoster panel
- Game version on host: e.g. **42.20.x**

## Panel

- Product: `docs/PRODUCT.md`. Onboarding: `docs/ONBOARDING.md`. Next sprint: **6 — JVM process**
- Start: `python run_panel.py` → http://127.0.0.1:8000/ (or :8001 if :8000 stuck)
- Panel **3.15.0**: SteamCMD auto-bootstrap; ModPack compile + FTP/SFTP deploy + world.ini Mods= injection
- Panel **3.14.0**: AdminTools city wipe (`GET/POST /api/admintools/*`) via `Lua/mb_admintools_cmd.txt` + RCON `servermsg`; Admin Audit in Логи; Hard FS wipe under advanced toggle
- Panel **3.13.1**: Snapshot on Главная
- Profiles: `panel/data/servers/` + `panel/data/secrets/` (gitignored)
- Catalog: `src/modpacks/meatballs.catalog.json`
- **AdminTools**: city wipe + DisableMapShare on; Louisville safehouse ban **off** by default (`Config.safehouseRestrictions=false`); polls panel cmd file
- Local dedicated helper: `tools/local_server.py`
- B42 GameServer: use `-cachedir=C:\abs\path` (single arg)

## Dedicated on this PC

- Optional: set `PZ_DEDICATED_DIR` in `.env`
- Client GameServer path is machine-specific — do not hardcode in shared docs

## Mods (intent template)

Example loadout: `Mods=ServerTweaker;LogExtender;MeatballsSlots;AdminTools`

## What still needs a human

- **Hoster restart** after RCON `quit` — process.kind=`none`; panel cannot start JVM. After start, confirm `loading AdminTools` + panel cmd poller; Rosewood wipe line already on FTP (`Lua/mb_admintools_cmd.txt`)
- Pull `_admin.txt` / `_cmd.txt` into mirror so Admin Audit has rows (UI works; empty until Pull)
- Join the live server to verify in-game city wipe on loaded chunks
- Do not commit `.env` or `panel/backups/*`

## Tools to prefer

- FTP: `tools/ftp_client.py`, `tools/ftp_manager.py`
- Catalog apply: `POST /api/mods/apply-ini` or `tools/mod_catalog.py`
- Local dedi: `python tools/local_server.py status|start|stop`
