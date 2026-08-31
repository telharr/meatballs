"""Full text snapshot of the panel repository (filenames + source)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

PANEL = Path(__file__).resolve().parents[1]
BACKUPS = PANEL / "backups"

# Directories under panel/ to skip entirely
SKIP_DIR_NAMES = {
    "__pycache__",
    "backups",
    "data._v1validate_backup",
    ".git",
    "node_modules",
}

# Paths relative to panel/ that must never be dumped (secrets)
SKIP_REL_PREFIXES = (
    "data/secrets/",
    "data\\secrets\\",
)

SKIP_REL_FILES = {
    "data/auth.json",
    "data\\auth.json",
}

TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".css",
    ".html",
    ".json",
    ".md",
    ".txt",
    ".ini",
    ".toml",
    ".yml",
    ".yaml",
    ".svg",
    ".map",
    ".example",
}

MAX_FILE_BYTES = 2_000_000  # 2 MB per file safety cap


def _rel_posix(path: Path) -> str:
    return path.relative_to(PANEL).as_posix()


def _should_skip(path: Path) -> bool:
    rel = path.relative_to(PANEL)
    if any(part in SKIP_DIR_NAMES for part in rel.parts):
        return True
    rel_s = str(rel).replace("\\", "/")
    for prefix in SKIP_REL_PREFIXES:
        if rel_s.startswith(prefix.replace("\\", "/")):
            return True
    if rel_s in {x.replace("\\", "/") for x in SKIP_REL_FILES}:
        return True
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ("mod.info", "Dockerfile"):
        # allow extensionless small text? skip binaries / ico
        if path.suffix.lower() in {".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ttf", ".bin", ".zip"}:
            return True
        if path.suffix.lower() == "":
            return True
        return True
    return False


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        return f"[SKIPPED: file larger than {MAX_FILE_BYTES} bytes ({len(raw)} bytes)]\n"
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return "[SKIPPED: binary / undecodable]\n"


def collect_panel_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(PANEL.rglob("*")):
        if not path.is_file():
            continue
        if _should_skip(path):
            continue
        files.append(path)
    return files


def build_snapshot_text(*, panel_version: str = "unknown") -> tuple[str, dict[str, Any]]:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    files = collect_panel_files()
    lines: list[str] = [
        "MEATBALLS PZ Control Panel — full source snapshot",
        f"Created: {datetime.now().isoformat(timespec='seconds')}",
        f"Panel version: {panel_version}",
        f"Root: {PANEL}",
        f"Files: {len(files)}",
        "Secrets (data/secrets/, auth.json) omitted.",
        "Backups directory omitted.",
        "",
    ]
    total_bytes = 0
    for path in files:
        rel = _rel_posix(path)
        body = _read_text(path)
        total_bytes += len(body.encode("utf-8", errors="replace"))
        sep = "=" * 80
        lines.append(sep)
        lines.append(f"FILE: panel/{rel}")
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        lines.append(f"BYTES: {size}")
        lines.append(sep)
        lines.append(body.rstrip("\n"))
        lines.append("")  # blank between files

    text = "\n".join(lines) + "\n"
    meta = {
        "stamp": stamp,
        "file_count": len(files),
        "content_bytes": len(text.encode("utf-8")),
        "source_bytes": total_bytes,
        "panel_version": panel_version,
        "paths": [f"panel/{_rel_posix(p)}" for p in files],
    }
    return text, meta


def write_panel_snapshot(*, panel_version: str = "unknown") -> dict[str, Any]:
    text, meta = build_snapshot_text(panel_version=panel_version)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    filename = f"panel-snapshot-{meta['stamp']}-v{panel_version}.txt"
    path = BACKUPS / filename
    path.write_text(text, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "filename": filename,
        "path": str(path),
        "relative": f"panel/backups/{filename}",
        "bytes": path.stat().st_size,
        "file_count": meta["file_count"],
        "panel_version": panel_version,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "download": f"/api/panel/snapshot/file?name={filename}",
    }


def resolve_snapshot_file(name: str) -> Path:
    safe = Path(name).name
    if not safe.startswith("panel-snapshot-") or not safe.endswith(".txt"):
        raise FileNotFoundError("Invalid snapshot name")
    path = (BACKUPS / safe).resolve()
    if not str(path).startswith(str(BACKUPS.resolve())):
        raise FileNotFoundError("Invalid snapshot path")
    if not path.is_file():
        raise FileNotFoundError(safe)
    return path
