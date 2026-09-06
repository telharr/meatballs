#!/usr/bin/env python3
"""Merge inner-mod media/registries.lua into the five packs (last-wins left only AliceGear)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from apply_five_live_ini import FIVE, FIVE_WS, LIVE_ID, log, set_active  # noqa: E402
from ftp_client import load_dotenv  # noqa: E402
from merge_pack_sandbox import version_score  # noqa: E402
from panel.servers import active_files_client, active_id  # noqa: E402
from panel.services.pack_merger import BACKUPS, _remote_paths  # noqa: E402

MIRROR = ROOT / ".mirror" / "meatballs-xl" / "mods"
STEAM_WS = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\108600")
GLOBAL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{", re.MULTILINE)
PACK_GLOBALS = {
    "MeatballsCharacter": (
        "SPNCC",
        "SpnOpenCloth",
        "AliceRegistries",
        "KATTAJ1_BodyLocation",
    ),
    "MeatballsGameplay": (
        "MuleBodyLocations",
    ),
}


def harvest_roots() -> list[Path]:
    return [
        Path.home() / "Zomboid" / "mods",
        STEAM_WS,
        ROOT / ".mirror" / "meatballs-xl" / "steamapps" / "workshop" / "content" / "108600",
    ]


def collect_registry_files() -> list[tuple[int, Path, str]]:
    found: dict[str, tuple[int, Path, str]] = {}
    for root in harvest_roots():
        if not root.exists():
            continue
        for path in root.rglob("registries.lua"):
            if path.name.lower() != "registries.lua":
                continue
            parts = [p.lower() for p in path.parts]
            if any(p.startswith("meatballs") for p in parts):
                continue
            if "lua" in parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            score = version_score(path)
            key = path.as_posix()
            parent_mod = path.parts[-4] if len(path.parts) >= 4 else path.parent.name
            dedupe = f"{parent_mod}:{path.name}"
            prev = found.get(dedupe)
            if prev and prev[0] >= score:
                continue
            found[dedupe] = (score, path, text)
    return sorted(found.values(), key=lambda row: row[1].as_posix())


def file_globals(text: str) -> set[str]:
    return set(GLOBAL_RE.findall(text))


def merge_for_pack(wanted: tuple[str, ...], files: list[tuple[int, Path, str]]) -> str:
    wanted_set = set(wanted)
    best_path: dict[str, tuple[int, Path, str]] = {}
    for score, path, text in files:
        names = file_globals(text) & wanted_set
        if not names:
            continue
        for name in names:
            prev = best_path.get(name)
            if prev and prev[0] >= score:
                continue
            best_path[name] = (score, path, text)
    chunks = ["-- Meatballs merged registries (inner mods, last-wins was dropping SPNCC/Spongie/etc.)\n"]
    seen_files: set[Path] = set()
    for name in wanted:
        row = best_path.get(name)
        if not row:
            continue
        _score, path, text = row
        if path in seen_files:
            continue
        seen_files.add(path)
        chunks.append(f"-- source: {path.name} ({name})\n")
        chunks.append(text.strip())
        chunks.append("\n")
    return "\n".join(chunks).rstrip() + "\n"


def write_everywhere(mid: str, rel: str, text: str, client) -> None:
    paths = _remote_paths(LIVE_ID)
    ws = FIVE_WS[FIVE.index(mid)]
    targets = [
        MIRROR / mid / rel,
        STEAM_WS / ws / "mods" / mid / rel,
    ]
    for local in targets:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(text, encoding="utf-8")
        log(f"[local] {local}")
    remotes = [
        f"{paths['mods_dir']}/{mid}/{rel.replace(chr(92), '/')}",
        f"/steamapps/workshop/content/108600/{ws}/mods/{mid}/{rel.replace(chr(92), '/')}",
    ]
    temp = BACKUPS / f".upload_{mid}_{Path(rel).name}"
    temp.write_text(text, encoding="utf-8")
    try:
        for remote in remotes:
            client.upload_file(temp, remote, allow_protected=True)
            log(f"[ftp] {remote}")
    finally:
        temp.unlink(missing_ok=True)


def patch_traits(text: str) -> str:
    return text.replace("if Trait.class then", "if Trait and Trait.class then", 1)


def patch_reflection(text: str) -> str:
    needle = """    metatable.__index = function(self, key)
        ---@type table<string, Field>
        local fields = {}
        local fieldNames = table.newarray()

        for i = 0, getNumClassFields(self)-1 do
"""
    insert = """    metatable.__index = function(self, key)
        if not isDebugEnabled() then
            return nil
        end
        ---@type table<string, Field>
        local fields = {}
        local fieldNames = table.newarray()

        for i = 0, getNumClassFields(self)-1 do
"""
    if needle not in text:
        raise SystemExit("Reflection.lua patch point not found")
    return text.replace(needle, insert, 1)


def patch_killcount(text: str) -> str:
    old = """lcl.player_base          = __classmetatables[IsoPlayer.class].__index
lcl.player_isLocalPlayer = lcl.player_base.isLocalPlayer
lcl.player_getModData    = lcl.player_base.getModData

