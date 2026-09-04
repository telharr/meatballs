"""Game-server uptime (not panel process uptime).

Priority:
1. Local JVM process create_time (process.kind=local)
2. Latest `st:` from server-console.txt (PZ JVM elapsed ms)
3. RCON online session tracked by the panel (survives browser refresh)
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from panel.paths import DATA_DIR, PANEL

STATE_FILE = DATA_DIR / "server_uptime.json"
ROOT = PANEL.parent

# LOG  : General      f:0 st:188\xa0400\xa0465> ...
_ST_RE = re.compile(r"\bst:([0-9\s\u00a0\u202f\u2009]+)\s*>", re.I)
_BOOT_MARKERS = (
    "*** server started",
    "server started ****",
    "server is listening",
    "steam is initialised",
)

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}


def _read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"sessions": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"sessions": {}}
    except (json.JSONDecodeError, OSError):
        return {"sessions": {}}


def _write_state(data: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)


def _load_sessions() -> None:
    global _sessions
    with _lock:
        if _sessions:
            return
        data = _read_state()
        raw = data.get("sessions") or {}
        if isinstance(raw, dict):
            _sessions = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}


def _persist() -> None:
    with _lock:
        _write_state({"sessions": _sessions})


def note_rcon(server_id: str | None, online: bool) -> None:
    """Remember continuous RCON-online window per profile."""
    sid = (server_id or "").strip() or "default"
    _load_sessions()
    now = time.time()
    with _lock:
        row = _sessions.get(sid) or {}
        if online:
            if not row.get("online_since"):
                row["online_since"] = now
            row["last_online_at"] = now
            row["online"] = True
        else:
            row["online"] = False
            row["online_since"] = None
            row["last_offline_at"] = now
        _sessions[sid] = row
    _persist()


def _parse_st_ms(text: str) -> int | None:
    best: int | None = None
    for match in _ST_RE.finditer(text or ""):
        digits = "".join(ch for ch in match.group(1) if ch.isdigit())
        if not digits:
            continue
        try:
            value = int(digits)
        except ValueError:
            continue
        # Ignore tiny/noise values under 1s; cap absurd (> 10 years)
        if value < 1000 or value > 10 * 365 * 24 * 3600 * 1000:
            continue
        if best is None or value > best:
            best = value
    return best


def _console_candidates(server_id: str | None) -> list[Path]:
    from panel.servers import load_profile, mirror_root

    roots: list[Path] = []
    sid = server_id or "default"
    try:
        roots.append(mirror_root(sid))
    except Exception:
        pass
    roots.append(ROOT / ".mirror" / sid)
    roots.append(ROOT / ".cache" / "dedi-test")
    try:
        profile = load_profile(sid)
        files = profile.get("files") or {}
        if str(files.get("kind") or "") == "local":
            root = str(files.get("root") or "").strip()
            if root:
                roots.append(Path(root))
    except Exception:
        pass

    out: list[Path] = []
    names = ("server-console.txt", "console.txt", "DebugLog.txt")
    for root in roots:
        if not root:
            continue
        try:
            exists = root.exists()
        except OSError:
            continue
        if not exists:
            continue
        for name in names:
            direct = root / name
            if direct.is_file():
                out.append(direct)
        try:
            for path in root.rglob("server-console.txt"):
                if path.is_file():
                    out.append(path)
        except OSError:
            pass
    # unique preserve order
    seen: set[str] = set()
    uniq: list[Path] = []
    for path in out:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(path)
    return uniq


def uptime_from_console(server_id: str | None = None) -> dict[str, Any] | None:
    """Read latest JVM `st:` from mirrored console (milliseconds since boot)."""
    newest: tuple[float, Path] | None = None
    for path in _console_candidates(server_id):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest[0]:
            newest = (mtime, path)
    if not newest:
        return None
    path = newest[1]
    try:
        data = path.read_bytes()
    except OSError:
        return None
    # last ~64 KiB is enough for recent st:
    text = data[-65536:].decode("utf-8", errors="replace")
    st_ms = _parse_st_ms(text)
    if st_ms is None:
        return None
    return {
        "seconds": int(st_ms // 1000),
        "source": "console_st",
        "path": str(path),
        "boot_markers": any(m in text.lower() for m in _BOOT_MARKERS),
    }


def uptime_from_local_process() -> dict[str, Any] | None:
    try:
        import psutil
        from local_server import inspect

        info = inspect()
    except Exception:
        return None
    pid = info.get("pid")
    if not pid or not info.get("running"):
        return None
    try:
        proc = psutil.Process(int(pid))
        created = float(proc.create_time())
    except Exception:
        return None
    seconds = max(0, int(time.time() - created))
    return {"seconds": seconds, "source": "local_process", "pid": int(pid)}


def uptime_from_rcon_session(server_id: str | None) -> dict[str, Any] | None:
    sid = (server_id or "").strip() or "default"
    _load_sessions()
    with _lock:
        row = _sessions.get(sid) or {}
        since = row.get("online_since")
        online = bool(row.get("online"))
    if not online or not since:
        return None
    try:
        started = float(since)
    except (TypeError, ValueError):
        return None
    return {"seconds": max(0, int(time.time() - started)), "source": "rcon_session"}


def resolve_uptime(server_id: str | None = None, *, rcon_online: bool | None = None) -> dict[str, Any]:
    """Best available game-server uptime."""
    if rcon_online is not None:
        note_rcon(server_id, bool(rcon_online))

    local = uptime_from_local_process()
    if local and int(local.get("seconds") or 0) > 0:
        return {"ok": True, **local}

    console = uptime_from_console(server_id)
    if console and int(console.get("seconds") or 0) > 0:
        return {"ok": True, **console}

    if rcon_online is False:
        return {"ok": False, "seconds": None, "source": "offline"}

    session = uptime_from_rcon_session(server_id)
    if session is not None:
        return {"ok": True, **session}

    return {"ok": False, "seconds": None, "source": "unknown"}
