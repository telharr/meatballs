"""Steam Workshop update monitor via GetPublishedFileDetails."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from panel.servers import active_id, mirror_root
from panel.services.workshop_downloader import list_local_workshop_items, read_workshop_ids

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "panel" / "data"
STATE_FILE = STATE_DIR / "workshop_monitor.json"
STEAM_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

_lock = threading.Lock()
_restart_job: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "message": "",
    "started_at": None,
    "finished_at": None,
}


def _read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"items": {}, "last_check": None, "auto_restart": False}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"items": {}, "last_check": None, "auto_restart": False}


def _write_state(data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch_published_details(workshop_ids: list[str], timeout: float = 20.0) -> dict[str, dict[str, Any]]:
    """Query Steam Web API for published file details (time_updated, title, …)."""
    ids = [str(i).strip() for i in workshop_ids if str(i).strip().isdigit()]
    if not ids:
        return {}
    form: list[tuple[str, str]] = [("itemcount", str(len(ids)))]
    for idx, wid in enumerate(ids):
        form.append((f"publishedfileids[{idx}]", wid))
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        STEAM_API,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Steam API unreachable: {exc}") from exc

    details = (payload.get("response") or {}).get("publishedfiledetails") or []
    out: dict[str, dict[str, Any]] = {}
    for row in details:
        wid = str(row.get("publishedfileid") or "")
        if not wid:
            continue
        out[wid] = {
            "workshop_id": wid,
            "title": row.get("title") or wid,
            "time_updated": int(row.get("time_updated") or 0),
            "time_created": int(row.get("time_created") or 0),
            "result": int(row.get("result") or 0),
            "file_size": int(row.get("file_size") or 0),
        }
    return out


def check_updates(server_id: str | None = None) -> dict[str, Any]:
    parsed = read_workshop_ids(server_id)
    ids = parsed["workshop_ids"]
    local_map = {r["workshop_id"]: r for r in list_local_workshop_items(server_id)}
    remote = fetch_published_details(ids) if ids else {}
    state = _read_state()
    items_state: dict[str, Any] = state.setdefault("items", {})

    rows: list[dict[str, Any]] = []
    updates = 0
    for wid in ids:
        rem = remote.get(wid) or {}
        loc = local_map.get(wid) or {}
        remote_ts = int(rem.get("time_updated") or 0)
        local_epoch = int(loc.get("local_epoch") or 0)
        remembered = int((items_state.get(wid) or {}).get("seen_updated") or 0)
        # Prefer filesystem mtime; fall back to last acknowledged stamp
        baseline = local_epoch or remembered
        update_available = bool(remote_ts and baseline and remote_ts > baseline)
        if remote_ts and not baseline:
            # installed never, or unknown local time — still flag if Steam has a stamp
            update_available = not bool(loc.get("installed"))
        if update_available:
            updates += 1
        items_state[wid] = {
            "title": rem.get("title") or (items_state.get(wid) or {}).get("title") or wid,
            "time_updated": remote_ts,
            "seen_updated": remembered or (remote_ts if not update_available else remembered),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        rows.append(
            {
                "workshop_id": wid,
                "title": rem.get("title") or wid,
                "installed": bool(loc.get("installed")),
                "local_mtime": loc.get("local_mtime"),
                "local_epoch": local_epoch or None,
                "remote_updated": remote_ts or None,
                "remote_updated_iso": (
                    datetime.utcfromtimestamp(remote_ts).isoformat(timespec="seconds") + "Z"
                    if remote_ts
                    else None
                ),
                "update_available": update_available,
                "mod_ids": loc.get("mod_ids") or [],
            }
        )

    state["last_check"] = datetime.now().isoformat(timespec="seconds")
    state["items"] = items_state
    _write_state(state)

    return {
        "ok": True,
        "server_id": server_id or active_id(),
        "ini_path": parsed["ini_path"],
        "updates_available": updates,
        "items": rows,
        "checked_at": state["last_check"],
        "auto_restart": bool(state.get("auto_restart")),
    }


def acknowledge_updates(workshop_ids: list[str] | None = None) -> dict[str, Any]:
    state = _read_state()
    items = state.setdefault("items", {})
    targets = workshop_ids or list(items.keys())
    for wid in targets:
        row = items.get(wid)
        if not row:
            continue
        row["seen_updated"] = int(row.get("time_updated") or row.get("seen_updated") or 0)
    _write_state(state)
    return {"ok": True, "acknowledged": targets}


def set_auto_restart(enabled: bool) -> dict[str, Any]:
    state = _read_state()
    state["auto_restart"] = bool(enabled)
    _write_state(state)
    return {"ok": True, "auto_restart": bool(enabled)}


def restart_status() -> dict[str, Any]:
    with _lock:
        return dict(_restart_job)


def _set_restart(**kwargs: Any) -> None:
    with _lock:
        _restart_job.update(kwargs)


def _run_graceful_restart(minutes: int, message: str) -> None:
    from panel.rcon_client import rcon_execute

    try:
        warn = message or (
            f'Внимание: вышло обновление мода в Steam! Рестарт через {minutes} минут.'
        )
        rcon_execute(f'servermsg "{warn}"')
        _set_restart(phase="countdown", message=warn)
        # countdown ticks every 30s for short waits; cap sleep chunks
        remaining = max(1, int(minutes) * 60)
        while remaining > 0:
            chunk = min(30, remaining)
            time.sleep(chunk)
            remaining -= chunk
            _set_restart(message=f"Countdown… {remaining}s left")
        rcon_execute("save")
        _set_restart(phase="saving", message="save")
        time.sleep(5)
        rcon_execute("quit")
        _set_restart(
            running=False,
            phase="done",
            message="quit sent",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as exc:
        _set_restart(
            running=False,
            phase="error",
            message=str(exc)[:300],
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


def start_graceful_restart(minutes: int = 3, message: str = "") -> dict[str, Any]:
    if restart_status().get("running"):
        raise RuntimeError("Graceful restart already running")
    _set_restart(
        running=True,
        phase="starting",
        message="Starting countdown",
        started_at=datetime.now().isoformat(timespec="seconds"),
        finished_at=None,
    )
    thread = threading.Thread(
        target=_run_graceful_restart,
        args=(minutes, message),
        daemon=True,
    )
    thread.start()
    return {"ok": True, "status": restart_status()}


def monitor_snapshot(server_id: str | None = None) -> dict[str, Any]:
    state = _read_state()
    return {
        "last_check": state.get("last_check"),
        "auto_restart": bool(state.get("auto_restart")),
        "tracked": len(state.get("items") or {}),
        "restart": restart_status(),
        "server_id": server_id or active_id(),
        "state_file": str(STATE_FILE),
    }
