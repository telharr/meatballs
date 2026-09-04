"""Safehouse panel API: dump, map data, create/update/release, install bridge mod."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from panel.auth import require_role
from panel import knox_map
from panel import safehouses as sh

router = APIRouter(tags=["safehouses"])


class RectBody(BaseModel):
    x: int
    y: int
    w: int = Field(..., ge=1, le=400)
    h: int = Field(..., ge=1, le=400)
    owner: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=80)
    members: list[str] = Field(default_factory=list)
    add: list[str] = Field(default_factory=list)
    kick: list[str] = Field(default_factory=list)
    confirm: str = Field(default="", max_length=20)
    upload: bool = True
    rcon_notify: bool = True


class InstallBody(BaseModel):
    patch_ini: bool = False


def _clean_names(names: list[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        cleaned = str(name or "").strip()
        if cleaned and cleaned not in out:
            out.append(cleaned[:80])
    return out


@router.get("/api/safehouses")
async def api_safehouses(pull: bool = Query(default=False)) -> dict[str, Any]:
    data = sh.snapshot(pull=pull)
    ack = data.get("ack") or {}
    if ack.get("nonce"):
        sh.mark_job_ack(ack)
        data["queue"] = sh.pending_jobs()[-10:]
    return data


@router.get("/api/safehouses/map")
async def api_map() -> dict[str, Any]:
    return knox_map.snapshot_map()


@router.get("/api/safehouses/map/atlas")
async def api_atlas() -> FileResponse:
    path = knox_map.atlas_file()
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="Atlas not generated. Run: python tools/knox_atlas.py",
        )
    return FileResponse(path, media_type="image/png", filename="atlas.png")


@router.post("/api/safehouses/create")
async def api_create(body: RectBody, _user: dict[str, Any] = require_role("admin")) -> dict[str, Any]:
    try:
        return sh.create_safehouse(
            x=body.x,
            y=body.y,
            w=body.w,
            h=body.h,
            owner=body.owner,
            title=body.title,
            members=_clean_names(body.members),
            upload=body.upload,
            rcon_notify=body.rcon_notify,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc


@router.post("/api/safehouses/update")
async def api_update(body: RectBody, _user: dict[str, Any] = require_role("admin")) -> dict[str, Any]:
    try:
        return sh.update_safehouse(
            x=body.x,
            y=body.y,
            w=body.w,
            h=body.h,
            owner=body.owner or None,
            title=body.title if body.title != "" else None,
            add=_clean_names(body.add),
            kick=_clean_names(body.kick),
            members=_clean_names(body.members),
            upload=body.upload,
            rcon_notify=body.rcon_notify,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc


@router.post("/api/safehouses/release")
async def api_release(body: RectBody, _user: dict[str, Any] = require_role("admin")) -> dict[str, Any]:
    try:
        return sh.release_safehouse(
            x=body.x,
            y=body.y,
            w=body.w,
            h=body.h,
            confirm=body.confirm,
            upload=body.upload,
            rcon_notify=body.rcon_notify,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc


@router.post("/api/safehouses/install")
async def api_install(body: InstallBody | None = None, _user: dict[str, Any] = require_role("admin")) -> dict[str, Any]:
    payload = body or InstallBody()
    try:
        return sh.install_mod(patch_ini=payload.patch_ini)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc


@router.post("/api/safehouses/pull")
async def api_pull(_user: dict[str, Any] = require_role("moderator")) -> dict[str, Any]:
    pulled = sh.pull_remote_state()
    data = sh.snapshot(pull=False)
    data["pulled"] = pulled
    ack = data.get("ack") or {}
    if ack.get("nonce"):
        sh.mark_job_ack(ack)
    return data
