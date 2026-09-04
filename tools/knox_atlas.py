#!/usr/bin/env python3
"""Render a paper-style Knox Country atlas from Project Zomboid worldmap XML.

Uses the same cell=300 / Y-down contract as SafeHouse.addSafeHouse.
Does not copy Indie Stone textures. Output PNG is gitignored.

    python tools/knox_atlas.py
    python tools/knox_atlas.py --game-dir "C:\\Program Files (x86)\\Steam\\steamapps\\common\\ProjectZomboid"

Requires Pillow. Optional: PZ_GAME_DIR.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CELL = 300
DEFAULT_BOUNDS = {"x0": 3000, "y0": 0, "x1": 16000, "y1": 14000}
PAPER = (201, 196, 160, 255)
FOREST = (92, 122, 70, 255)
WATER = (106, 143, 160, 255)
BUILDING = (214, 198, 158, 255)
RAIL = (110, 96, 82, 255)
ROADS = {
    "trail": (184, 168, 120, 255),
    "tertiary": (198, 178, 128, 255),
    "secondary": (214, 196, 144, 255),
    "primary": (232, 216, 168, 255),
}

STEAM_DEFAULTS = [
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"),
    Path(r"C:\Program Files\Steam\steamapps\common\ProjectZomboid"),
    Path.home() / ".steam/steam/steamapps/common/ProjectZomboid",
    Path.home() / ".local/share/Steam/steamapps/common/ProjectZomboid",
]


def find_game_dir(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    for key in ("PZ_GAME_DIR", "PZ_CLIENT_DIR"):
        raw = os.environ.get(key)
        if raw:
            candidates.append(Path(raw))
    candidates.extend(STEAM_DEFAULTS)
    for path in candidates:
        maps = _maps_root(path)
        if maps and (maps / "worldmap.xml").is_file():
            return path
    return None


def _maps_root(game_dir: Path) -> Path | None:
    for rel in (
        Path("media") / "maps" / "Muldraugh, KY",
        Path("projectzomboid") / "media" / "maps" / "Muldraugh, KY",
    ):
        folder = game_dir / rel
        if folder.is_dir():
            return folder
    return None


def iter_features(path: Path) -> Iterator[tuple[dict[str, str], list[tuple[int, int]]]]:
    cell_x = 0
    cell_y = 0
    points: list[tuple[int, int]] = []
    props: dict[str, str] = {}
    for event, elem in ET.iterparse(path, events=("start", "end")):
        tag = elem.tag.rsplit("}", 1)[-1]
        if event == "start":
            if tag == "cell":
                cell_x = int(elem.attrib.get("x", 0))
                cell_y = int(elem.attrib.get("y", 0))
            elif tag == "feature":
                points = []
                props = {}
            continue
        if tag == "point":
            px = int(float(elem.attrib.get("x", 0)))
            py = int(float(elem.attrib.get("y", 0)))
            points.append((cell_x * CELL + px, cell_y * CELL + py))
            elem.clear()
        elif tag == "property":
            name = elem.attrib.get("name", "")
            if name:
                props[name] = elem.attrib.get("value", "")
            elem.clear()
        elif tag == "feature":
            if len(points) >= 3:
                yield dict(props), list(points)
            points = []
            props = {}
            elem.clear()
        elif tag == "cell":
            elem.clear()


def classify(props: dict[str, str]) -> str | None:
    if "water" in props:
        return "water"
    natural = props.get("natural", "")
    if natural in ("forest", "wood"):
        return "forest"
    if "building" in props:
        return "building"
    if "highway" in props:
        return "road:" + (props.get("highway") or "secondary")
    if "railway" in props or "driveway" in props:
        return "rail" if "railway" in props else "road:trail"
    return None


def _color_for(kind: str) -> tuple[int, int, int, int] | None:
    if kind == "forest":
        return FOREST
    if kind == "water":
        return WATER
    if kind == "building":
        return BUILDING
    if kind == "rail":
        return RAIL
    if kind.startswith("road:"):
        return ROADS.get(kind.split(":", 1)[1], ROADS["secondary"])
    return None


def _to_px(
    points: list[tuple[int, int]],
    x0: int,
    y0: int,
    scale: float,
    img_w: int,
    img_h: int,
) -> list[tuple[int, int]] | None:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x1 = x0 + int(round(img_w / scale))
    y1 = y0 + int(round(img_h / scale))
    if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
        return None
    out: list[tuple[int, int]] = []
    for wx, wy in points:
        out.append((int(round((wx - x0) * scale)), int(round((wy - y0) * scale))))
    return out if len(out) >= 3 else None


def _layer_name(kind: str) -> str | None:
    if kind in ("forest", "water", "building"):
        return kind
    if kind == "rail" or kind.startswith("road:"):
        return "road"
    return None


def render_atlas(
    xml_paths: Iterable[Path],
    out_png: Path,
    *,
    x0: int = DEFAULT_BOUNDS["x0"],
    y0: int = DEFAULT_BOUNDS["y0"],
    x1: int = DEFAULT_BOUNDS["x1"],
    y1: int = DEFAULT_BOUNDS["y1"],
    scale: float = 0.25,
) -> dict[str, Any]:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise SystemExit("Pillow is required: python -m pip install pillow") from exc

    img_w = max(1, int(round((x1 - x0) * scale)))
    img_h = max(1, int(round((y1 - y0) * scale)))
    order = ("forest", "water", "building", "road")
    layers = {name: Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0)) for name in order}
    draws = {name: ImageDraw.Draw(image, "RGBA") for name, image in layers.items()}
    xml_list = [Path(p) for p in xml_paths if Path(p).is_file()]
    for xml_path in xml_list:
        count = 0
        print(f"  parse {xml_path.name}", flush=True)
        for props, points in iter_features(xml_path):
            kind = classify(props)
            if kind is None:
                continue
            layer = _layer_name(kind)
            color = _color_for(kind)
            if layer is None or color is None:
                continue
            poly = _to_px(points, x0, y0, scale, img_w, img_h)
            if poly is None:
                continue
            draws[layer].polygon(poly, fill=color)
            count += 1
        print(f"    drawn {count} features", flush=True)

    image = Image.new("RGBA", (img_w, img_h), PAPER)
    for name in order:
        image = Image.alpha_composite(image, layers[name])
        layers[name].close()

    out_png.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(out_png, format="PNG")
    return {
        "image": out_png.name,
        "x0": x0,
        "y0": y0,
        "x1": x1,
        "y1": y1,
        "cell": CELL,
        "scale": scale,
        "image_w": img_w,
        "image_h": img_h,
        "anchors": [
            {"id": "westpoint", "x": 11690, "y": 6990},
            {"id": "muldraugh", "x": 10780, "y": 9830},
            {"id": "rosewood", "x": 8300, "y": 11670},
        ],
    }


def default_out_dir() -> Path:
    try:
        from panel.paths import DATA_DIR

        return DATA_DIR / "maps" / "knox"
    except Exception:
        return REPO / "panel" / "data" / "maps" / "knox"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--scale", type=float, default=0.25)
    parser.add_argument("--xml", type=Path, action="append", default=[])
    args = parser.parse_args()

    xml_paths: list[Path] = list(args.xml)
    if not xml_paths:
        game = find_game_dir(args.game_dir)
        if game is None:
            print("Project Zomboid media/maps not found. Set PZ_GAME_DIR or --game-dir.", file=sys.stderr)
            return 2
        maps = _maps_root(game)
        assert maps is not None
        xml_paths = [maps / "worldmap-forest.xml", maps / "worldmap.xml"]
        xml_paths = [p for p in xml_paths if p.is_file()]
        if not xml_paths:
            print(f"No worldmap XML under {maps}", file=sys.stderr)
            return 2
        print(f"Maps: {maps}")

    out_dir = args.out_dir or default_out_dir()
    out_png = out_dir / "atlas.png"
    print(f"Rendering {out_png} at scale={args.scale} …")
    cal = render_atlas(xml_paths, out_png, scale=args.scale)
    cal_path = out_dir / "calibration.json"
    cal_path.write_text(json.dumps(cal, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_png} ({cal['image_w']}x{cal['image_h']})")
    print(f"Wrote {cal_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
