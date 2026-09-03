# Deployment Guide — PZ Server Control Panel v3.18.0

Multi-scenario reference for operators and packagers. No real credentials belong in this file.

| Scenario | Audience | Auth model | Process |
|----------|----------|------------|---------|
| **A — Local desktop** | Dev / local dedi on same PC | `AUTH_LOCAL_BYPASS=true` | `run_panel.py` or Windows installer |
| **B — Linux VPS** | Public or team admin panel | JWT + HTTPS | systemd + Nginx |
| **C — Docker** | VPS / homelab container | JWT recommended | `docker compose` |

See also: `docs/ONBOARDING.md` (first-run wizard), `panel/README.md`, `packaging/`.

---

## Scenario A — Local Standalone / Local Dedicated

### Prerequisites

| Component | Purpose |
|-----------|---------|
| **Python 3.10+** | Dev / git install path |
| **Java 17+** | Local smoke test / GameServer JVM |
| **SteamCMD** | Workshop downloads — **auto-installed** to `.cache/steamcmd/` on first use (3.15+) |
| **PZ Dedicated or client GameServer** | Optional smoke test — set `PZ_DEDICATED_DIR` |

### Quick start (from git)

```bash
python -m pip install -r panel/requirements.txt
python run_panel.py
```

Opens http://127.0.0.1:8000/ and launches the browser.

### Recommended `.env` (local desktop)

```ini
AUTH_DISABLED=false
AUTH_LOCAL_BYPASS=true
PANEL_HOST=127.0.0.1
PANEL_PORT=8000
```

- **Local bypass:** button «Локальный вход» on `127.0.0.1` only — no password on your machine.
- Do **not** use `AUTH_DISABLED=true` on any host reachable from the LAN/internet.

### Windows installer (zero-touch)

1. Build bundle: `python packaging/build_exe.py`
2. Compile installer (Inno Setup 6): `ISCC packaging/installer.iss`
3. Run `Output/PZControlPanel-3.18.0-setup.exe`

**Wizard modes:**

| Mode | `.env` generated | Desktop shortcut |
|------|------------------|------------------|
| **Локальный сервер / Разработчик** | `AUTH_LOCAL_BYPASS=true` | Yes (optional task) |
| **Клиент удалённого сервера** | `AUTH_LOCAL_BYPASS=false`, RCON/FTP host template | Optional |

Post-install: `start_panel.bat` launches `PZControlPanel.exe` and opens the browser.

### First boot (all local paths)

1. Welcome modal → **Главная** → profile wizard (RCON + FTP/SFTP/local path).
2. **Workshop** tab — if SteamCMD missing, click **«Установить SteamCMD в один клик»**.
3. **Зеркало** → Pull → **Smoke test** for local dedi validation.

### Desktop shortcut (manual)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/create_panel_shortcut.ps1
```

---

## Scenario B — Linux VPS / Dedicated Server

Headless panel bound to localhost or behind reverse proxy. **Never** expose port 8000 directly without auth + TLS.

### 1. System user & checkout

```bash
sudo useradd -r -m -d /opt/pz-panel -s /usr/sbin/nologin pzpanel || true
sudo mkdir -p /opt/pz-panel
sudo chown pzpanel:pzpanel /opt/pz-panel
sudo -u pzpanel git clone <your-repo-url> /opt/pz-panel/app
cd /opt/pz-panel/app
sudo -u pzpanel python3 -m venv /opt/pz-panel/venv
sudo -u pzpanel /opt/pz-panel/venv/bin/pip install -r panel/requirements.txt
```

### 2. Generate `.env` (no secrets in git)

```bash
sudo -u pzpanel cp .env.example /opt/pz-panel/.env
sudo -u pzpanel nano /opt/pz-panel/.env
```

**Production minimum:**

```ini
AUTH_DISABLED=false
AUTH_LOCAL_BYPASS=false
PANEL_HOST=127.0.0.1
PANEL_PORT=8000

ADMIN_USER=admin
ADMIN_PASS_HASH=<pbkdf2 hash>
JWT_SECRET=<random 48+ chars>

RCON_HOST=127.0.0.1
RCON_PORT=16284
RCON_PASS=<rcon password>

