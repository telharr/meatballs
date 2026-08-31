"""Ban lists from cachedir db/ plus kick hints from logs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from panel.logs_hub import latest_text

ROOT = Path(__file__).resolve().parents[1]


def _db_dirs() -> list[Path]:
    try:
        from panel.servers import cachedir_paths

        return [root / "db" for root in cachedir_paths()]
    except Exception:
        return [
            ROOT / ".mirror" / "ServerWorld" / "db",
            ROOT / ".cache" / "dedi-test" / "db",
        ]
BAN_NAMES = (
    "bannedid.txt",
    "banned-id.txt",
    "bannedIDs.txt",
    "bannedids.txt",
    "bannedip.txt",
    "banned-ip.txt",
    "bannedIPs.txt",
)
STEAM_RE = re.compile(r"(\d{15,20})")
KICK_RE = re.compile(r"kick|banned|banuser|banid", re.I)


def _parse_ban_line(line: str, kind: str) -> dict[str, str] | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    steam = ""
    match = STEAM_RE.search(raw)
    if match:
        steam = match.group(1)
    name = STEAM_RE.sub("", raw).strip(" -–—()[]\"'")
    return {"kind": kind, "steamid": steam, "name": name, "raw": raw}


def _kind_from_name(filename: str) -> str:
    lower = filename.lower()
    if "ip" in lower:
        return "ip"
    return "id"


def load_bans() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for folder in _db_dirs():
        if not folder.is_dir():
            continue
        for name in BAN_NAMES:
            path = folder / name
            if not path.is_file():
                continue
            kind = _kind_from_name(name)
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                row = _parse_ban_line(line, kind)
                if not row:
                    continue
                key = f"{row['kind']}:{row['steamid'] or row['raw']}"
                if key in seen:
                    continue
                seen.add(key)
                row["source"] = str(path)
                rows.append(row)
    return rows


def kick_journal(limit: int = 40) -> list[dict[str, str]]:
    text = "\n".join((latest_text("user", 2), latest_text("console", 1)))
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not KICK_RE.search(line) and "disconnected" not in line.lower():
            continue
        if "fully connected" in line.lower():
            continue
        steam = ""
        match = STEAM_RE.search(line)
        if match:
            steam = match.group(1)
        rows.append({"line": line.strip(), "steamid": steam})
    return rows[-max(5, min(int(limit), 80)) :]


def snapshot() -> dict[str, Any]:
    bans = load_bans()
    return {
        "bans": bans,
        "count": len(bans),
        "kicks": kick_journal(),
        "note": "Список из db/ на зеркале. Если банов ещё не было — файлов нет.",
    }


def unban_command(steamid: str = "", name: str = "") -> str:
    steam = (steamid or "").strip()
    nick = (name or "").strip()
    if steam:
        return f"unbanid {steam}"
    if nick:
        return f'unbanuser "{nick}"'
    raise ValueError("Need steamid or name")
