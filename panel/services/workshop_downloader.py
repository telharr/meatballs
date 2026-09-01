"""Workshop SteamCMD downloads into active server mirror for smoke/local."""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from panel.servers import active_id, active_profile, mirror_root

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
PZ_APP_ID = "108600"

_job_lock = threading.Lock()
_job: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "percent": 0,
    "message": "",
    "workshop_ids": [],
    "results": [],
    "errors": [],
    "started_at": None,
    "finished_at": None,
}


def _job_snapshot() -> dict[str, Any]:
    with _job_lock:
        return dict(_job)


def _set_job(**kwargs: Any) -> None:
    with _job_lock:
        _job.update(kwargs)
    try:
        from panel.services.event_bus import emit

        emit("pull_progress", _job_snapshot())
    except Exception:
        pass


def download_status() -> dict[str, Any]:
    return _job_snapshot()


def parse_ini_list(content: str, key: str) -> list[str]:
    match = re.search(rf"^{re.escape(key)}=(.*)$", content, re.M)
    if not match:
        return []
    return [part.strip() for part in match.group(1).split(";") if part.strip()]


def _candidate_ini_paths(server_id: str | None = None) -> list[Path]:
    profile = active_profile() if server_id is None else None
    try:
        if server_id:
            from panel.servers import load_profile

            profile = load_profile(server_id)
        assert profile is not None
    except Exception:
        return []
    files = profile.get("files") or {}
    ini_name = str(files.get("ini") or "world.ini")
    root_name = str(files.get("root") or "ServerWorld").strip("/").split("/")[-1] or "ServerWorld"
    mirror = mirror_root(profile["id"])
    candidates = [
        mirror / root_name / "Server" / ini_name,
        mirror / "Server" / ini_name,
        mirror / root_name / ini_name,
        mirror / ini_name,
    ]
    if files.get("kind") == "local" and files.get("root"):
        local = Path(str(files["root"]))
        candidates.extend(
            [
                local / "Server" / ini_name,
                local / ini_name,
            ]
        )
    # de-dupe preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for path in candidates:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def read_workshop_ids(server_id: str | None = None) -> dict[str, Any]:
    ids: list[str] = []
    mods: list[str] = []
    ini_path: str | None = None
    for path in _candidate_ini_paths(server_id):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        ids = parse_ini_list(text, "WorkshopItems")
        mods = parse_ini_list(text, "Mods")
        ini_path = str(path)
        break
    return {
        "workshop_ids": ids,
        "mods": mods,
        "ini_path": ini_path,
        "server_id": server_id or active_id(),
    }


def mirror_paths(server_id: str | None = None) -> dict[str, Path]:
    sid = server_id or active_id() or "default"
    mirror = mirror_root(sid)
    return {
        "mirror": mirror,
        "steam_install": mirror,
        "workshop_content": mirror / "steamapps" / "workshop" / "content" / PZ_APP_ID,
        "mods": mirror / "mods",
    }


def list_local_workshop_items(server_id: str | None = None) -> list[dict[str, Any]]:
    paths = mirror_paths(server_id)
    content = paths["workshop_content"]
    rows: list[dict[str, Any]] = []
    if not content.is_dir():
        return rows
    for child in sorted(content.iterdir()):
        if not child.is_dir() or not child.name.isdigit():
            continue
        mtime = child.stat().st_mtime
        mod_dirs = []
        for info in child.rglob("mod.info"):
            mod_dirs.append(info.parent.name)
        rows.append(
            {
                "workshop_id": child.name,
                "path": str(child),
                "mod_ids": mod_dirs,
                "local_mtime": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
                "local_epoch": int(mtime),
                "installed": True,
            }
        )
    return rows


