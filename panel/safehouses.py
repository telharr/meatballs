"""Safehouse dump + panel → MeatballsSafehouses command bridge."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from uuid import uuid4

from panel.knox_map import snapshot_map as knox_snapshot_map
from panel.logs_hub import latest_text
from panel.paths import DATA_DIR

PANEL = Path(__file__).resolve().parent
REPO = PANEL.parent
ROOT = PANEL
MOD_DIR = REPO / "src" / "mods" / "MeatballsSafehouses"
QUEUE_DIR = DATA_DIR / "safehouse_queue"

CMD_FILE = "mb_safehouse_cmd.txt"
ACK_FILE = "mb_safehouse_ack.json"
DUMP_FILE = "mb_safehouses.json"
BRIDGE_FILE = "mb_safehouse_bridge.json"
MOD_ID = "MeatballsSafehouses"
BRIDGE_STALE_SEC = 180

CITIES: list[dict[str, Any]] = [
    {"id": "louisville", "name": "Louisville", "x1": 11700, "y1": 1000, "x2": 14700, "y2": 4500},
    {"id": "riverside", "name": "Riverside", "x1": 5700, "y1": 5100, "x2": 6900, "y2": 6000},
    {"id": "westpoint", "name": "West Point", "x1": 11140, "y1": 6600, "x2": 12240, "y2": 7380},
    {"id": "fallaslake", "name": "Fallas Lake", "x1": 7000, "y1": 8200, "x2": 7800, "y2": 8800},
    {"id": "muldraugh", "name": "Muldraugh", "x1": 10540, "y1": 9150, "x2": 11020, "y2": 10120},
    {"id": "rosewood", "name": "Rosewood", "x1": 7900, "y1": 11140, "x2": 8700, "y2": 12200},
    {"id": "marchridge", "name": "March Ridge", "x1": 9700, "y1": 12600, "x2": 10500, "y2": 13200},
]

HOW_IT_WORKS = (
    "Панель не пишет сейвы. Мод MeatballsSafehouses на дедике читает Lua/mb_safehouse_cmd.txt "
    "примерно раз в секунду, вызывает SafeHouse.*, пишет дамп и ack. "
    "Нужен залив мода в mods/ + Mods= + рестарт JVM. Работает на любом хосте с FTP/SFTP/local."
)

REMOTE_DUMP = "/ServerWorld/Lua/mb_safehouses.json"


def _active_server_id() -> str:
    try:
        from panel.servers import active_id

        return active_id() or "default"
    except Exception:
        return "default"


def _lua_dirs() -> list[Path]:
    found: list[Path] = []
    try:
        from panel.servers import cachedir_paths

        found = [root / "Lua" for root in cachedir_paths()]
    except Exception:
        found = [
            REPO / ".mirror" / "ServerWorld" / "Lua",
            REPO / ".cache" / "dedi-test" / "Lua",
        ]
    found.append(DATA_DIR)
    return found


def _files_root() -> str:
    try:
        from panel.servers import active_profile

        root = str((active_profile().get("files") or {}).get("root") or "/ServerWorld")
        return root.replace("\\", "/").rstrip("/") or "/ServerWorld"
    except Exception:
        return "/ServerWorld"


def remote_lua_path(name: str) -> str:
    try:
        from ftp_client import join_remote, normalize_remote

        return join_remote(normalize_remote(_files_root()), "Lua", name)
    except Exception:
        return f"{_files_root()}/Lua/{name}"


def remote_mod_dir() -> str:
    try:
        from ftp_client import join_remote, normalize_remote
        from panel.servers import active_profile

        files = active_profile().get("files") or {}
        mods = str(files.get("mods") or "").strip()
        if mods:
            return join_remote(normalize_remote(mods), MOD_ID)
        return join_remote(normalize_remote(_files_root()), "mods", MOD_ID)
    except Exception:
        return f"{_files_root()}/mods/{MOD_ID}"


def percent_encode(value: str) -> str:
    return quote(str(value or ""), safe="")


def percent_decode(value: str) -> str:
    text = str(value or "").replace("+", " ")
    return unquote(text)


def encode_members(names: list[str] | None) -> str:
    parts: list[str] = []
    for name in names or []:
        cleaned = str(name or "").strip()
        if cleaned:
            parts.append(percent_encode(cleaned))
    return ",".join(parts)


def decode_members(raw: str) -> list[str]:
    names: list[str] = []
    for token in str(raw or "").split(","):
        name = percent_decode(token).strip()
        if name:
            names.append(name)
    return names


def encode_cmd(
    op: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    nonce: str | None = None,
    owner: str | None = None,
    title: str | None = None,
    members: list[str] | None = None,
    add: list[str] | None = None,
    kick: list[str] | None = None,
) -> str:
    token = nonce or uuid4().hex[:12]
    lines = [
        f"op={op}",
        f"nonce={token}",
        f"x={int(x)}",
        f"y={int(y)}",
        f"w={int(w)}",
        f"h={int(h)}",
    ]
    if owner is not None:
        lines.append(f"owner={percent_encode(owner)}")
    if title is not None:
        lines.append(f"title={percent_encode(title)}")
    if members:
        lines.append(f"members={encode_members(members)}")
    if add:
        lines.append(f"add={encode_members(add)}")
    if kick:
        lines.append(f"kick={encode_members(kick)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_cmd_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if line == "---":
            if current:
                blocks.append(current)
            current = {}
            continue
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip()] = value
    if current:
        blocks.append(current)
    return blocks


def rects_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ax, ay, aw, ah = int(a["x"]), int(a["y"]), int(a["w"]), int(a["h"])
    bx, by, bw, bh = int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"])
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def house_key(house: dict[str, Any]) -> tuple[int, int, int, int]:
    return int(house.get("x") or 0), int(house.get("y") or 0), int(house.get("w") or 0), int(house.get("h") or 0)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        data["source"] = str(path)
        data["mtime"] = path.stat().st_mtime
        return data
    return None


def _first_json(filename: str) -> dict[str, Any] | None:
    for folder in _lua_dirs():
        data = _load_json(folder / filename)
        if data:
            return data
    return None


def _parse_journal(text: str, limit: int = 40) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if "safehouse" not in line.lower() and "приват" not in line.lower():
            continue
        rows.append({"line": line.strip()})
    return rows[-max(5, min(int(limit), 80)) :]


def _bridge_status() -> dict[str, Any]:
    data = _first_json(BRIDGE_FILE) or {}
    mtime = float(data.get("mtime") or 0)
    age = (time.time() - mtime) if mtime else None
    loaded = bool(data.get("ok")) and age is not None and age <= BRIDGE_STALE_SEC
    return {
        "loaded": loaded,
        "version": data.get("version"),
        "mod": data.get("mod") or MOD_ID,
        "age_seconds": round(age, 1) if age is not None else None,
        "source": data.get("source"),
        "stale_after": BRIDGE_STALE_SEC,
    }


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
        json.dumps(
            {"jobs": jobs[-40:], "updated_at": datetime.now().isoformat(timespec="seconds")},
            indent=2,
        ),
        encoding="utf-8",
    )


def pending_jobs(jobs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = jobs if jobs is not None else load_queue()
    return [j for j in rows if j.get("status") == "queued"]


def _write_local_cmd(body: str) -> list[str]:
    written: list[str] = []
    text = body if body.endswith("\n") or body == "" else body + "\n"
    for folder in _lua_dirs():
        if folder == DATA_DIR:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / CMD_FILE
        path.write_text(text, encoding="utf-8")
        written.append(str(path))
    return written


def _upload_text(filename: str, body: str) -> dict[str, Any]:
    local_paths = _write_local_cmd(body) if filename == CMD_FILE else []
    remote = remote_lua_path(filename)
    uploaded: dict[str, Any] | None = None
    upload_error: str | None = None
    try:
        from panel.servers import active_files_client

        client = active_files_client()
        ROOT.joinpath("backups").mkdir(parents=True, exist_ok=True)
        tmp_path = ROOT / "backups" / f".safehouse_{filename}_{uuid4().hex[:8]}"
        payload = body if body.endswith("\n") or body == "" else body + "\n"
        tmp_path.write_text(payload, encoding="utf-8")
        try:
            uploaded = client.upload_file(tmp_path, remote)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception as exc:
        upload_error = str(exc)[:300]
        if filename != CMD_FILE:
            for folder in _lua_dirs():
                folder.mkdir(parents=True, exist_ok=True)
                (folder / filename).write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
    result: dict[str, Any] = {
        "remote": remote,
        "uploaded": uploaded,
        "upload_error": upload_error,
    }
    if local_paths:
        result["local_paths"] = local_paths
    return result


def write_cmd_body(body: str) -> dict[str, Any]:
    local_paths = _write_local_cmd(body)
    file_result = _upload_text(CMD_FILE, body)
    file_result["local_paths"] = local_paths
    file_result["line_count"] = len([ln for ln in body.splitlines() if ln.strip()])
    return file_result


def cmd_body_from_jobs(jobs: list[dict[str, Any]] | None = None) -> str:
    lines = [j["line"] for j in pending_jobs(jobs) if j.get("line")]
    return "".join(lines) if lines else ""


def _clear_local_lua(name: str) -> None:
    for folder in _lua_dirs():
        if folder == DATA_DIR:
            continue
        path = folder / name
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass


def _remote_missing(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "550" in text or "not found" in text or "no such file" in text


def _pull_remote_lua(name: str) -> dict[str, Any]:
    remote = remote_lua_path(name)
    error: str | None = None
    saved: list[str] = []
    try:
        from panel.servers import active_files_client

        client = active_files_client()
        content = client.read_file(remote, binary=False)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        text = str(content or "")
        for folder in _lua_dirs():
            if folder == DATA_DIR:
                continue
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / name
            path.write_text(text, encoding="utf-8")
            saved.append(str(path))
        return {"ok": True, "remote": remote, "saved": saved, "bytes": len(text.encode("utf-8"))}
    except Exception as exc:
        error = str(exc)[:300]
        missing = _remote_missing(exc)
        if missing:
            _clear_local_lua(name)
        return {"ok": False, "remote": remote, "saved": saved, "error": error, "missing": missing}


def pull_remote_state() -> dict[str, Any]:
    files = {}
    for name in (DUMP_FILE, ACK_FILE, BRIDGE_FILE):
        files[name] = _pull_remote_lua(name)
    return {"ok": any(row.get("ok") for row in files.values()), "files": files}


def probe_install() -> dict[str, Any]:
    """FTP/SFTP/local: is MeatballsSafehouses on disk and listed in Mods=?"""
    result: dict[str, Any] = {
        "files_ok": False,
        "ini_ok": False,
        "ready": False,
        "mods": [],
        "mod_info": None,
        "error": None,
    }
    try:
        from panel.servers import active_files_client, active_profile
        from panel.services.workshop_downloader import parse_ini_list

        client = active_files_client()
        remote = remote_mod_dir().rstrip("/")
        for rel in ("42/mod.info", "mod.info"):
            try:
                raw = client.read_file(f"{remote}/{rel}")
                if raw:
                    result["files_ok"] = True
                    result["mod_info"] = rel
                    break
            except Exception:
                continue
        files = active_profile().get("files") or {}
        ini_name = str(files.get("ini") or "world.ini")
        kind = str(files.get("kind") or "ftp")
        if kind == "local":
            root = Path(str(files.get("root") or ""))
            ini_path = root / "Server" / ini_name
            if not ini_path.is_file():
                ini_path = root / ini_name
            previous = ini_path.read_text(encoding="utf-8", errors="replace") if ini_path.is_file() else ""
        else:
            try:
                from ftp_client import join_remote, normalize_remote

                ini_remote = join_remote(normalize_remote(_files_root()), "Server", ini_name)
            except Exception:
                ini_remote = f"{_files_root()}/Server/{ini_name}"
            previous = client.read_file(ini_remote)
            if isinstance(previous, bytes):
                previous = previous.decode("utf-8", errors="replace")
        mods = parse_ini_list(str(previous or ""), "Mods")
        result["mods"] = mods
        result["ini_ok"] = MOD_ID in mods
    except Exception as exc:
        result["error"] = str(exc)[:300]
    result["ready"] = bool(result["files_ok"] and result["ini_ok"])
    return result


def status_note(*, bridge: dict[str, Any], install: dict[str, Any], dump_live: bool) -> str:
    if bridge.get("loaded"):
        return (
            f"Мост {bridge.get('version') or MOD_ID} живой. "
            "Продление lastVisited панель не пишет. Saves не трогаем."
        )
    if install.get("ready"):
        return (
            "MeatballsSafehouses уже на диске и в Mods=. "
            "JVM его не загрузила — нужен рестарт dedicated. "
            "Панель процесс не поднимает: Graceful restart (RCON quit), потом Start у хостера."
        )
    if install.get("files_ok") and not install.get("ini_ok"):
        return (
            "Файлы мода на сервере есть, но Mods= без MeatballsSafehouses. "
            "Workshop → Залить выбранные как есть с галкой «Добавить ID в Mods=»."
        )
    if dump_live:
        return (
            "Дамп Lua есть, но мост не отвечает. "
            "Проверьте Mods= и рестартните JVM."
        )
    return (
        "Мод не найден в mods/. Workshop: только MeatballsSafehouses → "
        "«Залить выбранные как есть», затем рестарт dedicated."
    )


def snapshot(*, pull: bool = False) -> dict[str, Any]:
    pulled: dict[str, Any] | None = None
    if pull:
        pulled = pull_remote_state()
    dump = _first_json(DUMP_FILE) or {}
    ack = _first_json(ACK_FILE) or {}
    houses = dump.get("safehouses") or dump.get("houses") or []
    factions = dump.get("factions") or []
    bridge = _bridge_status()
    dump_live = False
    if pulled:
        dump_live = bool((pulled.get("files") or {}).get(DUMP_FILE, {}).get("ok"))
    else:
        dump_live = bool(houses)
    install = probe_install()
    note = status_note(bridge=bridge, install=install, dump_live=dump_live)
    return {
        "safehouses": houses,
        "factions": factions,
        "updated_at": dump.get("updated_at"),
        "source": dump.get("source"),
        "remote": remote_lua_path(DUMP_FILE),
        "journal": _parse_journal(latest_text("safehouse", 3)),
        "note": note,
        "how_it_works": HOW_IT_WORKS,
        "bridge": bridge,
        "install": install,
        "ack": {k: ack.get(k) for k in ("ok", "nonce", "op", "error", "x", "y", "w", "h", "updated_at") if k in ack},
        "cities": CITIES,
        "map": knox_snapshot_map(),
        "mod_id": MOD_ID,
        "mod_dir_local": str(MOD_DIR),
        "remote_mod": remote_mod_dir(),
        "cmd_file": CMD_FILE,
        "queue": pending_jobs()[-10:],
        "pulled": pulled,
    }


def find_overlap(x: int, y: int, w: int, h: int, ignore: dict[str, int] | None = None) -> dict[str, Any] | None:
    candidate = {"x": x, "y": y, "w": w, "h": h}
    dump = _first_json(DUMP_FILE) or {}
    ignore_key = house_key(ignore) if ignore else None
    for house in dump.get("safehouses") or dump.get("houses") or []:
        if ignore_key and house_key(house) == ignore_key:
            continue
        if rects_overlap(candidate, house):
            return house
    return None


def _validate_rect(x: int, y: int, w: int, h: int) -> None:
    if w < 1 or h < 1:
        raise ValueError("Размер зоны должен быть минимум 1×1")
    if w > 400 or h > 400:
        raise ValueError("Слишком большая зона (макс 400×400 тайлов)")
    if x < -1000 or y < -1000 or x > 40000 or y > 40000:
        raise ValueError("Координаты вне карты Knox Country")


def _rcon_notify(message: str) -> tuple[str | None, str | None]:
    try:
        from panel.rcon_client import rcon_execute

        return rcon_execute(f'servermsg "{message}"'), None
    except Exception as exc:
        return None, str(exc)[:300]


def _enqueue(op: str, line: str, nonce: str, payload: dict[str, Any], *, upload: bool, notify: bool) -> dict[str, Any]:
    job = {
        "id": nonce,
        "op": op,
        "line": line,
        "status": "queued",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    jobs = load_queue()
    jobs.append(job)
    save_queue(jobs)
    body = cmd_body_from_jobs(jobs)
    file_result = {"local_paths": _write_local_cmd(body), "remote": remote_lua_path(CMD_FILE)}
    if upload:
        file_result = write_cmd_body(body)
        if file_result.get("upload_error") and not file_result.get("uploaded") and not file_result.get("local_paths"):
            job["status"] = "upload_failed"
            job["upload_error"] = file_result.get("upload_error")
            save_queue(jobs)
    rcon_out, rcon_error = (None, None)
    if notify:
        rcon_out, rcon_error = _rcon_notify(f"[Safehouses] {op} queued ({nonce})")
    return {
        "ok": job["status"] == "queued",
        "job": job,
        "line": line,
        "nonce": nonce,
        "queued": True,
        "needs_mod": True,
        "how_it_works": HOW_IT_WORKS,
        "bridge": _bridge_status(),
        "overlap": payload.get("overlap"),
        **file_result,
        "rcon": rcon_out,
        "rcon_error": rcon_error,
    }


def create_safehouse(
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    owner: str,
    title: str = "",
    members: list[str] | None = None,
    upload: bool = True,
    rcon_notify: bool = True,
) -> dict[str, Any]:
    _validate_rect(x, y, w, h)
    owner_name = (owner or "").strip()
    if not owner_name:
        raise ValueError("Нужен владелец (username)")
    zone_title = (title or "").strip() or owner_name
    overlap = find_overlap(x, y, w, h)
    if overlap:
        raise ValueError(
            f"Пересечение с приватом {overlap.get('title') or overlap.get('owner')} "
            f"@ {overlap.get('x')},{overlap.get('y')}"
        )
    nonce = uuid4().hex[:12]
    line = encode_cmd(
        "create",
        x=x,
        y=y,
        w=w,
        h=h,
        nonce=nonce,
        owner=owner_name,
        title=zone_title,
        members=members or [],
    )
    return _enqueue(
        "create",
        line,
        nonce,
        {
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "owner": owner_name,
            "title": zone_title,
            "members": members or [],
        },
        upload=upload,
        notify=rcon_notify,
    )


def update_safehouse(
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    owner: str | None = None,
    title: str | None = None,
    add: list[str] | None = None,
    kick: list[str] | None = None,
    members: list[str] | None = None,
    upload: bool = True,
    rcon_notify: bool = False,
) -> dict[str, Any]:
    _validate_rect(x, y, w, h)
    nonce = uuid4().hex[:12]
    line = encode_cmd(
        "update",
        x=x,
        y=y,
        w=w,
        h=h,
        nonce=nonce,
        owner=owner,
        title=title,
        members=members,
        add=add,
        kick=kick,
    )
    return _enqueue(
        "update",
        line,
        nonce,
        {"x": x, "y": y, "w": w, "h": h, "owner": owner, "title": title, "add": add or [], "kick": kick or []},
        upload=upload,
        notify=rcon_notify,
    )


def release_safehouse(
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    confirm: str,
    upload: bool = True,
    rcon_notify: bool = True,
) -> dict[str, Any]:
    _validate_rect(x, y, w, h)
    if (confirm or "").strip().lower() != "release":
        raise ValueError("Для снятия введи confirm=release")
    nonce = uuid4().hex[:12]
    line = encode_cmd("release", x=x, y=y, w=w, h=h, nonce=nonce)
    return _enqueue(
        "release",
        line,
        nonce,
        {"x": x, "y": y, "w": w, "h": h, "confirm": "release"},
        upload=upload,
        notify=rcon_notify,
    )


def iter_mod_files() -> list[tuple[Path, str]]:
    if not MOD_DIR.is_dir():
        return []
    remote_root = remote_mod_dir()
    out: list[tuple[Path, str]] = []
    for path in MOD_DIR.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(MOD_DIR).as_posix()
        try:
            from ftp_client import join_remote

            remote = join_remote(remote_root, rel)
        except Exception:
            remote = f"{remote_root.rstrip('/')}/{rel}"
        out.append((path, remote))
    return out


def _install_local() -> dict[str, Any]:
    from panel.servers import active_profile

    files = active_profile().get("files") or {}
    if str(files.get("kind") or "") != "local":
        raise ValueError("not local")
    dest = Path(str(files.get("root") or "")) / "mods" / MOD_ID
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.copytree(MOD_DIR, dest, dirs_exist_ok=True)
    else:
        shutil.copytree(MOD_DIR, dest)
    count = sum(1 for p in dest.rglob("*") if p.is_file())
    return {"ok": True, "kind": "local", "dest": str(dest), "files": count}


def install_mod(*, patch_ini: bool = False) -> dict[str, Any]:
    if not MOD_DIR.is_dir():
        raise FileNotFoundError(f"Mod not found: {MOD_DIR}")
    local_result: dict[str, Any] | None = None
    try:
        local_result = _install_local()
    except Exception:
        local_result = None

    uploaded: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    remote = remote_mod_dir()
    upload_error: str | None = None
    try:
        from panel.servers import active_files_client

        client = active_files_client()
        if hasattr(client, "sync_modpack"):
            sync = client.sync_modpack(MOD_DIR, remote)
            uploaded = list(getattr(sync, "uploaded", []) or [])
            skipped = list(getattr(sync, "skipped", []) or [])
            errors = list(getattr(sync, "errors", []) or [])
        else:
            for local, rem in iter_mod_files():
                client.upload_file(local, rem)
                uploaded.append(rem)
    except Exception as exc:
        upload_error = str(exc)[:300]
        if local_result is None:
            raise

    ini_result: dict[str, Any] | None = None
    if patch_ini:
        ini_result = _append_mod_to_ini()

    ok = not errors and not upload_error and bool(local_result or uploaded)
    return {
        "ok": ok,
        "mod_id": MOD_ID,
        "remote_mod": remote,
        "local": local_result,
        "uploaded": uploaded,
        "skipped": skipped,
        "errors": errors,
        "upload_error": upload_error,
        "ini": ini_result,
        "hint": "Добавь MeatballsSafehouses в Mods= (если ещё нет) и рестартни dedicated.",
        "how_it_works": HOW_IT_WORKS,
    }


def _append_mod_to_ini() -> dict[str, Any]:
    from mod_catalog import apply_lists_to_ini, parse_ini_list
    from panel.servers import active_files_client, active_profile

    profile = active_profile()
    files = profile.get("files") or {}
    ini_name = str(files.get("ini") or "world.ini")
    try:
        from ftp_client import join_remote, normalize_remote

        remote_ini = join_remote(normalize_remote(_files_root()), "Server", ini_name)
    except Exception:
        remote_ini = f"{_files_root()}/Server/{ini_name}"
    client = active_files_client()
    previous = client.read_file(remote_ini)
    if isinstance(previous, bytes):
        previous = previous.decode("utf-8", errors="replace")
    mods = parse_ini_list(previous, "Mods")
    workshop = parse_ini_list(previous, "WorkshopItems")
    if MOD_ID in mods:
        return {"changed": False, "mods": mods, "remote": remote_ini}
    mods.append(MOD_ID)
    updated = apply_lists_to_ini(previous, mods, workshop)
    tmp = ROOT / "backups" / f".safehouse_ini_{uuid4().hex[:8]}.ini"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(updated, encoding="utf-8")
    try:
        upload = client.upload_file(tmp, remote_ini)
    finally:
        tmp.unlink(missing_ok=True)
    return {"changed": True, "mods": mods, "remote": remote_ini, "upload": upload}


def mark_job_ack(ack: dict[str, Any]) -> None:
    nonce = str(ack.get("nonce") or "")
    if not nonce:
        return
    jobs = load_queue()
    changed = False
    for job in jobs:
        if job.get("id") == nonce and job.get("status") == "queued":
            job["status"] = "ok" if ack.get("ok") else "error"
            job["ack_error"] = ack.get("error")
            job["acked_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
    if changed:
        save_queue(jobs)
