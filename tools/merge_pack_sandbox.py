#!/usr/bin/env python3
"""Harvest inner-mod sandbox-options and merge them into live world_SandboxVars.lua."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from apply_five_live_ini import FIVE, FIVE_WS, LIVE_ID, log, set_active  # noqa: E402
from ftp_client import load_dotenv  # noqa: E402
from panel.prefs import remember_remote  # noqa: E402
from panel.servers import active_files_client, active_id  # noqa: E402
from panel.services.pack_merger import BACKUPS, _backup_ini_content, _remote_paths  # noqa: E402

MIRROR = ROOT / ".mirror" / "meatballs-xl" / "mods"
STEAM_WS = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\108600")
LUA_SV = re.compile(r"SandboxVars\.([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)")
OPTION_RE = re.compile(
    r"option\s+([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\{([^}]*)\}",
    re.MULTILINE,
)
DEFAULT_RE = re.compile(r"default\s*=\s*([^,\n]*)", re.IGNORECASE)
TYPE_RE = re.compile(r"type\s*=\s*([A-Za-z]+)", re.IGNORECASE)
VER_RE = re.compile(r"^42(?:\.(\d+))?", re.IGNORECASE)


def lua_literal(raw: str, type_name: str) -> str:
    value = raw.strip().strip(",")
    kind = (type_name or "").lower()
    if kind == "boolean":
        return "true" if value.lower() == "true" else "false"
    if kind in {"integer", "int", "double", "float", "enum"}:
        return value or "0"
    if kind == "string":
        if not value:
            return '""'
        if value.startswith('"') and value.endswith('"'):
            return value
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered
    if re.fullmatch(r"-?\d+(\.\d+)?", value):
        return value
    if not value:
        return '""'
    if value.startswith('"') and value.endswith('"'):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_sandbox_options(text: str) -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}
    for match in OPTION_RE.finditer(text):
        table, key, body = match.group(1), match.group(2), match.group(3)
        type_match = TYPE_RE.search(body)
        default_match = DEFAULT_RE.search(body)
        if not default_match:
            continue
        type_name = type_match.group(1) if type_match else ""
        tables.setdefault(table, {})[key] = lua_literal(default_match.group(1), type_name)
    return tables


def option_blocks(text: str) -> dict[tuple[str, str], str]:
    blocks: dict[tuple[str, str], str] = {}
    for match in OPTION_RE.finditer(text):
        blocks[(match.group(1), match.group(2))] = match.group(0).strip()
    return blocks


def version_score(path: Path) -> int:
    parts = [p.lower() for p in path.parts]
    if any(p.startswith("meatballs") for p in parts):
        return 1
    best = 0
    for part in parts:
        match = VER_RE.match(part)
        if not match:
            continue
        minor = int(match.group(1) or "20")
        best = max(best, 4000 + minor)
    if "common" in parts:
        best = max(best, 500)
    if path.parent.name.lower() == "media":
        best = max(best, 100)
    return best


def harvest_roots() -> list[Path]:
    return [
        ROOT / "src" / "mods",
        Path.home() / "Zomboid" / "mods",
        STEAM_WS,
        ROOT / ".mirror" / "meatballs-xl" / "steamapps" / "workshop" / "content" / "108600",
        MIRROR,
    ]


def harvest_options() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    values: dict[str, dict[str, str]] = {}
    blocks: dict[str, dict[str, str]] = {}
    scores: dict[str, int] = {}
    for root in harvest_roots():
        if not root.exists():
            continue
        for path in root.rglob("sandbox-options.txt"):
            score = version_score(path)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parsed = parse_sandbox_options(text)
            raw = option_blocks(text)
            for table, options in parsed.items():
                prev = scores.get(table, -1)
                if score < prev:
                    continue
                if score > prev:
                    values[table] = dict(options)
                    blocks[table] = {}
                    scores[table] = score
                else:
                    values.setdefault(table, {}).update(options)
                for (t, key), block in raw.items():
                    if t == table:
                        blocks[table][key] = block
    return values, blocks


def pack_lua_tables(mods_root: Path) -> dict[str, dict[str, set[str]]]:
    needed: dict[str, dict[str, set[str]]] = {mid: {} for mid in FIVE}
    for mid in FIVE:
        lua_dir = mods_root / mid / "42" / "media" / "lua"
        if not lua_dir.is_dir():
            continue
        for path in lua_dir.rglob("*.lua"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in LUA_SV.finditer(text):
                needed[mid].setdefault(match.group(1), set()).add(match.group(2))
    return needed


def top_level_keys(lua: str) -> set[str]:
    start = lua.find("SandboxVars")
    brace = lua.find("{", start) if start >= 0 else -1
    if brace < 0:
        return set()
    keys: set[str] = set()
    depth = 0
    i = brace
    token = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")
    while i < len(lua):
        ch = lua[i]
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                break
            i += 1
            continue
        if ch == '"':
            i += 1
            while i < len(lua) and lua[i] != '"':
                if lua[i] == "\\":
                    i += 1
                i += 1
            i += 1
            continue
        if depth == 1:
            match = token.match(lua, i)
            if match:
                keys.add(match.group(1))
                i = match.end()
                continue
        i += 1
    return keys


def format_table(name: str, options: dict[str, str]) -> str:
    lines = [f"    {name} = {{"]
    for key in sorted(options):
        lines.append(f"        {key} = {options[key]},")
    lines.append("    },")
    return "\n".join(lines)


def merge_sandbox(lua: str, defaults: dict[str, dict[str, str]]) -> tuple[str, list[str]]:
    existing = top_level_keys(lua)
    added: list[str] = []
    blocks: list[str] = []
    for name in sorted(defaults):
        if name in existing or name == "VERSION":
            continue
        added.append(f"{name} ({len(defaults[name])} keys)")
        blocks.append(format_table(name, defaults[name]))
    if not blocks:
        return lua, added
    stripped = lua.rstrip()
    if not stripped.endswith("}"):
        raise SystemExit("world_SandboxVars.lua does not end with }")
    body, _, _ = stripped.rpartition("}")
    body = body.rstrip()
    if not body.endswith(","):
        body += ","
    return body + "\n\n" + "\n\n".join(blocks) + "\n}\n", added


def write_sandbox_options(tables: list[str], harvested_blocks: dict[str, dict[str, str]]) -> str:
    chunks = ["VERSION = 1,\n"]
    for table in sorted(tables):
        for key in sorted(harvested_blocks.get(table, {})):
            chunks.append(harvested_blocks[table][key] + "\n")
    return "\n".join(chunks)


def sandbox_remote() -> tuple[str, str]:
    paths = _remote_paths(LIVE_ID)
    sandbox_name = paths["ini_name"].replace(".ini", "_SandboxVars.lua")
    remote = paths["ini_remote"].rsplit("/", 1)[0] + "/" + sandbox_name
    return remote, sandbox_name


def needed_defaults(
    lua_tables: dict[str, dict[str, set[str]]], harvested: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    wanted: dict[str, set[str]] = {}
    for tables in lua_tables.values():
        for name, keys in tables.items():
            wanted.setdefault(name, set()).update(keys)
    out: dict[str, dict[str, str]] = {}
    for name, keys in wanted.items():
        if name in harvested:
            out[name] = dict(harvested[name])
            for key in keys:
                out[name].setdefault(key, "true")
            continue
        stub = {}
        for key in sorted(keys):
            stub[key] = "1" if key.startswith("Level") else "true"
        if stub:
            out[name] = stub
    return out


def main() -> int:
    load_dotenv()
    previous_active = active_id() or "local-dedi"
    set_active(LIVE_ID)
    dry = "--dry" in sys.argv
    try:
        harvested, blocks = harvest_options()
        lua_tables = pack_lua_tables(MIRROR)
        defaults = needed_defaults(lua_tables, harvested)
        missing_lua = sorted(
            {name for names in lua_tables.values() for name in names if name not in harvested}
        )
        log(f"[harvest] tables={len(harvested)} needed={len(defaults)} lua-missing={missing_lua[:20]}")
        remote, sandbox_name = sandbox_remote()
        client = active_files_client()
        client.config.timeout = 120
        log(f"[ftp] pull {remote}")
        previous = client.read_file(remote)
        if isinstance(previous, bytes):
            previous = previous.decode("utf-8", errors="replace")
        merged, added = merge_sandbox(previous, defaults)
        log(f"[merge] missing tables to add={len(added)}")
        for name in added:
            log(f"[add] {name}")
        backup = _backup_ini_content(sandbox_name, previous)
        log(f"[backup] {backup}")
        sandbox_files: dict[str, str] = {}
        for mid in FIVE:
            text = write_sandbox_options(sorted(set(lua_tables[mid]) & set(blocks)), blocks)
            sandbox_files[mid] = text
            log(f"[options] {mid} bytes={len(text)}")

        if dry:
            out = BACKUPS / "world_SandboxVars.merged.lua"
            out.write_text(merged, encoding="utf-8")
            for mid, text in sandbox_files.items():
                (BACKUPS / f"{mid}_sandbox-options.txt").write_text(text, encoding="utf-8")
            log(f"[dry] wrote {out} bytes={len(merged)}")
            return 0

        temp = BACKUPS / ".upload_world_SandboxVars.lua"
        temp.write_text(merged, encoding="utf-8")
        try:
            client.upload_file(temp, remote, allow_protected=True)
        finally:
            temp.unlink(missing_ok=True)
        remember_remote(sandbox_name, remote, merged)
        log(f"[ftp] uploaded {remote} bytes={len(merged)}")

        paths = _remote_paths(LIVE_ID)
        for mid, text in sandbox_files.items():
            local_pack = MIRROR / mid / "42" / "media" / "sandbox-options.txt"
            local_pack.parent.mkdir(parents=True, exist_ok=True)
            local_pack.write_text(text, encoding="utf-8")
            steam_pack = STEAM_WS / FIVE_WS[FIVE.index(mid)] / "mods" / mid / "42" / "media" / "sandbox-options.txt"
            if steam_pack.parent.is_dir():
                steam_pack.write_text(text, encoding="utf-8")
            opt_temp = BACKUPS / f".upload_{mid}_sandbox-options.txt"
            opt_temp.write_text(text, encoding="utf-8")
            ws = FIVE_WS[FIVE.index(mid)]
            remotes = [
                f"{paths['mods_dir']}/{mid}/42/media/sandbox-options.txt",
                f"/steamapps/workshop/content/108600/{ws}/mods/{mid}/42/media/sandbox-options.txt",
            ]
            try:
                for remote_opt in remotes:
                    client.upload_file(opt_temp, remote_opt, allow_protected=True)
                    log(f"[ftp] uploaded {remote_opt}")
            finally:
                opt_temp.unlink(missing_ok=True)

        log("[done] Restart the XLGAMES JVM so SandboxVars reload.")
        return 0
    finally:
        set_active(previous_active)
        log(f"[profile] restored {previous_active}")


if __name__ == "__main__":
    raise SystemExit(main())
