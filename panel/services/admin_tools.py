"""AdminTools panel bridge: city wipe file drop + RCON notify, city catalog."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
PANEL = Path(__file__).resolve().parents[1]
from panel.paths import DATA_DIR  # noqa: E402

CMD_FILE = "mb_admintools_cmd.txt"
REMOTE_DEFAULT = "/ServerWorld/Lua/mb_admintools_cmd.txt"
QUEUE_DIR = DATA_DIR / "admintools_queue"

# Keep in sync with src/mods/AdminTools/.../AdminTools.lua
CITIES: list[dict[str, Any]] = [
    {"id": "muldraugh", "name": "Muldraugh", "x1": 10540, "y1": 9150, "x2": 11020, "y2": 10120},
    {"id": "westpoint", "name": "West Point", "x1": 11140, "y1": 6600, "x2": 12240, "y2": 7380},
    {"id": "rosewood", "name": "Rosewood", "x1": 7900, "y1": 11140, "x2": 8700, "y2": 12200},
    {"id": "riverside", "name": "Riverside", "x1": 5700, "y1": 5100, "x2": 6900, "y2": 6000},
    {"id": "louisville", "name": "Louisville", "x1": 11700, "y1": 1000, "x2": 14700, "y2": 4500},
    {"id": "marchridge", "name": "March Ridge", "x1": 9700, "y1": 12600, "x2": 10500, "y2": 13200},
    {"id": "fallaslake", "name": "Fallas Lake", "x1": 7000, "y1": 8200, "x2": 7800, "y2": 8800},
]

HOW_IT_WORKS = (
    "AdminTools на дедике раз в ~1 с читает Lua/mb_admintools_cmd.txt (несколько строк = очередь). "
    "Каждый город становится job в памяти сервера и идёт по клеткам. "
    "Вайп касается только загруженных чанков (игрок рядом / клетка в RAM). "
    "Пустые missing-квадраты пропускаются. Подтверждение: servermsg, лог AdminTools, вкладка Логи → Admin Audit."
)


def list_cities() -> dict[str, Any]:
    return {
        "cities": CITIES,
        "count": len(CITIES),
        "cmd_file": CMD_FILE,
        "note": "In-game wipe via Lua/mb_admintools_cmd.txt + RCON servermsg. Needs AdminTools mod loaded.",
        "how_it_works": HOW_IT_WORKS,
    }


def get_city(city_id: str) -> dict[str, Any] | None:
    cid = (city_id or "").strip().lower()
    for city in CITIES:
        if city["id"] == cid:
            return city
    return None


def _active_server_id() -> str:
    try:
        from panel.servers import active_id

        return active_id() or "default"
    except Exception:
        return "default"


def _queue_path(server_id: str | None = None) -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    sid = (server_id or _active_server_id()).replace("/", "_")
    return QUEUE_DIR / f"{sid}.json"


def load_queue(server_id: str | None = None) -> list[dict[str, Any]]:
    path = _queue_path(server_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        jobs = data.get("jobs") if isinstance(data, dict) else data
        return list(jobs) if isinstance(jobs, list) else []
    except Exception:
        return []


def save_queue(jobs: list[dict[str, Any]], server_id: str | None = None) -> None:
    path = _queue_path(server_id)
    path.write_text(
        json.dumps({"jobs": jobs[-40:], "updated_at": datetime.now().isoformat(timespec="seconds")}, indent=2),
        encoding="utf-8",
    )


def pending_jobs(jobs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = jobs if jobs is not None else load_queue()
    return [j for j in rows if j.get("status") == "queued"]


def queue_status() -> dict[str, Any]:
    jobs = load_queue()
    pending = pending_jobs(jobs)
    return {
        "jobs": jobs[-20:],
        "pending": pending,
        "pending_count": len(pending),
        "cmd_file": CMD_FILE,
        "remote": remote_cmd_path(),
        "how_it_works": HOW_IT_WORKS,
    }


def clear_queue(*, keep_history: bool = True) -> dict[str, Any]:
    jobs = load_queue()
    if keep_history:
        for job in jobs:
            if job.get("status") == "queued":
                job["status"] = "cleared"
                job["cleared_at"] = datetime.now().isoformat(timespec="seconds")
        save_queue(jobs)
    else:
        save_queue([])
    write_cmd_body("")
    return queue_status()


def _local_lua_dirs() -> list[Path]:
    try:
        from panel.servers import cachedir_paths

        return [root / "Lua" for root in cachedir_paths()]
    except Exception:
        return [
            ROOT / ".mirror" / "ServerWorld" / "Lua",
            ROOT / ".cache" / "dedi-test" / "Lua",
        ]


def remote_cmd_path() -> str:
    try:
        from panel.servers import active_profile

        root = str((active_profile().get("files") or {}).get("root") or "/ServerWorld").rstrip("/")
        return f"{root}/Lua/{CMD_FILE}"
    except Exception:
        return REMOTE_DEFAULT


def encode_city_wipe_line(
    city_id: str,
    *,
    refill_loot: bool = True,
    reconstruct_containers: bool = False,
    nonce: str | None = None,
) -> str:
    token = nonce or uuid4().hex[:12]
    return (
        f"v1|citywipe|{city_id}|"
        f"{1 if refill_loot else 0}|{1 if reconstruct_containers else 0}|"
        f"{token}|panel"
    )


def cmd_body_from_jobs(jobs: list[dict[str, Any]] | None = None) -> str:
    lines = [j["line"] for j in pending_jobs(jobs) if j.get("line")]
    return ("\n".join(lines) + "\n") if lines else ""


def write_local_cmd(body: str) -> list[str]:
    written: list[str] = []
    text = body if body.endswith("\n") or body == "" else body + "\n"
    for folder in _local_lua_dirs():
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / CMD_FILE
        path.write_text(text, encoding="utf-8")
        written.append(str(path))
    return written


def write_cmd_body(body: str) -> dict[str, Any]:
    local_paths = write_local_cmd(body)
    remote = remote_cmd_path()
    uploaded: dict[str, Any] | None = None
    upload_error: str | None = None
    try:
        from panel.servers import active_files_client

        client = active_files_client()
        PANEL.joinpath("backups").mkdir(parents=True, exist_ok=True)
        tmp_path = PANEL / "backups" / f".admintools_cmd_{uuid4().hex[:8]}.txt"
        tmp_path.write_text(body if body.endswith("\n") or body == "" else body + "\n", encoding="utf-8")
        try:
            uploaded = client.upload_file(tmp_path, remote)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception as exc:
        upload_error = str(exc)[:300]
    return {
        "local_paths": local_paths,
        "remote": remote,
        "uploaded": uploaded,
        "upload_error": upload_error,
        "line_count": len([ln for ln in body.splitlines() if ln.strip()]),
    }


def trigger_city_wipe(
    city_id: str,
    *,
    refill_loot: bool = True,
    reconstruct_containers: bool = False,
    upload: bool = True,
    rcon_notify: bool = True,
) -> dict[str, Any]:
    city = get_city(city_id)
    if not city:
        raise ValueError(f"Unknown city_id: {city_id}")

    nonce = uuid4().hex[:12]
    line = encode_city_wipe_line(
        city["id"],
        refill_loot=refill_loot,
        reconstruct_containers=reconstruct_containers,
        nonce=nonce,
    )
    job = {
        "id": nonce,
        "city_id": city["id"],
        "city_name": city["name"],
        "line": line,
        "refill_loot": refill_loot,
        "reconstruct_containers": reconstruct_containers,
        "status": "queued",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    jobs = load_queue()
    jobs.append(job)
    save_queue(jobs)

    body = cmd_body_from_jobs(jobs)
    file_result: dict[str, Any] = {"local_paths": write_local_cmd(body), "remote": remote_cmd_path()}
    uploaded: dict[str, Any] | None = None
    upload_error: str | None = None
    if upload:
        file_result = write_cmd_body(body)
        uploaded = file_result.get("uploaded")
        upload_error = file_result.get("upload_error")
        if upload_error and not uploaded:
            job["status"] = "upload_failed"
            job["upload_error"] = upload_error
            save_queue(jobs)

    rcon_out: str | None = None
    rcon_error: str | None = None
    pending = pending_jobs(jobs)
    if rcon_notify:
        msg = (
            f"[AdminTools] City wipe queued: {city['name']} "
            f"({len(pending)} in file; loot={'on' if refill_loot else 'off'}, "
            f"containers={'on' if reconstruct_containers else 'off'})"
        )
        try:
            from panel.rcon_client import rcon_execute

            rcon_out = rcon_execute(f'servermsg "{msg}"')
        except Exception as exc:
            rcon_error = str(exc)[:300]

    return {
        "ok": True,
        "city": city,
        "job": job,
        "line": line,
        "queue": pending,
        "pending_count": len(pending),
        "local_paths": file_result.get("local_paths") or [],
        "remote": file_result.get("remote") or remote_cmd_path(),
        "uploaded": uploaded,
        "upload_error": upload_error,
        "rcon": rcon_out,
        "rcon_error": rcon_error,
        "created_at": job["created_at"],
        "how_it_works": HOW_IT_WORKS,
        "hint": HOW_IT_WORKS,
    }
