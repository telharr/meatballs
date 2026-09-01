"""Zero-config SteamCMD detection and bootstrap for Workshop downloads."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import threading
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".cache" / "steamcmd"
LOCAL_DIR = ROOT / "steamcmd"

WIN_URL = "https://client-update.steamstatic.com/installer/steamcmd.zip"
LINUX_URL = "https://client-update.steamstatic.com/installer/steamcmd_linux.tar.gz"

_job_lock = threading.Lock()
_job: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "percent": 0,
    "message": "",
    "errors": [],
    "started_at": None,
    "finished_at": None,
    "path": None,
}


def _is_windows() -> bool:
    return os.name == "nt" or platform.system().lower().startswith("win")


def _expected_binary() -> str:
    return "steamcmd.exe" if _is_windows() else "steamcmd.sh"


def _candidate_paths() -> list[Path]:
    binary = _expected_binary()
    out: list[Path] = []
    for raw in (
        os.environ.get("STEAMCMD"),
        os.environ.get("STEAMCMD_PATH"),
    ):
        if raw and str(raw).strip():
            out.append(Path(str(raw).strip()))
    which = shutil.which("steamcmd") or shutil.which("steamcmd.exe")
    if which:
        out.append(Path(which))
    out.extend(
        [
            LOCAL_DIR / binary,
            CACHE_DIR / binary,
            ROOT / "steamcmd" / binary,
        ]
    )
    seen: set[str] = set()
    unique: list[Path] = []
    for path in out:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def detect_steamcmd() -> Path | None:
    for path in _candidate_paths():
        if path.is_file():
            return path
    return None


def _version_hint(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return mtime.strftime("%Y-%m-%d %H:%M")
    except OSError:
        return str(path)


def status() -> dict[str, Any]:
    path = detect_steamcmd()
    return {
        "installed": bool(path),
        "path": str(path) if path else "",
        "version_hint": _version_hint(path),
        "cache_dir": str(CACHE_DIR),
        "platform": "windows" if _is_windows() else "linux",
        "install": install_status(),
    }


def install_status() -> dict[str, Any]:
    with _job_lock:
        return dict(_job)


def _set_job(**kwargs: Any) -> None:
    with _job_lock:
        _job.update(kwargs)


def _download(url: str, dest: Path, on_progress: Any) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "MEATBALLS-Panel/3.15"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        read = 0
        chunk_size = 256 * 1024
        with dest.open("wb") as handle:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                read += len(chunk)
                if total > 0:
                    pct = min(99, int(read * 100 / total))
                    on_progress(
                        phase="download",
                        percent=pct,
                        message=f"Downloading SteamCMD… {pct}%",
                    )


def _extract(archive: Path, dest: Path, on_progress: Any) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    on_progress(phase="extract", percent=0, message="Extracting SteamCMD…")
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest)
    binary = dest / _expected_binary()
    if not binary.is_file():
        found = next(dest.rglob(_expected_binary()), None)
        if found:
            binary = found
    if not binary.is_file():
        raise FileNotFoundError(f"{_expected_binary()} not found after extract")
    if not _is_windows():
        binary.chmod(binary.stat().st_mode | 0o111)
    on_progress(phase="extract", percent=100, message=f"Extracted to {binary.parent}")
    return binary


def _self_update(binary: Path, on_progress: Any) -> None:
    on_progress(phase="update", percent=0, message="Running SteamCMD self-update…")
    cmd = [str(binary), "+quit"]
    proc = subprocess.run(
        cmd,
        cwd=str(binary.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    tail = (proc.stdout or proc.stderr or "")[-400:]
    if proc.returncode not in (0, 7):
        raise RuntimeError(f"SteamCMD bootstrap failed (exit {proc.returncode}): {tail[:240]}")
    on_progress(phase="update", percent=100, message="SteamCMD ready")


def _run_install() -> None:
    def on_progress(**payload: Any) -> None:
        _set_job(
            phase=str(payload.get("phase") or "running"),
            percent=int(payload.get("percent") or 0),
            message=str(payload.get("message") or ""),
        )

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        archive = CACHE_DIR / ("steamcmd.zip" if _is_windows() else "steamcmd_linux.tar.gz")
        url = WIN_URL if _is_windows() else LINUX_URL
        _download(url, archive, on_progress)
        binary = _extract(archive, CACHE_DIR, on_progress)
        _self_update(binary, on_progress)
        _set_job(
            running=False,
            phase="done",
            percent=100,
            message="SteamCMD installed",
            path=str(binary),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as exc:
        _set_job(
            running=False,
            phase="error",
            message=str(exc)[:400],
            errors=[str(exc)[:400]],
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


def start_install() -> dict[str, Any]:
    snap = install_status()
    if snap.get("running"):
        raise RuntimeError("SteamCMD install already running")
    if detect_steamcmd():
        path = detect_steamcmd()
        return {
            "ok": True,
            "skipped": True,
            "message": "SteamCMD already installed",
            "path": str(path),
            "status": status(),
        }
    _set_job(
        running=True,
        phase="starting",
        percent=0,
        message="Preparing download…",
        errors=[],
        started_at=datetime.now().isoformat(timespec="seconds"),
        finished_at=None,
        path=None,
    )
    thread = threading.Thread(target=_run_install, daemon=True)
    thread.start()
    return {"ok": True, "started": True, "status": install_status()}


def resolve_steamcmd() -> Path:
    """Used by workshop downloader — detect or raise with bootstrap hint."""
    path = detect_steamcmd()
    if path:
        return path
    raise FileNotFoundError(
        "SteamCMD not found. Install via Workshop tab or set STEAMCMD / ./steamcmd/"
    )
