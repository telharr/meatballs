"""Workshop picker dedupe and as-is deploy helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from panel.services.pack_merger import (  # noqa: E402
    append_ids_to_ini,
    dedupe_mods_by_id,
    pack_folder_for_mod,
    source_kind,
)


def test_pack_folder_b42() -> None:
    nested = ROOT / "src" / "mods" / "MeatballsSafehouses" / "42"
    assert pack_folder_for_mod(nested).name == "MeatballsSafehouses"
    assert pack_folder_for_mod(nested.parent) == nested.parent


def test_source_kind_repo() -> None:
    path = ROOT / "src" / "mods" / "MeatballsSafehouses" / "42"
    assert source_kind(path) == "repo"


def test_dedupe_prefers_repo() -> None:
    repo = SimpleNamespace(id="LogExtender", path=ROOT / "src" / "mods" / "LogExtender" / "42")
    mirror = SimpleNamespace(id="LogExtender", path=ROOT / ".mirror" / "x" / "mods" / "LogExtender" / "42")
    picked = dedupe_mods_by_id([mirror, repo])
    assert len(picked) == 1
    assert picked[0] is repo


def test_append_ids_keeps_existing() -> None:
    ini = "Mods=ServerTweaker;LogExtender\nWorkshopItems=\n"
    updated, mods = append_ids_to_ini(ini, ["LogExtender", "MeatballsSafehouses"])
    assert mods == ["ServerTweaker", "LogExtender", "MeatballsSafehouses"]
    assert "MeatballsSafehouses" in updated
    assert updated.count("Mods=") == 1


if __name__ == "__main__":
    test_pack_folder_b42()
    test_source_kind_repo()
    test_dedupe_prefers_repo()
    test_append_ids_keeps_existing()
    print("ok")
