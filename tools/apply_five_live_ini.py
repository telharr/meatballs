#!/usr/bin/env python3
"""Apply five-pack Mods= to live XLGAMES world.ini; verify FTP folders; wipe leftover Saves."""

from __future__ import annotations

import sys
from ftplib import error_perm
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ftp_client import is_protected_remote, load_dotenv  # noqa: E402
from mod_catalog import apply_lists_to_ini, parse_ini_list  # noqa: E402
from panel.prefs import remember_remote  # noqa: E402
from panel.servers import active_files_client, active_id, load_index, save_index  # noqa: E402
from panel.services.pack_merger import BACKUPS, _backup_ini_content, _remote_paths  # noqa: E402

LIVE_ID = "meatballs-xl"
FIVE = (
    "MeatballsLibraries",
    "MeatballsCore",
    "MeatballsKI5",
    "MeatballsCharacter",
    "MeatballsGameplay",
)
FIVE_WS = (
    "3796197817",
    "3796206775",
    "3796212345",
    "3796217229",
    "3796224319",
)


def log(msg: str) -> None:
    print(str(msg).encode("ascii", "replace").decode("ascii"), flush=True)


def set_active(server_id: str) -> None:
    index = load_index()
    index["active"] = server_id
    save_index(index)


def ftp_delete_tree(client, remote: str, *, allow_protected: bool, wipe_worlddict: bool) -> tuple[int, int]:
    files = 0
    dirs = 0

    def walk(ftp, path: str) -> None:
        nonlocal files, dirs
        try:
            entries = client.list_dir(ftp, path)
        except error_perm as exc:
            if "550" in str(exc):
                return
            raise
        for entry in entries:
            if entry.type == "dir":
                walk(ftp, entry.path)
                continue
            name = entry.path.replace("\\", "/").lower()
            if "worlddictionary" in name and not wipe_worlddict:
                continue
            if not allow_protected and is_protected_remote(entry.path, False):
                log(f"[wipe] protected skip {entry.path}")
                continue
            try:
                ftp.delete(entry.path)
                files += 1
            except error_perm as exc:
                if "550" not in str(exc):
                    raise
        try:
            ftp.rmd(path)
            dirs += 1
        except error_perm as exc:
            if "550" not in str(exc):
                raise

    with client.connect() as ftp:
        ftp.set_pasv(True)
        walk(ftp, remote)
    return files, dirs


def apply_world_ini(client, workshop_ids: list[str]) -> dict:
    paths = _remote_paths(LIVE_ID)
    previous = client.read_file(paths["ini_remote"])
    if isinstance(previous, bytes):
        previous = previous.decode("utf-8", errors="replace")
    updated = apply_lists_to_ini(previous, list(FIVE), workshop_ids)
    backup = _backup_ini_content(paths["ini_name"], previous)
    temp = BACKUPS / f".upload_{paths['ini_name']}"
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(updated, encoding="utf-8")
    try:
        client.upload_file(temp, paths["ini_remote"], allow_protected=True)
    finally:
        temp.unlink(missing_ok=True)
    remember_remote(paths["ini_name"], paths["ini_remote"], updated)
    return {
        "remote": paths["ini_remote"],
        "backup": str(backup),
        "mods": parse_ini_list(updated, "Mods"),
        "workshop_ids": parse_ini_list(updated, "WorkshopItems"),
    }


def verify_mods(client) -> None:
    paths = _remote_paths(LIVE_ID)
    with client.connect() as ftp:
        ftp.set_pasv(True)
        entries = client.list_dir(ftp, paths["mods_dir"])
        names = sorted(e.name for e in entries if e.type == "dir")
        log(f"[mods] remote folders={names}")
        for mid in FIVE:
            info = f"{paths['mods_dir']}/{mid}/42/mod.info"
            try:
                size = ftp.size(info)
                log(f"[mods] {mid} mod.info size={size}")
            except error_perm:
                log(f"[mods] MISSING {info}")


def main() -> int:
    load_dotenv()
    previous_active = active_id() or "local-dedi"
    set_active(LIVE_ID)
    log(f"[profile] {LIVE_ID} (was {previous_active})")
    wipe_saves = "--wipe-saves" in sys.argv
    workshop_ids = list(FIVE_WS) if "--workshop-items" in sys.argv else []
    try:
        client = active_files_client()
        client.config.timeout = 120
        verify_mods(client)
        log(f"[ini] apply five-pack, WorkshopItems={workshop_ids or '(empty)'}")
        ini = apply_world_ini(client, workshop_ids)
        log(f"[ini] {ini['remote']} mods={ini['mods']} ws={ini['workshop_ids']} backup={ini['backup']}")
        if wipe_saves:
            leftover = f"{_remote_paths(LIVE_ID)['root']}/Saves"
            log(f"[wipe] leftover {leftover}")
            f, d = ftp_delete_tree(client, leftover, allow_protected=True, wipe_worlddict=True)
            log(f"[wipe] leftover saves files={f} dirs={d}")
        log("[done] Restart the XLGAMES JVM in the hoster panel.")
        return 0
    finally:
        set_active(previous_active)
        log(f"[profile] restored {previous_active}")


if __name__ == "__main__":
    raise SystemExit(main())
