"""VPS auto-provision API (Amnezia-style SSH deploy)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from panel.auth import require_role
from panel.services import vps_provisioner as prov

router = APIRouter(prefix="/api/vps", tags=["vps-provision"])


class ProvisionBody(BaseModel):
    host: str = Field(..., max_length=200)
    port: int = Field(default=22, ge=1, le=65535)
    user: str = Field(default="root", max_length=80)
    secret: str = Field(..., max_length=16000)
    web_port: int = Field(default=8000, ge=1, le=65535)
    admin_password: str = Field(..., min_length=12, max_length=200)


def _is_key(secret: str) -> bool:
    t = (secret or "").strip()
    return "BEGIN" in t and "PRIVATE KEY" in t


@router.post("/provision")
async def api_vps_provision(
    body: ProvisionBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    host = body.host.strip()
    # Allow host:ssh_port in host field; body.port wins if host has no :port
    ssh_port = int(body.port)
    if ":" in host and not host.startswith("["):
        # IPv4 host:port — only if trailing part is digits
        left, _, right = host.rpartition(":")
        if left and right.isdigit():
            host = left
            ssh_port = int(right)
    secret = body.secret
    key_mode = _is_key(secret)
    try:
        status = prov.start_provision(
            prov.ProvisionRequest(
                host=host,
                port=ssh_port,
                user=(body.user or "root").strip() or "root",
                password="" if key_mode else secret,
                private_key=secret.strip() if key_mode else "",
                web_port=int(body.web_port),
                admin_password=body.admin_password,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "status": status}


@router.get("/provision/status")
async def api_vps_provision_status(
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    return prov.provision_status()
