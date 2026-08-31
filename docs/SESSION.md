# Agent session log

**Сначала** `docs/PRODUCT.md` (цели панели, профиль сервера), **потом** этот файл. Спринты: `docs/SPRINTS.md`.

Last updated: 2026-08-31 (open-source prep; panel 3.13.1)

## Host (do not commit secrets)

Fill this section **locally only**. Do not put real passwords, tokens, or private FTP users in commits.

- Dedicated host: `(set locally)`
- FTP / SFTP: port + user under hoster paths (e.g. `/ServerWorld`)
- Live INI name: e.g. `world.ini`
- RCON / Query / game ports: from hoster panel
- Game version on host: e.g. **42.20.x**

## Panel

- Product: `docs/PRODUCT.md`. Onboarding: `docs/ONBOARDING.md`. Next sprint: **6 — JVM process**
- Start: `python run_panel.py` → http://127.0.0.1:8000/
- Panel **3.13.1**: Snapshot on Главная → `panel/backups/panel-snapshot-*.txt` (secrets omitted)
- Panel **3.13.0**: Workshop / ModPack / update monitor
- Panel **3.12.0**: SFTP + `plugins.meatballs`
- Panel **3.11.0**: JWT auth, RU|EN, `AUTH_DISABLED` for local dev
- Profiles: `panel/data/servers/` + `panel/data/secrets/` (both gitignored)
- Catalog: `src/modpacks/meatballs.catalog.json`
- **AdminTools** (`src/mods/AdminTools/42/`): city wipe, Louisville claim ban, safehouse borders, disable map share
- Local dedicated helper: `tools/local_server.py`
- B42 GameServer: use `-cachedir=C:\abs\path` (single arg)

## Dedicated on this PC

- Optional: set `PZ_DEDICATED_DIR` in `.env`
- Client GameServer path is machine-specific — do not hardcode in shared docs

## Mods (intent template)

Example loadout (adjust per world): `Mods=ServerTweaker;LogExtender;MeatballsSlots` — Workshop IDs optional when mods are FTP-local.

## What still needs a human

- Join the live server to verify in-game features RCON cannot see
- Do not commit `.env` or `panel/backups/*` (may contain secrets)

## Tools to prefer

- FTP: `tools/ftp_client.py`, `tools/ftp_manager.py`
- Catalog apply: `POST /api/mods/apply-ini` or `tools/mod_catalog.py`
- Local dedi: `python tools/local_server.py status|start|stop`
