# Onboarding — Universal PZ Control Panel (v3.18.0)

Step-by-step from zero to first **Smoke test**. No `.env` required for local dev; see **`docs/DEPLOYMENT.md`** for VPS/Docker/installer paths.

## Prerequisites

- Python 3.10+ with `pip` — or Windows **PZ Control Panel** installer from `packaging/` (Sprint 6)
- Network access to your PZ host (RCON TCP + FTP/SFTP or a local cachedir path)
- Optional for smoke test: Java 17+ and PZ Dedicated / client **GameServer** (`PZ_DEDICATED_DIR`)
- **SteamCMD:** optional pre-install — panel **auto-downloads** to `.cache/steamcmd/` on first Workshop use (3.15+)

## 1. Install

**From git:**

```bash
python -m pip install -r panel/requirements.txt
python run_panel.py
```

**Windows installer:** build with `python packaging/build_exe.py` + Inno Setup → run setup wizard (local or remote client mode).

Open http://127.0.0.1:8000/

### Zero-config first boot

| Condition | What happens |
|-----------|----------------|
| No profiles, no `.env` | Welcome modal → **Главная** wizard |
| `AUTH_LOCAL_BYPASS=true` (local installer mode) | «Локальный вход» on 127.0.0.1 |
| No admin configured | Login modal → **Create admin** |
| Legacy `.env` only | Auto-migrates to profile `meatballs-xl`, wizard skipped |

The wizard **detects capabilities** after RCON/FTP probes — tabs stay gray until the channel works (no HTTP 500).

## 2. Create a server profile (wizard)

On **Главная**, fill the wizard:

| Step | Fields | Required |
|------|--------|----------|
| 1 | Name, hoster preset, PZ version | Name |
| 2 | RCON host, port, password | Host + port |
| 3 | File channel: **FTP**, **SFTP (SSH)**, or **Local path**, root | Yes — panel needs files for logs/mirror/smoke |
| 4 | Public IP, game/query UDP | Optional (invite / A2S) |
| 5 | Process: `none` / `local` | `none` on shared hosters (XLGAMES) |

Use **Проверить RCON** / **Проверить файлы** / **Проверить всё** — successful probes set `capabilities` and enable tabs.

- **Сохранить черновик** — saves without requiring FTP user/password or activation.
- **Сохранить и активировать** — full profile; becomes active in the header switcher.

For **Local path**, confirm the warning: direct edits on live cachedir are risky; prefer mirror workflow.

Profiles live in `panel/data/servers/<id>.json` (gitignored). Passwords in `panel/data/secrets/<id>.json`.

### SFTP (Linux VPS)

In step 3, choose **SFTP (SSH)**:

| Field | Notes |
|-------|--------|
| Host / User | Same as SSH login |
| Password | Or leave empty when using a key |
| SFTP port | Default `22` |
| SSH key path | Path on the **panel machine** to `id_rsa` / `id_ed25519` |
| Inline private key | Alternative: paste key text (stored in secrets, not profile JSON) |
| Root | e.g. `/home/steam/Zomboid` or `/home/user/.local/share/ProjectZomboid` |

Use **Проверить файлы** — deep probe looks for `server-console.txt`, `Logs/`, and `*.ini`.

### MEATBALLS plugin toggle

Check **Enable MEATBALLS mod tools** for server-specific features (NPC trainers, safehouse privates, repo mod catalog). Leave unchecked for a generic PZ admin panel. XLGAMES preset enables this by default.

## 3. Switch profiles

Use the header dropdown to change active server. Capabilities and disabled tabs update per profile.

**Редактировать профиль** / **Удалить профиль** on Главная act on the active profile.

## 4. Mirror pull

Open **Зеркало** → **Pull (только новое)**. Files sync to:

```text
.mirror/<profile-id>/
```

Progress streams over WebSocket (`pull_progress`) when connected (3.16+).

## 5. Smoke test

Open **Smoke test**:

1. **Start smoke** — spawns local GameServer with `-cachedir` pointing at `.mirror/<id>/`
2. Watch stdout; critical errors (`IllegalArgumentException`, `duplicate texture`, `Mod ID mismatch`, …) are highlighted
3. Status: **PASS — чистый старт** or **FAIL — N ошибок**
4. **Stop** when done

If mirror is empty, pull first. Set `PZ_DEDICATED_DIR` or install dedicated via SteamCMD if Start reports no JVM.

## 6. Daily operations

| Task | Tab | Channel |
|------|-----|---------|
| Save / restart / servermsg | Console | RCON |
| Edit `world.ini` | Файлы | FTP/SFTP/local |
| Mod list | Моды | files |
| Workshop download / ModPack | Workshop | files + SteamCMD (auto-bootstrap) |
| Logs / chat | Логи / Чат | files + WS `console_tail` |
| Players online | Игроки | RCON + WS `status` |

Tabs without capability stay gray with a hint — not HTTP 500.

## 6b. Workshop mods & ModPack

On the **panel machine**, SteamCMD is **optional** — use **«Установить SteamCMD в один клик»** if the banner appears.

| Action | Effect |
|--------|--------|
| **Скачать недостающие** | SteamCMD → `.mirror/<id>/steamapps/workshop/...` |
| **Проверить обновления** | Steam API → UPDATE badge |
| **ModPack Builder** | Compile → `.mirror/<id>/modpacks/<PackId>/`; optional FTP deploy (3.15+) |
| Auto-restart | Optional graceful RCON restart on mod update |

Live progress: WebSocket channels `workshop_progress`, `steamcmd_progress`, `compile_progress`.

## 7. Legacy `.env` path

Existing setups: keep `.env` with FTP/RCON vars. First boot migrates to profile `meatballs-xl`.

## 8. Auth & production deployment

Full VPS/Docker/Nginx guide: **`docs/DEPLOYMENT.md`**.

Quick checklist:

1. Generate hash: `python -c "from panel.auth import hash_password; print(hash_password('…'))"`
2. Set `ADMIN_USER`, `ADMIN_PASS_HASH`, `JWT_SECRET` in `.env`
3. Bind behind reverse proxy with HTTPS and WebSocket upgrade for `/ws/events`, `/ws/console`
4. Do **not** set `AUTH_LOCAL_BYPASS` on public hosts

## 9. What's implemented

- JWT / admin login — 3.11.0
- RU/EN — 3.11.0
- SFTP — 3.12.0
- Workshop / ModPack — 3.13–3.15
- WebSocket event bus + telemetry + RBAC — 3.16.0
- Deployment docs + Windows installer pipeline — 3.18.0 (zero-click + Amnezia UI)

See `docs/PRODUCT.md`, `docs/SPRINTS.md`, `docs/DEPLOYMENT.md`.
