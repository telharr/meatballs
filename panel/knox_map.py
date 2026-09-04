"""Knox Country atlas calibration and file locations (Sprint 13).

The PNG is generated locally from the installed game's worldmap XML
(`tools/knox_atlas.py`). Indie Stone textures are not committed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from panel.paths import DATA_DIR

PANEL = Path(__file__).resolve().parent
DEFAULT_BOUNDS = {"x0": 3000, "y0": 0, "x1": 16000, "y1": 14000, "cell": 300}
EXAMPLE_CALIBRATION = PANEL / "data" / "maps" / "knox" / "calibration.example.json"


def maps_dir() -> Path:
    primary = DATA_DIR / "maps" / "knox"
    fallback = PANEL / "data" / "maps" / "knox"
    if (primary / "atlas.png").is_file():
        return primary
    if (fallback / "atlas.png").is_file():
        return fallback
    return primary


def calibration_path() -> Path | None:
    for folder in (maps_dir(), PANEL / "data" / "maps" / "knox"):
        path = folder / "calibration.json"
        if path.is_file():
            return path
    return None


def load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def calibration() -> dict[str, Any]:
    path = calibration_path()
    if path is None and EXAMPLE_CALIBRATION.is_file():
        path = EXAMPLE_CALIBRATION
    data = load_json(path) if path else {}
    out = dict(DEFAULT_BOUNDS)
    for key in ("x0", "y0", "x1", "y1", "cell", "image_w", "image_h", "image", "scale"):
        if key in data:
            out[key] = data[key]
    if "anchors" in data:
        out["anchors"] = data["anchors"]
    out.setdefault("cell", 300)
    out.setdefault("image", "atlas.png")
    return out


def atlas_file() -> Path | None:
    path = maps_dir() / "atlas.png"
    return path if path.is_file() else None


def world_to_atlas_px(x: float, y: float, cal: dict[str, Any]) -> tuple[float, float]:
    x0 = float(cal["x0"])
    y0 = float(cal["y0"])
    x1 = float(cal["x1"])
    y1 = float(cal["y1"])
    image_w = float(cal.get("image_w") or 1)
    image_h = float(cal.get("image_h") or 1)
    u = (float(x) - x0) / (x1 - x0)
    v = (float(y) - y0) / (y1 - y0)
    return u * image_w, v * image_h


def atlas_px_to_world(px: float, py: float, cal: dict[str, Any]) -> tuple[float, float]:
    x0 = float(cal["x0"])
    y0 = float(cal["y0"])
    x1 = float(cal["x1"])
    y1 = float(cal["y1"])
    image_w = float(cal.get("image_w") or 1)
    image_h = float(cal.get("image_h") or 1)
    x = x0 + (float(px) / image_w) * (x1 - x0)
    y = y0 + (float(py) / image_h) * (y1 - y0)
    return x, y


def atlas_meta() -> dict[str, Any]:
    cal = calibration()
    path = atlas_file()
    ready = path is not None
    if ready and path is not None:
        stat = path.stat()
        cal.setdefault("image_w", None)
        url = f"/api/safehouses/map/atlas?v={int(stat.st_mtime)}"
    else:
        url = ""
    return {
        "ready": ready,
        "url": url,
        "image": cal.get("image", "atlas.png"),
        "image_w": cal.get("image_w"),
        "image_h": cal.get("image_h"),
        "source": "worldmap.xml" if ready else None,
    }


def snapshot_map() -> dict[str, Any]:
    cal = calibration()
    meta = atlas_meta()
    return {
        "x0": int(cal["x0"]),
        "y0": int(cal["y0"]),
        "x1": int(cal["x1"]),
        "y1": int(cal["y1"]),
        "cell": int(cal.get("cell") or 300),
        "image_w": cal.get("image_w"),
        "image_h": cal.get("image_h"),
        "atlas": meta,
    }