# files channel — prefer profile wizard; legacy .env migration still works
FTP_HOST=127.0.0.1
FTP_USER=
FTP_PASS=
FTP_REMOTE_DIR=/home/steam/Zomboid
```

Generate hash:

```bash
/opt/pz-panel/venv/bin/python -c "from panel.auth import hash_password; print(hash_password('YOUR_SECURE_PASSWORD'))"
```

Symlink env into app root:

```bash
ln -sf /opt/pz-panel/.env /opt/pz-panel/app/.env
mkdir -p /opt/pz-panel/mirror /opt/pz-panel/data
ln -sf /opt/pz-panel/mirror /opt/pz-panel/app/.mirror
```

### 3. systemd unit

`/etc/systemd/system/pz-panel.service`:

```ini
[Unit]
Description=PZ Server Control Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pzpanel
Group=pzpanel
WorkingDirectory=/opt/pz-panel/app
EnvironmentFile=/opt/pz-panel/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/pz-panel/venv/bin/python -m uvicorn panel.server:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pz-panel
sudo systemctl status pz-panel
curl -fsS http://127.0.0.1:8000/api/health
```

### 4. Nginx reverse proxy (HTTPS + WebSocket)

Replace `panel.example.com` and certificate paths.

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream pz_panel {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name panel.example.com;

    ssl_certificate     /etc/letsencrypt/live/panel.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.example.com/privkey.pem;

    client_max_body_size 20m;

    location / {
        proxy_pass http://pz_panel;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket — RCON console + live event bus (3.16+)
    location /ws/console {
        proxy_pass http://pz_panel;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    location /ws/events {
        proxy_pass http://pz_panel;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 5. Firewall

```bash
sudo ufw allow 443/tcp
# Do NOT open 8000 publicly if Nginx terminates TLS
```

### 6. Verify WebSocket + telemetry

1. Login via HTTPS.
2. DevTools → Network → WS: `/ws/events` (telemetry every ~2.5s), `/ws/console` (RCON).
3. Navbar CPU/RAM badges update without polling.

---

## Scenario C — Docker Container

Uses root `Dockerfile` and `docker-compose.yml`.

### Quick start

```bash
cp .env.example .env
# Edit: ADMIN_PASS_HASH, JWT_SECRET — required if AUTH_LOCAL_BYPASS=false

docker compose up -d --build
curl -fsS http://127.0.0.1:8000/api/health
```

### Volumes

| Mount | Container path | Purpose |
|-------|----------------|---------|
| `panel-data` | `/data` | Profiles, secrets, auth, scheduler |
| `panel-mirror` | `/mirror` | FTP mirror / workshop cache |

Persistent data survives `docker compose down`. To reset:

```bash
docker compose down -v   # destroys named volumes — careful
```

### Production bind

In `.env`:

```ini
PANEL_BIND=0.0.0.0
AUTH_LOCAL_BYPASS=false
ADMIN_USER=admin
ADMIN_PASS_HASH=...
JWT_SECRET=...
```

Put Nginx in front (Scenario B config) pointing at `host:8000`.

### SteamCMD inside container

Workshop auto-bootstrap downloads to `/app/.cache/steamcmd/` (ephemeral unless you mount extra volume). For heavy Workshop use, mount:

```yaml
volumes:
  - panel-data:/data
  - panel-mirror:/mirror
  - panel-cache:/app/.cache
```

---

## Packaging pipeline (maintainers)

```bash
python -m pip install pyinstaller
python packaging/build_exe.py --clean
# Windows: ISCC packaging/installer.iss
```

Artifacts (gitignored): `dist/`, `build/`, `packaging/Output/`, `*.exe`.

---

## Panel self-update (Sprint 11 / 3.22.0)

Source of truth: **GitHub Releases** on `PANEL_UPDATE_REPO` (default `telharr/meatballs`). Tag `vX.Y.Z` must match `panel/version.py`.

| Install | How state is kept | How to update |
|---------|-------------------|---------------|
| **Windows setup** | `%LOCALAPPDATA%\PZControlPanel\data` (migrated from `{app}\panel\data` once) | Banner → download setup → Inno; `.env` uses `onlyifdoesntexist` |
| **Docker** | volumes `panel-data` → `/data`, `panel-mirror` → `/mirror` | `docker compose pull && docker compose up -d` (**never** `down -v`) |
| **git + python** | `panel/data/` (gitignored) | `git fetch && git checkout vX.Y.Z` + restart |

API (admin): `GET /api/panel/updates`, `POST .../download`, `POST .../apply`, `POST .../snooze`.

Optional env:

```ini
PANEL_UPDATE_REPO=telharr/meatballs
PANEL_DATA_DIR=C:\path\to\data
PANEL_STATE_DIR=%LOCALAPPDATA%\PZControlPanel
```

Release checklist: publish setup.exe + optional `SHA256SUMS`; bump `panel/version.py` and Inno `MyAppVersion`.

---

## Security checklist

See **[docs/SECURITY.md](SECURITY.md)** for VPS hardening (TLS, rate limits, 2FA, firewall, prebuilt images).

- [ ] No `.env` / `panel/data/auth.json` / `panel/data/secrets/` in git
- [ ] `AUTH_LOCAL_BYPASS=false` on VPS and Docker public binds
- [ ] `PANEL_PUBLIC=true` on internet-facing hosts
- [ ] Unique `JWT_SECRET` / `SECRETS_KEY` per deployment
- [ ] HTTPS in front of panel on the internet (Caddy/Nginx/Tunnel)
- [ ] Enable TOTP (header **2FA**) for admin
- [ ] Moderator accounts only when needed (`role: moderator` in `auth.json`)
- [ ] RCON/FTP passwords encrypted at rest (`enc:v1:…` in secrets JSON)

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| WS disconnects behind proxy | Nginx `Upgrade` / `Connection` headers (see above) |
| 401 on all API | Complete admin setup or set `AUTH_DISABLED` only on localhost |
| SteamCMD missing | Workshop tab → one-click install, or set `STEAMCMD` path |
| Empty mirror | Profile wizard → Pull on **Зеркало** tab |
| PyInstaller static 404 | Rebuild with `packaging/build_exe.py`; ensure `panel/static` in bundle |

---

## Version

Panel **3.18.0** — zero-click installer + Amnezia-style VPS onboarding. API version in `GET /api/health`.
