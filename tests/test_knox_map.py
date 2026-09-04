"""Knox atlas calibration and XML → pixel math."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from knox_atlas import CELL, classify, iter_features, render_atlas
from panel.knox_map import atlas_px_to_world, snapshot_map, world_to_atlas_px


FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<world version="1.0">
 <cell x="10" y="0">
  <feature>
   <geometry type="Polygon">
    <coordinates>
     <point x="0" y="0"/>
     <point x="40" y="0"/>
     <point x="40" y="20"/>
     <point x="0" y="20"/>
    </coordinates>
   </geometry>
   <properties>
    <property name="water" value="river"/>
   </properties>
  </feature>
 </cell>
</world>
"""


def test_cell_size_is_300() -> None:
    assert CELL == 300


def test_world_pixel_roundtrip() -> None:
    cal = {"x0": 3000, "y0": 0, "x1": 16000, "y1": 14000, "image_w": 3250, "image_h": 3500}
    px, py = world_to_atlas_px(10648, 6912, cal)
    x, y = atlas_px_to_world(px, py, cal)
    assert abs(x - 10648) < 0.6
    assert abs(y - 6912) < 0.6


def test_westpoint_inside_atlas() -> None:
    cal = {"x0": 3000, "y0": 0, "x1": 16000, "y1": 14000, "image_w": 3250, "image_h": 3500}
    px, py = world_to_atlas_px(11690, 6990, cal)
    assert 0 < px < 3250
    assert 0 < py < 3500


def test_iter_features_cell_offset() -> None:
    with tempfile.TemporaryDirectory() as raw:
        xml_path = Path(raw) / "tiny.xml"
        xml_path.write_text(FIXTURE, encoding="utf-8")
        features = list(iter_features(xml_path))
        assert len(features) == 1
        props, points = features[0]
        assert classify(props) == "water"
        assert points[0] == (10 * 300, 0)


def test_render_tiny_atlas() -> None:
    from PIL import Image

    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        xml_path = folder / "tiny.xml"
        xml_path.write_text(FIXTURE, encoding="utf-8")
        out = folder / "atlas.png"
        cal = render_atlas([xml_path], out, x0=3000, y0=0, x1=3100, y1=50, scale=1.0)
        assert out.is_file()
        assert cal["image_w"] == 100
        assert cal["cell"] == 300
        img = Image.open(out)
        sample = img.getpixel((10, 10))
        assert sample[2] > sample[0]


def test_snapshot_map_shape() -> None:
    data = snapshot_map()
    assert data["cell"] == 300
    assert data["x0"] == 3000
    assert "atlas" in data
    assert "ready" in data["atlas"]


if __name__ == "__main__":
    test_cell_size_is_300()
    test_world_pixel_roundtrip()
    test_westpoint_inside_atlas()
    test_iter_features_cell_offset()
    test_render_tiny_atlas()
    test_snapshot_map_shape()
    print("ok")
