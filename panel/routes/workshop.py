"""Workshop download, update monitor, and ModPack compile API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from panel.services import pack_merger as pack_svc
from panel.services import workshop_downloader as dl_svc
from panel.services import workshop_monitor as mon_svc

router = APIRouter(prefix="/api/workshop", tags=["workshop"])


class DownloadBody(BaseModel):
    workshop_ids: list[str] = Field(default_factory=list)
    missing_only: bool = True
    username: str | None = Field(default=None, max_length=80)


class CompileBody(BaseModel):
    mod_ids: list[str] = Field(default_factory=list)
    pack_id: str = Field(..., max_length=40)
    pack_name: str = Field(default="", max_length=80)
    fail_on_conflict: bool = False


class AnalyzeBody(BaseModel):
    mod_ids: list[str] = Field(default_factory=list)


class AutoRestartFlagBody(BaseModel):
    enabled: bool = False


class GracefulRestartBody(BaseModel):
    minutes: int = Field(default=3, ge=1, le=30)
    message: str = Field(default="", max_length=200)


class AckBody(BaseModel):
    workshop_ids: list[str] = Field(default_factory=list)


@router.get("/status")
async def api_workshop_status() -> dict[str, Any]:
    data = dl_svc.status_bundle()
    mon = mon_svc.monitor_snapshot()
    # merge last known Steam stamps if present
    state_items = {}
    try:
        raw = mon_svc._read_state()  # noqa: SLF001 — shared panel state
        state_items = raw.get("items") or {}
    except Exception:
        pass
    for item in data.get("items") or []:
        wid = item.get("workshop_id")
        remembered = state_items.get(wid) or {}
        item["title"] = remembered.get("title") or item.get("title") or wid
        item["remote_updated"] = remembered.get("time_updated") or None
        local_epoch = item.get("local_epoch") or 0
        remote_ts = int(remembered.get("time_updated") or 0)
        baseline = int(local_epoch or remembered.get("seen_updated") or 0)
        item["update_available"] = bool(remote_ts and baseline and remote_ts > baseline)
    data["monitor"] = mon
    data["available_mods"] = pack_svc.list_available_mods()
    return data


@router.post("/download")
async def api_workshop_download(body: DownloadBody) -> dict[str, Any]:
    try:
        return dl_svc.start_download(
            body.workshop_ids or None,
            missing_only=body.missing_only,
            username=body.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/download/status")
async def api_workshop_download_status() -> dict[str, Any]:
    return dl_svc.download_status()


@router.post("/check-updates")
async def api_workshop_check_updates() -> dict[str, Any]:
    try:
        return mon_svc.check_updates()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/ack-updates")
async def api_workshop_ack(body: AckBody) -> dict[str, Any]:
    return mon_svc.acknowledge_updates(body.workshop_ids or None)


@router.get("/monitor")
async def api_workshop_monitor() -> dict[str, Any]:
    return mon_svc.monitor_snapshot()


@router.post("/auto-restart")
async def api_workshop_auto_restart_flag(body: AutoRestartFlagBody) -> dict[str, Any]:
    return mon_svc.set_auto_restart(body.enabled)


@router.post("/graceful-restart")
async def api_workshop_graceful_restart(body: GracefulRestartBody) -> dict[str, Any]:
    try:
        return mon_svc.start_graceful_restart(body.minutes, body.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/mods")
async def api_workshop_mods() -> dict[str, Any]:
    return {"mods": pack_svc.list_available_mods()}


@router.post("/analyze")
async def api_workshop_analyze(body: AnalyzeBody) -> dict[str, Any]:
    return pack_svc.analyze_mods(body.mod_ids or None)


@router.post("/compile")
async def api_workshop_compile(body: CompileBody) -> dict[str, Any]:
    try:
        return pack_svc.compile_pack(
            mod_ids=body.mod_ids,
            pack_id=body.pack_id,
            pack_name=body.pack_name,
            fail_on_conflict=body.fail_on_conflict,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
