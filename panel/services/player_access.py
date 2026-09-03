"""Track player access levels (B42 setaccesslevel) for the players UI."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

PANEL = Path(__file__).resolve().parents[1]
from panel.paths import DATA_DIR as PANEL_DATA  # noqa: E402

DATA_DIR = PANEL_DATA / "player_access"

ELEVATED_LEVELS = frozenset({"admin", "moderator", "overseer", "gm", "observer", "priority"})
DEFAULT_LEVEL = "user"

RE_SETACCESS_CMD = re.compile(
    r"""setaccesslevel\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))""",
    re.IGNORECASE,
)
RE_SETACCESS_OUT = re.compile(r"User\s+(.+?)\s+is now\s+(\w+)", re.IGNORECASE)
RE_LOG_SETACCESS = re.compile(
    r"""setaccesslevel\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))""",
    re.IGNORECASE,
)

_cache: dict[str, dict[str, str]] = {}
_last_log_sync: dict[str, float] = {}
_recent_rcon: dict[str, float] = {}
LOG_SYNC_TTL = 45.0
RCON_CACHE_TTL = 120.0


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def _store_path(server_id: str) -> Path:
    safe = re.sub(r"[^\w\-]+", "_", server_id or "default")
    return DATA_DIR / f"{safe}.json"


def _load_store(server_id: str) -> dict[str, str]:
    if server_id in _cache:
        return _cache[server_id]
    path = _store_path(server_id)
    levels: dict[str, str] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                levels = {str(k).lower(): str(v).lower() for k, v in raw.items()}
        except (OSError, json.JSONDecodeError, TypeError):
            levels = {}
    _cache[server_id] = levels
    return levels


def _save_store(server_id: str) -> None:
    levels = _cache.get(server_id)
    if levels is None:
        return
    path = _store_path(server_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(levels, indent=2, ensure_ascii=False), encoding="utf-8")


def is_elevated(level: str | None) -> bool:
    lvl = (level or DEFAULT_LEVEL).strip().lower()
    return lvl in ELEVATED_LEVELS


def record_level(server_id: str, player: str, level: str) -> None:
    name = _norm(player)
    if not name:
        return
    lvl = (level or DEFAULT_LEVEL).strip().lower()
    store = _load_store(server_id)
    store[name] = lvl
    _recent_rcon[f"{server_id}:{name}"] = time.time()
    _save_store(server_id)


def _log_sync_allowed(server_id: str, player_key: str) -> bool:
    stamp = _recent_rcon.get(f"{server_id}:{player_key}", 0)
    return time.time() - stamp >= RCON_CACHE_TTL


def record_from_rcon(server_id: str, command: str, output: str) -> None:
    cmd = (command or "").strip()
    out = (output or "").strip()
    m = RE_SETACCESS_CMD.search(cmd)
    if m:
        player = m.group(1) or m.group(2) or ""
        level = m.group(3) or m.group(4) or DEFAULT_LEVEL
        record_level(server_id, player, level)
    m = RE_SETACCESS_OUT.search(out)
    if m:
        record_level(server_id, m.group(1), m.group(2))


def _merge_log_levels(levels: dict[str, str], text: str, server_id: str) -> None:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if "setaccesslevel" not in line.lower():
            continue
        m = RE_LOG_SETACCESS.search(line)
        if not m:
            continue
        player = m.group(1) or m.group(2) or ""
        level = m.group(3) or m.group(4) or DEFAULT_LEVEL
        key = _norm(player)
        if key:
            parsed[key] = level.lower()
    for key, lvl in parsed.items():
        if key not in levels:
            levels[key] = lvl
        elif _log_sync_allowed(server_id, key):
            levels[key] = lvl


def sync_from_mirror_logs(server_id: str, *, force: bool = False) -> None:
    now = time.time()
    if not force and now - _last_log_sync.get(server_id, 0) < LOG_SYNC_TTL:
        return
    _last_log_sync[server_id] = now
    try:
        from panel.logs_hub import _iter_local_logs
    except Exception:
        return
    levels = _load_store(server_id)
    for kind in ("cmd", "admin"):
        for row in _iter_local_logs():
            if row.get("kind") != kind:
                continue
            try:
                text = Path(row["path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            _merge_log_levels(levels, text, server_id)
            break
    _save_store(server_id)


def sync_from_remote_logs(server_id: str) -> None:
    """Best-effort FTP tail of latest cmd/admin log (short timeout)."""
    try:
        from ftp_client import client_from_env, load_dotenv

        load_dotenv()
        client = client_from_env()
        levels = _load_store(server_id)
        for suffix in ("_cmd.txt", "_admin.txt"):
            try:
                entries = client.list_files("/ServerWorld/Logs", recursive=False)
            except Exception:
                return
            names = [
                e["path"]
                for e in entries
                if e.get("type") == "file" and str(e.get("name", "")).endswith(suffix)
            ]
            if not names:
                continue
            names.sort(reverse=True)
            try:
                text = client.read_file(names[0])
            except Exception:
                continue
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            _merge_log_levels(levels, str(text), server_id)
        _save_store(server_id)
    except Exception:
        return


def enrich_players(players: list[dict[str, Any]], server_id: str) -> list[dict[str, Any]]:
    sync_from_mirror_logs(server_id)
    store = _load_store(server_id)
    out: list[dict[str, Any]] = []
    for row in players:
        item = dict(row)
        key = _norm(str(item.get("name") or ""))
        level = store.get(key, DEFAULT_LEVEL)
        item["access_level"] = level
        item["is_elevated"] = is_elevated(level)
        out.append(item)
    return out


def revoke_command(player: str) -> str:
    return f'setaccesslevel "{player}" user'


def grant_command(player: str, level: str = "admin") -> str:
    return f'setaccesslevel "{player}" {level}'
