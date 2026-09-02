#!/usr/bin/env python3
"""Catalog of local mods, Workshop items, and libraries for the MEATBALLS pack."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from pack_merger import parse_mod_info, scan_mods  # noqa: E402
from workshop_downloader import DEFAULT_OUTPUT, download_mod, find_steamcmd  # noqa: E402

LEGACY_CATALOG_PATH = ROOT / "src" / "modpacks" / "meatballs.catalog.json"
PANEL_CATALOG_PATH = ROOT / "panel" / "data" / "mods.catalog.json"
TEMPLATE = ROOT / "templates" / "mod"
LOCAL_MODS = ROOT / "src" / "mods"
WORKSHOP_CACHE = ROOT / ".cache" / "workshop"
INI_KEYS = ("Mods", "WorkshopItems")


def _default_catalog() -> dict[str, Any]:
    return {"name": "default", "ini_filename": "world.ini", "items": []}


def _ensure_catalog_file() -> None:
    if PANEL_CATALOG_PATH.exists():
        return
    PANEL_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LEGACY_CATALOG_PATH.exists():
        PANEL_CATALOG_PATH.write_text(
            LEGACY_CATALOG_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return
    save_catalog(_default_catalog())


def load_catalog() -> dict[str, Any]:
    _ensure_catalog_file()
    return json.loads(PANEL_CATALOG_PATH.read_text(encoding="utf-8"))


def save_catalog(data: dict[str, Any]) -> None:
    PANEL_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PANEL_CATALOG_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def list_local_mods() -> list[dict[str, Any]]:
    mods = []
    for info in scan_mods([LOCAL_MODS]):
        mods.append(
            {
                "id": info.id,
                "name": info.name,
                "workshop_id": info.workshop_id,
                "path": str(info.path.relative_to(ROOT)).replace("\\", "/"),
                "source": "local",
            }
        )
    return mods


def list_workshop_cache() -> list[dict[str, Any]]:
    mods = []
    if not WORKSHOP_CACHE.exists():
        return mods
    for info in scan_mods([WORKSHOP_CACHE]):
        mods.append(
            {
                "id": info.id,
                "name": info.name,
                "workshop_id": info.workshop_id,
                "path": str(info.path.relative_to(ROOT)).replace("\\", "/"),
                "source": "workshop",
            }
        )
    return mods


def add_item(
    *,
    kind: str,
    mod_id: str,
    workshop_id: str | None = None,
    name: str | None = None,
    source: str = "workshop",
    notes: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    kind = kind if kind in ("mod", "library") else "mod"
    source = source if source in ("local", "workshop") else "workshop"
    catalog = load_catalog()
    item = {
        "kind": kind,
        "id": mod_id.strip(),
        "name": (name or mod_id).strip(),
        "source": source,
        "enabled": enabled,
    }
    if workshop_id:
        item["workshop_id"] = str(workshop_id).strip()
    if source == "local":
        item["path"] = f"src/mods/{mod_id.strip()}"
    if notes:
        item["notes"] = notes

    items = catalog.setdefault("items", [])
    for i, existing in enumerate(items):
        same_id = existing.get("id") == item["id"]
        same_ws = workshop_id and existing.get("workshop_id") == item.get("workshop_id")
        if same_id or same_ws:
            items[i] = {**existing, **item}
            save_catalog(catalog)
            return items[i]
    items.append(item)
    save_catalog(catalog)
    return item


def remove_item(mod_id: str) -> bool:
    catalog = load_catalog()
    before = len(catalog.get("items", []))
    catalog["items"] = [i for i in catalog.get("items", []) if i.get("id") != mod_id]
    save_catalog(catalog)
    return len(catalog["items"]) < before


def set_item_enabled(mod_id: str, enabled: bool) -> dict[str, Any]:
    catalog = load_catalog()
    for item in catalog.get("items", []):
        if item.get("id") == mod_id:
            item["enabled"] = bool(enabled)
            save_catalog(catalog)
            return item
    raise KeyError(mod_id)


def _lookup_known_mod(mod_id: str) -> dict[str, Any] | None:
    for row in list_local_mods() + list_workshop_cache():
        if row.get("id") == mod_id:
            return row
    return None


def _lookup_workshop_mod(workshop_id: str) -> dict[str, Any] | None:
    for row in list_workshop_cache():
        if str(row.get("workshop_id") or "") == str(workshop_id):
            return row
    return None


def import_from_lists(mods: list[str], workshop_ids: list[str]) -> dict[str, Any]:
    catalog = load_catalog()
    existing_ids = {str(i.get("id")) for i in catalog.get("items", []) if i.get("id")}
    existing_ws = {
        str(i.get("workshop_id"))
        for i in catalog.get("items", [])
        if i.get("workshop_id")
    }
    added: list[str] = []

    for mod_id in mods:
        mid = str(mod_id).strip()
        if not mid or mid in existing_ids:
            continue
        known = _lookup_known_mod(mid)
        add_item(
            kind="mod",
            mod_id=mid,
            name=(known or {}).get("name") or mid,
            workshop_id=(known or {}).get("workshop_id"),
            source=(known or {}).get("source") or "local",
            enabled=True,
        )
        existing_ids.add(mid)
        added.append(mid)

    for ws_id in workshop_ids:
        wid = str(ws_id).strip()
        if not wid or wid in existing_ws:
            continue
        known = _lookup_workshop_mod(wid)
        mod_id = (known or {}).get("id") or wid
        if mod_id in existing_ids:
            existing_ws.add(wid)
            continue
        add_item(
            kind="mod",
            mod_id=mod_id,
            name=(known or {}).get("name") or mod_id,
            workshop_id=wid,
            source="workshop" if known else "workshop",
            enabled=True,
        )
        existing_ids.add(mod_id)
        existing_ws.add(wid)
        added.append(mod_id)

    return {"added": added, "count": len(added)}


def catalog_path() -> Path:
    _ensure_catalog_file()
    return PANEL_CATALOG_PATH


def scaffold_local(mod_id: str, name: str | None = None, kind: str = "mod") -> dict[str, Any]:
    safe = re.sub(r"[^A-Za-z0-9_]", "", mod_id)
    if not safe:
        raise ValueError("Invalid mod id")
    dest = LOCAL_MODS / safe
    if dest.exists():
        raise FileExistsError(f"Already exists: {dest}")
    if not TEMPLATE.is_dir():
        raise FileNotFoundError("templates/mod is missing")

    shutil.copytree(TEMPLATE, dest)
    readme = dest / "README.md"
    if readme.exists():
        readme.unlink()

    replacements = {
        "REPLACE_ME": safe,
    }
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".lua", ".txt", ".info", ".md"} and path.name != "mod.info":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for old, new in replacements.items():
            text = text.replace(old, new)
        if path.name == "mod.info" and name:
            text = re.sub(r"^name=.*$", f"name={name}", text, flags=re.M)
        path.write_text(text, encoding="utf-8")

    for path in list(dest.rglob("REPLACE_ME*")):
        path.rename(path.with_name(path.name.replace("REPLACE_ME", safe)))

    return add_item(kind=kind, mod_id=safe, name=name or safe, source="local")


def download_workshop(workshop_id: str, username: str | None = None) -> dict[str, Any]:
    steamcmd = find_steamcmd(None)
    code = download_mod(steamcmd, workshop_id, WORKSHOP_CACHE, username)
    if code != 0:
        raise RuntimeError(f"SteamCMD failed for {workshop_id} (exit {code})")

    app_content = WORKSHOP_CACHE / "steamapps" / "workshop" / "content" / "108600" / workshop_id
    search_roots = [p for p in (app_content, WORKSHOP_CACHE) if p.exists()]
    found = None
    for root in search_roots:
        for info in scan_mods([root]):
            if info.workshop_id == workshop_id or workshop_id in str(info.path):
                found = info
                break
        if found:
            break
    if not found and search_roots:
        scanned = scan_mods(search_roots)
        found = scanned[0] if scanned else None

    payload = {
        "kind": "mod",
        "mod_id": found.id if found else workshop_id,
        "name": found.name if found else workshop_id,
        "workshop_id": workshop_id,
        "source": "workshop",
    }
    return add_item(**payload)


def parse_ini_list(content: str, key: str) -> list[str]:
    match = re.search(rf"^{re.escape(key)}=(.*)$", content, re.M)
    if not match:
        return []
    return [part.strip() for part in match.group(1).split(";") if part.strip()]


def apply_lists_to_ini(content: str, mods: list[str], workshop_ids: list[str]) -> str:
    def _replace(text: str, key: str, value: str) -> str:
        pattern = rf"^{re.escape(key)}=.*$"
        line = f"{key}={value}"
        if re.search(pattern, text, re.M):
            return re.sub(pattern, line, text, count=1, flags=re.M)
        return text.rstrip() + f"\n{line}\n"

    text = _replace(content, "Mods", ";".join(mods))
    return _replace(text, "WorkshopItems", ";".join(workshop_ids))


def catalog_loadout() -> dict[str, list[str]]:
    items = [i for i in load_catalog().get("items", []) if i.get("enabled", True)]
    mods = [i["id"] for i in items if i.get("kind", "mod") != "library"]
    workshop = [str(i["workshop_id"]) for i in items if i.get("workshop_id")]
    return {"mods": mods, "workshop_ids": workshop}


def snapshot() -> dict[str, Any]:
    catalog = load_catalog()
    return {
        "catalog": catalog,
        "catalog_path": str(catalog_path().relative_to(ROOT)).replace("\\", "/"),
        "local_mods": list_local_mods(),
        "workshop_cache": list_workshop_cache(),
        "loadout": catalog_loadout(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MEATBALLS mod/library catalog")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("--id", required=True)
    add.add_argument("--kind", default="mod", choices=["mod", "library"])
    add.add_argument("--workshop-id")
    add.add_argument("--name")
    add.add_argument("--source", default="workshop", choices=["local", "workshop"])

    rm = sub.add_parser("remove")
    rm.add_argument("mod_id")

    sc = sub.add_parser("scaffold")
    sc.add_argument("--id", required=True)
    sc.add_argument("--name")
    sc.add_argument("--kind", default="mod", choices=["mod", "library"])

    dl = sub.add_parser("download")
    dl.add_argument("workshop_id")
    dl.add_argument("--username")

    args = parser.parse_args()
    if args.cmd == "list":
        print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "add":
        item = add_item(
            kind=args.kind,
            mod_id=args.id,
            workshop_id=args.workshop_id,
            name=args.name,
            source=args.source,
        )
        print(json.dumps(item, indent=2))
        return 0
    if args.cmd == "remove":
        ok = remove_item(args.mod_id)
        print("removed" if ok else "not found")
        return 0 if ok else 1
    if args.cmd == "scaffold":
        print(json.dumps(scaffold_local(args.id, args.name, args.kind), indent=2))
        return 0
    if args.cmd == "download":
        print(json.dumps(download_workshop(args.workshop_id, args.username), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
