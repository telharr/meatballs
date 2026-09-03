"""Persistent state paths — separate from install/app tree (Sprint 11).

Resolution order for DATA_DIR:
1. PANEL_STATE_DIR / PANEL_DATA_DIR env (explicit)
2. Frozen Windows exe → %LOCALAPPDATA%/PZControlPanel/data
3. Frozen other → ~/.local/share/pz-control-panel/data
4. Dev / Docker → panel/data (Docker already symlinks to /data volume)

On first frozen start, legacy panel/data next to the exe is copied into the new location
(never deletes the legacy copy).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PANEL = Path(__file__).resolve().parent
ROOT = PANEL.parent
LEGACY_DATA = PANEL / "data"
LEGACY_BACKUPS = PANEL / "backups"

_APP_NAME = "PZControlPanel"
_resolved = False
DATA_DIR: Path = LEGACY_DATA
BACKUPS_DIR: Path = LEGACY_BACKUPS
UPDATES_DIR: Path = LEGACY_DATA / "updates"
STATE_ROOT: Path = PANEL


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _default_state_root() -> Path | None:
    """External state root for packaged installs; None = keep panel/data."""
    if not _is_frozen():
        return None
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / _APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "pz-control-panel"
    return Path.home() / ".local" / "share" / "pz-control-panel"


def _env_data_dir() -> Path | None:
    raw = (os.environ.get("PANEL_DATA_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    root = (os.environ.get("PANEL_STATE_DIR") or "").strip()
    if root:
        return Path(root).expanduser() / "data"
    return None


def _needs_migrate(src: Path, dest: Path) -> bool:
    if not src.exists() or not src.is_dir():
        return False
    try:
        if src.resolve() == dest.resolve():
            return False
    except OSError:
        if str(src) == str(dest):
            return False
    # Dest empty or missing meaningful files
    if not dest.exists():
        return True
    try:
        any_file = next(dest.rglob("*"), None)
    except OSError:
        return True
    if any_file is None:
        return True
    # If dest has only empty dirs, still migrate markers from src
    markers = ("servers.json", "auth.json", "prefs.json", "secrets")
    dest_has = any((dest / m).exists() for m in markers)
    src_has = any((src / m).exists() for m in markers)
    return src_has and not dest_has


def _copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                _copy_tree(item, target)
            else:
                shutil.copytree(item, target, dirs_exist_ok=True)
        elif item.is_file():
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)


def ensure_state_dirs() -> Path:
    """Resolve DATA_DIR, migrate once if needed, create dirs. Idempotent."""
    global _resolved, DATA_DIR, BACKUPS_DIR, UPDATES_DIR, STATE_ROOT
    if _resolved:
        return DATA_DIR

    env_data = _env_data_dir()
    if env_data is not None:
        DATA_DIR = env_data
        state = env_data.parent if env_data.name == "data" else env_data
        STATE_ROOT = state
        BACKUPS_DIR = state / "backups" if env_data.name == "data" else env_data / "backups"
    else:
        root = _default_state_root()
        if root is not None:
            STATE_ROOT = root
            DATA_DIR = root / "data"
            BACKUPS_DIR = root / "backups"
            if _needs_migrate(LEGACY_DATA, DATA_DIR):
                try:
                    _copy_tree(LEGACY_DATA, DATA_DIR)
                except OSError:
                    # Fall back to legacy in-place if copy fails
                    DATA_DIR = LEGACY_DATA
                    BACKUPS_DIR = LEGACY_BACKUPS
                    STATE_ROOT = PANEL
            if _needs_migrate(LEGACY_BACKUPS, BACKUPS_DIR) and BACKUPS_DIR != LEGACY_BACKUPS:
                try:
                    _copy_tree(LEGACY_BACKUPS, BACKUPS_DIR)
                except OSError:
                    pass
        else:
            DATA_DIR = LEGACY_DATA
            BACKUPS_DIR = LEGACY_BACKUPS
            STATE_ROOT = PANEL

    UPDATES_DIR = STATE_ROOT / "updates" if STATE_ROOT != PANEL else DATA_DIR / "updates"
    for path in (DATA_DIR, DATA_DIR / "servers", DATA_DIR / "secrets", BACKUPS_DIR, UPDATES_DIR):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    _resolved = True
    return DATA_DIR


# Resolve at import so DATA_DIR is ready for other modules
ensure_state_dirs()
