# Agent session log

**Сначала** `docs/PRODUCT.md` (цели панели, профиль сервера), **потом** этот файл. Спринты: `docs/SPRINTS.md`.

Last updated: 2026-09-03 (v3.22.2: version badge + force update check on boot)

## Host (do not commit secrets)

Fill this section **locally only**. Do not put real passwords, tokens, or private FTP users in commits.

- Dedicated host: `(set locally)`
- FTP / SFTP: port + user under hoster paths (e.g. `/ServerWorld`)
- Live INI name: e.g. `world.ini`
- RCON / Query / game ports: from hoster panel
- Game version on host: e.g. **42.20.x**

## Panel

- Product: `docs/PRODUCT.md`. Onboarding: `docs/ONBOARDING.md`. **Now: Sprint 11** — обновления с GitHub; Sprint 10 мастер почти закрыт; later: **7 — JVM**
- Start: `python run_panel.py` → http://127.0.0.1:8000/ (or :8001 if :8000 stuck)
- Panel **3.22.2**: badge `vX.Y.Z` в navbar; boot `checkPanelUpdates(true)` (обход кэша 15 мин); клик по badge = force check; ошибки проверки не глотаются наклик
- Panel **3.22.1**: RU/EN sync; packaging scrub secrets from setup.exe
- Test VPS **2026-09-03**: still **3.22.0** — баннер мог не показаться из‑за кэша `update_check.json` (~1ч на 3.22.0). SSH с этой машины без ключа. Release 3.22.1: https://github.com/telharr/meatballs/releases/tag/v3.22.1
- Panel **3.22.0**: `PANEL_DATA_DIR` / frozen `%LocalAppData%\PZControlPanel\data`; banner обновлений; `/api/panel/updates*`

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
