# PZ Server Control Panel

Hosting-agnostic web dashboard: **RCON** console, **FTP/local** config editor, mirror pull, local **smoke test**.

Read first: `docs/PRODUCT.md`, `docs/SESSION.md`. Onboarding: **`docs/ONBOARDING.md`**. Sprints: `docs/SPRINTS.md`.

Panel **3.16.0**: WebSocket event bus (`/ws/events`), live CPU/RAM telemetry, RBAC (admin / moderator).

Panel **3.15.0**: SteamCMD auto-bootstrap (`.cache/steamcmd/`); ModPack compile + one-click FTP/SFTP deploy; `world.ini` Mods= injection with `panel/backups/` snapshot.

Panel **3.14.0**: AdminTools city wipe API + Admin Audit in Logs; Snapshot; Workshop / ModPack; SFTP; JWT; Smoke.

## Authentication (Sprint 3)

On first run (no `ADMIN_*` in `.env` and no `panel/data/auth.json`), the UI prompts **Create admin**.

**VPS / public bind** — set before exposing the panel:

```ini
ADMIN_USER=admin
ADMIN_PASS_HASH=<pbkdf2 hash>
JWT_SECRET=<random string>
```

Generate password hash:

```bash
python -c "from panel.auth import hash_password; print(hash_password('your-secure-password'))"
```

**Local dev bypass** (desktop shortcut, 127.0.0.1):

```ini
AUTH_DISABLED=true
```

Opens with a **«Локальный вход (без пароля)»** button — no admin password required. Works only from localhost.

Optional: `AUTH_LOCAL_BYPASS=true` without full `AUTH_DISABLED` (local button + normal login on VPS).

API: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET /api/auth/status`.  
Token: `Authorization: Bearer …` or HttpOnly cookie `pz_panel_token`.

Optional moderator accounts in `panel/data/auth.json`:

```json
{
  "username": "admin",
  "password_hash": "...",
  "role": "admin",
  "users": [
    { "username": "mod", "password_hash": "...", "role": "moderator" }
  ]
}
```

Moderators: read-only config, RCON/chat/bans/logs; cannot edit servers, wipe, compile ModPacks, or save INI.

## Language (RU / EN)

Header toggle **RU | EN** — stored in `localStorage.pz_lang`. Dictionaries: `panel/static/locales/`.

## Quick start (zero `.env`)

1. Install:

```bash
python -m pip install -r panel/requirements.txt
```

2. Start:

```bash
python run_panel.py
```

3. Open http://127.0.0.1:8000/ — if no profiles exist, follow the welcome modal → **Главная** wizard (RCON + FTP or local path).

4. **Зеркало** → Pull → **Smoke test** → Start/Stop.

Full walkthrough: `docs/ONBOARDING.md`.

## Legacy setup (MEATBALLS / `.env`)

First boot migrates `.env` → profile `meatballs-xl`. You can still use `.env`:

```ini
FTP_HOST=your.server.example
FTP_PORT=21
FTP_USER=
FTP_PASS=

RCON_HOST=your.server.example
RCON_PORT=16284
RCON_PASS=
```

Then `python run_panel.py` as above.

Or manually:

```bash
uvicorn panel.server:app --host 127.0.0.1 --port 8000 --reload
```

## Backups

Timestamped backups before FTP upload: `panel/backups/YYYY-MM-DD_HH-MM-SS_<filename>`

## Desktop shortcut

```powershell
.\scripts\create_panel_shortcut.ps1
```

Creates **PZ Server Panel** on the desktop (icon from XLGAMES panel branding).

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/auth/status` | Auth state (`needs_setup`, `auth_disabled`) |
| `POST /api/auth/login` | Login → JWT + cookie |
| `POST /api/auth/logout` | Clear session |
| `GET /api/auth/me` | Current user (requires auth) |
| `POST /api/auth/setup` | First-run admin creation |
| `GET /api/onboarding` | First-run wizard state (`needs_wizard`) |
| `GET/POST/PATCH/DELETE /api/servers` | Profile CRUD + activate |
| `POST /api/servers/probe/*` | RCON / files / query / all probes |
| `GET /api/smoke/status` | Local smoke test status + log tail |
| `POST /api/smoke/start` | Start GameServer on `.mirror/<id>/` |
| `POST /api/smoke/stop` | Stop local smoke process |
| `GET /api/configs` | List remote config/Lua files |
| `GET /api/config/load?filename=` | Download via FTP |
| `POST /api/config/save` | Backup locally + upload to FTP (409 if XLGAMES changed the file) |
| `POST /api/mirror/pull` | Incremental Pull (`mode=incremental\|verify\|force`) |
| `POST /api/mirror/verify` | Local MD5 vs `checksums.json`, no re-download of same-size files |
| `GET/POST /api/prefs` | `host_panel_wins` checkbox |
| `GET /api/slots` | Empty test/NPC slot count |
| `POST /api/slots` | Set count, write `Lua/mb_slots.txt`, optional FTP + mod upload |
| `GET /api/launch` | Invite card + founder roster |
| `POST /api/launch/adduser` | RCON `adduser` (real account) |
| `POST /api/rcon/exec` | Run RCON command |
| `POST /api/rcon/graceful-restart` | 5-minute restart sequence |
| `WS /ws/console` | Interactive RCON (JSON messages) |

## Notes

- FTP requires VPN exclusions for XLGAMES host if you use EU VPN.
- RCON commands must use **Latin characters** (PZ limitation).
- Saves create timestamped files in `backups/` before upload.
