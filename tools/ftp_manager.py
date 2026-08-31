#!/usr/bin/env python3
"""CLI for FTP pull/push operations against the PZ dedicated server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from ftp_client import (  # noqa: E402
    DEFAULT_CONFIG_FILES,
    client_from_env,
    join_remote,
    load_dotenv,
    normalize_remote,
)

REMOTE_CONFIGS_DIR = ROOT / "remote_configs"
DEFAULT_REMOTE_MODS = os.environ.get("FTP_REMOTE_MODS_DIR", "/mods")


def cmd_list(args: argparse.Namespace) -> int:
    client = client_from_env()
    if args.tree:
        print(client.list_tree(args.remote_path))
        return 0
    entries = client.list_files(args.remote_path, recursive=args.recursive)
    print(json.dumps(entries, indent=2))
    return 0


def cmd_pull_configs(args: argparse.Namespace) -> int:
    load_dotenv()
    client = client_from_env()
    REMOTE_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)

    names = args.names or list(DEFAULT_CONFIG_FILES)
    pulled: list[str] = []
    missing: list[str] = []

    all_files = client.list_files("/", recursive=True)
    index: dict[str, str] = {}
    for entry in all_files:
        if entry["type"] == "file":
            index[entry["name"]] = entry["path"]

    for name in names:
        remote_path = index.get(name)
        if not remote_path:
            missing.append(name)
            continue
        dest = REMOTE_CONFIGS_DIR / name
        client.download_file(remote_path, dest)
        pulled.append(str(dest))
        print(f"Pulled {remote_path} -> {dest}")

    manifest = {
        "pulled": pulled,
        "missing": missing,
        "output_dir": str(REMOTE_CONFIGS_DIR),
    }
    (REMOTE_CONFIGS_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    if missing:
        print(f"Missing on remote: {', '.join(missing)}", file=sys.stderr)
    return 0 if pulled else 1


def cmd_push_mods(args: argparse.Namespace) -> int:
    load_dotenv()
    pack_name = args.pack
    local_dir = Path(args.local_dir) if args.local_dir else ROOT / "src" / "modpacks" / pack_name
    if not local_dir.is_dir():
        alt = ROOT / "src" / "modpacks" / "output" / pack_name
        if alt.is_dir():
            local_dir = alt
        else:
            print(f"Modpack directory not found: {local_dir}", file=sys.stderr)
            return 1

    remote_dir = normalize_remote(args.remote_dir or DEFAULT_REMOTE_MODS)
    if args.pack_subdir:
        remote_dir = join_remote(remote_dir, pack_name)

    client = client_from_env()
    print(f"Syncing {local_dir} -> {remote_dir}")
    result = client.sync_modpack(local_dir, remote_dir)
    print(json.dumps(
        {
            "uploaded": result.uploaded,
            "skipped": result.skipped,
            "errors": result.errors,
        },
        indent=2,
    ))
    return 1 if result.errors else 0


def cmd_read(args: argparse.Namespace) -> int:
    client = client_from_env()
    print(client.read_file(args.remote_path))
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="PZ dedicated server FTP manager")
    sub = parser.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list", help="List remote directory")
    ls.add_argument("remote_path", nargs="?", default="/")
    ls.add_argument("--recursive", action="store_true")
    ls.add_argument("--tree", action="store_true")
    ls.set_defaults(func=cmd_list)

    pull = sub.add_parser("pull-configs", help="Download server INI/shell scripts")
    pull.add_argument("--name", dest="names", action="append", help="Config filename")
    pull.set_defaults(func=cmd_pull_configs)

    push = sub.add_parser("push-mods", help="Upload modpack via MD5 sync")
    push.add_argument("--pack", required=True, help="Modpack folder name under src/modpacks/")
    push.add_argument("--local-dir", help="Override local modpack path")
    push.add_argument("--remote-dir", help=f"Remote mods root (default {DEFAULT_REMOTE_MODS})")
    push.add_argument("--pack-subdir", action="store_true", help="Upload into <remote>/<pack>/")
    push.set_defaults(func=cmd_push_mods)

    read = sub.add_parser("read", help="Print remote file contents")
    read.add_argument("remote_path")
    read.set_defaults(func=cmd_read)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
