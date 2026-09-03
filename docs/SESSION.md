# Agent session log

**Сначала** `docs/PRODUCT.md` (цели панели, профиль сервера), **потом** этот файл. Спринты: `docs/SPRINTS.md`.

Last updated: 2026-09-03 (v3.22.2 released; VPS + local on 3.22.2; update pipeline OK)

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
- Panel **3.22.2**: navbar version badge; boot force-check; 5‑min update cache; `PANEL_GITHUB_TOKEN`; `packaging/deploy_vps.sh`
- Test VPS **2026-09-03**: upgraded to **3.22.2** via deploy script; container can reach GitHub `releases/latest`. Release: https://github.com/telharr/meatballs/releases/tag/v3.22.2
- Panel **3.22.1**: RU/EN sync; packaging scrub secrets from setup.exe
- Panel **3.22.0**: `PANEL_DATA_DIR` / frozen data; banner updates API

## What still needs a human

- **Rotate VPS root password** (was reused from older chat for deploy)
- **Hoster restart** after RCON `quit` — process.kind=`none`
- Do not commit `.env` or `panel/backups/*`

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
