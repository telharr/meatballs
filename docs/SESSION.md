# Agent session log

**Сначала** `docs/PRODUCT.md` (цели панели, профиль сервера), **потом** этот файл. Спринты: `docs/SPRINTS.md`.

Last updated: 2026-09-04 (panel 3.24.1 wizard step-up; Sprint 13 atlas 3.24.0)

## Host (do not commit secrets)

Fill this section **locally only**. Do not put real passwords, tokens, or private FTP users in commits.

- Dedicated host: `(set locally)`
- FTP / SFTP: port + user under hoster paths (e.g. `/ServerWorld`)
- Live INI name: e.g. `world.ini`
- RCON / Query / game ports: from hoster panel
- Game version on host: e.g. **42.20.x**

## Panel bugfix agent

- Screenshot reports: reproduce local (`python run_panel.py`) then test VPS; commits only on branch **`fix`**; merge after user readiness check. Protocol: `.cursor/rules/panel-bugfix.mdc`.

## Panel

- Product: `docs/PRODUCT.md`. Onboarding: `docs/ONBOARDING.md`. **Now: Sprint 13 Phase A** — атлас Knox на вкладке Приваты
- Start: `python run_panel.py` → http://127.0.0.1:8000/ (or :8001 if :8000 stuck)
- Panel **3.24.1**: wizard «Сохранить и сделать активным» uses in-app step-up (not `window.prompt`); errors show in the wizard; `/api/status` no longer paints `[500]` when no profile
- Panel **3.24.0**: Приваты рисуют бумажный атлас из `worldmap.xml` (`python tools/knox_atlas.py`). PNG gitignore.
- Panel **3.23.2**: Приваты больше не пишут «мод отсутствует», если файлы и `Mods=` уже на хосте — нужен рестарт JVM
- Panel **3.23.1**: Workshop builder — **Залить выбранные как есть** (без склейки в один pack). «Собрать» с fail-on-conflict падает на общих Lua-хуках — это не способ залить MeatballsSafehouses.
- Panel **3.23.0**: вкладка Приваты — карта Knox, разметка, мост `MeatballsSafehouses` (сейвы не пишет)
- Panel **3.22.2**: navbar version badge; boot force-check; 5‑min update cache; `PANEL_GITHUB_TOKEN`; `packaging/deploy_vps.sh`
- Test VPS **2026-09-03**: upgraded to **3.22.2** via deploy script; container can reach GitHub `releases/latest`. Release: https://github.com/telharr/meatballs/releases/tag/v3.22.2

## What still needs a human

- **Rotate VPS root password** (was reused from older chat for deploy)
- Hoster restart after RCON `quit` — process.kind=`none`. **2026-09-04:** MeatballsSafehouses **1.1.1** world-ready poll. Live test zone `MB-panel-probe` 10648,6912 8×8 owner PanelProbe (+ Alice). Atlas: `python tools/knox_atlas.py`
- Pull `_admin.txt` / `_cmd.txt` into mirror so Admin Audit has rows
- Do not commit `.env` or `panel/backups/*`

## Dedicated on this PC

- Optional: set `PZ_DEDICATED_DIR` in `.env`
- Client GameServer path is machine-specific — do not hardcode in shared docs

## Mods (intent template)

Example loadout: `Mods=ServerTweaker;LogExtender;MeatballsSlots;AdminTools;MeatballsSafehouses`

## Tools to prefer

- FTP: `tools/ftp_client.py`, `tools/ftp_manager.py`
- Catalog apply: `POST /api/mods/apply-ini` or `tools/mod_catalog.py`
- Local dedi: `python tools/local_server.py status|start|stop`
- Safehouses: panel **Приваты**, `src/mods/MeatballsSafehouses`