lcl.sm_base    = __classmetatables[ScriptManager.class].__index
lcl.sm_getItem = lcl.sm_base.getItem

lcl.item_base           = __classmetatables[zombie.scripting.objects.Item.class].__index
lcl.item_getDisplayName = lcl.item_base.getDisplayName

lcl.hw_base                = __classmetatables[HandWeapon.class].__index
lcl.hw_getWeaponCategories = lcl.hw_base.getWeaponCategories--B42.12.3-
lcl.hw_getPerk             = lcl.hw_base.getPerk--B42.13+
lcl.hw_getSubCategory      = lcl.hw_base.getSubCategory
lcl.hw_getType             = lcl.hw_base.getType
lcl.hw_isInstantExplosion  = lcl.hw_base.isInstantExplosion
lcl.hw_getExplosionRange   = lcl.hw_base.getExplosionRange


lcl.ArrayList_base        = __classmetatables[ArrayList.class].__index
lcl.ArrayList_size        = lcl.ArrayList_base.size
lcl.ArrayList_get         = lcl.ArrayList_base.get
"""
    new = """local function bindJava(getter)
    local ok, value = pcall(getter)
    if ok then
        return value
    end
    return nil
end

lcl.player_base          = bindJava(function() return __classmetatables[IsoPlayer.class].__index end)
lcl.player_isLocalPlayer = lcl.player_base and lcl.player_base.isLocalPlayer
lcl.player_getModData    = lcl.player_base and lcl.player_base.getModData

lcl.sm_base    = bindJava(function() return __classmetatables[ScriptManager.class].__index end)
lcl.sm_getItem = lcl.sm_base and lcl.sm_base.getItem

lcl.item_base           = bindJava(function() return __classmetatables[zombie.scripting.objects.Item.class].__index end)
lcl.item_getDisplayName = lcl.item_base and lcl.item_base.getDisplayName

lcl.hw_base                = bindJava(function() return __classmetatables[HandWeapon.class].__index end)
lcl.hw_getWeaponCategories = lcl.hw_base and lcl.hw_base.getWeaponCategories
lcl.hw_getPerk             = lcl.hw_base and lcl.hw_base.getPerk
lcl.hw_getSubCategory      = lcl.hw_base and lcl.hw_base.getSubCategory
lcl.hw_getType             = lcl.hw_base and lcl.hw_base.getType
lcl.hw_isInstantExplosion  = lcl.hw_base and lcl.hw_base.isInstantExplosion
lcl.hw_getExplosionRange   = lcl.hw_base and lcl.hw_base.getExplosionRange

lcl.ArrayList_base        = bindJava(function() return __classmetatables[ArrayList.class].__index end)
lcl.ArrayList_size        = lcl.ArrayList_base and lcl.ArrayList_base.size
lcl.ArrayList_get         = lcl.ArrayList_base and lcl.ArrayList_base.get
"""
    if old not in text:
        raise SystemExit("WeaponTypeKillCount.lua patch point not found")
    return text.replace(old, new, 1)


def main() -> int:
    load_dotenv()
    prev = active_id() or "local-dedi"
    set_active(LIVE_ID)
    dry = "--dry" in sys.argv
    try:
        files = collect_registry_files()
        log(f"[harvest] registry files={len(files)}")
        merged: dict[str, str] = {}
        for mid, wanted in PACK_GLOBALS.items():
            text = merge_for_pack(wanted, files)
            merged[mid] = text
            log(f"[merge] {mid} bytes={len(text)} globals={wanted}")
        if dry:
            for mid, text in merged.items():
                out = BACKUPS / f"{mid}_registries.lua"
                out.write_text(text, encoding="utf-8")
                log(f"[dry] {out}")
            return 0
        client = active_files_client()
        client.config.timeout = 120
        for mid, text in merged.items():
            write_everywhere(mid, "42/media/registries.lua", text, client)

        traits = STEAM_WS / FIVE_WS[0] / "mods" / "MeatballsLibraries" / "42/media/lua/client/Starlit/client/internal/Traits.lua"
        refl = STEAM_WS / FIVE_WS[0] / "mods" / "MeatballsLibraries" / "42/media/lua/shared/Starlit/utils/Reflection.lua"
        kc = STEAM_WS / FIVE_WS[4] / "mods" / "MeatballsGameplay" / "42/media/lua/client/WeaponTypeKillCount.lua"
        write_everywhere("MeatballsLibraries", "42/media/lua/client/Starlit/client/internal/Traits.lua", patch_traits(traits.read_text(encoding="utf-8")), client)
        write_everywhere("MeatballsLibraries", "42/media/lua/shared/Starlit/utils/Reflection.lua", patch_reflection(refl.read_text(encoding="utf-8")), client)
        write_everywhere("MeatballsGameplay", "42/media/lua/client/WeaponTypeKillCount.lua", patch_killcount(kc.read_text(encoding="utf-8")), client)
        log("[done] Restart PZ client. Other players need a Workshop update of Character+Libraries+Gameplay.")
        return 0
    finally:
        set_active(prev)
        log(f"[profile] restored {prev}")


if __name__ == "__main__":
    raise SystemExit(main())
