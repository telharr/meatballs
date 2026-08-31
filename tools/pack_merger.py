#!/usr/bin/env python3
"""Modpack compiler: merge Workshop mods, validate manifests and collisions."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

MOD_INFO = "mod.info"
TILEDEF_PATTERN = re.compile(r"^\s*tiledef\s*=\s*(\d+)", re.IGNORECASE | re.MULTILINE)
LUA_HOOK_PATTERN = re.compile(
    r"\b(?:Events|Event)\.([A-Za-z0-9_]+)\s*\.\s*Add\s*\(",
    re.MULTILINE,
)
TEXTURE_EXTS = {".png", ".jpg", ".jpeg", ".tga", ".dds"}


@dataclass
class ModInfo:
    path: Path
    id: str
    name: str
    workshop_id: str | None = None
    tiledefs: list[int] = field(default_factory=list)
    textures: list[str] = field(default_factory=list)
    lua_hooks: list[str] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class Conflict:
    kind: str
    message: str
    mod_a: str
    mod_b: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def parse_mod_info(mod_dir: Path) -> ModInfo | None:
    info_path = mod_dir / MOD_INFO
    if not info_path.exists():
        return None

    raw: dict[str, str] = {}
    for line in info_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            raw[key.strip().lower()] = value.strip()

    mod_id = raw.get("id", mod_dir.name)
    mod_name = raw.get("name", mod_id)
    workshop_id = raw.get("workshopid") or raw.get("workshop_id")

    tiledefs: list[int] = []
    textures: list[str] = []
    lua_hooks: list[str] = []
    for path in mod_dir.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        suffix = path.suffix.lower()
        if suffix in TEXTURE_EXTS:
            textures.append(path.name.lower())
        if suffix == ".lua":
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lua_hooks.extend(LUA_HOOK_PATTERN.findall(content))
        if suffix == ".txt" and ("tiledef" in lower or "tiles" in str(path.parent).lower()):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            tiledefs.extend(int(m.group(1)) for m in TILEDEF_PATTERN.finditer(content))

    return ModInfo(
        path=mod_dir,
        id=mod_id,
        name=mod_name,
        workshop_id=workshop_id,
        tiledefs=sorted(set(tiledefs)),
        textures=sorted(set(textures)),
        lua_hooks=sorted(set(lua_hooks)),
        raw=raw,
    )


def scan_mods(source_dirs: list[Path]) -> list[ModInfo]:
    mods: list[ModInfo] = []
    seen_paths: set[Path] = set()

    for source in source_dirs:
        if not source.exists():
            continue
        for info_file in source.rglob(MOD_INFO):
            mod_dir = info_file.parent
            resolved = mod_dir.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            parsed = parse_mod_info(mod_dir)
            if parsed:
                mods.append(parsed)
    return mods


def detect_conflicts(mods: list[ModInfo]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    id_map: dict[str, ModInfo] = {}
    tiledef_map: dict[int, list[str]] = {}
    texture_map: dict[str, list[str]] = {}
    hook_map: dict[str, list[str]] = {}

    for mod in mods:
        if mod.id in id_map:
            conflicts.append(
                Conflict(
                    kind="duplicate_mod_id",
                    message=f"Duplicate mod.info id '{mod.id}'",
                    mod_a=mod.id,
                    mod_b=id_map[mod.id].id,
                )
            )
        id_map[mod.id] = mod

        for td in mod.tiledefs:
            tiledef_map.setdefault(td, []).append(mod.id)
        for tex in mod.textures:
            texture_map.setdefault(tex, []).append(mod.id)
        for hook in mod.lua_hooks:
            hook_map.setdefault(hook, []).append(mod.id)

    for tiledef, mod_ids in tiledef_map.items():
        unique = list(dict.fromkeys(mod_ids))
        if len(unique) > 1:
            conflicts.append(
                Conflict(
                    kind="tiledef_collision",
                    message=(
                        f"Tiledef {tiledef} used by multiple mods — "
                        "may cause 'duplicate texture' or Entity registration errors"
                    ),
                    mod_a=unique[0],
                    mod_b=unique[1],
                )
            )

    for tex, mod_ids in texture_map.items():
        unique = list(dict.fromkeys(mod_ids))
        if len(unique) > 1:
            conflicts.append(
                Conflict(
                    kind="duplicate_texture",
                    message=f"Texture filename '{tex}' appears in multiple mods",
                    mod_a=unique[0],
                    mod_b=unique[1],
                )
            )

    for hook, mod_ids in hook_map.items():
        unique = list(dict.fromkeys(mod_ids))
        if len(unique) > 1:
            conflicts.append(
                Conflict(
                    kind="duplicate_lua_hook",
                    message=f"Events.{hook}.Add used by multiple mods (order-sensitive)",
                    mod_a=unique[0],
                    mod_b=unique[1],
                )
            )

    return conflicts


def merge_modpack(
    mods: list[ModInfo],
    output_dir: Path,
    manifest_name: str = "manifest.json",
) -> Path:
    """Copy each mod as a subfolder (isolated multi-mod pack)."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    manifest = {
        "kind": "multi",
        "mods": [
            {
                "id": m.id,
                "name": m.name,
                "workshop_id": m.workshop_id,
                "source": str(m.path),
                "tiledefs": m.tiledefs,
            }
            for m in mods
        ],
    }

    for mod in mods:
        dest = output_dir / mod.id
        shutil.copytree(mod.path, dest, dirs_exist_ok=True)

    manifest_path = output_dir / manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _write_mod_info(path: Path, mod_id: str, name: str, description: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"name={name}",
                f"id={mod_id}",
                f"description={description}",
                "poster=poster.png",
                "",
            ]
        ),
        encoding="utf-8",
    )


