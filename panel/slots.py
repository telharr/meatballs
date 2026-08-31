"""Named trainer NPCs (max 5). Does not spoof Steam Query."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from panel.prefs import load_prefs, save_prefs

PANEL = Path(__file__).resolve().parent
ROOT = PANEL.parent
DATA_FILE = PANEL / "data" / "slots.json"
MOD_DIR = ROOT / "src" / "mods" / "MeatballsSlots"
REMOTE_SLOTS = "/ServerWorld/Lua/mb_slots.txt"
REMOTE_MOD = "/ServerWorld/mods/MeatballsSlots"
MAX_SLOTS = 5
def _local_lua_dirs() -> tuple[Path, ...]:
    try:
        from panel.servers import cachedir_paths

        return tuple(root / "Lua" for root in cachedir_paths())
    except Exception:
        return (
            ROOT / ".mirror" / "ServerWorld" / "Lua",
            ROOT / ".cache" / "dedi-test" / "Lua",
        )

# Keep in sync with src/mods/MeatballsSlots/.../MeatballsSlots.lua
ROSTER: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Rook",
        "role": "Burglar",
        "role_ru": "Взломщик",
        "city": "West Point",
        "teaches": "Lockpicking",
    },
    {
        "id": 2,
        "name": "Otto",
        "role": "Mechanic",
        "role_ru": "Автомеханик",
        "city": "Riverside",
        "teaches": "Mechanics",
    },
    {
        "id": 3,
        "name": "Sarge",
        "role": "Veteran",
        "role_ru": "Военный",
        "city": "March Ridge",
        "teaches": "Aiming",
    },
    {
        "id": 4,
        "name": "Ash",
        "role": "Carpenter",
        "role_ru": "Плотник",
        "city": "Rosewood",
        "teaches": "Carpentry",
    },
    {
        "id": 5,
        "name": "Vera",
        "role": "Doctor",
        "role_ru": "Доктор",
        "city": "Brandenburg",
        "teaches": "Doctor",
    },
]

NEXT_TRAINER = {
    "name": "Anvil",
    "role_ru": "Кузнец",
    "city": "Muldraugh",
    "teaches": "Metalworking",
}


def clamp_count(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(MAX_SLOTS, n))


def active_npcs(count: int) -> list[dict[str, Any]]:
    n = clamp_count(count)
    return [dict(row) for row in ROSTER[:n]]


TRAINER_NAMES = frozenset(row["name"] for row in ROSTER)


def is_trainer_name(name: str) -> bool:
    return str(name or "").strip() in TRAINER_NAMES


def filter_real_players(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop trainer nicks so Игроки never mixes with NPC."""
    return [row for row in players if not is_trainer_name(row.get("name", ""))]


def encode_line(count: int, x: int = 0, y: int = 0, z: int = 0, prefix: str = "Dummy") -> str:
    return f"count={clamp_count(count)};x={int(x)};y={int(y)};z={int(z)}\n"


def snapshot() -> dict[str, Any]:
    prefs = load_prefs()
    stored = {}
    if DATA_FILE.exists():
        try:
            stored = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stored = {}
    count = clamp_count(stored.get("count", prefs.get("dummy_slots", 0)))
    return {
        "count": count,
        "max": MAX_SLOTS,
        "x": int(stored.get("x") or 0),
        "y": int(stored.get("y") or 0),
        "z": int(stored.get("z") or 0),
        "updated_at": stored.get("updated_at"),
        "remote": REMOTE_SLOTS,
        "mod_id": "MeatballsSlots",
        "roster": ROSTER,
        "npcs": active_npcs(count),
        "next": NEXT_TRAINER,
        "note": "Trainers are world NPCs only. Steam / RCON players stay real.",
    }


def _write_payload(data: dict[str, Any]) -> Path:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    line = encode_line(data["count"], data["x"], data["y"], data["z"])
    for folder in _local_lua_dirs():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "mb_slots.txt").write_text(line, encoding="utf-8")
    return DATA_FILE


def set_slots(count: int, x: int = 0, y: int = 0, z: int = 0, prefix: str = "Dummy") -> dict[str, Any]:
    data = {
        "count": clamp_count(count),
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_payload(data)
    save_prefs({"dummy_slots": data["count"]})
    return snapshot()


def write_temp_line(data: dict[str, Any] | None = None) -> Path:
    snap = data or snapshot()
    path = PANEL / "data" / ".mb_slots.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        encode_line(snap["count"], snap["x"], snap["y"], snap["z"]),
        encoding="utf-8",
    )
    return path


def iter_mod_files() -> list[tuple[Path, str]]:
    if not MOD_DIR.exists():
        return []
    out: list[tuple[Path, str]] = []
    for path in MOD_DIR.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(MOD_DIR).as_posix()
        out.append((path, f"{REMOTE_MOD}/{rel}"))
    return out
