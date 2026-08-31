"""Typed log tails: server-console + ServerWorld/Logs (vanilla + LogExtender)."""

from __future__ import annotations

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
