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


def detect_install_kind() -> str:
    """How this panel binary/process is installed (not which GitHub assets exist)."""
    forced = (os.environ.get("PANEL_INSTALL") or "").strip().lower()
    if forced in {"windows_setup", "docker", "git"}:
        return forced
    if getattr(sys, "frozen", False) and os.name == "nt":
        return "windows_setup"
    if Path("/.dockerenv").exists() or (os.environ.get("PANEL_DOCKER_PROJECT") or "").strip():
        return "docker"
    return "git"


def docker_project_dir() -> Path:
    raw = (os.environ.get("PANEL_DOCKER_PROJECT") or "/host/pz-panel").strip() or "/host/pz-panel"
    return Path(raw)


def docker_self_update_ready() -> bool:
    """True when the container can rebuild itself via Docker Engine API/CLI."""
    if detect_install_kind() != "docker":
        return False
    project = docker_project_dir()
    if not project.is_dir():
        return False
    has_compose = any((project / name).is_file() for name in ("docker-compose.yml", "compose.yml", "compose.yaml"))
    if not has_compose:
        return False
    sock = Path("/var/run/docker.sock")
    host = (os.environ.get("DOCKER_HOST") or "").strip()
    if host.startswith("tcp://") or host.startswith("http"):
        return True
    return sock.exists()


def _compose_file(project: Path) -> Path:
    for name in ("docker-compose.yml", "compose.yml", "compose.yaml"):
        path = project / name
        if path.is_file():
            return path
    raise RuntimeError(f"No compose file in {project}")


def _docker_compose_cmd(project: Path) -> list[str]:
    compose = _compose_file(project)
    # Image ships standalone docker-compose; plugin may be absent with static docker CLI
    if shutil.which("docker-compose"):
        return ["docker-compose", "-f", str(compose), "--project-directory", str(project)]
    return ["docker", "compose", "-f", str(compose), "--project-directory", str(project)]


def _copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def apply_docker_update(tag: str | None = None) -> dict[str, Any]:
    """Pull release sources into host project mount and rebuild the panel container."""
    if not docker_self_update_ready():
        raise RuntimeError(
            "Docker self-update not ready: mount docker.sock and PANEL_DOCKER_PROJECT "
            "(see packaging/templates/vps.docker-compose.yml)"
        )
    info = check_for_updates(force=True)
    if not info.get("ok"):
        raise RuntimeError(info.get("error") or "update check failed")
    latest = str(info.get("latest") or "").strip()
    tag_name = (tag or info.get("tag") or (f"v{latest}" if latest else "")).strip()
    if not tag_name:
        raise RuntimeError("No release tag to apply")
    if not tag_name.startswith("v"):
        tag_name = f"v{tag_name}"
    ver = tag_name.lstrip("vV")
    if _parse_semver(ver) < _parse_semver(current_version()):
        raise RuntimeError(f"Refusing downgrade {current_version()} → {ver}")

    project = docker_project_dir()
    repo = update_repo()
    url = f"https://github.com/{repo}/archive/refs/tags/{tag_name}.tar.gz"
    _set_job(
        phase="download",
        percent=5,
        message=f"Downloading {tag_name}",
        path=None,
        error=None,
        started_at=time.time(),
        finished_at=None,
    )
    work = Path(tempfile.mkdtemp(prefix="pz-docker-upd-"))
    try:
        tarball = work / "src.tar.gz"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as resp, tarball.open("wb") as out:
            shutil.copyfileobj(resp, out)
        _set_job(phase="extract", percent=35, message="Extracting sources")
        subprocess.run(["tar", "-xzf", str(tarball), "-C", str(work)], check=True, timeout=120)
        extracted = next((p for p in work.iterdir() if p.is_dir() and p.name.startswith("meatballs-")), None)
        if extracted is None or not (extracted / "panel").is_dir():
            raise RuntimeError("Unexpected archive layout from GitHub")

        _set_job(phase="sync", percent=55, message=f"Syncing into {project}")
        # Preserve host .env / data / mirror; refresh app sources for build context
        for rel in ("panel", "tools", "packaging"):
            src = extracted / rel
            if src.is_dir():
                _copy_tree(src, project / rel)
        for rel in ("Dockerfile", "run_panel.py"):
            src = extracted / rel
            if src.is_file():
                shutil.copy2(src, project / rel)
        # Never ship runtime state in build context
        for junk in (project / "panel" / "data", project / "panel" / "backups"):
            if junk.exists():
                shutil.rmtree(junk, ignore_errors=True)

        _set_job(phase="rebuild", percent=75, message="docker compose up -d --build")
        cmd = _docker_compose_cmd(project) + ["up", "-d", "--build"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-1500:]
            raise RuntimeError(f"docker compose failed ({proc.returncode}): {detail}")
        _set_job(
            phase="launched",
            percent=100,
            message=f"Rebuilding to {tag_name} — refresh the UI in ~30s",
            finished_at=time.time(),
        )
        return {
            "ok": True,
            "channel": "docker",
            "tag": tag_name,
            "project": str(project),
            "restart_hint": True,
        }
    except Exception as exc:
        _set_job(phase="error", message=str(exc), error=str(exc), finished_at=time.time())
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


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
    kind = detect_install_kind()
    setup_ok = bool(setup and kind == "windows_setup" and getattr(sys, "frozen", False) and os.name == "nt")
    docker_ok = bool(kind == "docker" and docker_self_update_ready() and available)
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
        "channel": kind,
        "install_kind": kind,
        "asset": None,
        "checked_at": now,
        "frozen": bool(getattr(sys, "frozen", False)),
        "apply_supported": bool(setup_ok or docker_ok),
        "docker_self_update_ready": docker_self_update_ready() if kind == "docker" else False,
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
