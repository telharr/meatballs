"""Auth API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from panel.auth import (
    TOKEN_COOKIE,
    TOKEN_TTL_HOURS,
    auth_status,
    authenticate_user,
    create_admin,
    create_token,
    get_current_user,
    issue_local_session,
    needs_setup,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class SetupBody(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=200)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=TOKEN_TTL_HOURS * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=TOKEN_COOKIE, path="/")


@router.get("/status")
async def api_auth_status(request: Request) -> dict[str, Any]:
    return auth_status(request)


@router.post("/local")
async def api_auth_local(request: Request, response: Response) -> dict[str, Any]:
    out = issue_local_session(request)
    _set_auth_cookie(response, out["token"])
    return out


@router.get("/me")
async def api_auth_me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"username": user.get("username"), "role": user.get("role", "admin")}


@router.post("/login")
async def api_auth_login(body: LoginBody, response: Response) -> dict[str, Any]:
    user = authenticate_user(body.username, body.password)
    token = create_token(user)
    _set_auth_cookie(response, token)
    return {"ok": True, "token": token, "user": user}


@router.post("/setup")
async def api_auth_setup(body: SetupBody, response: Response) -> dict[str, Any]:
    if not needs_setup():
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="Admin already configured")
    user = create_admin(body.username, body.password)
    token = create_token({**user, "role": "admin"})
    _set_auth_cookie(response, token)
    return {"ok": True, "token": token, "user": {**user, "role": "admin"}}


@router.post("/logout")
async def api_auth_logout(response: Response, request: Request) -> dict[str, Any]:
    _clear_auth_cookie(response)
    return {"ok": True}
