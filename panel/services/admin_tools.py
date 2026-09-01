"""AdminTools panel bridge: city wipe file drop + RCON notify, city catalog."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
PANEL = Path(__file__).resolve().parents[1]
CMD_FILE = "mb_admintools_cmd.txt"
REMOTE_DEFAULT = "/ServerWorld/Lua/mb_admintools_cmd.txt"

# Keep in sync with src/mods/AdminTools/.../AdminTools.lua
CITIES: list[dict[str, Any]] = [
    {"id": "muldraugh", "name": "Muldraugh", "x1": 10540, "y1": 9150, "x2": 11020, "y2": 10120},
    {"id": "westpoint", "name": "West Point", "x1": 11140, "y1": 6600, "x2": 12240, "y2": 7380},
    {"id": "rosewood", "name": "Rosewood", "x1": 7900, "y1": 11140, "x2": 8700, "y2": 12200},
    {"id": "riverside", "name": "Riverside", "x1": 5700, "y1": 5100, "x2": 6900, "y2": 6000},
    {"id": "louisville", "name": "Louisville", "x1": 11700, "y1": 1000, "x2": 14700, "y2": 4500},
    {"id": "marchridge", "name": "March Ridge", "x1": 9700, "y1": 12600, "x2": 10500, "y2": 13200},
    {"id": "fallaslake", "name": "Fallas Lake", "x1": 7000, "y1": 8200, "x2": 7800, "y2": 8800},
]


def list_cities() -> dict[str, Any]:
    return {
        "cities": CITIES,
        "count": len(CITIES),
        "cmd_file": CMD_FILE,
        "note": "In-game wipe via Lua/mb_admintools_cmd.txt + RCON servermsg. Needs AdminTools mod loaded.",
    }


def get_city(city_id: str) -> dict[str, Any] | None:
    cid = (city_id or "").strip().lower()
    for city in CITIES:
        if city["id"] == cid:
            return city
    return None


def _local_lua_dirs() -> list[Path]:
    try:
        from panel.servers import cachedir_paths

        return [root / "Lua" for root in cachedir_paths()]
    except Exception:
        return [
            ROOT / ".mirror" / "ServerWorld" / "Lua",
            ROOT / ".cache" / "dedi-test" / "Lua",
        ]


def remote_cmd_path() -> str:
    try:
        from panel.servers import active_profile

        root = str((active_profile().get("files") or {}).get("root") or "/ServerWorld").rstrip("/")
        return f"{root}/Lua/{CMD_FILE}"
    except Exception:
        return REMOTE_DEFAULT


def encode_city_wipe_line(
    city_id: str,
    *,
    refill_loot: bool = True,
    reconstruct_containers: bool = False,
    nonce: str | None = None,
) -> str:
    token = nonce or uuid4().hex[:12]
    return (
        f"v1|citywipe|{city_id}|"
        f"{1 if refill_loot else 0}|{1 if reconstruct_containers else 0}|"
        f"{token}|panel"
    )


def write_local_cmd(line: str) -> list[str]:
    written: list[str] = []
    for folder in _local_lua_dirs():
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / CMD_FILE
        path.write_text(line.strip() + "\n", encoding="utf-8")
        written.append(str(path))
    return written


def trigger_city_wipe(
    city_id: str,
    *,
    refill_loot: bool = True,
    reconstruct_containers: bool = False,
    upload: bool = True,
    rcon_notify: bool = True,
) -> dict[str, Any]:
    city = get_city(city_id)
    if not city:
        raise ValueError(f"Unknown city_id: {city_id}")

    line = encode_city_wipe_line(
        city["id"],
        refill_loot=refill_loot,
        reconstruct_containers=reconstruct_containers,
    )
    local_paths = write_local_cmd(line)
    remote = remote_cmd_path()
    uploaded: dict[str, Any] | None = None
    upload_error: str | None = None

    if upload:
        try:
            from panel.servers import active_files_client

            client = active_files_client()
            PANEL.joinpath("backups").mkdir(parents=True, exist_ok=True)
            tmp_path = PANEL / "backups" / f".admintools_cmd_{uuid4().hex[:8]}.txt"
            tmp_path.write_text(line.strip() + "\n", encoding="utf-8")
            try:
                uploaded = client.upload_file(tmp_path, remote)
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        except Exception as exc:
            upload_error = str(exc)[:300]

    rcon_out: str | None = None
    rcon_error: str | None = None
    if rcon_notify:
        msg = (
            f"[AdminTools] City wipe queued: {city['name']} "
            f"(loot={'on' if refill_loot else 'off'}, "
            f"containers={'on' if reconstruct_containers else 'off'})"
        )
        try:
            from panel.rcon_client import rcon_execute

            rcon_out = rcon_execute(f'servermsg "{msg}"')
        except Exception as exc:
            rcon_error = str(exc)[:300]

    return {
        "ok": True,
        "city": city,
        "line": line,
        "local_paths": local_paths,
        "remote": remote,
        "uploaded": uploaded,
        "upload_error": upload_error,
        "rcon": rcon_out,
        "rcon_error": rcon_error,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "hint": "Server must load AdminTools; wipe runs on next OnTick after reading Lua command file.",
    }
