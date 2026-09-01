"""AdminTools API: cities, city wipe, audit journal."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from panel.auth import require_role
from panel.logs_hub import audit_actions
from panel.services import admin_tools as at_svc

router = APIRouter(prefix="/api/admintools", tags=["admintools"])


class CityWipeBody(BaseModel):
    city_id: str = Field(..., min_length=2, max_length=40)
    refill_loot: bool = True
    reconstruct_containers: bool = False
    upload: bool = True
    rcon_notify: bool = True


@router.get("/cities")
async def api_cities() -> dict[str, Any]:
    return at_svc.list_cities()


@router.post("/city-wipe")
async def api_city_wipe(
    body: CityWipeBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    try:
        return at_svc.trigger_city_wipe(
            body.city_id,
            refill_loot=body.refill_loot,
            reconstruct_containers=body.reconstruct_containers,
            upload=body.upload,
            rcon_notify=body.rcon_notify,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc


@router.get("/audit")
async def api_audit(limit: int = 200) -> dict[str, Any]:
    try:
        return audit_actions(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
