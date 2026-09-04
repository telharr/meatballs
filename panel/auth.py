"""JWT session auth for the control panel (Sprint 3 + RBAC + VPS hardening)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, Request, WebSocket

from ftp_client import load_dotenv
from panel.security_hardening import (
    check_login_allowed,
    client_ip,
    dummy_password_hash,
    is_jti_revoked,
    is_public_deployment,
    record_login_failure,
    record_login_success,
    revoke_jti,
    totp_verify,
    validate_password_strength,
)

PANEL = Path(__file__).resolve().parent
from panel.paths import DATA_DIR  # noqa: E402

AUTH_FILE = DATA_DIR / "auth.json"
TOKEN_COOKIE = "pz_panel_token"
ALGORITHM = "HS256"
# Short-lived access tokens; bump token_version to revoke all sessions
TOKEN_TTL_HOURS = float(os.environ.get("TOKEN_TTL_HOURS", "1") or "1")
CHALLENGE_TTL_SEC = 120
PBKDF2_ITERATIONS = 260_000
ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"
VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_MODERATOR})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def auth_disabled() -> bool:
    load_dotenv()
    return os.environ.get("AUTH_DISABLED", "").strip().lower() in ("1", "true", "yes")


def _client_host(request: Request) -> str:
    return client_ip(request)


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in ("127.0.0.1", "::1", "localhost"):
        return True
    if h.startswith("127."):
        return True
    return False


def local_bypass_enabled() -> bool:
    load_dotenv()
    if auth_disabled():
        return True
    # Never auto-enable bypass on public binds
    if is_public_deployment():
        flag = os.environ.get("AUTH_LOCAL_BYPASS", "").strip().lower()
        return flag in ("1", "true", "yes")
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
    tmp = AUTH_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(AUTH_FILE)


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


def _env_credentials() -> tuple[str, str, str] | None:
    load_dotenv()
    user = (os.environ.get("ADMIN_USER") or "").strip()
    pwd_hash = (os.environ.get("ADMIN_PASS_HASH") or "").strip()
    if user and pwd_hash:
        return user, pwd_hash, ROLE_ADMIN
    return None


def _primary_credentials() -> tuple[str, str, str] | None:
    env = _env_credentials()
    if env:
        return env
    data = _read_auth_file()
    user = str(data.get("username") or "").strip()
    pwd_hash = str(data.get("password_hash") or "").strip()
    role = str(data.get("role") or ROLE_ADMIN).strip() or ROLE_ADMIN
    if user and pwd_hash:
        return user, pwd_hash, role if role in VALID_ROLES else ROLE_ADMIN
    return None


def stored_credentials() -> tuple[str, str] | None:
    primary = _primary_credentials()
    if primary:
        return primary[0], primary[1]
    return None


def list_extra_users() -> list[dict[str, str]]:
    data = _read_auth_file()
    out: list[dict[str, str]] = []
    for row in data.get("users") or []:
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "").strip()
        pwd_hash = str(row.get("password_hash") or "").strip()
        role = str(row.get("role") or ROLE_MODERATOR).strip()
        if username and pwd_hash and role in VALID_ROLES:
            out.append({"username": username, "password_hash": pwd_hash, "role": role})
    return out


def token_version() -> int:
    data = _read_auth_file()
    try:
        return int(data.get("token_version") or 0)
    except (TypeError, ValueError):
        return 0


def bump_token_version() -> int:
    data = _read_auth_file()
    ver = int(data.get("token_version") or 0) + 1
    data["token_version"] = ver
    _write_auth_file(data)
    return ver


def totp_secret_for(username: str) -> str | None:
    data = _read_auth_file()
    primary = str(data.get("username") or "").strip()
    if username == primary:
        sec = str(data.get("totp_secret") or "").strip()
        return sec or None
    for row in data.get("users") or []:
        if isinstance(row, dict) and str(row.get("username") or "").strip() == username:
            sec = str(row.get("totp_secret") or "").strip()
            return sec or None
    # Env-only admin: optional ADMIN_TOTP_SECRET
    env = _env_credentials()
    if env and username == env[0]:
        sec = (os.environ.get("ADMIN_TOTP_SECRET") or "").strip()
        return sec or None
    return None


def totp_enabled_for(username: str) -> bool:
    return bool(totp_secret_for(username))


def set_totp_secret(username: str, secret: str | None) -> None:
    data = _read_auth_file()
    primary = str(data.get("username") or "").strip()
    if username == primary or (not primary and _env_credentials() and username == _env_credentials()[0]):
        if not primary and _env_credentials():
            # Persist overlay for env-based admin
            data["username"] = username
            data.setdefault("password_hash", _env_credentials()[1])
            data.setdefault("role", ROLE_ADMIN)
        if secret:
            data["totp_secret"] = secret
            data["totp_enabled"] = True
        else:
            data.pop("totp_secret", None)
            data["totp_enabled"] = False
        _write_auth_file(data)
        return
    users = list(data.get("users") or [])
    found = False
    for row in users:
        if isinstance(row, dict) and str(row.get("username") or "").strip() == username:
            if secret:
                row["totp_secret"] = secret
            else:
                row.pop("totp_secret", None)
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="User not found")
    data["users"] = users
    _write_auth_file(data)


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
    out: dict[str, Any] = {
        "auth_disabled": auth_disabled(),
        "local_bypass": local_ok,
        "needs_setup": needs_setup(),
        "configured": creds is not None,
        "public": is_public_deployment(),
        "password_min_length": 12,
    }
    # Do not leak username to anonymous callers
    if request is not None:
        try:
            token = _token_from_request(request)
            if token:
                user = decode_token(token)
                out["username"] = user.get("username")
                out["totp_enabled"] = totp_enabled_for(str(user.get("username") or ""))
        except HTTPException:
            pass
    return out


def create_admin(username: str, password: str) -> dict[str, Any]:
    if stored_credentials() and not needs_setup():
        raise HTTPException(status_code=409, detail="Admin already configured")
    user = username.strip()
    if len(user) < 2:
        raise HTTPException(status_code=400, detail="Username too short")
    validate_password_strength(password)
    data = _read_auth_file()
    data.update(
        {
            "username": user,
            "password_hash": hash_password(password),
            "role": ROLE_ADMIN,
            "token_version": int(data.get("token_version") or 0),
            "created_at": _utcnow().isoformat(timespec="seconds"),
        }
    )
    if not data.get("jwt_secret"):
        data["jwt_secret"] = secrets.token_urlsafe(48)
    _write_auth_file(data)
    return {"username": user, "role": ROLE_ADMIN}


def _match_user(username: str, password: str) -> dict[str, Any] | None:
    name = username.strip()
    primary = _primary_credentials()
    if primary:
        stored_user, stored_hash, role = primary
        if name == stored_user and verify_password(password, stored_hash):
            return {"username": stored_user, "role": role}
    for row in list_extra_users():
        if name == row["username"] and verify_password(password, row["password_hash"]):
            return {"username": row["username"], "role": row["role"]}
    return None


def authenticate_user(username: str, password: str, *, request: Request | None = None) -> dict[str, Any]:
    ip = client_ip(request) if request else ""
    check_login_allowed(ip, username)
    primary = _primary_credentials()
    if not primary and not list_extra_users():
        # Same response shape as bad password to reduce enumeration
        verify_password(password or "x", dummy_password_hash())
        record_login_failure(ip, username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    matched = _match_user(username, password)
    if not matched:
        # Constant-ish work on miss
        verify_password(password or "x", dummy_password_hash())
        record_login_failure(ip, username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    record_login_success(ip, username)
    return matched


def create_totp_challenge(user: dict[str, Any]) -> str:
    now = _utcnow()
    payload = {
        "sub": user["username"],
        "role": user.get("role", ROLE_ADMIN),
        "purpose": "totp",
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=CHALLENGE_TTL_SEC)).timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=ALGORITHM)


def consume_totp_challenge(challenge: str, code: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(challenge, jwt_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired TOTP challenge") from exc
    if payload.get("purpose") != "totp":
        raise HTTPException(status_code=401, detail="Invalid TOTP challenge")
    username = str(payload.get("sub") or "")
    secret = totp_secret_for(username)
    if not secret or not totp_verify(secret, code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    return {
        "username": username,
        "role": payload.get("role", ROLE_ADMIN) if payload.get("role") in VALID_ROLES else ROLE_ADMIN,
    }


def create_token(user: dict[str, Any]) -> str:
    now = _utcnow()
    jti = secrets.token_urlsafe(16)
    payload = {
        "sub": user["username"],
        "role": user.get("role", ROLE_ADMIN),
        "local": bool(user.get("local")),
        "ver": token_version(),
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=ALGORITHM)


def local_session_user() -> dict[str, Any]:
    return {"username": "local", "role": ROLE_ADMIN, "local": True}


def issue_local_session(request: Request) -> dict[str, Any]:
    if not local_bypass_allowed(request):
        raise HTTPException(status_code=403, detail="Local bypass not available from this host")
    user = local_session_user()
    return {"ok": True, "user": user, "token": create_token(user)}


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
        jti = str(payload.get("jti") or "")
        if jti and is_jti_revoked(jti):
            raise HTTPException(status_code=401, detail="Session revoked")
        ver = int(payload.get("ver") or 0)
        if ver != token_version() and not payload.get("local"):
            raise HTTPException(status_code=401, detail="Session revoked")
        role = payload.get("role", ROLE_ADMIN)
        return {
            "username": payload.get("sub"),
            "role": role if role in VALID_ROLES else ROLE_ADMIN,
            "local": bool(payload.get("local")),
            "jti": jti,
            "exp": int(payload.get("exp") or 0),
        }
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def revoke_token(user: dict[str, Any]) -> None:
    jti = str(user.get("jti") or "")
    exp = int(user.get("exp") or 0) or int((_utcnow() + timedelta(hours=TOKEN_TTL_HOURS)).timestamp())
    if jti:
        revoke_jti(jti, exp)


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
        if not user.get("local"):
            return user
        # local token from non-loopback
        if user.get("local") and not local_bypass_allowed(request):
            raise HTTPException(status_code=401, detail="Authentication required")
        return user
    if needs_setup():
        raise HTTPException(status_code=401, detail="Admin setup required")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(token)


def authenticate_websocket(ws: WebSocket) -> dict[str, Any]:
    if auth_disabled():
        return local_session_user()
    # Prefer cookie (browser); query token allowed for tooling but discouraged
    token = ws.cookies.get(TOKEN_COOKIE) or ws.query_params.get("token")
    if token:
        user = decode_token(token)
        if user.get("local"):
            host = ws.client.host if ws.client else ""
            if is_loopback_host(host):
                return user
            raise HTTPException(status_code=401, detail="Authentication required")
        return user
    if needs_setup():
        raise HTTPException(status_code=401, detail="Admin setup required")
    raise HTTPException(status_code=401, detail="Authentication required")


def is_public_api_path(path: str) -> bool:
    if path == "/api/health":
        return True
    if path in (
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/login/totp",
        "/api/auth/setup",
        "/api/auth/local",
        "/api/auth/csrf",
    ):
        return True
    return False


def moderator_write_forbidden(method: str, path: str) -> bool:
    if method.upper() in ("GET", "HEAD", "OPTIONS"):
        return False
    if path == "/api/auth/setup":
        return True
    if path.startswith("/api/servers"):
        return True
    if path == "/api/config/save":
        return True
    if path.startswith("/api/wipe/"):
        return True
    if path == "/api/workshop/compile":
        return True
    if path == "/api/workshop/deploy-mods":
        return True
    if path == "/api/admintools/city-wipe":
        return True
    if path == "/api/admintools/queue/clear":
        return True
    if path.startswith("/api/safehouses/") and path != "/api/safehouses/pull":
        return True
    return False


def ensure_role(user: dict[str, Any], *roles: str) -> None:
    role = user.get("role", ROLE_ADMIN)
    if role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def require_role(*roles: str) -> Callable[..., dict[str, Any]]:
    allowed = frozenset(roles)

    def _dependency(request: Request) -> dict[str, Any]:
        user = getattr(request.state, "user", None) or authenticate_request(request)
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return Depends(_dependency)


def verify_step_up(request: Request, user: dict[str, Any]) -> None:
    """Re-auth: password (+ TOTP if enabled) for destructive actions."""
    if user.get("local") or auth_disabled():
        return
    password = (
        request.headers.get("x-panel-confirm-password")
        or (request.headers.get("X-Panel-Confirm-Password") or "")
    ).strip()
    # Also accept from JSON body already parsed into state by routes (optional)
    body_pw = getattr(request.state, "confirm_password", None)
    if body_pw:
        password = str(body_pw)
    if not password:
        raise HTTPException(
            status_code=403,
            detail="Step-up required: send X-Panel-Confirm-Password",
        )
    primary = _primary_credentials()
    ok = False
    if primary and user.get("username") == primary[0]:
        ok = verify_password(password, primary[1])
    else:
        for row in list_extra_users():
            if row["username"] == user.get("username"):
                ok = verify_password(password, row["password_hash"])
                break
    if not ok:
        raise HTTPException(status_code=403, detail="Step-up password invalid")
    secret = totp_secret_for(str(user.get("username") or ""))
    if secret:
        code = (request.headers.get("x-panel-totp") or request.headers.get("X-Panel-TOTP") or "").strip()
        body_code = getattr(request.state, "confirm_totp", None)
        if body_code:
            code = str(body_code)
        if not totp_verify(secret, code):
            raise HTTPException(status_code=403, detail="Step-up TOTP invalid")
