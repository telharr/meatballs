"""Read LogExtender dump + _safehouse.txt journal."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from panel.logs_hub import latest_text

ROOT = Path(__file__).resolve().parents[1]
def _dump_candidates() -> list[Path]:
    found = [Path(__file__).resolve().parent / "data" / "mb_safehouses.json"]
    try:
        from panel.servers import cachedir_paths

        found = [root / "Lua" / "mb_safehouses.json" for root in cachedir_paths()] + found
    except Exception:
        found = [
            ROOT / ".mirror" / "ServerWorld" / "Lua" / "mb_safehouses.json",
            ROOT / ".cache" / "dedi-test" / "Lua" / "mb_safehouses.json",
        ] + found
    return found
REMOTE_DUMP = "/ServerWorld/Lua/mb_safehouses.json"


def _load_dump() -> dict[str, Any] | None:
    for path in _dump_candidates():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            data["source"] = str(path)
            return data
    return None


def _parse_journal(text: str, limit: int = 40) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if "safehouse" not in line.lower() and "приват" not in line.lower():
            continue
        rows.append({"line": line.strip()})
    return rows[-max(5, min(int(limit), 80)) :]


def snapshot() -> dict[str, Any]:
    dump = _load_dump() or {}
    houses = dump.get("safehouses") or dump.get("houses") or []
    factions = dump.get("factions") or []
    return {
        "safehouses": houses,
        "factions": factions,
        "updated_at": dump.get("updated_at"),
        "source": dump.get("source"),
        "remote": REMOTE_DUMP,
        "journal": _parse_journal(latest_text("safehouse", 3)),
        "note": (
            "Текущий список — из Lua/mb_safehouses.json (LogExtender). "
            "Продление срока в сейве панели не пишем. Saves не трогаем."
            if houses
            else "Нет дампа приватов. Нужен рестарт хоста с обновлённым LogExtender "
            "или события в _safehouse.txt."
        ),
    }