def _run_download(workshop_ids: list[str], server_id: str | None, username: str | None) -> None:
    from workshop_downloader import download_batch

    paths = mirror_paths(server_id)
    paths["mirror"].mkdir(parents=True, exist_ok=True)
    paths["mods"].mkdir(parents=True, exist_ok=True)

    def on_progress(payload: dict[str, Any]) -> None:
        _set_job(
            phase=str(payload.get("phase") or "running"),
            percent=int(payload.get("percent") or _job_snapshot().get("percent") or 0),
            message=str(payload.get("message") or ""),
            current=payload.get("workshop_id"),
        )

    try:
        from panel.services.steamcmd_bootstrap import resolve_steamcmd

        steamcmd = resolve_steamcmd()
    except FileNotFoundError as exc:
        _set_job(
            running=False,
            phase="error",
            message=str(exc),
            errors=[str(exc)],
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        return

    try:
        result = download_batch(
            workshop_ids,
            paths["steam_install"],
            steamcmd=steamcmd,
            username=username,
            mods_dir=paths["mods"],
            on_progress=on_progress,
        )
        _set_job(
            running=False,
            phase="done" if result.get("ok") else "error",
            percent=100,
            message="Download complete" if result.get("ok") else "Finished with errors",
            results=result.get("results") or [],
            errors=result.get("errors") or [],
            finished_at=datetime.now().isoformat(timespec="seconds"),
            elapsed_seconds=result.get("elapsed_seconds"),
        )
    except Exception as exc:
        _set_job(
            running=False,
            phase="error",
            message=str(exc)[:400],
            errors=[str(exc)],
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


def start_download(
    workshop_ids: list[str] | None = None,
    *,
    server_id: str | None = None,
    username: str | None = None,
    missing_only: bool = True,
) -> dict[str, Any]:
    if _job_snapshot().get("running"):
        raise RuntimeError("Workshop download already running")

    parsed = read_workshop_ids(server_id)
    ids = [str(x).strip() for x in (workshop_ids or parsed["workshop_ids"]) if str(x).strip()]
    if not ids:
        raise ValueError("No WorkshopItems to download — pull mirror / set world.ini first")

    if missing_only:
        existing = {row["workshop_id"] for row in list_local_workshop_items(server_id)}
        ids = [i for i in ids if i not in existing]

    if not ids:
        return {
            "ok": True,
            "skipped": True,
            "message": "All WorkshopItems already present in mirror",
            "workshop_ids": [],
        }

    _set_job(
        running=True,
        phase="starting",
        percent=0,
        message="Starting SteamCMD…",
        workshop_ids=ids,
        results=[],
        errors=[],
        started_at=datetime.now().isoformat(timespec="seconds"),
        finished_at=None,
        current=None,
    )
    thread = threading.Thread(
        target=_run_download,
        args=(ids, server_id or active_id(), username),
        daemon=True,
    )
    thread.start()
    return {"ok": True, "started": True, "workshop_ids": ids, "status": _job_snapshot()}


def status_bundle(server_id: str | None = None) -> dict[str, Any]:
    parsed = read_workshop_ids(server_id)
    local = {row["workshop_id"]: row for row in list_local_workshop_items(server_id)}
    items: list[dict[str, Any]] = []
    for wid in parsed["workshop_ids"]:
        row = local.get(wid) or {
            "workshop_id": wid,
            "installed": False,
            "mod_ids": [],
            "local_mtime": None,
            "local_epoch": None,
            "path": None,
        }
        items.append(row)
    # include orphan local downloads not in ini
    for wid, row in local.items():
        if wid not in parsed["workshop_ids"]:
            items.append({**row, "orphan": True})
    paths = mirror_paths(server_id)
    try:
        from panel.services.steamcmd_bootstrap import status as steamcmd_status

        sc = steamcmd_status()
    except Exception:
        sc = {"installed": False, "path": "", "version_hint": ""}
    return {
        "server_id": server_id or active_id(),
        "ini_path": parsed["ini_path"],
        "mods": parsed["mods"],
        "workshop_ids": parsed["workshop_ids"],
        "items": items,
        "paths": {k: str(v) for k, v in paths.items()},
        "download": _job_snapshot(),
        "steamcmd_hint": "Workshop → Install SteamCMD or set STEAMCMD",
        "steamcmd": sc,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
