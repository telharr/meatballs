"""Panel wrapper around tools.pack_merger for unified ModPack compile."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from panel.servers import active_id, mirror_root

ROOT = Path(__file__).resolve().parents[2]
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")


def _sources_for_server(server_id: str | None = None) -> list[Path]:
    sid = server_id or active_id() or "default"
    mirror = mirror_root(sid)
    return [
        mirror / "mods",
        mirror / "steamapps" / "workshop" / "content" / "108600",
        ROOT / "src" / "mods",
        ROOT / ".cache" / "workshop",
    ]


def list_available_mods(server_id: str | None = None) -> list[dict[str, Any]]:
    from pack_merger import scan_mods

    mods = scan_mods(_sources_for_server(server_id))
    return [
        {
            "id": m.id,
            "name": m.name,
            "workshop_id": m.workshop_id,
            "path": str(m.path),
            "tiledefs": m.tiledefs,
            "textures": len(m.textures),
            "lua_hooks": m.lua_hooks[:20],
        }
        for m in mods
    ]


def analyze_mods(mod_ids: list[str] | None = None, server_id: str | None = None) -> dict[str, Any]:
    from pack_merger import detect_conflicts, scan_mods

    mods = scan_mods(_sources_for_server(server_id))
    if mod_ids:
        wanted = {m.strip() for m in mod_ids if m.strip()}
        mods = [m for m in mods if m.id in wanted]
    conflicts = detect_conflicts(mods)
    return {
        "mods": [{"id": m.id, "name": m.name, "workshop_id": m.workshop_id} for m in mods],
        "conflicts": [c.to_dict() for c in conflicts],
        "count": len(mods),
    }


def compile_pack(
    *,
    mod_ids: list[str],
    pack_id: str,
    pack_name: str = "",
    server_id: str | None = None,
    fail_on_conflict: bool = False,
) -> dict[str, Any]:
    from pack_merger import compile_unified_pack, scan_mods

    pack_id = (pack_id or "").strip()
    if not ID_RE.match(pack_id):
        raise ValueError("pack_id must be alphanumeric (start with letter), e.g. ServerModPack_v1")
    wanted = [m.strip() for m in mod_ids if m.strip()]
    if not wanted:
        raise ValueError("Select at least one mod to compile")

    all_mods = scan_mods(_sources_for_server(server_id))
    by_id = {m.id: m for m in all_mods}
    missing = [mid for mid in wanted if mid not in by_id]
    if missing:
        raise ValueError(f"Mods not found: {', '.join(missing[:8])}")
    selected = [by_id[mid] for mid in wanted]

    sid = server_id or active_id() or "default"
    out = mirror_root(sid) / "modpacks" / pack_id
    result = compile_unified_pack(
        selected,
        out,
        mod_id=pack_id,
        mod_name=pack_name.strip() or pack_id,
        fail_on_conflict=fail_on_conflict,
    )
    # also expose under mods/ for smoke convenience
    if result.get("ok"):
        mods_link = mirror_root(sid) / "mods" / pack_id
        try:
            from workshop_downloader import link_or_copy

            link_or_copy(out, mods_link)
            result["mods_path"] = str(mods_link)
        except Exception as exc:
            result["mods_link_error"] = str(exc)[:200]
    return result
