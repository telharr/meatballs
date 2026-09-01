"""Typed log tails: server-console + ServerWorld/Logs (vanilla + LogExtender)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PANEL = Path(__file__).resolve().parent


def _mirror_roots() -> list[Path]:
    try:
        from panel.servers import cachedir_paths

        return cachedir_paths()
    except Exception:
        return [ROOT / ".mirror" / "ServerWorld", ROOT / ".cache" / "dedi-test"]
REMOTE_LOGS = "/ServerWorld/Logs"
REMOTE_CONSOLE = "/ServerWorld/server-console.txt"

KINDS: dict[str, dict[str, str]] = {
    "console": {"label": "server-console", "suffix": "server-console.txt"},
    "chat": {"label": "чат", "suffix": "_chat.txt"},
    "user": {"label": "игроки (вход/выход)", "suffix": "_user.txt"},
    "player": {"label": "LogExtender player", "suffix": "_player.txt"},
    "safehouse": {"label": "приваты", "suffix": "_safehouse.txt"},
    "admin": {"label": "админ", "suffix": "_admin.txt"},
    "cmd": {"label": "команды", "suffix": "_cmd.txt"},
    "pvp": {"label": "PVP", "suffix": "_pvp.txt"},
}


def _kind_of(name: str) -> str | None:
    lower = name.lower()
    if lower == "server-console.txt" or lower.endswith("server-console.txt"):
        return "console"
    for kind, meta in KINDS.items():
        if kind == "console":
            continue
        if lower.endswith(meta["suffix"]):
            return kind
    return None


def _iter_local_logs() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in _mirror_roots():
        if not root.exists():
            continue
        console = root / "server-console.txt"
        if console.is_file() and str(console) not in seen:
            seen.add(str(console))
            found.append(
                {
                    "kind": "console",
                    "name": console.name,
                    "path": str(console),
                    "source": "mirror",
                    "mtime": console.stat().st_mtime,
                    "size": console.stat().st_size,
                }
            )
        logs = root / "Logs"
        if not logs.is_dir():
            continue
        for path in logs.rglob("*.txt"):
            if not path.is_file():
                continue
            kind = _kind_of(path.name)
            if not kind or str(path) in seen:
                continue
            seen.add(str(path))
            found.append(
                {
                    "kind": kind,
                    "name": path.name,
                    "path": str(path),
                    "source": "mirror",
                    "mtime": path.stat().st_mtime,
                    "size": path.stat().st_size,
                }
            )
    found.sort(key=lambda row: row.get("mtime") or 0, reverse=True)
    return found


def catalog() -> dict[str, Any]:
    files = _iter_local_logs()
    latest: dict[str, dict[str, Any]] = {}
    for row in files:
        latest.setdefault(row["kind"], row)
    return {
        "kinds": [
            {"id": kid, "label": meta["label"], "has_file": kid in latest}
            for kid, meta in KINDS.items()
        ],
        "files": files[:80],
        "latest": latest,
    }


def _tail_text(text: str, lines: int) -> tuple[str, int]:
    all_lines = text.splitlines()
    tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
    return "\n".join(tail), len(all_lines)


def tail_kind(kind: str, lines: int = 400) -> dict[str, Any]:
    kid = (kind or "console").strip().lower()
    if kid not in KINDS:
        raise ValueError(f"Unknown log kind: {kind}")
    lines = max(50, min(int(lines), 5000))
    files = [row for row in _iter_local_logs() if row["kind"] == kid]
    if not files:
        return {
            "kind": kid,
            "label": KINDS[kid]["label"],
            "filename": None,
            "source": None,
            "total_lines": 0,
            "lines": lines,
            "content": "",
        }
    chosen = files[0]
    text = Path(chosen["path"]).read_text(encoding="utf-8", errors="replace")
    content, total = _tail_text(text, lines)
    return {
        "kind": kid,
        "label": KINDS[kid]["label"],
        "filename": chosen["name"],
        "path": chosen["path"],
        "source": chosen["source"],
        "total_lines": total,
        "lines": lines,
        "content": content,
    }


def latest_text(kind: str, max_files: int = 3) -> str:
    chunks: list[str] = []
    count = 0
    for row in _iter_local_logs():
        if row["kind"] != kind:
            continue
        chunks.append(Path(row["path"]).read_text(encoding="utf-8", errors="replace"))
        count += 1
        if count >= max_files:
            break
    return "\n".join(chunks)


def recent_errors(limit: int = 5) -> list[str]:
    data = tail_kind("console", 800)
    hits = [
        line
        for line in (data.get("content") or "").splitlines()
        if "ERROR" in line.upper() or "EXCEPTION" in line.upper()
    ]
    return hits[-limit:]


# —— Admin command audit ——

_TS_RE = re.compile(
    r"^\[(?P<ts>\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]\s*(?P<body>.*)$"
)
_STEAM_ACT_RE = re.compile(
    r'^(?P<steamid>\d{15,20})\s+"(?P<name>[^"]+)"\s+(?P<action>.+?)(?:\s+@\s+(?P<coords>[\d,\-]+))?\s*$'
)
_SLASH_RE = re.compile(
    r'(?P<name>\S+)\s+(?:used\s+command|executed|ran)[:\s]+/?(?P<cmd>\S+)(?:\s+(?P<args>.*))?$',
    re.I,
)
_BARE_SLASH_RE = re.compile(r"^/?(?P<cmd>\S+)(?:\s+(?P<args>.*))?$")

HIGH_RISK = frozenset(
    {
        "ban",
        "banid",
        "banuser",
        "unban",
        "unbanid",
        "setaccesslevel",
        "teleport",
        "teleportto",
        "gunload",
        "additem",
        "createhorde",
        "removeuserfromwhitelist",
        "adduser",
        "kick",
        "kickuser",
        "godmod",
        "invisible",
        "noclip",
        "citywipe",
        "triggercitywipe",
    }
)

MEDIUM_RISK = frozenset(
    {
        "alarm",
        "chopper",
        "thunder",
        "chopper",
        "reloadoptions",
        "save",
        "quit",
        "servermsg",
        "players",
    }
)


def _severity_for(command: str) -> str:
    key = (command or "").lower().lstrip("/")
    base = key.split(".", 1)[0]
    if base in HIGH_RISK or key in HIGH_RISK:
        return "high"
    if base in MEDIUM_RISK:
        return "medium"
    if key.startswith("admin") or "wipe" in key or "ban" in key:
        return "high"
    return "low"


def _parse_audit_line(raw: str, source_kind: str) -> dict[str, Any] | None:
    line = (raw or "").strip()
    if not line:
        return None
    ts = ""
    body = line
    m = _TS_RE.match(line)
    if m:
        ts = m.group("ts")
        body = m.group("body").strip()

    admin = ""
    steamid = ""
    command = ""
    args = ""
    coords = ""
    target = ""

    sm = _STEAM_ACT_RE.match(body)
    if sm:
        steamid = sm.group("steamid") or ""
        admin = sm.group("name") or ""
        action = (sm.group("action") or "").strip()
        coords = sm.group("coords") or ""
        # action may be "ban Player" or "vehicle.damageWindow"
        parts = action.split(None, 1)
        command = parts[0] if parts else action
        args = parts[1] if len(parts) > 1 else ""
        if args:
            target = args.split()[0]
    else:
        slash = _SLASH_RE.search(body)
        if slash:
            admin = slash.group("name") or ""
            command = slash.group("cmd") or ""
            args = (slash.group("args") or "").strip()
            target = args.split()[0] if args.split() else ""
        elif "AdminTools" in body or "citywipe" in body.lower():
            command = "citywipe" if "wipe" in body.lower() else "admintools"
            args = body
            admin = "panel/server"
        else:
            # Skip noisy non-admin chatter in cmd logs (e.g. vehicle.damageWindow for players)
            # unless kind is admin
            if source_kind == "cmd" and "." in body and " " in body and not body.lstrip().startswith("/"):
                # still record but mark low — filter later for high-only UIs
                sm2 = _STEAM_ACT_RE.match(body)
                if not sm2 and '"' not in body:
                    return None
            bare = _BARE_SLASH_RE.match(body.lstrip("/"))
            if bare and source_kind == "admin":
                command = bare.group("cmd") or ""
                args = (bare.group("args") or "").strip()
            else:
                return None

    command = command.lstrip("/")
    severity = _severity_for(command)
    # Drop ultra-noisy player actions from cmd unless high/medium
    if source_kind == "cmd" and severity == "low" and "." in command:
        return None

    return {
        "ts": ts,
        "admin": admin,
        "steamid": steamid,
        "command": command,
        "args": args,
        "target": target,
        "coords": coords,
        "severity": severity,
        "source": source_kind,
        "raw": line[:400],
    }


def audit_actions(limit: int = 200) -> dict[str, Any]:
    limit = max(20, min(int(limit), 1000))
    rows: list[dict[str, Any]] = []
    for kind in ("admin", "cmd"):
        for row in _iter_local_logs():
            if row["kind"] != kind:
                continue
            try:
                text = Path(row["path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                parsed = _parse_audit_line(line, kind)
                if parsed:
                    parsed["file"] = row["name"]
                    rows.append(parsed)
            break  # latest file per kind only

    # newest first when timestamps sortable as DD-MM-YY — keep file order reverse
    rows.reverse()
    high = sum(1 for r in rows if r["severity"] == "high")
    return {
        "actions": rows[:limit],
        "count": min(len(rows), limit),
        "total_parsed": len(rows),
        "high_risk": high,
        "kinds": ["admin", "cmd"],
    }
