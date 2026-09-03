"""Panel self-update via GitHub Releases (Sprint 11)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from panel.paths import DATA_DIR, UPDATES_DIR, ensure_state_dirs
from panel.prefs import load_prefs, save_prefs

DEFAULT_REPO = "telharr/meatballs"
UA = "PZControlPanel-Updater/1.0"
_lock = threading.Lock()
_job: dict[str, Any] = {
    "phase": "idle",
    "percent": 0,
    "message": "",
    "path": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def current_version() -> str:
    try:
        from panel.version import __version__

        return str(__version__)
    except Exception:
        return os.environ.get("PANEL_VERSION", "0.0.0").strip() or "0.0.0"


def update_repo() -> str:
    return (os.environ.get("PANEL_UPDATE_REPO") or DEFAULT_REPO).strip() or DEFAULT_REPO


def _parse_semver(text: str) -> tuple[int, ...]:
    raw = (text or "").strip().lstrip("vV")
    parts = re.split(r"[^\d]+", raw)
    nums = []
    for p in parts:
        if not p:
            continue
        try:
            nums.append(int(p))
        except ValueError:
            break
        if len(nums) >= 3:
            break
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def version_gt(a: str, b: str) -> bool:
    return _parse_semver(a) > _parse_semver(b)


def _http_json(url: str, timeout: float = 20.0) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": UA,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (os.environ.get("PANEL_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _find_setup_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred = []
    for a in assets or []:
        name = str(a.get("name") or "")
        lower = name.lower()
        if not lower.endswith(".exe"):
            continue
        if "setup" in lower or "pzcontrolpanel" in lower:
            preferred.append(a)
    if preferred:
        # Prefer names containing setup
        setup = [a for a in preferred if "setup" in str(a.get("name") or "").lower()]
        return (setup or preferred)[0]
    return None


def _find_sha_for(asset_name: str, assets: list[dict[str, Any]]) -> str | None:
    for a in assets or []:
        name = str(a.get("name") or "").lower()
        if name in ("sha256sums", "sha256sums.txt", "checksums.txt"):
            url = a.get("browser_download_url")
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[-1].endswith(asset_name):
                        return parts[0].lower()
                    if len(parts) >= 2 and asset_name in parts[-1]:
                        return parts[0].lower()
            except Exception:
                return None
    return None


def check_for_updates(*, force: bool = False) -> dict[str, Any]:
    ensure_state_dirs()
    local = current_version()
    prefs = load_prefs()
    snooze = str(prefs.get("update_snooze_version") or "")
    repo = update_repo()
    cache_path = DATA_DIR / "update_check.json"
    now = time.time()
    if not force and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            # Short TTL: stale "no update" must not hide a just-published GitHub release.
            if now - float(cached.get("checked_at") or 0) < 300 and cached.get("repo") == repo and cached.get("ok") is not False:
                latest_cached = str(cached.get("latest") or local)
                cached["current"] = local
                cached["update_available"] = bool(latest_cached and version_gt(latest_cached, local))
                cached["snoozed"] = bool(cached["update_available"] and snooze == latest_cached)
                return cached
        except Exception:
            pass

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        release = _http_json(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "ok": True,
                "current": local,
                "latest": local,
                "update_available": False,
                "message": "No GitHub releases yet",
                "repo": repo,
                "checked_at": now,
            }
        return {"ok": False, "current": local, "error": f"GitHub HTTP {exc.code}", "repo": repo, "checked_at": now}
    except Exception as exc:
        return {"ok": False, "current": local, "error": str(exc), "repo": repo, "checked_at": now}

    tag = str(release.get("tag_name") or "").strip()
    latest = tag.lstrip("vV") or tag
    assets = release.get("assets") or []
    setup = _find_setup_asset(assets)
    sha = _find_sha_for(str(setup.get("name") if setup else ""), assets) if setup else None
    available = bool(latest and version_gt(latest, local))
    result = {
        "ok": True,
        "current": local,
        "latest": latest,
        "tag": tag,
        "update_available": available,
        "snoozed": bool(available and snooze == latest),
        "name": release.get("name") or tag,
        "body": (release.get("body") or "")[:4000],
        "html_url": release.get("html_url"),
        "published_at": release.get("published_at"),
        "repo": repo,
        "channel": "windows_setup" if setup else ("docker_or_git" if available else None),
        "asset": None,
        "checked_at": now,
        "frozen": bool(getattr(sys, "frozen", False)),
        "apply_supported": bool(setup and getattr(sys, "frozen", False) and os.name == "nt"),
        "docker_hint": (
            f"curl -fsSL https://raw.githubusercontent.com/telharr/meatballs/v{latest}/packaging/deploy_vps.sh | bash -s -- {latest}"
            if available
            else "docker compose up -d --build"
        ),
        "git_hint": f"git fetch && git checkout {tag} && restart panel",
    }
    if setup:
        result["asset"] = {
            "name": setup.get("name"),
            "size": setup.get("size"),
            "url": setup.get("browser_download_url"),
            "sha256": sha,
        }
    try:
        cache_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass
    return result


def snooze_update(version: str | None = None) -> dict[str, Any]:
    info = check_for_updates(force=False)
    ver = (version or info.get("latest") or "").strip()
    save_prefs({"update_snooze_version": ver})
    return {"ok": True, "snoozed": ver}


def job_status() -> dict[str, Any]:
    with _lock:
        return dict(_job)


def _set_job(**kwargs: Any) -> None:
    with _lock:
        _job.update(kwargs)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_latest_setup() -> dict[str, Any]:
    ensure_state_dirs()
    info = check_for_updates(force=True)
    if not info.get("ok"):
        raise RuntimeError(info.get("error") or "update check failed")
    asset = info.get("asset") or {}
    url = asset.get("url")
    name = asset.get("name") or "update.exe"
    if not url:
        raise RuntimeError("No Windows setup asset on latest release")
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPDATES_DIR / name
    _set_job(phase="download", percent=0, message=f"Downloading {name}", path=str(dest), error=None, started_at=time.time(), finished_at=None)
    tmp = Path(tempfile.mkstemp(prefix="pz-upd-", suffix=".exe")[1])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                pct = int(done * 100 / total) if total else 0
                _set_job(percent=min(99, pct), message=f"Downloading {name} ({done // 1024} KB)")
        expect = (asset.get("sha256") or "").lower().strip()
        if expect:
            digest = _sha256_file(tmp)
            if digest != expect:
                raise RuntimeError(f"SHA-256 mismatch: got {digest}, expected {expect}")
        shutil.move(str(tmp), str(dest))
        _set_job(phase="ready", percent=100, message="Download ready", path=str(dest), finished_at=time.time())
        return {"ok": True, "path": str(dest), "sha256_ok": bool(expect), "info": info}
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        _set_job(phase="error", message=str(exc), error=str(exc), finished_at=time.time())
        raise


def apply_downloaded_setup(path: str | None = None) -> dict[str, Any]:
    """Launch Inno setup; does not wait. Panel should exit after this on Windows."""
    ensure_state_dirs()
    target = Path(path) if path else None
    if target is None:
        with _lock:
            p = _job.get("path")
        target = Path(p) if p else None
    if target is None or not target.is_file():
        # pick newest exe in updates dir
        candidates = sorted(UPDATES_DIR.glob("*.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise RuntimeError("No downloaded installer — download first")
        target = candidates[0]
    if os.name != "nt":
        raise RuntimeError("In-app apply is only supported on Windows installer builds")
    # /SILENT keeps UI minimal; .env uses onlyifdoesntexist in Inno
    args = [str(target), "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART"]
    _set_job(phase="launching", message=f"Starting {target.name}", path=str(target))
    subprocess.Popen(args, cwd=str(target.parent), close_fds=True)
    _set_job(phase="launched", message="Installer started — panel will restart after setup", finished_at=time.time())
    return {"ok": True, "path": str(target), "restart_hint": True}


def backup_state_zip() -> Path:
    """Zip DATA_DIR (+ note) into BACKUPS before apply."""
    from panel.paths import BACKUPS_DIR

    ensure_state_dirs()
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = BACKUPS_DIR / f"pre-update-{stamp}"
    archive = shutil.make_archive(str(base), "zip", root_dir=str(DATA_DIR))
    return Path(archive)
