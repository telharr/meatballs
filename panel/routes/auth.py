"""Auth API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from panel.auth import (
    TOKEN_COOKIE,
    TOKEN_TTL_HOURS,
    auth_status,
    authenticate_user,
    bump_token_version,
    create_admin,
    create_token,
    create_totp_challenge,
    consume_totp_challenge,
    get_current_user,
    issue_local_session,
    needs_setup,
    revoke_token,
    set_totp_secret,
    totp_enabled_for,
    totp_secret_for,
    verify_password,
    _primary_credentials,
    _read_auth_file,
    _write_auth_file,
)
from panel.security_hardening import (
    new_csrf_token,
    request_is_https,
    set_csrf_cookie,
    totp_generate_secret,
    totp_provisioning_uri,
    totp_verify,
    validate_password_strength,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class SetupBody(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=12, max_length=200)


class TotpLoginBody(BaseModel):
    challenge: str = Field(min_length=10, max_length=4000)
    code: str = Field(min_length=6, max_length=12)


class TotpEnableBody(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class TotpDisableBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=6, max_length=12)


def _set_auth_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        key=TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=int(TOKEN_TTL_HOURS * 3600),
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=TOKEN_COOKIE, path="/")


def _session_payload(response: Response, request: Request, user: dict[str, Any]) -> dict[str, Any]:
    token = create_token(user)
    secure = request_is_https(request)
    _set_auth_cookie(response, token, secure=secure)
    csrf = new_csrf_token()
    set_csrf_cookie(response, csrf, secure=secure)
    # Do not return JWT in body (XSS / localStorage theft)
    return {"ok": True, "user": user, "csrf": csrf}


@router.get("/status")
async def api_auth_status(request: Request) -> dict[str, Any]:
    return auth_status(request)


@router.get("/csrf")
async def api_auth_csrf(request: Request, response: Response) -> dict[str, Any]:
    token = new_csrf_token()
    set_csrf_cookie(response, token, secure=request_is_https(request))
    return {"csrf": token}


@router.post("/local")
async def api_auth_local(request: Request, response: Response) -> dict[str, Any]:
    out = issue_local_session(request)
    return _session_payload(response, request, out["user"])


@router.get("/me")
async def api_auth_me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "username": user.get("username"),
        "role": user.get("role", "admin"),
        "local": bool(user.get("local")),
        "totp_enabled": totp_enabled_for(str(user.get("username") or "")),
    }


@router.post("/login")
async def api_auth_login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
    user = authenticate_user(body.username, body.password, request=request)
    if totp_enabled_for(user["username"]):
        challenge = create_totp_challenge(user)
        return {"ok": True, "needs_totp": True, "challenge": challenge}
    return _session_payload(response, request, user)


@router.post("/login/totp")
async def api_auth_login_totp(body: TotpLoginBody, request: Request, response: Response) -> dict[str, Any]:
    user = consume_totp_challenge(body.challenge, body.code)
    return _session_payload(response, request, user)


@router.post("/setup")
async def api_auth_setup(body: SetupBody, request: Request, response: Response) -> dict[str, Any]:
    if not needs_setup():
        raise HTTPException(status_code=409, detail="Admin already configured")
    validate_password_strength(body.password)
    user = create_admin(body.username, body.password)
    return _session_payload(response, request, {**user, "role": "admin"})


@router.post("/logout")
async def api_auth_logout(response: Response, request: Request) -> dict[str, Any]:
    try:
        user = get_current_user(request)
        revoke_token(user)
    except HTTPException:
        pass
    _clear_auth_cookie(response)
    response.delete_cookie(key="pz_panel_csrf", path="/")
    return {"ok": True}


@router.post("/logout-all")
async def api_auth_logout_all(
    response: Response,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if user.get("role") != "admin" and not user.get("local"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    bump_token_version()
    _clear_auth_cookie(response)
    return {"ok": True}


@router.post("/totp/setup")
async def api_totp_setup(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("local"):
        raise HTTPException(status_code=400, detail="TOTP not available for local bypass sessions")
    username = str(user.get("username") or "")
    secret = totp_generate_secret()
    # Stash pending secret in auth file under totp_pending
    from panel.auth import _read_auth_file, _write_auth_file

    data = _read_auth_file()
    data["totp_pending"] = {"username": username, "secret": secret}
    _write_auth_file(data)
    return {
        "secret": secret,
        "otpauth_url": totp_provisioning_uri(secret, username),
    }


@router.post("/totp/enable")
async def api_totp_enable(
    body: TotpEnableBody,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from panel.auth import _read_auth_file, _write_auth_file

    data = _read_auth_file()
    pending = data.get("totp_pending") or {}
    if str(pending.get("username") or "") != str(user.get("username") or ""):
        raise HTTPException(status_code=400, detail="Run /api/auth/totp/setup first")
    secret = str(pending.get("secret") or "")
    if not totp_verify(secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    set_totp_secret(str(user.get("username") or ""), secret)
    data = _read_auth_file()
    data.pop("totp_pending", None)
    _write_auth_file(data)
    bump_token_version()
    return {"ok": True, "totp_enabled": True}


@router.post("/totp/disable")
async def api_totp_disable(
    body: TotpDisableBody,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    username = str(user.get("username") or "")
    primary = _primary_credentials()
    ok = False
    if primary and username == primary[0]:
        ok = verify_password(body.password, primary[1])
    if not ok:
        raise HTTPException(status_code=403, detail="Password invalid")
    secret = totp_secret_for(username)
    if not secret or not totp_verify(secret, body.code):
        raise HTTPException(status_code=403, detail="TOTP invalid")
    set_totp_secret(username, None)
    bump_token_version()
    return {"ok": True, "totp_enabled": False}
