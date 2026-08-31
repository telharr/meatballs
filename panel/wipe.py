"""Targeted chunk wipe: backup then delete map_CX_CY.bin only."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PANEL = Path(__file__).resolve().parent
BACKUPS = PANEL / "backups"
CELL = 256
def _save_roots() -> list[Path]:
    try:
        from panel.servers import cachedir_paths

        return [root / "Saves" for root in cachedir_paths()]
    except Exception:
        return [
            ROOT / ".mirror" / "ServerWorld" / "Saves",
            ROOT / ".cache" / "dedi-test" / "Saves",
        ]
ALLOWED_PREFIXES = ("map_", "chunkdata_", "zpop_")


def cell_from_coords(x: int | None, y: int | None, cell_x: int | None, cell_y: int | None) -> tuple[int, int]:
    if cell_x is not None and cell_y is not None:
        return int(cell_x), int(cell_y)
    if x is None or y is None:
        raise ValueError("Нужны координаты клетки (x,y) или cell_x / cell_y")
    return int(x) // CELL, int(y) // CELL


def _matches_cell(name: str, cx: int, cy: int) -> bool:
    lower = name.lower()
    if "worlddictionary" in lower:
        return False
    if not any(lower.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return False
    token = f"_{cx}_{cy}."
    return token in lower


def list_chunk_files(cx: int, cy: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in _save_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or not _matches_cell(path.name, cx, cy):
                continue
            rel = path.relative_to(root).as_posix()
            rows.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "relative": rel,
                    "size": path.stat().st_size,
                    "remote": f"/ServerWorld/Saves/{rel}",
                }
            )
    return rows


def confirm_token(cx: int, cy: int) -> str:
    return f"WIPE {cx} {cy}"


def preview(x: int | None = None, y: int | None = None, cell_x: int | None = None, cell_y: int | None = None) -> dict[str, Any]:
    cx, cy = cell_from_coords(x, y, cell_x, cell_y)
    files = list_chunk_files(cx, cy)
    return {
        "cell_x": cx,
        "cell_y": cy,
        "world_x": cx * CELL,
        "world_y": cy * CELL,
        "confirm": confirm_token(cx, cy),
        "files": files,
        "count": len(files),
        "note": "Лут перегенерится при заходе в клетку. Нужен рестарт или разгрузка чанка. WorldDictionary не трогаем.",
    }


def apply(
    *,
    confirm: str,
    x: int | None = None,
    y: int | None = None,
    cell_x: int | None = None,
    cell_y: int | None = None,
    delete_remote: bool = True,
) -> dict[str, Any]:
    from panel.servers import active_files_client  # local import: tools/ on path

    data = preview(x, y, cell_x, cell_y)
    cx, cy = data["cell_x"], data["cell_y"]
    expected = confirm_token(cx, cy)
    if (confirm or "").strip() != expected:
        raise ValueError(f"Подтверждение должно быть точно: {expected}")
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = BACKUPS / f"wipe-{stamp}-c{cx}_{cy}"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    deleted_local: list[str] = []
    deleted_remote: list[str] = []
    errors: list[str] = []
    client = None
    if delete_remote:
        try:
            client = active_files_client()
        except Exception as exc:
            errors.append(f"Remote files: {exc}")
    for row in data["files"]:
        src = Path(row["path"])
        if not src.is_file():
            continue
        backup = dest / src.name
        shutil.copy2(src, backup)
        copied.append(str(backup))
        try:
            src.unlink()
            deleted_local.append(row["path"])
        except OSError as exc:
            errors.append(f"local {src.name}: {exc}")
        if client:
            try:
                client.delete_file(row["remote"], allow_protected=True)
                deleted_remote.append(row["remote"])
            except Exception as exc:
                errors.append(f"FTP {row['remote']}: {exc}")
    return {
        **data,
        "backup": str(dest),
        "copied": copied,
        "deleted_local": deleted_local,
        "deleted_remote": deleted_remote,
        "errors": errors,
        "ok": not errors,
    }
