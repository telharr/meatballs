"""Telemetry REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from panel.services import telemetry as telemetry_svc

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/stats")
async def api_telemetry_stats() -> dict[str, Any]:
    return telemetry_svc.collect_stats()
