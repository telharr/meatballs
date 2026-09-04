"""Production hardening helpers for public / VPS panel deployments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from panel.paths import DATA_DIR

RATE_FILE = DATA_DIR / "login_rate.json"
REVOKED_FILE = DATA_DIR / "revoked_jti.json"

# Login brute-force
LOGIN_WINDOW_SEC = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SEC = 30 * 60

# Password policy
PASSWORD_MIN_LEN = 12
COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "123456789012",
        "qwerty123456",
        "adminadmin",
        "admin123456",
        "letmein12345",
        "welcome12345",
        "changeme1234",
        "projectzomboid",
        "zomboid12345",
        "meatballs123",
        "paneladmin12",
    }
)

# Dummy PBKDF2 target for constant-time failed logins (scheme matches auth.hash_password)
_DUMMY_HASH_CACHE: str | None = None

CSRF_COOKIE = "pz_panel_csrf"
CSRF_HEADER = "x-csrf-token"

STEP_UP_PATHS = frozenset(
    {
        "/api/wipe/apply",
        "/api/admintools/city-wipe",
        "/api/admintools/queue/clear",
        "/api/safehouses/create",
        "/api/safehouses/update",
        "/api/safehouses/release",
        "/api/safehouses/install",
        "/api/vps/provision",
        "/api/panel/snapshot",
        "/api/auth/totp/disable",
    }
)

_rate_lock = threading.Lock()
_revoke_lock = threading.Lock()


def is_public_deployment() -> bool:
    """True when panel is meant to be reachable beyond loopback."""
    flag = os.environ.get("PANEL_PUBLIC", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    host = os.environ.get("PANEL_HOST", "127.0.0.1").strip().lower()
    return host in ("0.0.0.0", "::", "[::]")


def trust_proxy() -> bool:
    return os.environ.get("TRUST_PROXY", "").strip().lower() in ("1", "true", "yes")


def request_is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if trust_proxy():
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        return proto == "https"
    return False


def client_ip(request: Request) -> str:
    """Client IP. X-Forwarded-For is ignored unless TRUST_PROXY=true."""
    if trust_proxy():
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def dummy_password_hash() -> str:
    global _DUMMY_HASH_CACHE
    if _DUMMY_HASH_CACHE:
        return _DUMMY_HASH_CACHE
    from panel.auth import hash_password

    _DUMMY_HASH_CACHE = hash_password("timing-pad-not-a-real-password")
    return _DUMMY_HASH_CACHE


def validate_password_strength(password: str) -> None:
    if len(password) < PASSWORD_MIN_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {PASSWORD_MIN_LEN} characters",
        )
    lowered = password.lower().strip()
    if lowered in COMMON_PASSWORDS:
        raise HTTPException(status_code=400, detail="Password is too common")
    if password.isdigit() or password.isalpha():
        raise HTTPException(status_code=400, detail="Password must mix letters and digits or symbols")


def _rate_key(ip: str, username: str) -> str:
    return f"{ip}|{(username or '').strip().lower()}"


def check_login_allowed(ip: str, username: str) -> None:
    key = _rate_key(ip, username)
    now = time.time()
    with _rate_lock:
        data = _read_json(RATE_FILE)
        row = data.get(key) or {}
        locked_until = float(row.get("locked_until") or 0)
        if locked_until > now:
            wait = int(locked_until - now)
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed logins. Try again in {wait}s",
                headers={"Retry-After": str(max(1, wait))},
            )


def record_login_failure(ip: str, username: str) -> None:
    key = _rate_key(ip, username)
    now = time.time()
    with _rate_lock:
        data = _read_json(RATE_FILE)
        row = data.get(key) or {"fails": [], "locked_until": 0}
        fails = [float(t) for t in (row.get("fails") or []) if now - float(t) < LOGIN_WINDOW_SEC]
        fails.append(now)
        locked_until = float(row.get("locked_until") or 0)
        if len(fails) >= LOGIN_MAX_ATTEMPTS:
            locked_until = now + LOGIN_LOCK_SEC
            fails = []
        data[key] = {"fails": fails, "locked_until": locked_until}
        # prune stale keys
        keep: dict[str, Any] = {}
        for k, v in data.items():
            lu = float((v or {}).get("locked_until") or 0)
            fs = [float(t) for t in ((v or {}).get("fails") or []) if now - float(t) < LOGIN_WINDOW_SEC]
            if lu > now or fs:
                keep[k] = {"fails": fs, "locked_until": lu}
        _write_json(RATE_FILE, keep)


def record_login_success(ip: str, username: str) -> None:
    key = _rate_key(ip, username)
    with _rate_lock:
        data = _read_json(RATE_FILE)
        if key in data:
            del data[key]
            _write_json(RATE_FILE, data)


def revoke_jti(jti: str, exp: int) -> None:
    if not jti:
        return
    with _revoke_lock:
        data = _read_json(REVOKED_FILE)
        data[jti] = int(exp)
        now = int(time.time())
        data = {k: v for k, v in data.items() if int(v) > now}
        _write_json(REVOKED_FILE, data)


def is_jti_revoked(jti: str) -> bool:
    if not jti:
        return False
    with _revoke_lock:
        data = _read_json(REVOKED_FILE)
        exp = data.get(jti)
        if exp is None:
            return False
        if int(exp) < int(time.time()):
            return False
        return True


# —— TOTP (RFC 6238) without extra deps ——


def totp_generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_pad_secret(secret: str) -> bytes:
    s = secret.strip().upper()
    pad = (-len(s)) % 8
    return base64.b32decode(s + ("=" * pad), casefold=True)


def totp_at(secret: str, for_time: int | None = None, step: int = 30, digits: int = 6) -> str:
    counter = int((for_time if for_time is not None else time.time()) // step)
    key = _totp_pad_secret(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def totp_verify(secret: str, code: str, window: int = 1) -> bool:
    raw = (code or "").strip().replace(" ", "")
    if not raw.isdigit():
        return False
    now = int(time.time())
    for delta in range(-window, window + 1):
        if hmac.compare_digest(totp_at(secret, now + delta * 30), raw.zfill(6)[-6:]):
            return True
    return False


def totp_provisioning_uri(secret: str, username: str, issuer: str = "PZ Control Panel") -> str:
    label = f"{issuer}:{username}"
    from urllib.parse import quote

    return (
        f"otpauth://totp/{quote(label)}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


# —— Secrets at rest ——

ENC_PREFIX = "enc:v1:"


def _fernet():
    from cryptography.fernet import Fernet

    raw = (os.environ.get("SECRETS_KEY") or os.environ.get("JWT_SECRET") or "dev-insecure").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if not value:
        return value
    if value.startswith(ENC_PREFIX):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return ENC_PREFIX + token


def decrypt_secret(value: str) -> str:
    if not value:
        return value
    if not value.startswith(ENC_PREFIX):
        return value
    token = value[len(ENC_PREFIX) :].encode("ascii")
    return _fernet().decrypt(token).decode("utf-8")


# —— CSRF ——


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        httponly=False,
        samesite="strict",
        secure=secure,
        max_age=24 * 3600,
        path="/",
    )


def validate_csrf(request: Request) -> None:
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return
    path = request.url.path
    if path.startswith("/api/auth/login") or path.startswith("/api/auth/setup") or path == "/api/auth/local":
        return
    if path == "/api/auth/csrf":
        return
    # Enforce only for browser cookie sessions
    from panel.auth import TOKEN_COOKIE

    if not request.cookies.get(TOKEN_COOKIE):
        return
    # Bearer-only clients skip CSRF
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    header = request.headers.get(CSRF_HEADER) or request.headers.get("X-CSRF-Token") or ""
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def path_needs_step_up(method: str, path: str) -> bool:
    if method.upper() not in ("POST", "PUT", "PATCH", "DELETE"):
        return False
    if path in STEP_UP_PATHS:
        return True
    if path.startswith("/api/servers/probe"):
        return False
    if path.startswith("/api/servers/") and path.endswith("/activate"):
        return False
    # Create/patch confirm the password in the JSON body (route), not only a
    # custom header — proxies and window.prompt+fetch drop/break that header,
    # so OK on the native dialog looks like a no-op.
    if path == "/api/servers" and method.upper() == "POST":
        return False
    if method.upper() == "PATCH" and path.startswith("/api/servers/"):
        return False
    if path.startswith("/api/servers") and method.upper() in ("POST", "PATCH", "DELETE"):
        return True
    return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'",
        )
        if request_is_https(request) or is_public_deployment():
            # HSTS only meaningful over HTTPS; still set when public so reverse-proxy TLS benefits
            if request_is_https(request):
                response.headers.setdefault(
                    "Strict-Transport-Security",
                    "max-age=31536000; includeSubDomains",
                )
        return response
