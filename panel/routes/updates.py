"""Panel update API (GitHub Releases)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from panel.auth import require_role
from panel.services import panel_updates as upd

router = APIRouter(prefix="/api/panel", tags=["panel-updates"])


class SnoozeBody(BaseModel):
    version: str = Field(default="", max_length=40)


class ApplyBody(BaseModel):
    path: str = Field(default="", max_length=500)


@router.get("/updates")
async def api_panel_updates(
    force: bool = False,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    return await asyncio.to_thread(upd.check_for_updates, force=force)


@router.post("/updates/snooze")
async def api_panel_updates_snooze(
    body: SnoozeBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    return await asyncio.to_thread(upd.snooze_update, body.version or None)


@router.get("/updates/job")
async def api_panel_updates_job(
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    return upd.job_status()


@router.post("/updates/download")
async def api_panel_updates_download(
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    try:
        await asyncio.to_thread(upd.backup_state_zip)
        return await asyncio.to_thread(upd.download_latest_setup)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/updates/apply")
async def api_panel_updates_apply(
    body: ApplyBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    try:
        await asyncio.to_thread(upd.backup_state_zip)
        return await asyncio.to_thread(upd.apply_downloaded_setup, body.path or None)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
