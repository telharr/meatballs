#!/usr/bin/env python3
"""FastAPI control panel: FTP config editor + live RCON console."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sys
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from ftplib import error_perm, error_proto, error_reply, error_temp
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PANEL = Path(__file__).resolve().parent
from panel.paths import BACKUPS_DIR, DATA_DIR, UPDATES_DIR, ensure_state_dirs  # noqa: E402

BACKUPS = BACKUPS_DIR
STATIC = PANEL / "static"
SERVER_LOG_CANDIDATES = ("server-console.txt",)

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ftp_client import IntegrityError, client_from_env, load_dotenv  # noqa: E402

from panel.rcon_client import RconConfig, rcon_execute  # noqa: E402
from mod_catalog import (  # noqa: E402
    add_item,
    apply_lists_to_ini,
    catalog_loadout,
    download_workshop,
    import_from_lists,
    parse_ini_list,
    remove_item,
    scaffold_local,
    set_item_enabled,
    snapshot as catalog_snapshot,
)
from server_mirror import abort as mirror_abort  # noqa: E402
from server_mirror import default_remote as mirror_default_remote
from server_mirror import pull as mirror_pull
from server_mirror import resume as mirror_resume
from server_mirror import status as mirror_status
from server_mirror import verify as mirror_verify
from panel.launch import (  # noqa: E402
    add_founder,
    adduser_command,
    announce_command,
    invite_text,
    load_roster,
    mark_account_created,
    mark_joined,
    post_discord,
    public_endpoints,
    remove_founder,
)
from panel.prefs import (  # noqa: E402
    host_conflict,
    load_prefs,
    remember_remote,
    save_prefs,
)
from panel.slots import (  # noqa: E402
    filter_real_players,
    iter_mod_files,
    set_slots,
    snapshot as slots_snapshot,
    write_temp_line,
)
from panel.logs_hub import catalog as logs_catalog  # noqa: E402
from panel.logs_hub import recent_errors as logs_recent_errors
from panel.logs_hub import tail_kind as logs_tail_kind
from panel.services import player_access as player_access_svc  # noqa: E402
from panel.chat import snapshot as chat_snapshot
from panel.bans import snapshot as bans_snapshot
from panel.bans import unban_command
from panel.wipe import apply as wipe_apply
from panel.wipe import preview as wipe_preview
from panel.servers import (  # noqa: E402
    activate_server,
    active_capabilities,
    active_files_client,
    active_id,
    active_profile,
    delete_server,
    ensure_migrated,
    effective_capabilities,
    effective_plugins,
    evaluate_draft_capabilities,
    list_servers,
    onboarding_state,
    probe_files,
    probe_query,
    probe_rcon,
    public_profile,
    upsert_server,
    views_state,
)
from local_server import inspect as local_inspect  # noqa: E402
from local_server import parse_world_status
from local_server import start as local_start
from local_server import stop as local_stop
from panel.services.local_runner import smoke_start, smoke_status, smoke_stop  # noqa: E402
from panel.services.snapshot import resolve_snapshot_file, write_panel_snapshot  # noqa: E402
from panel.auth import (  # noqa: E402
    auth_disabled,
    authenticate_request,
    authenticate_websocket,
    is_public_api_path,
    moderator_write_forbidden,
    needs_setup,
    require_role,
    verify_step_up,
)
from panel.routes.auth import router as auth_router  # noqa: E402
from panel.routes.workshop import router as workshop_router  # noqa: E402
from panel.routes.admintools import router as admintools_router  # noqa: E402
from panel.routes.telemetry import router as telemetry_router  # noqa: E402
from panel.routes.provision import router as provision_router  # noqa: E402
from panel.routes.updates import router as updates_router  # noqa: E402
from panel.routes.safehouses import router as safehouses_router  # noqa: E402
from panel.version import __version__ as PANEL_VERSION  # noqa: E402
from panel.services.event_bus import bus as event_bus  # noqa: E402
from panel.security_hardening import (  # noqa: E402
    SecurityHeadersMiddleware,
    is_public_deployment,
    path_needs_step_up,
    validate_csrf,
)

from panel.scheduler import (  # noqa: E402
    add_task,
    delete_task,
    format_last_run,
    get_task,
    load_tasks,
    mark_task_run,
    parse_cron_fields,
    tasks_due_now,
    update_task,
    validate_cron,
)

load_dotenv()

_PANEL_STARTED_AT = time.time()
_scheduler_task: asyncio.Task | None = None
_monitor_task: asyncio.Task | None = None
_telemetry_task: asyncio.Task | None = None
_status_bus_task: asyncio.Task | None = None
_console_tail_task: asyncio.Task | None = None

CONFIG_EXTENSIONS = {".ini", ".sh", ".bat", ".cfg", ".txt", ".lua", ".json"}

SERVER_INI_NAMES = frozenset(
    {
        "MEATBALLS.ini",
        "MEATBALLS_SandboxVars.lua",
        "MEATBALLS_spawnregions.lua",
        "world.ini",
        "world_SandboxVars.lua",
        "world_spawnregions.lua",
        "world_spawnpoints.lua",
        "options.ini",
        "ServerOptions.ini",
        "servertest.ini",
    }
)
STARTUP_NAMES = frozenset({"start-server.sh", "start-server.bat"})
FTP_SKIP_DIRS = frozenset(
    {
        "java",
        "media",
        "backup",
        "steamapps",
        "workshop",
        "libs",
        "natives",
        "jre",
        "linux64",
        "win64",
        "macos",
        "logs",
        "cache",
        ".git",
    }
)
CONFIG_SCAN_MAX_DEPTH = 5
CONFIG_INDEX_TTL = 120

_config_index: dict[str, str] = {}
_config_index_cached_at: float = 0.0


class SaveConfigBody(BaseModel):
    filename: str
    content: str = Field(..., max_length=5_000_000)


class RconBody(BaseModel):
    command: str = Field(..., max_length=4000)


class SchedulerTaskBody(BaseModel):
    name: str = Field(..., max_length=200)
    cron: str = Field(..., max_length=80)
    command: str = Field(..., max_length=4000)
    preset: str = Field(default="custom", max_length=40)
    enabled: bool = True


class SchedulerPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    cron: str | None = Field(default=None, max_length=80)
    command: str | None = Field(default=None, max_length=4000)
    preset: str | None = Field(default=None, max_length=40)
    enabled: bool | None = None


class CatalogAddBody(BaseModel):
    kind: str = Field(default="mod", max_length=20)
    id: str = Field(..., max_length=120)
    workshop_id: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, max_length=200)
    source: str = Field(default="workshop", max_length=20)
    notes: str = Field(default="", max_length=500)
    download: bool = False


class CatalogScaffoldBody(BaseModel):
    id: str = Field(..., max_length=80)
    name: str | None = Field(default=None, max_length=200)
    kind: str = Field(default="mod", max_length=20)


class CatalogPatchBody(BaseModel):
    enabled: bool


class MirrorPullBody(BaseModel):
    remote: str = Field(default="/ServerWorld", max_length=200)
    mode: str = Field(default="incremental", max_length=20)


class PrefsBody(BaseModel):
    host_panel_wins: bool | None = None


class MirrorResumeBody(BaseModel):
    retry_corrupt: bool = True


class FounderBody(BaseModel):
    name: str = Field(..., max_length=24)
    steamid: str = Field(default="", max_length=20)
    note: str = Field(default="", max_length=200)


class AddUserBody(BaseModel):
    name: str = Field(..., max_length=24)
    password: str = Field(default="", max_length=24)


class LaunchAnnounceBody(BaseModel):
    message: str = Field(..., max_length=280)
    discord: bool = False


class InviteBody(BaseModel):
    include_password: bool = False


class SlotsBody(BaseModel):
    count: int = Field(default=0, ge=0, le=5)
    x: int = 0
    y: int = 0
    z: int = 0
    prefix: str = Field(default="Dummy", max_length=16)
    push_ftp: bool = True
    upload_mod: bool = False


class UnbanBody(BaseModel):
    steamid: str = Field(default="", max_length=20)
    name: str = Field(default="", max_length=24)


class ServerUpsertBody(BaseModel):
    id: str | None = Field(default=None, max_length=40)
    name: str = Field(..., max_length=80)
    hoster: str = Field(default="vps", max_length=20)
    game_version: str = Field(default="", max_length=20)
    rcon: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Any] = Field(default_factory=dict)
    public: dict[str, Any] = Field(default_factory=dict)
    process: dict[str, Any] = Field(default_factory=dict)
    plugins: dict[str, Any] = Field(default_factory=dict)
    authority: str = Field(default="host_wins", max_length=20)
    secrets: dict[str, str] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    draft: bool = False
    confirm_password: str | None = Field(default=None, max_length=200)
    confirm_totp: str | None = Field(default=None, max_length=12)


class ServerProbeRconBody(BaseModel):
    host: str = Field(..., max_length=200)
    port: int = 16284
    password: str = Field(default="", max_length=200)
    timeout: float = 8


class ServerProbeFilesBody(BaseModel):
    kind: str = Field(default="ftp", max_length=10)
    host: str = Field(default="", max_length=200)
    port: int = 21
    user: str = Field(default="", max_length=120)
    password: str = Field(default="", max_length=200)
    root: str = Field(default="/ServerWorld", max_length=300)
    tls: bool = False
    sftp_key_path: str = Field(default="", max_length=500)
    sftp_private_key: str = Field(default="", max_length=16000)
    sftp_key_passphrase: str = Field(default="", max_length=200)


class ServerProbeQueryBody(BaseModel):
    host: str = Field(..., max_length=200)
    port: int = 16261


class ServerProbeAllBody(BaseModel):
    rcon: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Any] = Field(default_factory=dict)
    public: dict[str, Any] = Field(default_factory=dict)
    process: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class WipeBody(BaseModel):
    x: int | None = None
    y: int | None = None
    cell_x: int | None = None
    cell_y: int | None = None
    confirm: str = Field(default="", max_length=40)
    apply: bool = False


def _ftp_error_message(exc: BaseException) -> str:
    if isinstance(exc, error_perm):
        return f"FTP permission error (550): {exc}"
    if isinstance(exc, error_temp):
        return f"FTP temporary error (4xx): {exc}"
    if isinstance(exc, error_proto):
        return f"FTP protocol error: {exc}"
    if isinstance(exc, error_reply):
        return f"FTP unexpected reply: {exc}"
    if isinstance(exc, TimeoutError):
        return "FTP connection timed out"
    if isinstance(exc, ConnectionError):
        return f"FTP connection failed: {exc}"
    return str(exc) or exc.__class__.__name__


def _rcon_error_message(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "RCON connection timed out"
    if isinstance(exc, ConnectionError):
        return f"RCON connection failed: {exc}"
    if isinstance(exc, ValueError):
        return str(exc)
    return str(exc) or exc.__class__.__name__


async def _scheduler_loop() -> None:
    while True:
        try:
            now = datetime.now()
            for task in tasks_due_now(now):
                try:
                    output = await asyncio.to_thread(rcon_execute, task["command"])
                    mark_task_run(task["id"], f"ok: {(output or '')[:120]}")
                except Exception as exc:
                    mark_task_run(task["id"], f"error: {_rcon_error_message(exc)}")
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(30)


async def _workshop_monitor_loop() -> None:
    while True:
        try:
            from panel.services import workshop_monitor as mon_svc

            snap = mon_svc.monitor_snapshot()
            if snap.get("auto_restart"):
                result = await asyncio.to_thread(mon_svc.check_updates)
                if int(result.get("updates_available") or 0) > 0 and not mon_svc.restart_status().get("running"):
                    await asyncio.to_thread(
                        mon_svc.start_graceful_restart,
                        3,
                        "Внимание: вышло обновление мода в Steam! Рестарт через 3 минуты.",
                    )
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(1800)


async def _telemetry_loop() -> None:
    from panel.services import telemetry as telemetry_svc

    while True:
        try:
            stats = await asyncio.to_thread(telemetry_svc.collect_stats)
            await event_bus.publish("telemetry", stats)
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(2.5)


async def _status_bus_loop() -> None:
    while True:
        try:
            if await event_bus.has_subscribers("status"):
                payload = await server_status()
                await event_bus.publish("status", payload)
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(10)


async def _console_tail_loop() -> None:
    last_hash = ""
    while True:
        try:
            if await event_bus.has_subscribers("console_tail"):
                data = await asyncio.to_thread(logs_tail_kind, "console", 200)
                content = str(data.get("content") or "")
                digest = str(hash(content))
                if digest != last_hash:
                    last_hash = digest
                    await event_bus.publish("console_tail", data)
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(12)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task, _monitor_task, _telemetry_task, _status_bus_task, _console_tail_task
    event_bus.bind_loop(asyncio.get_running_loop())
    try:
        ensure_state_dirs()
        ensure_migrated()
    except Exception:
        traceback.print_exc()
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    _monitor_task = asyncio.create_task(_workshop_monitor_loop())
    _telemetry_task = asyncio.create_task(_telemetry_loop())
    _status_bus_task = asyncio.create_task(_status_bus_loop())
    _console_tail_task = asyncio.create_task(_console_tail_loop())
    yield
    for task in (_scheduler_task, _monitor_task, _telemetry_task, _status_bus_task, _console_tail_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _scheduler_task = None
    _monitor_task = None
    _telemetry_task = None
    _status_bus_task = None
    _console_tail_task = None


_PUBLIC = is_public_deployment()
app = FastAPI(
    title="MEATBALLS PZ Control Panel",
    version=PANEL_VERSION,
    lifespan=lifespan,
    docs_url=None if _PUBLIC else "/docs",
    redoc_url=None if _PUBLIC else "/redoc",
    openapi_url=None if _PUBLIC else "/openapi.json",
)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(auth_router)
app.include_router(workshop_router)
app.include_router(admintools_router)
app.include_router(telemetry_router)
app.include_router(provision_router)
app.include_router(updates_router)
app.include_router(safehouses_router)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        try:
            validate_csrf(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if path.startswith("/api/") and not is_public_api_path(path) and not auth_disabled():
        if needs_setup():
            return JSONResponse(status_code=401, content={"detail": "Admin setup required"})
        try:
            request.state.user = authenticate_request(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        user = request.state.user
        if user.get("role") == "moderator" and moderator_write_forbidden(request.method, path):
            return JSONResponse(status_code=403, content={"detail": "Insufficient permissions"})
        if path_needs_step_up(request.method, path):
            try:
                verify_step_up(request, user)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


def _active_files_kind() -> str:
    try:
        return str((active_profile().get("files") or {}).get("kind") or "ftp")
    except Exception:
        return "ftp"


def _invalidate_config_index() -> None:
    global _config_index, _config_index_cached_at
    _config_index = {}
    _config_index_cached_at = 0.0


def _files_client():
    try:
        return active_files_client()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        return client_from_env()


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text_file(path: Path, content: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "bytes": path.stat().st_size, "local": True}


def _backup_local(filename: str, content: str) -> Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe = filename.replace("/", "_").replace("\\", "_")
    path = BACKUPS / f"{stamp}_{safe}"
    path.write_text(content, encoding="utf-8")
    return path


def _is_config_candidate(name: str) -> bool:
    if name in SERVER_INI_NAMES or name in STARTUP_NAMES:
        return True
    ext = Path(name).suffix.lower()
    return ext in CONFIG_EXTENSIONS


def _walk_config_files(client, ftp, remote_path: str, index: dict[str, str], depth: int = 0) -> None:
    if depth > CONFIG_SCAN_MAX_DEPTH:
        return
    try:
        entries = client.list_dir(ftp, remote_path)
    except Exception:
        return
    for entry in entries:
        if entry.type == "file":
            if _is_config_candidate(entry.name) and entry.name not in index:
                index[entry.name] = entry.path
            continue
        if entry.type != "dir":
            continue
        if entry.name.lower() in FTP_SKIP_DIRS:
            continue
        _walk_config_files(client, ftp, entry.path, index, depth + 1)


def _walk_local_config_files(root: Path, index: dict[str, str], depth: int = 0) -> None:
    if depth > CONFIG_SCAN_MAX_DEPTH or not root.is_dir():
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for path in entries:
        if path.is_dir():
            if path.name.lower() in FTP_SKIP_DIRS:
                continue
            _walk_local_config_files(path, index, depth + 1)
            continue
        if _is_config_candidate(path.name) and path.name not in index:
            index[path.name] = str(path)


def _refresh_config_index(*, force: bool = False) -> dict[str, str]:
    global _config_index, _config_index_cached_at
    now = time.time()
    if not force and _config_index and now - _config_index_cached_at < CONFIG_INDEX_TTL:
        return _config_index

    kind = _active_files_kind()
    index: dict[str, str] = {}
    if kind == "local":
        try:
            root = Path(str((active_profile().get("files") or {}).get("root") or ""))
        except Exception:
            root = Path()
        _walk_local_config_files(root, index)
    elif kind in ("ftp", "sftp"):
        client = _files_client()
        with client.connect() as handle:
            _walk_config_files(client, handle, "/", index)
    _config_index = index
    _config_index_cached_at = now
    return index


def _group_for_file(filename: str) -> str:
    if filename in SERVER_INI_NAMES:
        return "server_ini"
    if filename in STARTUP_NAMES:
        return "startup"
    if filename.lower().endswith(".lua"):
        return "mod_lua"
    if filename.lower().endswith((".sh", ".bat")):
        return "startup"
    return "other"


def _group_label(group_id: str) -> str:
    return {
        "server_ini": "Server INI / Lua",
        "startup": "Startup Scripts",
        "mod_lua": "Mod / Faction Lua",
        "other": "Other Configs",
    }.get(group_id, "Other")


def _editor_language(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".lua"):
        return "lua"
    if lower.endswith(".ini"):
        return "ini"
    if lower.endswith((".sh", ".bat")):
        return "shell"
    if lower.endswith(".json"):
        return "json"
    return "plaintext"


def _resolve_remote_path(filename: str) -> str:
    if not _config_index:
        _refresh_config_index()
    path = _config_index.get(filename)
    if not path:
        raise HTTPException(status_code=404, detail=f"Config not found on FTP: {filename}")
    return path


def _resolve_server_log_path() -> str:
    if not _config_index:
        _refresh_config_index()
    for name in SERVER_LOG_CANDIDATES:
        if name in _config_index:
            return _config_index[name]
    for name, path in _config_index.items():
        if name.endswith("server-console.txt"):
            return path
    raise HTTPException(status_code=404, detail="server-console.txt not found on FTP")


def parse_players_list(output: str) -> list[dict[str, str]]:
    if not output or output.strip() in {"(no output)", "(empty)"}:
        return []
    players: list[dict[str, str]] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("players connected") or lower.startswith("players online"):
            continue
        if lower in {"players", "(no players)"}:
            continue

        # B42 RCON prefixes player lines with "-" (list marker, not admin).
        if line.startswith("-"):
            line = line[1:].strip()

        line = line.lstrip("•*").strip()
        if not line:
            continue

        steamid = ""
        name = line
        m = re.match(r"^(.+?)\s*\((\d{15,20})\)\s*$", line)
        if m:
            name, steamid = m.group(1).strip(), m.group(2)
        else:
            m = re.match(r"^(.+?)\s*[-–—]\s*(\d{15,20})\s*$", line)
            if m:
                name, steamid = m.group(1).strip(), m.group(2)
            else:
                m = re.search(r"(\d{15,20})", line)
                if m:
                    steamid = m.group(1)
                    name = line.replace(steamid, "").strip(" -–—()[]")

        name = name.strip().strip('"').strip("'")
        if name and not name.isdigit():
            players.append(
                {
                    "name": name,
                    "steamid": steamid,
                    "id": steamid,
                }
            )
    return players


def parse_players_count(output: str) -> int:
    if not output or output.strip() == "(no output)":
        return 0
    match = re.search(r"\((\d+)\)", output)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s+players?", output, re.I)
    if match:
        return int(match.group(1))
    return len(parse_players_list(output))


def _network_meta() -> dict[str, Any]:
    try:
        profile = active_profile()
        rcon = profile.get("rcon") or {}
        files = profile.get("files") or {}
        pub = profile.get("public") or {}
        ftp_host = str(files.get("host") or "")
        files_kind = str(files.get("kind") or "ftp")
        if files_kind == "sftp":
            ftp_port = int(files.get("port") or files.get("sftp_port") or 22)
        else:
            ftp_port = int(files.get("port") or 21)
        rcon_host = str(rcon.get("host") or ftp_host)
        rcon_port = int(rcon.get("port") or 16284)
        query_port = int(pub.get("query_port") or 16281)
        game_port = int(pub.get("game_port") or 16282)
        max_players = int(pub.get("max_players") or 32)
        from panel.servers import load_secrets

        rcon_ok = bool(load_secrets(profile["id"]).get("rcon_password"))
        server_id = profile["id"]
        server_name = profile.get("name")
        process_kind = str((profile.get("process") or {}).get("kind") or "none")
        caps = effective_capabilities(profile)
        plugins = effective_plugins(profile)
        profile_for_views = profile
    except Exception:
        rcon = RconConfig.from_env()
        ftp_host = os.environ.get("FTP_HOST", "")
        ftp_port = int(os.environ.get("FTP_PORT", "21") or "21")
        rcon_host = rcon.host
        rcon_port = rcon.port
        query_port = int(os.environ.get("QUERY_PORT", "16281") or "16281")
        game_port = int(os.environ.get("GAME_PORT", "16282") or "16282")
        max_players = int(os.environ.get("MAX_PLAYERS", "32") or "32")
        rcon_ok = bool(rcon.password)
        server_id = None
        server_name = None
        files_kind = "ftp"
        process_kind = "none"
        caps = active_capabilities()
        plugins = {"meatballs": False}
        profile_for_views = None
    return {
        "ftp_host": ftp_host,
        "ftp_port": ftp_port,
        "rcon_host": rcon_host,
        "rcon_port": rcon_port,
        "query_port": query_port,
        "game_port": game_port,
        "max_players": max_players,
        "rcon_configured": rcon_ok,
        "server_id": server_id,
        "server_name": server_name,
        "files_kind": files_kind,
        "process_kind": process_kind,
        "plugins": plugins,
        "capabilities": caps,
        "views": views_state(caps, profile_for_views),
        "header": {
            "server_ip": rcon_host or ftp_host,
            "rcon_endpoint": f"{rcon_host}:{rcon_port}",
            "rcon_port": rcon_port,
            "query_port": query_port,
            "game_port": game_port,
            "ftp_port": ftp_port,
            "max_players": max_players,
            "server_name": server_name,
        },
    }


def _active_server_id() -> str:
    sid = _network_meta().get("server_id")
    return str(sid) if sid else "default"


async def _tcp_probe(host: str, port: int, timeout: float = 4.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        latency = round((time.perf_counter() - started) * 1000)
        return {"host": host, "port": port, "protocol": "tcp", "reachable": True, "latency_ms": latency}
    except Exception as exc:
        return {
            "host": host,
            "port": port,
            "protocol": "tcp",
            "reachable": False,
            "latency_ms": None,
            "error": exc.__class__.__name__,
            "detail": str(exc) or exc.__class__.__name__,
        }


def _udp_steam_query_probe(host: str, port: int, timeout: float = 3.0) -> dict[str, Any]:
    """Steam A2S query — Query port on PZ is UDP-only."""
    started = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(b"\xff\xff\xff\xffTSource Engine Query\x00", (host, port))
        data, _ = sock.recvfrom(4096)
        latency = round((time.perf_counter() - started) * 1000)
        return {
            "host": host,
            "port": port,
            "protocol": "udp",
            "reachable": True,
            "latency_ms": latency,
            "response_bytes": len(data),
        }
    except Exception as exc:
        return {
            "host": host,
            "port": port,
            "protocol": "udp",
            "reachable": False,
            "latency_ms": None,
            "error": exc.__class__.__name__,
            "detail": str(exc) or exc.__class__.__name__,
        }
    finally:
        sock.close()


async def _udp_probe(host: str, port: int, timeout: float = 3.0) -> dict[str, Any]:
    return await asyncio.to_thread(_udp_steam_query_probe, host, port, timeout)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    """Public health: minimal on internet-facing hosts unless authenticated."""
    base = {
        "ok": True,
        "version": app.version,
        "uptime_seconds": int(time.time() - _PANEL_STARTED_AT),
    }
    public = is_public_deployment()
    if public:
        if auth_disabled():
            # Misconfiguration on a public bind — never leak network meta
            return base
        try:
            authenticate_request(request)
        except HTTPException:
            return base
        return {**base, **_network_meta()}
    if auth_disabled():
        return {**base, **_network_meta()}
    try:
        authenticate_request(request)
        return {**base, **_network_meta()}
    except HTTPException:
        return base


def _step_up_from_body(request: Request, user: dict[str, Any], body: ServerUpsertBody) -> None:
    request.state.confirm_password = body.confirm_password
    request.state.confirm_totp = body.confirm_totp
    if auth_disabled() or user.get("local"):
        return
    verify_step_up(request, user)


def _upsert_payload(body: ServerUpsertBody) -> dict[str, Any]:
    payload = body.model_dump()
    payload.pop("confirm_password", None)
    payload.pop("confirm_totp", None)
    return payload


@app.get("/api/servers")
async def api_servers_list() -> dict[str, Any]:
    try:
        return list_servers()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"servers list: {exc}") from exc


@app.post("/api/servers")
async def api_servers_create(
    request: Request,
    body: ServerUpsertBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    _step_up_from_body(request, _user, body)
    try:
        return upsert_server(_upsert_payload(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/servers/{server_id}")
async def api_servers_patch(
    request: Request,
    server_id: str,
    body: ServerUpsertBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    _step_up_from_body(request, _user, body)
    try:
        return upsert_server(_upsert_payload(body), server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Server not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/servers/{server_id}")
async def api_servers_delete(
    server_id: str,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    try:
        data = delete_server(server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Server not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_config_index()
    return data


@app.post("/api/servers/{server_id}/activate")
async def api_servers_activate(
    server_id: str,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    try:
        profile = activate_server(server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Server not found") from exc
    _invalidate_config_index()
    return profile


@app.post("/api/servers/probe/rcon")
async def api_servers_probe_rcon(body: ServerProbeRconBody) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(probe_rcon, body.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc


@app.post("/api/servers/probe/files")
async def api_servers_probe_files(body: ServerProbeFilesBody) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(probe_files, body.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc


@app.post("/api/servers/probe/query")
async def api_servers_probe_query(body: ServerProbeQueryBody) -> dict[str, Any]:
    return await asyncio.to_thread(probe_query, body.host, body.port)


@app.post("/api/servers/probe/all")
async def api_servers_probe_all(body: ServerProbeAllBody) -> dict[str, Any]:
    return await asyncio.to_thread(evaluate_draft_capabilities, body.model_dump())


@app.get("/api/onboarding")
async def api_onboarding() -> dict[str, Any]:
    return onboarding_state()


@app.post("/api/panel/snapshot")
async def api_panel_snapshot() -> dict[str, Any]:
    """Write a full text dump of panel/ (paths + source) into panel/backups/."""
    return await asyncio.to_thread(write_panel_snapshot, panel_version=app.version)


@app.get("/api/panel/snapshot/file")
async def api_panel_snapshot_file(name: str) -> FileResponse:
    try:
        path = resolve_snapshot_file(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="text/plain; charset=utf-8",
        filename=path.name,
    )


@app.get("/api/smoke/status")
async def api_smoke_status() -> dict[str, Any]:
    return await asyncio.to_thread(smoke_status)


@app.post("/api/smoke/start")
async def api_smoke_start() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(smoke_start)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/smoke/stop")
async def api_smoke_stop() -> dict[str, Any]:
    return await asyncio.to_thread(smoke_stop)


@app.get("/api/status")
async def server_status() -> dict[str, Any]:
    try:
        meta = _network_meta()
    except Exception:
        meta = {
            "max_players": 32,
            "rcon_host": "",
            "rcon_port": 16284,
            "query_port": 16281,
            "game_port": 16282,
        }
    online = False
    players_count = 0
    players_raw = ""
    players_list: list[dict[str, str]] = []
    error = None
    try:
        players_raw = await asyncio.to_thread(rcon_execute, "players")
        online = True
        players_list = filter_real_players(parse_players_list(players_raw))
        players_list = player_access_svc.enrich_players(players_list, _active_server_id())
        players_count = len(players_list)
        mark_joined(players_list)
    except Exception as exc:
        error = _rcon_error_message(exc)

    from panel.services.server_uptime import resolve_uptime

    try:
        uptime = await asyncio.to_thread(
            resolve_uptime,
            _active_server_id(),
            rcon_online=online,
        )
    except Exception:
        uptime = {"seconds": None, "source": "unavailable"}
    server_secs = uptime.get("seconds")
    try:
        founders = load_roster()["founders"]
    except Exception:
        founders = []
    try:
        slots = slots_snapshot()
    except Exception:
        slots = {"count": 0, "npcs": []}
    return {
        "rcon_online": online,
        "players_online": players_count,
        "players": players_list,
        "players_raw": players_raw,
        "founders": founders,
        "dummy_slots": slots.get("count") or 0,
        "npcs": slots.get("npcs") or [],
        "max_players": meta["max_players"],
        "rcon_host": meta["rcon_host"],
        "rcon_port": meta["rcon_port"],
        "query_port": meta["query_port"],
        "game_port": meta["game_port"],
        "panel_uptime_seconds": int(time.time() - _PANEL_STARTED_AT),
        "server_uptime_seconds": server_secs,
        "uptime_seconds": server_secs if server_secs is not None else None,
        "uptime_source": uptime.get("source"),
        "error": error,
    }


@app.get("/api/network")
async def network_diagnostics() -> dict[str, Any]:
    """Probe only ports with a real health signal.

    - RCON: TCP + authenticated command
    - Query (DefaultPort): UDP Steam A2S
    - FTP: TCP + listing
    - Game (UDPPort): no public probe — omitted from services (config only)
    """
    meta = _network_meta()
    host = meta["rcon_host"] or meta["ftp_host"]
    rcon_probe, query_probe, ftp_probe = await asyncio.gather(
        _tcp_probe(host, meta["rcon_port"]),
        _udp_probe(host, meta["query_port"]),
        _tcp_probe(meta["ftp_host"], meta["ftp_port"]),
    )
    services = {
        "rcon": rcon_probe,
        "query": query_probe,
        "ftp": ftp_probe,
    }

    rcon_online = False
    rcon_error = None
    try:
        await asyncio.to_thread(rcon_execute, "players")
        rcon_online = True
    except Exception as exc:
        rcon_error = _rcon_error_message(exc)

    ftp_ok = False
    ftp_error = None
    try:
        await asyncio.to_thread(_refresh_config_index)
        ftp_ok = True
    except Exception as exc:
        ftp_error = _ftp_error_message(exc)

    return {
        **meta,
        "services": services,
        "rcon_online": rcon_online,
        "rcon_error": rcon_error,
        "ftp_ok": ftp_ok,
        "ftp_error": ftp_error,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "unmonitored": {
            "game_port": meta["game_port"],
            "reason": "UDPPort has no public healthcheck (PZ game traffic only)",
        },
        "notes": {
            "query": "Steam browser query uses UDP A2S",
            "game": "Not monitored — no reliable remote probe for UDPPort",
        },
    }


@app.get("/api/logs/server")
async def server_log(lines: int = 400) -> dict[str, Any]:
    lines = max(50, min(lines, 5000))
    try:
        remote_path = _resolve_server_log_path()
        client = _files_client()
        content = await asyncio.to_thread(client.read_file, remote_path)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        all_lines = content.splitlines()
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {
            "filename": Path(remote_path).name,
            "remote_path": remote_path,
            "total_lines": len(all_lines),
            "lines": lines,
            "content": "\n".join(tail),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc


@app.get("/api/logs")
async def api_logs_catalog() -> dict[str, Any]:
    return logs_catalog()


@app.get("/api/logs/tail")
async def api_logs_tail(kind: str = "console", lines: int = 400) -> dict[str, Any]:
    try:
        return logs_tail_kind(kind, lines)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/chat")
async def api_chat(channel: str = "all", limit: int = 200) -> dict[str, Any]:
    return chat_snapshot(channel, limit)


@app.get("/api/bans")
async def api_bans() -> dict[str, Any]:
    return bans_snapshot()


@app.post("/api/bans/unban")
async def api_bans_unban(body: UnbanBody) -> dict[str, Any]:
    try:
        command = unban_command(body.steamid, body.name)
        output = await asyncio.to_thread(rcon_execute, command)
        return {"ok": True, "command": command, "output": output, "bans": bans_snapshot()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc


@app.post("/api/wipe/preview")
async def api_wipe_preview(
    body: WipeBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    try:
        return wipe_preview(body.x, body.y, body.cell_x, body.cell_y)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/wipe/apply")
async def api_wipe_apply(
    body: WipeBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    if not body.apply:
        raise HTTPException(status_code=400, detail="apply=true required")
    try:
        return await asyncio.to_thread(
            wipe_apply,
            confirm=body.confirm,
            x=body.x,
            y=body.y,
            cell_x=body.cell_x,
            cell_y=body.cell_y,
            delete_remote=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/scheduler/tasks")
async def scheduler_list() -> dict[str, Any]:
    tasks = load_tasks()
    enriched = []
    for t in tasks:
        enriched.append(
            {
                **t,
                "cron_fields": parse_cron_fields(t["cron"]),
                "last_run_label": format_last_run(t.get("last_run")),
            }
        )
    return {"tasks": enriched, "count": len(enriched)}


@app.post("/api/scheduler/tasks")
async def scheduler_create(body: SchedulerTaskBody) -> dict[str, Any]:
    if not validate_cron(body.cron):
        raise HTTPException(status_code=400, detail="Invalid cron format (use: min hour day month weekday)")
    task = add_task(body.model_dump())
    return {"task": {**task, "cron_fields": parse_cron_fields(task["cron"]), "last_run_label": "Никогда"}}


@app.patch("/api/scheduler/tasks/{task_id}")
async def scheduler_patch(task_id: str, body: SchedulerPatchBody) -> dict[str, Any]:
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if "cron" in payload and not validate_cron(payload["cron"]):
        raise HTTPException(status_code=400, detail="Invalid cron format")
    try:
        task = update_task(task_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return {"task": {**task, "cron_fields": parse_cron_fields(task["cron"]), "last_run_label": format_last_run(task.get("last_run"))}}


@app.delete("/api/scheduler/tasks/{task_id}")
async def scheduler_delete(task_id: str) -> dict[str, bool]:
    if not get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    delete_task(task_id)
    return {"ok": True}


@app.post("/api/scheduler/tasks/{task_id}/run")
async def scheduler_run_now(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        output = await asyncio.to_thread(rcon_execute, task["command"])
        mark_task_run(task_id, f"manual ok: {(output or '')[:120]}")
        return {"ok": True, "command": task["command"], "output": output}
    except Exception as exc:
        mark_task_run(task_id, f"manual error: {_rcon_error_message(exc)}")
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc


@app.get("/api/mods/catalog")
async def mods_catalog() -> dict[str, Any]:
    data = catalog_snapshot()
    live_mods: list[str] = []
    live_workshop: list[str] = []
    try:
        index = await asyncio.to_thread(_refresh_config_index)
        ini_name = data.get("catalog", {}).get("ini_filename") or "world.ini"
        if ini_name in index:
            client = _files_client()
            content = await asyncio.to_thread(client.read_file, index[ini_name])
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            live_mods = parse_ini_list(content, "Mods")
            live_workshop = parse_ini_list(content, "WorkshopItems")
    except Exception:
        pass
    data["live"] = {"mods": live_mods, "workshop_ids": live_workshop, "ini": data.get("catalog", {}).get("ini_filename")}
    return data


@app.post("/api/mods/catalog")
async def mods_catalog_add(body: CatalogAddBody) -> dict[str, Any]:
    try:
        if body.download and body.workshop_id:
            item = await asyncio.to_thread(download_workshop, body.workshop_id)
            if body.kind == "library":
                item = add_item(
                    kind="library",
                    mod_id=item.get("id", body.id),
                    workshop_id=body.workshop_id,
                    name=body.name or item.get("name"),
                    source="workshop",
                    notes=body.notes,
                )
            return {"item": item}
        item = add_item(
            kind=body.kind,
            mod_id=body.id,
            workshop_id=body.workshop_id,
            name=body.name,
            source=body.source,
            notes=body.notes,
        )
        return {"item": item}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mods/scaffold")
async def mods_scaffold(body: CatalogScaffoldBody) -> dict[str, Any]:
    try:
        item = scaffold_local(body.id, body.name, body.kind)
        return {"item": item}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/mods/catalog/{mod_id}")
async def mods_catalog_delete(mod_id: str) -> dict[str, bool]:
    ok = remove_item(mod_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mod not in catalog")
    return {"ok": True}


@app.patch("/api/mods/catalog/{mod_id}")
async def mods_catalog_patch(mod_id: str, body: CatalogPatchBody) -> dict[str, Any]:
    try:
        item = await asyncio.to_thread(set_item_enabled, mod_id, body.enabled)
        return {"item": item}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mod not in catalog") from exc


@app.post("/api/mods/import-ini")
async def mods_import_ini() -> dict[str, Any]:
    data = catalog_snapshot()
    live_mods: list[str] = []
    live_workshop: list[str] = []
    ini_name = data.get("catalog", {}).get("ini_filename") or "world.ini"
    try:
        index = await asyncio.to_thread(_refresh_config_index)
        if ini_name not in index:
            raise HTTPException(status_code=404, detail=f"{ini_name} not in file index")
        client = _files_client()
        content = await asyncio.to_thread(client.read_file, index[ini_name])
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        live_mods = parse_ini_list(content, "Mods")
        live_workshop = parse_ini_list(content, "WorkshopItems")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not live_mods and not live_workshop:
        raise HTTPException(status_code=400, detail="world.ini has no Mods= or WorkshopItems=")
    result = await asyncio.to_thread(import_from_lists, live_mods, live_workshop)
    result["live_mods"] = len(live_mods)
    result["live_workshop"] = len(live_workshop)
    result["ini"] = ini_name
    return result


@app.post("/api/mods/apply-ini")
async def mods_apply_ini() -> dict[str, Any]:
    loadout = catalog_loadout()
    catalog = catalog_snapshot()["catalog"]
    ini_name = catalog.get("ini_filename") or "world.ini"
    try:
        remote_path = _resolve_remote_path(ini_name)
        client = _files_client()
        previous = await asyncio.to_thread(client.read_file, remote_path)
        if isinstance(previous, bytes):
            previous = previous.decode("utf-8", errors="replace")
        updated = apply_lists_to_ini(previous, loadout["mods"], loadout["workshop_ids"])
        clash = host_conflict(ini_name, previous, updated)
        if clash:
            remember_remote(ini_name, remote_path, previous)
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "host_panel_wins",
                    "message": "world.ini на хосте изменился (XLGAMES). Apply отменён.",
                    "filename": ini_name,
                    "remote_content": clash["remote_content"],
                },
            )
        backup_path = await asyncio.to_thread(_backup_local, ini_name, previous)
        temp = BACKUPS / f".upload_{ini_name}"
        temp.write_text(updated, encoding="utf-8")
        try:
            result = await asyncio.to_thread(client.upload_file, temp, remote_path)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Повреждённый upload — файл не принят. Перезагрузите: {exc}",
            ) from exc
        finally:
            temp.unlink(missing_ok=True)
        remember_remote(ini_name, remote_path, updated)
        return {
            "ok": True,
            "filename": ini_name,
            "backup": str(backup_path.relative_to(ROOT)),
            "mods": loadout["mods"],
            "workshop_ids": loadout["workshop_ids"],
            "upload": result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc


@app.get("/api/mirror/status")
async def api_mirror_status() -> dict[str, Any]:
    return mirror_status()


@app.post("/api/mirror/pull")
async def api_mirror_pull(body: MirrorPullBody | None = None) -> dict[str, Any]:
    remote = (body.remote if body else "") or mirror_default_remote()
    current = mirror_status()
    if current.get("pulling"):
        return {**current, "ok": True, "message": "Pull already running"}

    mode = (body.mode if body else "incremental") or "incremental"

    async def _run() -> None:
        try:
            await asyncio.to_thread(mirror_pull, remote, mode)
        except Exception:
            traceback.print_exc()

    asyncio.create_task(_run())
    return {**mirror_status(), "ok": True, "message": "Pull started"}


@app.post("/api/mirror/verify")
async def api_mirror_verify() -> dict[str, Any]:
    current = mirror_status()
    if current.get("pulling"):
        return {**current, "ok": True, "message": "Pull already running"}

    async def _run() -> None:
        try:
            await asyncio.to_thread(mirror_verify)
        except Exception:
            traceback.print_exc()

    asyncio.create_task(_run())
    return {**mirror_status(), "ok": True, "message": "Verify started"}


@app.get("/api/prefs")
async def api_prefs_get() -> dict[str, Any]:
    return load_prefs()


@app.post("/api/prefs")
async def api_prefs_set(body: PrefsBody) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if body.host_panel_wins is not None:
        payload["host_panel_wins"] = body.host_panel_wins
    return save_prefs(payload)


@app.post("/api/mirror/resume")
async def api_mirror_resume(body: MirrorResumeBody | None = None) -> dict[str, Any]:
    current = mirror_status()
    if current.get("pulling"):
        return {**current, "ok": True, "message": "Pull already running"}
    retry = True if body is None else body.retry_corrupt

    async def _run() -> None:
        try:
            await asyncio.to_thread(mirror_resume, retry)
        except Exception:
            traceback.print_exc()

    asyncio.create_task(_run())
    return {**mirror_status(), "ok": True, "message": "Resume started"}


@app.post("/api/mirror/abort")
async def api_mirror_abort() -> dict[str, Any]:
    return await asyncio.to_thread(mirror_abort)


@app.get("/api/world/status")
async def api_world_status() -> dict[str, Any]:
    local = local_inspect()
    remote = None
    try:
        log_data = await server_log(120)
        lines = (log_data.get("content") or "").splitlines()
        remote = parse_world_status(lines, True)
        remote["source"] = log_data.get("remote_path")
        try:
            st = await server_status()
            if st.get("rcon_online") and remote.get("stage") != "failed":
                remote["stage"] = "ready"
                remote["label"] = "Мир запущен"
                remote["ready"] = True
        except Exception:
            pass
    except Exception:
        from server_mirror import MIRROR_ROOT

        console = next(MIRROR_ROOT.rglob("server-console.txt"), None) if MIRROR_ROOT.exists() else None
        if console:
            text = console.read_text(encoding="utf-8", errors="replace")
            remote = parse_world_status(text.splitlines()[-120:], True)
            remote["source"] = str(console)
    return {"local": local.get("world"), "remote": remote, "local_process": local}


@app.get("/api/local-server")
async def api_local_server() -> dict[str, Any]:
    return local_inspect()


@app.post("/api/local-server/start")
async def api_local_start() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(local_start)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local-server/stop")
async def api_local_stop() -> dict[str, Any]:
    return await asyncio.to_thread(local_stop)


@app.get("/api/rcon/players")
async def rcon_players() -> dict[str, Any]:
    try:
        raw = await asyncio.to_thread(rcon_execute, "players")
        players = filter_real_players(parse_players_list(raw))
        players = player_access_svc.enrich_players(players, _active_server_id())
        founders = mark_joined(players)
        return {
            "command": "players",
            "raw": raw,
            "players": players,
            "players_online": len(players),
            "dummy_slots": slots_snapshot()["count"],
            "founders": founders,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc


@app.get("/api/launch")
async def api_launch() -> dict[str, Any]:
    return {
        "endpoints": public_endpoints(),
        "invite": invite_text(include_password=False),
        "founders": load_roster()["founders"],
    }


@app.post("/api/launch/invite")
async def api_launch_invite(body: InviteBody | None = None) -> dict[str, Any]:
    include = bool(body and body.include_password)
    return {"text": invite_text(include_password=include), "include_password": include}


@app.post("/api/launch/founders")
async def api_launch_add_founder(body: FounderBody) -> dict[str, Any]:
    try:
        row = add_founder(body.name, body.steamid, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "founder": row, "founders": load_roster()["founders"]}


@app.delete("/api/launch/founders/{founder_id}")
async def api_launch_remove_founder(founder_id: str) -> dict[str, Any]:
    if not remove_founder(founder_id):
        raise HTTPException(status_code=404, detail="Founder not found")
    return {"ok": True, "founders": load_roster()["founders"]}


@app.post("/api/launch/adduser")
async def api_launch_adduser(body: AddUserBody) -> dict[str, Any]:
    try:
        command, password = adduser_command(body.name, body.password or None)
        output = await asyncio.to_thread(rcon_execute, command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc
    mark_account_created(body.name)
    return {
        "ok": True,
        "command": command,
        "password": password,
        "output": output,
        "founders": load_roster()["founders"],
    }


@app.post("/api/launch/announce")
async def api_launch_announce(body: LaunchAnnounceBody) -> dict[str, Any]:
    try:
        command = announce_command(body.message)
        output = await asyncio.to_thread(rcon_execute, command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc
    discord = None
    if body.discord:
        try:
            discord = post_discord(body.message)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "command": command, "output": output, "discord": discord}


@app.get("/api/slots")
async def api_slots_get() -> dict[str, Any]:
    return slots_snapshot()


@app.post("/api/slots")
async def api_slots_set(body: SlotsBody) -> dict[str, Any]:
    snap = set_slots(body.count, body.x, body.y, body.z, body.prefix)
    uploaded: dict[str, Any] = {}
    if body.push_ftp:
        temp = write_temp_line(snap)
        try:
            client = _files_client()
            uploaded["slots"] = await asyncio.to_thread(client.upload_file, temp, snap["remote"])
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"slots upload rejected: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc
        finally:
            temp.unlink(missing_ok=True)
    files = 0
    if body.upload_mod:
        client = _files_client()
        try:
            for local, remote in iter_mod_files():
                await asyncio.to_thread(client.upload_file, local, remote)
                files += 1
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"mod upload rejected: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc
        uploaded["mod_files"] = files
    return {"ok": True, **snap, "uploaded": uploaded}


@app.get("/api/configs")
async def list_configs(refresh: bool = False) -> dict[str, Any]:
    try:
        index = await asyncio.to_thread(_refresh_config_index, force=refresh)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc

    items: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}

    priority_order = list(SERVER_INI_NAMES) + list(STARTUP_NAMES)

    for name in sorted(index.keys(), key=lambda n: (priority_order.index(n) if n in priority_order else 999, n.lower())):
        group_id = _group_for_file(name)
        item = {
            "filename": name,
            "remote_path": index[name],
            "group": group_id,
            "group_label": _group_label(group_id),
            "language": _editor_language(name),
            "priority": name in SERVER_INI_NAMES or name in STARTUP_NAMES,
        }
        items.append(item)
        groups.setdefault(group_id, []).append(item)

    group_list = [
        {"id": gid, "label": _group_label(gid), "files": groups[gid]}
        for gid in ("server_ini", "startup", "mod_lua", "other")
        if gid in groups
    ]

    return {"configs": items, "groups": group_list, "count": len(items)}


@app.get("/api/config/load")
async def load_config(filename: str) -> dict[str, str]:
    try:
        remote_path = _resolve_remote_path(filename)
        if _active_files_kind() == "local":
            content = await asyncio.to_thread(_read_text_file, Path(remote_path))
        else:
            client = _files_client()
            content = await asyncio.to_thread(client.read_file, remote_path)
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
        remember_remote(filename, remote_path, content)
        return {
            "filename": filename,
            "remote_path": remote_path,
            "content": content,
            "language": _editor_language(filename),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc


@app.post("/api/config/save")
async def save_config(
    body: SaveConfigBody,
    _user: dict[str, Any] = require_role("admin"),
) -> dict[str, Any]:
    try:
        remote_path = _resolve_remote_path(body.filename)
        if _active_files_kind() == "local":
            previous = await asyncio.to_thread(_read_text_file, Path(remote_path))
        else:
            client = _files_client()
            previous = await asyncio.to_thread(client.read_file, remote_path)
            if isinstance(previous, bytes):
                previous = previous.decode("utf-8", errors="replace")
        clash = host_conflict(body.filename, previous, body.content)
        if clash:
            remember_remote(body.filename, remote_path, previous)
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "host_panel_wins",
                    "message": (
                        "Файл на хосте изменился (панель XLGAMES). "
                        "Запись отменена — в редакторе актуальная версия с FTP."
                    ),
                    "filename": body.filename,
                    "remote_content": clash["remote_content"],
                    "seen_at": clash.get("seen_at"),
                },
            )
        backup_path = await asyncio.to_thread(_backup_local, body.filename, previous)
        if _active_files_kind() == "local":
            result = await asyncio.to_thread(_write_text_file, Path(remote_path), body.content)
        else:
            temp = BACKUPS / f".upload_{body.filename.replace('/', '_')}"
            temp.write_text(body.content, encoding="utf-8")
            try:
                result = await asyncio.to_thread(client.upload_file, temp, remote_path)
            except IntegrityError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"Повреждённый upload — файл не принят. Перезагрузите: {exc}",
                ) from exc
            finally:
                temp.unlink(missing_ok=True)
        remember_remote(body.filename, remote_path, body.content)
        return {
            "ok": True,
            "filename": body.filename,
            "remote_path": remote_path,
            "backup": str(backup_path.relative_to(ROOT)),
            "upload": result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_ftp_error_message(exc)) from exc


@app.post("/api/rcon/exec")
async def rcon_exec_endpoint(body: RconBody) -> dict[str, str]:
    try:
        output = await asyncio.to_thread(rcon_execute, body.command)
        player_access_svc.record_from_rcon(_active_server_id(), body.command, output)
        return {"command": body.command, "output": output}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc


@app.post("/api/rcon/graceful-restart")
async def graceful_restart() -> dict[str, Any]:
    sequence = [
        (0, 'servermsg "Server restart in 5 minutes"'),
        (180, 'servermsg "Server restart in 2 minutes"'),
        (60, 'servermsg "Server restart in 1 minute"'),
        (30, 'servermsg "Server restart in 30 seconds"'),
        (25, 'servermsg "Server restarting — saving world"'),
        (0, "save"),
        (3, "quit"),
    ]

    async def _run() -> None:
        for delay, cmd in sequence:
            if delay:
                await asyncio.sleep(delay)
            try:
                await asyncio.to_thread(rcon_execute, cmd)
            except Exception:
                pass

    asyncio.create_task(_run())
    return {"ok": True, "message": "Graceful restart sequence started (~5 min)"}


@app.post("/api/rcon/quick/{action}")
async def rcon_quick(action: str) -> dict[str, Any]:
    commands = {
        "save": "save",
        "players": "players",
        "mods": "checkModsNeedUpdate",
    }
    if action not in commands:
        raise HTTPException(status_code=404, detail="Unknown quick action")
    cmd = commands[action]
    try:
        output = await asyncio.to_thread(rcon_execute, cmd)
        result: dict[str, Any] = {"command": cmd, "output": output}
        if action == "players":
            result["players"] = filter_real_players(parse_players_list(output))
            result["players_online"] = len(result["players"])
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_rcon_error_message(exc)) from exc


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    if not auth_disabled():
        try:
            authenticate_websocket(ws)
        except HTTPException:
            await ws.close(code=4401, reason="Authentication required")
            return
    await ws.accept()
    client_id = await event_bus.connect(ws)
    try:
        await ws.send_json({"channel": "connected", "data": {"ok": True}, "ts": time.time()})
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "ping":
                await ws.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await event_bus.disconnect(client_id)


@app.websocket("/ws/console")
async def ws_console(ws: WebSocket) -> None:
    if not auth_disabled():
        try:
            authenticate_websocket(ws)
        except HTTPException:
            await ws.close(code=4401, reason="Authentication required")
            return
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = payload.get("type", "exec")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if msg_type == "exec":
                command = str(payload.get("command", "")).strip()
                if not command:
                    await ws.send_json({"type": "error", "message": "Empty command"})
                    continue
                try:
                    output = await asyncio.to_thread(rcon_execute, command)
                    await ws.send_json(
                        {"type": "result", "command": command, "output": output}
                    )
                except Exception as exc:
                    await ws.send_json({"type": "error", "message": _rcon_error_message(exc)})
                continue

            await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
