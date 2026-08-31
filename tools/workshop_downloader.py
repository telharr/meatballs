#!/usr/bin/env python3
"""SteamCMD batch downloader for Project Zomboid Workshop mods (AppID 108600)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

PZ_APP_ID = "108600"
DEFAULT_STEAMCMD = Path("steamcmd") / ("steamcmd.exe" if os.name == "nt" else "steamcmd.sh")
DEFAULT_OUTPUT = Path(".cache") / "workshop"
ProgressCb = Callable[[dict[str, Any]], None]


def find_steamcmd(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"SteamCMD not found at {path}")
        return path
    env = (os.environ.get("STEAMCMD") or os.environ.get("STEAMCMD_PATH") or "").strip()
    if env:
        path = Path(env)
        if path.exists():
            return path
    if DEFAULT_STEAMCMD.exists():
        return DEFAULT_STEAMCMD
    which = shutil.which("steamcmd") or shutil.which("steamcmd.exe")
    if which:
        return Path(which)
    raise FileNotFoundError(
        "SteamCMD not found. Install to ./steamcmd/, set STEAMCMD, or pass --steamcmd path."
    )


def workshop_content_dir(install_dir: Path, workshop_id: str) -> Path:
    return install_dir / "steamapps" / "workshop" / "content" / PZ_APP_ID / str(workshop_id)


def find_mod_dirs(workshop_item_dir: Path) -> list[Path]:
    """Return folders that contain mod.info under a Workshop item tree."""
    if not workshop_item_dir.is_dir():
        return []
    found: list[Path] = []
    for info in workshop_item_dir.rglob("mod.info"):
        found.append(info.parent)
    return found


def link_or_copy(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    try:
        dest.symlink_to(src, target_is_directory=True)
        return "symlink"
    except OSError:
        shutil.copytree(src, dest, dirs_exist_ok=True)
        return "copy"


def install_workshop_item_into_mods(workshop_item_dir: Path, mods_dir: Path) -> list[dict[str, str]]:
    """Copy/link each mod folder from a Workshop item into mods_dir."""
    mods_dir.mkdir(parents=True, exist_ok=True)
    installed: list[dict[str, str]] = []
    for mod_dir in find_mod_dirs(workshop_item_dir):
        dest = mods_dir / mod_dir.name
        method = link_or_copy(mod_dir, dest)
        installed.append({"id": mod_dir.name, "path": str(dest), "method": method})
    return installed


def download_mod(
    steamcmd: Path,
    workshop_id: str,
    output_dir: Path,
    username: str | None = None,
    *,
    on_progress: ProgressCb | None = None,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    login = f"+login {username}" if username else "+login anonymous"
    script_lines = [
        login,
        f"+force_install_dir {output_dir.resolve()}",
        f"+workshop_download_item {PZ_APP_ID} {workshop_id}",
        "+quit",
    ]
    cmd = [str(steamcmd)] + script_lines
    if on_progress:
        on_progress(
            {
                "phase": "downloading",
                "workshop_id": workshop_id,
                "message": f"SteamCMD workshop_download_item {workshop_id}",
            }
        )
    print(f"[workshop_downloader] Downloading workshop item {workshop_id} -> {output_dir}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            print(line)
            if on_progress:
                on_progress(
                    {
                        "phase": "steamcmd",
                        "workshop_id": workshop_id,
                        "message": line[:240],
                    }
                )
    return int(proc.wait())


def download_batch(
    workshop_ids: list[str],
    output_dir: Path,
    *,
    steamcmd: Path | None = None,
    username: str | None = None,
    mods_dir: Path | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Download many Workshop items; optionally install into mods_dir for smoke/local."""
    binary = steamcmd or find_steamcmd(None)
    started = time.time()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    total = len(workshop_ids)
    for idx, wid in enumerate(workshop_ids, start=1):
        wid = str(wid).strip()
        if not wid:
            continue
        if on_progress:
            on_progress(
                {
                    "phase": "item",
                    "workshop_id": wid,
                    "index": idx,
                    "total": total,
                    "percent": int((idx - 1) * 100 / max(total, 1)),
                    "message": f"Downloading {wid} ({idx}/{total})",
                }
            )
        code = download_mod(binary, wid, output_dir, username, on_progress=on_progress)
        item_dir = workshop_content_dir(output_dir, wid)
        installed: list[dict[str, str]] = []
        if code == 0 and mods_dir is not None and item_dir.is_dir():
            installed = install_workshop_item_into_mods(item_dir, mods_dir)
        row = {
            "workshop_id": wid,
            "ok": code == 0 and item_dir.is_dir(),
            "exit_code": code,
            "content_dir": str(item_dir),
            "installed": installed,
        }
        if not row["ok"]:
            errors.append(f"{wid}: steamcmd exit {code}" if code else f"{wid}: content missing")
        results.append(row)
        if on_progress:
            on_progress(
                {
                    "phase": "item_done",
                    "workshop_id": wid,
                    "index": idx,
                    "total": total,
                    "percent": int(idx * 100 / max(total, 1)),
                    "ok": row["ok"],
                    "message": f"Done {wid}",
                }
            )
    if on_progress:
        on_progress({"phase": "done", "percent": 100, "message": "Batch complete"})
    return {
        "ok": not errors,
        "results": results,
        "errors": errors,
        "output_dir": str(output_dir),
        "mods_dir": str(mods_dir) if mods_dir else None,
        "elapsed_seconds": round(time.time() - started, 1),
        "count": len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download PZ Workshop mods via SteamCMD")
    parser.add_argument("workshop_ids", nargs="+", help="One or more Workshop item IDs")
    parser.add_argument("--steamcmd", help="Path to steamcmd binary")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Download output directory")
    parser.add_argument("--mods-dir", help="Also copy/link mods into this folder")
    parser.add_argument("--username", help="Steam username (omit for anonymous)")
    args = parser.parse_args()

    try:
        steamcmd = find_steamcmd(args.steamcmd)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = download_batch(
        args.workshop_ids,
        Path(args.output),
        steamcmd=steamcmd,
        username=args.username,
        mods_dir=Path(args.mods_dir) if args.mods_dir else None,
    )
    if result["errors"]:
        for err in result["errors"]:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
