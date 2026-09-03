# VPS / public panel security

Applies when `PANEL_HOST=0.0.0.0` or `PANEL_PUBLIC=true` (Auto-Deploy sets both).

## Checklist (operators)

1. **HTTPS** — put Caddy/Nginx or Cloudflare Tunnel in front; do not expose raw `:8000` long-term.
2. **Firewall** — allow `22` (admin), `80`/`443` (panel via proxy). Do **not** publish `8000` publicly if proxy is used.
3. **Auth** — `AUTH_DISABLED=false`, `AUTH_LOCAL_BYPASS=false`, unique `JWT_SECRET`, strong admin password (≥12).
4. **2FA** — after login click **2FA** in the header; store the secret in an authenticator app.
5. **Secrets key** — set `SECRETS_KEY` (or reuse a strong `JWT_SECRET`) so RCON/FTP secrets encrypt at rest.
6. **Proxy** — only set `TRUST_PROXY=true` when a trusted reverse proxy strips/forges `X-Forwarded-*` correctly.
7. **Prebuilt image** — prefer `docker pull` of a tagged release image over rebuild-on-VPS for frequent updates (see Packaging).

## Built-in controls (panel 3.20+)

| Control | Behavior |
|---------|----------|
| Login rate limit | 5 failures / 15 min → 30 min lockout per IP+user |
| Password policy | ≥12 chars, not common, must mix character classes |
| Session | HttpOnly cookie, `SameSite=strict`, `Secure` on HTTPS; TTL 1h (`TOKEN_TTL_HOURS`) |
| JWT body | Not returned to browser JS / not stored in `localStorage` |
| WebSocket | Cookie session (no `?token=` from UI) |
| CSRF | Double-submit cookie + `X-CSRF-Token` for cookie sessions |
| Step-up | Password (+ TOTP if enabled) for wipe / provision / profile secrets / snapshot |
| TOTP 2FA | Optional; required at login when enabled |
| OpenAPI | Disabled when `PANEL_PUBLIC` / public bind |
| `/api/health` | Public returns `{ok, version, uptime}` only |
| Headers | CSP, `X-Frame-Options=DENY`, nosniff, HSTS (HTTPS) |
| Secrets files | Fernet `enc:v1:` at rest under `panel/data/secrets/` |

## Example Caddy

```caddyfile
panel.example.com {
  reverse_proxy 127.0.0.1:8000
}
```

Bind Docker/compose to `127.0.0.1:8000` only:

```ini
PANEL_BIND=127.0.0.1
PANEL_PUBLIC=true
TRUST_PROXY=true
```

## Prebuilt image (maintainers)

Frequent releases should publish `ghcr.io/<org>/pz-panel:<tag>` from CI and deploy with:

```bash
docker compose pull && docker compose up -d
```

Keep `data/` and `.env` as volumes; rebuild only the app layer, not Python deps every time.
