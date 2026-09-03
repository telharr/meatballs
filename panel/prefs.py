"""Local panel preferences: host (XLGAMES) authority over our writes."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from panel.paths import DATA_DIR

PREFS_FILE = DATA_DIR / "prefs.json"

HOST_WATCH = frozenset(
    {
        "world.ini",
        "world_SandboxVars.lua",
        "world_spawnregions.lua",
        "world_spawnpoints.lua",
        "options.ini",
        "ServerOptions.ini",
        "MEATBALLS.ini",
        "MEATBALLS_SandboxVars.lua",
    }
)


def _empty() -> dict[str, Any]:
    return {"host_panel_wins": True, "seen_remote": {}}


def load_prefs() -> dict[str, Any]:
    if not PREFS_FILE.exists():
        return _empty()
    try:
        data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty()
    data.setdefault("host_panel_wins", True)
    data.setdefault("seen_remote", {})
    return data


def save_prefs(data: dict[str, Any]) -> dict[str, Any]:
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = load_prefs()
    merged.update(data)
    PREFS_FILE.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return merged


def content_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def remember_remote(filename: str, remote_path: str, text: str) -> None:
    prefs = load_prefs()
    prefs["seen_remote"][filename] = {
        "path": remote_path,
        "md5": content_md5(text),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    save_prefs(prefs)


def remember_watched_from_dir(local_dir: Path, remote_prefix: str = "/ServerWorld") -> None:
    """After a Pull, remember host copies of watched configs so XLGAMES edits win."""
    root = Path(local_dir)
    if not root.exists():
        return
    prefix = remote_prefix.rstrip("/") or ""
    for path in root.rglob("*"):
        if not path.is_file() or path.name not in HOST_WATCH:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        remember_remote(path.name, f"{prefix}/{rel}", text)


def host_conflict(filename: str, remote_text: str, new_text: str) -> dict[str, Any] | None:
    prefs = load_prefs()
    if not prefs.get("host_panel_wins"):
        return None
    if filename not in HOST_WATCH:
        return None
    seen = (prefs.get("seen_remote") or {}).get(filename) or {}
    last = seen.get("md5")
    remote_hash = content_md5(remote_text)
    new_hash = content_md5(new_text)
    if not last:
        return None
    if remote_hash == last:
        return None
    if remote_hash == new_hash:
        return None
    return {
        "filename": filename,
        "remote_md5": remote_hash,
        "seen_md5": last,
        "local_md5": new_hash,
        "remote_content": remote_text,
        "seen_at": seen.get("at"),
    }
