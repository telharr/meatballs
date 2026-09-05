#!/usr/bin/env python3
"""Build as-is Workshop bundles (multiple mod folders, no Lua merge)."""

from __future__ import annotations

import json
import shutil
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from workshop_downloader import find_mod_dirs, workshop_content_dir  # noqa: E402
from ftp_client import load_dotenv  # noqa: E402
from mod_catalog import apply_lists_to_ini, parse_ini_list  # noqa: E402

CACHE_MODS = ROOT / ".mirror/meatballs-xl/ServerWorld/mods"
MIRROR_MODS = ROOT / ".mirror/meatballs-xl/mods"
STEAM_INSTALL = ROOT / ".mirror/meatballs-xl"
SRC_MODS = ROOT / "src/mods"
INI = ROOT / ".mirror/meatballs-xl/ServerWorld/Server/world.ini"
OUT = ROOT / ".cache/workshop-packs"
CATALOG = ROOT / "src/modpacks/meatballs.catalog.json"

CORE = (
    "ServerTweaker",
    "LogExtender",
    "MeatballsSlots",
    "AdminTools",
    "MeatballsSafehouses",
)
LIBRARIES = (
    "StarlitLibrary",
    "MoodleFramework",
    "NeatUI_Framework",
    "TchernoLib",
    "EasyConfigChucked",
    "ChuckleberryFinnAlertSystem",
    "errorMagnifier",
    "YAPZLib",
    "CommunityModdingDebugTools",
    "CommunityModdingFrameworks",
    "CommunityModdingPatch",
    "TargetSquareOnLoad",
    "BCGTools",
)
KI5 = (
    "damnlib",
    "91geoMetro",
    "92fordCVPI",
    "89volvo200",
    "92jeepYJ",
    "91fordRanger",
    "89fordBronco",
    "86fordE150",
    "86fordE150expanded",
    "93chevySuburban",
    "93chevySuburbanExpanded",
    "86oshkoshP19A",
    "92amgeneralM998",
    "KI5trailers",
    "KI5campers",
    "78amgeneralM35A2",
    "78amgeneralM49A2C",
    "78amgeneralM50A3",
    "78amgeneralM62",
    "90fordF350ambulance",
    "90pierceArrow",
    "89defender",
    "91range",
    "92nissanGTR",
    "70dodge",
    "isoContainers",
    "VVR",
    "KI5minifixes",
    "VSUIKI5",
    "POB42_Customs_92amgeneralM998",
    "POB42_Customs_92nissanGTR",
    "DynamicVehicleSnow",
    "CarRoofFix",
    "CarWeaponFix",
    "CarEnterExitFix",
)
CHARACTER = (
    "SpnOpenCloth",
    "SpnOpenClothBase",
    "SpnCloth",
    "SPNCC",
    "SPNCCDetails",
    "SPNCCDetailsHD",
    "SPNCCFaces",
    "FH",
    "SpnHair",
    "KATTAJ1_ClothesCore",
    "SM4BootsExpandedB42",
    "SM4BootsExpandedB42VanillaONLY",
    "SM4BootsExpandedFlatshoes",
    "GlassHats",
    "HardwoodsTurnoutGear",
    "VanillaGearExpanded",
    "VanillaOutfitsExpanded",
    "1VCESTANDARD",
    "AliceGear",
    "Military_Tool_Kit",
)
AUDIO = ("SHdynamicmusic",)
ASSIGNED = set(CORE + LIBRARIES + KI5 + CHARACTER + AUDIO)

PACKS = (
    {
        "slug": "meatballs-libraries",
        "title": "MEATBALLS Libraries (B42.20 snapshot)",
        "required": True,
        "ids": LIBRARIES,
        "color": (40, 90, 140),
    },
    {
        "slug": "meatballs-core",
        "title": "MEATBALLS Core (B42.20 snapshot)",
        "required": True,
        "ids": CORE,
        "color": (140, 50, 40),
    },
    {
        "slug": "meatballs-ki5",
        "title": "MEATBALLS KI5 Garage (B42.20 snapshot)",
        "required": True,
        "ids": KI5,
        "color": (50, 110, 60),
    },
    {
        "slug": "meatballs-character",
        "title": "MEATBALLS Character (B42.20 snapshot)",
        "required": True,
        "ids": CHARACTER,
        "color": (120, 70, 140),
    },
    {
        "slug": "meatballs-gameplay",
        "title": "MEATBALLS Gameplay (B42.20 snapshot)",
        "required": True,
        "ids": (),  # filled from leftover Mods=
        "color": (180, 120, 40),
    },
    {
        "slug": "meatballs-audio",
        "title": "MEATBALLS Audio optional (B42.20 snapshot)",
        "required": False,
        "ids": AUDIO,
        "color": (20, 20, 20),
    },
)


def _png(path: Path, rgb: tuple[int, int, int], size: int = 256) -> None:
    raw = b"".join(b"\x00" + (bytes(rgb) * size) for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data) & 0xFFFFFFFF
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _vdf(content: Path, preview: Path, title: str, description: str) -> str:
    # 3 = unlisted if SteamCMD accepts it; change in Workshop UI if not.
    return f'''"workshopitem"
{{
    "appid" "108600"
    "publishedfileid" "0"
    "contentfolder" "{content.resolve().as_posix()}"
    "previewfile" "{preview.resolve().as_posix()}"
    "visibility" "3"
    "title" "{title}"
    "description" "{description}"
    "changenote" "MEATBALLS server snapshot 2026-09-05"
}}
'''