def compile_unified_pack(
    mods: list[ModInfo],
    output_dir: Path,
    *,
    mod_id: str,
    mod_name: str,
    fail_on_conflict: bool = False,
) -> dict:
    """
    Merge selected mods into one isolated folder with a single mod.info.
    Scripts are concatenated under media/scripts/; other files are copied with
    last-wins on path collisions (reported in log).
    """
    conflicts = detect_conflicts(mods)
    if fail_on_conflict and conflicts:
        return {
            "ok": False,
            "conflicts": [c.to_dict() for c in conflicts],
            "output_dir": str(output_dir),
            "log": ["Aborted: conflicts and --fail-on-conflict set"],
        }

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    log: list[str] = [f"Compiling unified pack {mod_id} from {len(mods)} mod(s)"]
    overwritten: list[str] = []
    script_blobs: list[str] = []

    for mod in mods:
        log.append(f"+ {mod.id} ({mod.name}) from {mod.path}")
        for src in mod.path.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(mod.path)
            if rel.name.lower() == MOD_INFO:
                continue
            # Collect script texts for consolidation
            if rel.as_posix().lower().startswith("media/scripts/") and src.suffix.lower() == ".txt":
                body = src.read_text(encoding="utf-8", errors="replace")
                script_blobs.append(f"/* --- from {mod.id}/{rel.as_posix()} --- */\n{body}\n")
                continue
            dest = output_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                overwritten.append(str(rel).replace("\\", "/"))
            shutil.copy2(src, dest)

    if script_blobs:
        scripts_dir = output_dir / "media" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        merged_scripts = scripts_dir / f"{mod_id}_merged.txt"
        merged_scripts.write_text("\n".join(script_blobs), encoding="utf-8")
        log.append(f"Merged {len(script_blobs)} script file(s) -> {merged_scripts.name}")

    desc = "Unified server pack compiled by MEATBALLS panel: " + ", ".join(m.id for m in mods)
    _write_mod_info(output_dir / MOD_INFO, mod_id, mod_name, desc)

    manifest = {
        "kind": "unified",
        "id": mod_id,
        "name": mod_name,
        "sources": [
            {"id": m.id, "name": m.name, "workshop_id": m.workshop_id, "source": str(m.path)}
            for m in mods
        ],
        "overwritten_paths": overwritten[:200],
        "conflicts": [c.to_dict() for c in conflicts],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if overwritten:
        log.append(f"Path overwrites: {len(overwritten)} (last-wins)")
    log.append(f"Wrote {output_dir}")

    return {
        "ok": True,
        "mod_id": mod_id,
        "mod_name": mod_name,
        "output_dir": str(output_dir),
        "conflicts": [c.to_dict() for c in conflicts],
        "overwritten": overwritten[:100],
        "sources": [m.id for m in mods],
        "log": log,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge and validate PZ modpacks")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Source directory containing mods (repeatable)",
    )
    parser.add_argument(
        "--output",
        default="src/modpacks/output",
        help="Merged modpack output directory",
    )
    parser.add_argument("--unified-id", help="If set, compile a single unified mod folder")
    parser.add_argument("--unified-name", default="", help="Display name for unified pack")
    parser.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="Exit with error if conflicts are detected",
    )
    args = parser.parse_args()

    default_sources = [Path("src/mods"), Path(".cache/workshop")]
    sources = [Path(s) for s in args.source] if args.source else default_sources
    mods = scan_mods(sources)

    if not mods:
        print("No mods found. Add mods to src/mods/ or download via workshop_downloader.py")
        return 1

    print(f"Found {len(mods)} mod(s):")
    for mod in mods:
        td = f" tiledefs={mod.tiledefs}" if mod.tiledefs else ""
        print(f"  - {mod.id} ({mod.name}){td}")

    conflicts = detect_conflicts(mods)
    if conflicts:
        print("\nConflicts detected:")
        for c in conflicts:
            suffix = f" <-> {c.mod_b}" if c.mod_b else ""
            print(f"  [{c.kind}] {c.message}{suffix}")
        if args.fail_on_conflict and not args.unified_id:
            return 2
    else:
        print("\nNo conflicts detected.")

    output = Path(args.output)
    if args.unified_id:
        result = compile_unified_pack(
            mods,
            output,
            mod_id=args.unified_id,
            mod_name=args.unified_name or args.unified_id,
            fail_on_conflict=args.fail_on_conflict,
        )
        for line in result.get("log") or []:
            print(line)
        return 0 if result.get("ok") else 2

    manifest = merge_modpack(mods, output)
    print(f"\nModpack written to {output}")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
