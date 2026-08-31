"""JWT session auth for the control panel (Sprint 3)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from fastapi import HTTPException, Request, WebSocket

from ftp_client import load_dotenv

PANEL = Path(__file__).resolve().parent
AUTH_FILE = PANEL / "data" / "auth.json"
TOKEN_COOKIE = "pz_panel_token"
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 24
PBKDF2_ITERATIONS = 260_000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def auth_disabled() -> bool:
    load_dotenv()
    return os.environ.get("AUTH_DISABLED", "").strip().lower() in ("1", "true", "yes")


def _client_host(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in ("127.0.0.1", "::1", "localhost"):
        return True
    if h.startswith("127."):
        return True
    return False


def local_bypass_enabled() -> bool:
    """Desktop / localhost one-click entry (see AUTH_DISABLED, AUTH_LOCAL_BYPASS)."""
    load_dotenv()
    if auth_disabled():
        return True
    flag = os.environ.get("AUTH_LOCAL_BYPASS", "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    if flag in ("1", "true", "yes"):
        return True
    host = os.environ.get("PANEL_HOST", "127.0.0.1").strip().lower()
    return host in ("127.0.0.1", "localhost", "::1")


def local_bypass_allowed(request: Request) -> bool:
    if not local_bypass_enabled():
        return False
    return is_loopback_host(_client_host(request))


def _read_auth_file() -> dict[str, Any]:
    if not AUTH_FILE.exists():
        return {}
    try:
        return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_auth_file(data: dict[str, Any]) -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored or not password:
        return False
    try:
        scheme, salt_hex, digest_hex = stored.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _env_credentials() -> tuple[str, str] | None:
    load_dotenv()
    user = (os.environ.get("ADMIN_USER") or "").strip()
    pwd_hash = (os.environ.get("ADMIN_PASS_HASH") or "").strip()
    if user and pwd_hash:
        return user, pwd_hash
    return None


def stored_credentials() -> tuple[str, str] | None:
    env = _env_credentials()
    if env:
        return env
    data = _read_auth_file()
    user = str(data.get("username") or "").strip()
    pwd_hash = str(data.get("password_hash") or "").strip()
    if user and pwd_hash:
        return user, pwd_hash
    return None


def jwt_secret() -> str:
    load_dotenv()
    env = (os.environ.get("JWT_SECRET") or "").strip()
    if env:
        return env
    data = _read_auth_file()
    secret = str(data.get("jwt_secret") or "").strip()
    if secret:
        return secret
    secret = secrets.token_urlsafe(48)
    merged = {**data, "jwt_secret": secret}
    _write_auth_file(merged)
    return secret


def needs_setup() -> bool:
    if auth_disabled() or local_bypass_enabled():
        return False
    return stored_credentials() is None


def auth_status(request: Request | None = None) -> dict[str, Any]:
    creds = stored_credentials()
    local_ok = local_bypass_allowed(request) if request else local_bypass_enabled()
    return {
        "auth_disabled": auth_disabled(),
        "local_bypass": local_ok,
        "needs_setup": needs_setup(),
        "configured": creds is not None,
        "username": creds[0] if creds else None,
    }


def create_admin(username: str, password: str) -> dict[str, Any]:
    if stored_credentials() and not needs_setup():
        raise HTTPException(status_code=409, detail="Admin already configured")
    user = username.strip()
    if len(user) < 2:
        raise HTTPException(status_code=400, detail="Username too short")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    data = _read_auth_file()
    data.update(
        {
            "username": user,
            "password_hash": hash_password(password),
            "created_at": _utcnow().isoformat(timespec="seconds"),
        }
    )
    if not data.get("jwt_secret"):
        data["jwt_secret"] = secrets.token_urlsafe(48)
    _write_auth_file(data)
    return {"username": user}


def authenticate_user(username: str, password: str) -> dict[str, Any]:
    creds = stored_credentials()
    if not creds:
        raise HTTPException(status_code=503, detail="Admin not configured")
    stored_user, stored_hash = creds
    if username.strip() != stored_user or not verify_password(password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"username": stored_user, "role": "admin"}


def create_token(user: dict[str, Any]) -> str:
    now = _utcnow()
    payload = {
        "sub": user["username"],
        "role": user.get("role", "admin"),
        "local": bool(user.get("local")),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=ALGORITHM)


def local_session_user() -> dict[str, Any]:
    return {"username": "local", "role": "admin", "local": True}


def issue_local_session(request: Request) -> dict[str, Any]:
    if not local_bypass_allowed(request):
        raise HTTPException(status_code=403, detail="Local bypass not available from this host")
    user = local_session_user()
    return {"ok": True, "token": create_token(user), "user": user}


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
        return {
            "username": payload.get("sub"),
            "role": payload.get("role", "admin"),
            "local": bool(payload.get("local")),
        }
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    cookie = request.cookies.get(TOKEN_COOKIE)
    if cookie:
        return cookie
    return None


def get_current_user(request: Request) -> dict[str, Any]:
    if auth_disabled():
        return local_session_user()
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(token)


def authenticate_request(request: Request) -> dict[str, Any]:
    if auth_disabled():
        return local_session_user()
    token = _token_from_request(request)
    if token:
        user = decode_token(token)
        if user.get("local") and local_bypass_allowed(request):
            return user
    if needs_setup():
        raise HTTPException(status_code=401, detail="Admin setup required")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(token)


def authenticate_websocket(ws: WebSocket) -> dict[str, Any]:
    if auth_disabled():
        return local_session_user()
    token = ws.query_params.get("token") or ws.cookies.get(TOKEN_COOKIE)
    if token:
        user = decode_token(token)
        if user.get("local"):
            host = ws.client.host if ws.client else ""
            if is_loopback_host(host):
                return user
    if needs_setup():
        raise HTTPException(status_code=401, detail="Admin setup required")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(token)


def is_public_api_path(path: str) -> bool:
    if path == "/api/health":
        return True
    if path in ("/api/auth/status", "/api/auth/login", "/api/auth/setup", "/api/auth/local"):
        return True
    return False
