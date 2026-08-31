"""Parse vanilla PZ _chat.txt ChatMessage lines."""

from __future__ import annotations

import re
from typing import Any

from panel.logs_hub import latest_text

TS_RE = re.compile(r"^\[(\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]")
MSG_RE = re.compile(
    r"Got message:ChatMessage\{chat=([^,]+),\s*author='([^']*)',\s*text='(.*)'\}\.?\s*$"
)

CHANNEL_ALIASES: dict[str, set[str]] = {
    "global": {"general", "глобальный", "server", "сервер", "общий"},
    "local": {"say", "локальный", "shout", "крик", "радио", "radio"},
    "whisper": {"whisper", "личный", "шепот", "шёпот", "private", "pm"},
    "admin": {"admin", "админ", "администратор"},
}


def _channel_id(raw: str) -> str:
    name = (raw or "").strip().lower()
    for cid, aliases in CHANNEL_ALIASES.items():
        if name in aliases or any(alias in name for alias in aliases):
            return cid
    return "other"


def parse_chat(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        msg = MSG_RE.search(line)
        if not msg:
            continue
        ts_m = TS_RE.match(line)
        chat_name = msg.group(1).strip()
        rows.append(
            {
                "ts": ts_m.group(1) if ts_m else "",
                "chat": chat_name,
                "channel": _channel_id(chat_name),
                "author": msg.group(2),
                "text": msg.group(3),
            }
        )
    return rows


def snapshot(channel: str = "all", limit: int = 200) -> dict[str, Any]:
    wanted = (channel or "all").strip().lower()
    rows = parse_chat(latest_text("chat", max_files=12))
    if wanted and wanted != "all":
        rows = [row for row in rows if row["channel"] == wanted]
    rows = rows[-max(20, min(int(limit), 500)) :]
    return {
        "channel": wanted,
        "count": len(rows),
        "messages": rows,
        "note": "Личный чат только из лога. RCON whisper в PZ нет.",
    }