def _file_count(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file())


def _find_src(mid: str, index: dict[str, dict]) -> Path:
    candidates: list[Path] = []
    if mid in CORE:
        local = SRC_MODS / mid
        if local.is_dir():
            candidates.append(local)
    for root in (MIRROR_MODS, CACHE_MODS):
        cand = root / mid
        if cand.is_dir():
            candidates.append(cand)
    wid = str((index.get(mid) or {}).get("workshop_id") or "").strip()
    if wid:
        item = workshop_content_dir(STEAM_INSTALL, wid)
        if item.is_dir():
            for folder in find_mod_dirs(item):
                ids: list[str] = []
                for info in folder.rglob("mod.info"):
                    for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
                        if line.lower().startswith("id="):
                            ids.append(line.split("=", 1)[1].strip())
                if mid in ids or folder.name == mid:
                    candidates.append(folder)
    if not candidates:
        raise FileNotFoundError(mid)
    return max(candidates, key=_file_count)


def _copy(src: Path, dest: Path) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, dirs_exist_ok=False)
    return sum(1 for p in dest.rglob("*") if p.is_file())


def _catalog_index() -> dict[str, dict]:
    if not CATALOG.exists():
        return {}
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {str(i.get("id")): i for i in data.get("items", [])}


def _credits(ids: tuple[str, ...], index: dict[str, dict]) -> str:
    lines = [
        "MEATBALLS server snapshot. Original authors retain copyright.",
        "This item is a frozen copy for one dedicated server.",
        "",
        "id\tname\toriginal_workshop_id",
    ]
    for mid in ids:
        row = index.get(mid, {})
        lines.append(f"{mid}\t{row.get('name') or mid}\t{row.get('workshop_id') or 'local'}")
    return "\n".join(lines) + "\n"


def _ini_mods() -> list[str]:
    raw = INI.read_text(encoding="utf-8", errors="replace")
    return [m.lstrip("\\") for m in parse_ini_list(raw, "Mods")]


def main() -> int:
    load_dotenv()
    live = _ini_mods()
    leftover = [m for m in live if m not in ASSIGNED]
    packs = []
    for spec in PACKS:
        row = dict(spec)
        if row["slug"] == "meatballs-gameplay":
            row["ids"] = tuple(leftover)
        packs.append(row)

    claimed: dict[str, str] = {}
    for spec in packs:
        for mid in spec["ids"]:
            if mid in claimed:
                raise SystemExit(f"duplicate {mid} in {claimed[mid]} and {spec['slug']}")
            claimed[mid] = spec["slug"]

    missing_live = [m for m in live if m not in claimed and m != "SHdynamicmusic"]
    # SH is claimed by audio; leftover should include everything else
    extra = [m for m in claimed if m not in live and m not in CORE]
    print(f"live={len(live)} leftover_gameplay={len(leftover)} extra_not_in_ini={extra}")

    index = _catalog_index()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for spec in packs:
        dest_root = OUT / spec["slug"]
        mods_root = dest_root / "mods"
        if dest_root.exists():
            shutil.rmtree(dest_root)
        mods_root.mkdir(parents=True)
        copied = []
        for mid in spec["ids"]:
            src = _find_src(mid, index)
            n = _copy(src, mods_root / mid)
            copied.append({"id": mid, "files": n, "src": str(src)})
            print(f"{spec['slug']} {mid} files={n}", flush=True)
        preview = dest_root / "preview.png"
        _png(preview, spec["color"])
        credits = _credits(spec["ids"], index)
        (dest_root / "credits.txt").write_text(credits, encoding="utf-8")
        desc = (
            f"{spec['title']}. Frozen snapshot for MEATBALLS dedicated. "
            f"{'REQUIRED to join.' if spec['required'] else 'OPTIONAL. Not on server Mods=. Vanilla music without it.'} "
            "See credits.txt for original authors and Workshop IDs. Do not subscribe to originals."
        )
        vdf_path = OUT / f"{spec['slug']}.vdf"
        vdf_path.write_text(
            _vdf(dest_root, preview, spec["title"], desc.replace('"', "'")),
            encoding="utf-8",
        )
        (dest_root / "workshop_description.txt").write_text(desc + "\n\n" + credits, encoding="utf-8")
        bytes_total = sum(p.stat().st_size for p in dest_root.rglob("*") if p.is_file())
        summary.append(
            {
                "slug": spec["slug"],
                "title": spec["title"],
                "required": spec["required"],
                "ids": list(spec["ids"]),
                "count": len(spec["ids"]),
                "bytes": bytes_total,
                "path": str(dest_root),
                "vdf": str(vdf_path),
            }
        )

    # Audio is client-optional: drop from dedicated Mods=.
    raw = INI.read_text(encoding="utf-8", errors="replace")
    mods = parse_ini_list(raw, "Mods")
    kept = [m for m in mods if m.lstrip("\\") != "SHdynamicmusic"]
    if len(kept) != len(mods):
        backup = INI.with_name("world.ini.bak-drop-audio")
        backup.write_text(raw, encoding="utf-8")
        INI.write_text(apply_lists_to_ini(raw, kept, []), encoding="utf-8")
        print(f"dropped SHdynamicmusic Mods={len(kept)} backup={backup.name}")

    (OUT / "manifest.json").write_text(
        json.dumps(
            {"packs": summary, "missing_from_packs": missing_live, "live_mods": len(kept)},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "out": str(OUT), "packs": summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
