# Agent session log

**Сначала** `docs/PRODUCT.md` (цели панели, профиль сервера), **потом** этот файл. Спринты: `docs/SPRINTS.md`.

Last updated: 2026-09-04 (panel 3.24.3 CSRF headers on wizard save; VPS has MEATBALLS)

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
- Panel **3.24.2**: Update button on Docker chooses rebuild (sock + project mount), not Windows setup.exe. Release: https://github.com/telharr/meatballs/releases/tag/v3.24.2
- Test VPS **2026-09-04**: `185.221.154.241:8000` health **3.24.2** after one-shot `deploy_vps.sh`; compose has docker.sock + `/host/pz-panel` for later in-panel updates
- VPS panel active profile **MEATBALLS** (`meatballs`, XLGAMES, process `none`). Copied from local `meatballs-xl` via hosting wizard. Game version field empty on save (local had 42.20.4).
- Panel **3.24.3** (branch `fix`, not merged): `api()` keeps CSRF + `Content-Type` when `apiStepUp` adds confirm headers. Stock 3.24.2 wizard Save on public VPS returned 403 CSRF, then 422 if Content-Type was dropped.
- Panel **3.24.1**: wizard «Сохранить и сделать активным» uses in-app step-up (not `window.prompt`); errors show in the wizard; `/api/status` no longer paints `[500]` when no profile
- Panel **3.24.0**: Приваты рисуют бумажный атлас из `worldmap.xml` (`python tools/knox_atlas.py`). PNG gitignore.
- Panel **3.22.2**: navbar version badge; boot force-check; 5‑min update cache; `PANEL_GITHUB_TOKEN`; `packaging/deploy_vps.sh`

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
