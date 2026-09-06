#!/usr/bin/env python3
"""Seed XLGAMES /steamapps/workshop/content/108600 then set WorkshopItems= for client auto-download."""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from ftplib import error_perm
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ftp_client import join_remote, load_dotenv, normalize_remote  # noqa: E402
from apply_five_live_ini import FIVE, FIVE_WS, apply_world_ini, log, set_active  # noqa: E402
from panel.servers import active_files_client, active_id  # noqa: E402

LIVE_ID = "meatballs-xl"
MIRROR = ROOT / ".mirror" / "meatballs-xl" / "mods"
CONTENT = "/steamapps/workshop/content/108600"
ACF_REMOTE = "/steamapps/workshop/appworkshop_108600.acf"


def steam_details(ids: tuple[str, ...]) -> dict[str, dict]:
    body = urllib.parse.urlencode(
        {"itemcount": len(ids), **{f"publishedfileids[{i}]": ids[i] for i in range(len(ids))}}
    ).encode()
    req = urllib.request.Request(
        "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
        data=body,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    out: dict[str, dict] = {}
    for row in payload["response"]["publishedfiledetails"]:
        if int(row.get("result") or 0) != 1:
            raise SystemExit(f"Steam item not public: {row}")
        out[str(row["publishedfileid"])] = row
    return out


def dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def ftp_put_missing(client, local_dir: Path, remote_dir: str) -> tuple[int, int]:
    files = sorted(p for p in local_dir.rglob("*") if p.is_file())
    uploaded = 0
    skipped = 0
    i = 0
    total = len(files)
    log(f"[put] {local_dir.name} 0/{total} skip=0 up=0")
    while i < total:
        try:
            with client.connect() as ftp:
                ftp.set_pasv(True)
                while i < total:
                    path = files[i]
                    rel = path.relative_to(local_dir).as_posix()
                    remote = join_remote(normalize_remote(remote_dir), rel)
                    local_size = path.stat().st_size
                    try:
                        remote_size = ftp.size(remote)
                    except error_perm:
                        remote_size = None
                    if remote_size == local_size:
                        skipped += 1
                        i += 1
                        if i % 400 == 0:
                            log(f"[put] {local_dir.name} {i}/{total} skip={skipped} up={uploaded}")
                        continue
                    parent = remote.rsplit("/", 1)[0]
                    client._ensure_remote_dirs(ftp, parent)
                    with path.open("rb") as handle:
                        ftp.storbinary(f"STOR {remote}", handle)
                    uploaded += 1
                    i += 1
                    if uploaded % 25 == 0:
                        log(f"[put] {local_dir.name} uploaded {uploaded} ({rel})")
        except OSError as exc:
            log(f"[put] reconnect {local_dir.name} after {exc}")
            time.sleep(3)
    log(f"[put] {local_dir.name} done uploaded={uploaded} skipped={skipped} total={total}")
    return uploaded, skipped


def write_acf(client, details: dict[str, dict]) -> None:
    installed = []
    item_details = []
    total = 0
    now = int(time.time())
    for mod_id, ws_id in zip(FIVE, FIVE_WS):
        local = MIRROR / mod_id
        size = dir_bytes(local)
        total += size
        row = details[ws_id]
        manifest = str(row.get("hcontent_file") or "")
        updated = int(row.get("time_updated") or now)
        installed.append(
            f'\t\t"{ws_id}"\n'
            f"\t\t{{\n"
            f'\t\t\t"size"\t\t"{size}"\n'
            f'\t\t\t"timeupdated"\t\t"{updated}"\n'
            f'\t\t\t"manifest"\t\t"{manifest}"\n'
            f"\t\t}}"
        )
        item_details.append(
            f'\t\t"{ws_id}"\n'
            f"\t\t{{\n"
            f'\t\t\t"manifest"\t\t"{manifest}"\n'
            f'\t\t\t"timeupdated"\t\t"{updated}"\n'
            f'\t\t\t"timetouched"\t\t"{now}"\n'
            f'\t\t\t"BytesDownloaded"\t\t"{size}"\n'
            f'\t\t\t"BytesToDownload"\t\t"{size}"\n'
            f'\t\t\t"latest_timeupdated"\t\t"{updated}"\n'
            f'\t\t\t"latest_manifest"\t\t"{manifest}"\n'
            f"\t\t}}"
        )
    text = (
        '"AppWorkshop"\n{\n'
        f'\t"appid"\t\t"108600"\n'
        f'\t"SizeOnDisk"\t\t"{total}"\n'
        f'\t"NeedsUpdate"\t\t"0"\n'
        f'\t"NeedsDownload"\t\t"0"\n'
        f'\t"TimeLastUpdated"\t\t"{now}"\n'
        f'\t"TimeLastAppRan"\t\t"{now}"\n'
        '\t"WorkshopItemsInstalled"\n\t{\n'
        + "\n".join(installed)
        + "\n\t}\n"
        + '\t"WorkshopItemDetails"\n\t{\n'
        + "\n".join(item_details)
        + "\n\t}\n}\n"
    )
    tmp = ROOT / "panel" / "backups" / ".upload_appworkshop_108600.acf"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    try:
        client.upload_file(tmp, ACF_REMOTE)
    finally:
        tmp.unlink(missing_ok=True)
    log(f"[acf] wrote {ACF_REMOTE} bytes_on_disk={total}")


def main() -> int:
    for mid in FIVE:
        if not (MIRROR / mid).is_dir():
            raise SystemExit(f"missing mirror pack {MIRROR / mid}")
    details = steam_details(FIVE_WS)
    for ws_id, row in details.items():
        log(f"[steam] {ws_id} vis={row.get('visibility')} banned={row.get('banned')} title={row.get('title')}")
    load_dotenv()
    previous = active_id() or "local-dedi"
    set_active(LIVE_ID)
    try:
        client = active_files_client()
        client.config.timeout = 180
        for mod_id, ws_id in zip(FIVE, FIVE_WS):
            dest = f"{CONTENT}/{ws_id}/mods/{mod_id}"
            log(f"[seed] {mod_id} -> {dest}")
            ftp_put_missing(client, MIRROR / mod_id, dest)
        write_acf(client, details)
        log("[ini] WorkshopItems= five MEATBALLS ids (client auto-download)")
        ini = apply_world_ini(client, list(FIVE_WS))
        log(f"[ini] {ini['remote']} mods={ini['mods']} ws={ini['workshop_ids']}")
        log("[done] Restart XLGAMES JVM. Do not restart before this line.")
        return 0
    finally:
        set_active(previous)
        log(f"[profile] restored {previous}")


if __name__ == "__main__":
    raise SystemExit(main())
