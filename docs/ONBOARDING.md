# Onboarding — Universal PZ Control Panel

Step-by-step from zero to first **Smoke test** on a local mirror. No `.env` required if you use the wizard.

## Prerequisites

- Python 3.10+ with `pip`
- Network access to your PZ host (RCON TCP + FTP/SFTP or a local cachedir path)
- Optional for smoke test: Project Zomboid Dedicated Server or client **GameServer** (see `tools/local_server.py`)

## 1. Install

From the repository root:

```bash
python -m pip install -r panel/requirements.txt
```

Start the panel:

```bash
python run_panel.py
```

Open http://127.0.0.1:8000/

**Admin (3.11.0):** if no credentials exist, the login modal asks to **Create admin**. Local dev only: `AUTH_DISABLED=true` in `.env`.

On first run with **no profiles** and **no `.env`**, the welcome modal opens and points you to **Home → Connect server**.

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

This cachedir is what the local smoke runner uses.

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
| Workshop download / ModPack | Workshop | files + SteamCMD |
| Logs / chat | Логи / Чат | files |
| Players online | Игроки | RCON |

Tabs without capability stay gray with a hint — not HTTP 500.

## 6b. Workshop mods & ModPack (3.13.0)

Prerequisites on the **panel machine**:

1. Install [SteamCMD](https://developer.valvesoftware.com/wiki/SteamCMD) into `./steamcmd/` **or** set `STEAMCMD` to the binary path.
2. Pull the server mirror so `world.ini` (or profile `files.ini`) is under `.mirror/<id>/`.

On the **Workshop** tab:

| Action | Effect |
|--------|--------|
| **Скачать недостающие** | SteamCMD `workshop_download_item 108600 <id>` into `.mirror/<id>/steamapps/workshop/content/108600/`, then symlink/copy into `.mirror/<id>/mods/` |
| **Проверить обновления** | Steam Web API `GetPublishedFileDetails` → UPDATE badge when remote `time_updated` is newer |
| **ModPack Builder** | Select local mods → Compile unified pack → `.mirror/<id>/modpacks/<PackId>/` (+ link under `mods/`) |
| Auto-restart | Optional: on update poll, RCON warning → wait 3m → `save` → `quit` |

CLI equivalents:

```bash
python tools/workshop_downloader.py 2392709985 --output .mirror/meatballs-xl --mods-dir .mirror/meatballs-xl/mods
python tools/pack_merger.py --source .mirror/meatballs-xl/mods --unified-id ServerModPack_v1 --output .mirror/meatballs-xl/modpacks/ServerModPack_v1
```

## 7. Legacy `.env` path

Existing MEATBALLS setups: keep `.env` with FTP/RCON vars. First boot migrates to profile `meatballs-xl`. Wizard is skipped when `.env` or profiles exist.

## 8. Auth & VPS deployment

1. Generate hash: `python -c "from panel.auth import hash_password; print(hash_password('…'))"`
2. Set `ADMIN_USER`, `ADMIN_PASS_HASH`, `JWT_SECRET` in `.env`
3. Bind behind reverse proxy with HTTPS recommended
4. Do **not** set `AUTH_DISABLED` on public hosts

## 9. Next (not in v1)

- JWT / admin login — done in 3.11.0
- RU/EN language switcher — done in 3.11.0
- SFTP file channel — done in 3.12.0
- MEATBALLS plugin toggle — done in 3.12.0
- Workshop / ModPack / update monitor — done in 3.13.0

See `docs/PRODUCT.md` and `docs/SPRINTS.md`.
