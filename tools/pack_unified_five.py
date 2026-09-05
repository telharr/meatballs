#!/usr/bin/env python3
"""Merge as-is snapshots into five B42 mods (one id each). New-world loadout."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import pack_server_bundles as bundles  # noqa: E402
from ftp_client import load_dotenv  # noqa: E402
from mod_catalog import apply_lists_to_ini, parse_ini_list  # noqa: E402

OUT = ROOT / ".cache/workshop-packs/unified"
CACHE_MODS = bundles.CACHE_MODS
ZMODS = Path.home() / "Zomboid" / "mods"
INI = bundles.INI
PACK5 = INI.with_name("pack5.ini")
OVERWRITE_LOG = OUT / "overwrites.jsonl"

CORE_FIVE = (
    "ServerTweaker",
    "LogExtender",
    "MeatballsSlots",
    "AdminTools",
    "BetterSafehouse",
    "MeatballsSafehouses",
)
ASSIGNED = set(CORE_FIVE + bundles.LIBRARIES + bundles.KI5 + bundles.CHARACTER + bundles.AUDIO)

UNIFIED = (
    {
        "id": "MeatballsLibraries",
        "name": "MEATBALLS Libraries",
        "ids": bundles.LIBRARIES,
        "require": None,
        "color": (40, 90, 140),
    },
    {
        "id": "MeatballsCore",
        "name": "MEATBALLS Core",
        "ids": CORE_FIVE,
        "require": "MeatballsLibraries",
        "color": (140, 50, 40),
    },
    {
        "id": "MeatballsKI5",
        "name": "MEATBALLS KI5 Garage",
        "ids": bundles.KI5,
        "require": "MeatballsLibraries",
        "color": (50, 110, 60),
    },
    {
        "id": "MeatballsCharacter",
        "name": "MEATBALLS Character",
        "ids": bundles.CHARACTER,
        "require": "MeatballsLibraries",
        "color": (120, 70, 140),
    },
    {
        "id": "MeatballsGameplay",
        "name": "MEATBALLS Gameplay",
        "ids": (),
        "require": "MeatballsLibraries",
        "color": (180, 120, 40),
    },
)

SKIP_FILES = {"mod.info", "workshop.txt", ".ds_store"}
SKIP_DIR_NAMES = {".git", "__pycache__"}


def _version_score(name: str) -> tuple[int, int]:
    lower = name.lower()
    if lower == "42.20" or lower.startswith("42.20"):
        return (0, 0)
    if lower == "42":
        return (1, 0)
    match = re.match(r"42\.(\d+)", lower)
    if match:
        ver = int(match.group(1))
        if ver <= 20:
            return (2, -ver)
        return (3, ver)
    return (9, 0)


def _layers(src: Path) -> list[Path]:
    layers: list[Path] = []
    common = src / "common"
    if common.is_dir():
        layers.append(common)
    versioned = [
        path
        for path in src.iterdir()
        if path.is_dir() and (path.name == "42" or path.name.startswith("42"))
    ]
    versioned.sort(key=lambda path: _version_score(path.name), reverse=True)
    layers.extend(versioned)
    if not layers:
        layers.append(src)
    return layers


def _overlay(src: Path, dest_42: Path, mid: str, log) -> int:
    copied = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name.lower() in SKIP_FILES:
            continue
        rel = path.relative_to(src)
        dest = dest_42 / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            log.write(json.dumps({"mod": mid, "path": rel.as_posix()}, ensure_ascii=False) + "\n")
        shutil.copy2(path, dest)
        copied += 1
    return copied


def _write_mod_info(dest_42: Path, spec: dict, sources: list[str]) -> None:
    require = spec["require"]
    lines = [
        f"name={spec['name']}",
        f"id={spec['id']}",
        f"description=Unified MEATBALLS snapshot for a new B42.20 world. Sources: {', '.join(sources[:40])}"
        + ("…" if len(sources) > 40 else ""),
        "poster=poster.png",
        "versionMin=42.20.0",
    ]
    if require:
        lines.append(f"require={require}")
    (dest_42 / "mod.info").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _install(src_mod: Path, mid: str) -> None:
    for dest_root in (CACHE_MODS, ZMODS):
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / mid
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src_mod, dest)


def main() -> int:
    load_dotenv()
    live = bundles._ini_mods()
    leftover = [mid for mid in live if mid not in ASSIGNED]
    specs = []
    for spec in UNIFIED:
        row = dict(spec)
        if row["id"] == "MeatballsGameplay":
            row["ids"] = tuple(leftover)
        specs.append(row)

    index = bundles._catalog_index()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    OVERWRITE_LOG.write_text("", encoding="utf-8")

    summary = []
    with OVERWRITE_LOG.open("a", encoding="utf-8") as log:
        for spec in specs:
            dest = OUT / spec["id"]
            dest_42 = dest / "42"
            dest_42.mkdir(parents=True)
            files = 0
            for mid in spec["ids"]:
                src = bundles._find_src(mid, index)
                n = 0
                for layer in _layers(src):
                    n += _overlay(layer, dest_42, mid, log)
                files += n
                print(f"{spec['id']} +{mid} files={n} src={src}", flush=True)
            if not (dest_42 / "poster.png").exists():
                bundles._png(dest_42 / "poster.png", spec["color"])
            bundles._png(dest / "preview.png", spec["color"])
            _write_mod_info(dest_42, spec, list(spec["ids"]))
            credits = bundles._credits(spec["ids"], index)
            (dest / "credits.txt").write_text(credits, encoding="utf-8")
            _install(dest, spec["id"])
            bytes_total = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
            summary.append(
                {
                    "id": spec["id"],
                    "sources": list(spec["ids"]),
                    "count": len(spec["ids"]),
                    "files": files,
                    "bytes": bytes_total,
                    "path": str(dest),
                }
            )

    raw = INI.read_text(encoding="utf-8", errors="replace")
    mods_five = [
        "MeatballsLibraries",
        "MeatballsCore",
        "MeatballsKI5",
        "MeatballsCharacter",
        "MeatballsGameplay",
    ]
    PACK5.write_text(apply_lists_to_ini(raw, mods_five, []), encoding="utf-8")
    (OUT / "manifest.json").write_text(
        json.dumps({"mods": summary, "ini": str(PACK5), "Mods": mods_five}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "Mods": mods_five, "packs": summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
