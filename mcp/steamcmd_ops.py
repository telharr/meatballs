#!/usr/bin/env python3
"""Thin CLI contract for a future SteamCMD MCP / command-runner integration.

Exposes named operations that MCP wrappers can call without shelling ad-hoc strings.
Does not perform network I/O by itself when --dry-run is set.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def op_download(workshop_ids: list[str], dry_run: bool) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "workshop_downloader.py"),
        *workshop_ids,
    ]
    return {"op": "download", "cmd": cmd, "dry_run": dry_run}


def op_validate(sources: list[str], dry_run: bool) -> dict:
    cmd = [sys.executable, str(ROOT / "tools" / "pack_merger.py"), "--fail-on-conflict"]
    for src in sources:
        cmd.extend(["--source", src])
    return {"op": "validate", "cmd": cmd, "dry_run": dry_run}


def op_generate_vdf(content: str, title: str, dry_run: bool) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "uploader.py"),
        "generate",
        "--content",
        content,
        "--title",
        title,
    ]
    return {"op": "generate_vdf", "cmd": cmd, "dry_run": dry_run}


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP-facing SteamCMD / pack operations")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON plan only")
    sub = parser.add_subparsers(dest="op", required=True)

    d = sub.add_parser("download")
    d.add_argument("workshop_ids", nargs="+")

    v = sub.add_parser("validate")
    v.add_argument("--source", action="append", default=None)

    g = sub.add_parser("generate_vdf")
    g.add_argument("--content", required=True)
    g.add_argument("--title", required=True)

    args = parser.parse_args()

    if args.op == "download":
        plan = op_download(args.workshop_ids, args.dry_run)
    elif args.op == "validate":
        sources = args.source or ["src/mods", ".cache/workshop"]
        plan = op_validate(sources, args.dry_run)
    else:
        plan = op_generate_vdf(args.content, args.title, args.dry_run)

    print(json.dumps(plan, indent=2))

    if args.dry_run:
        return 0

    import subprocess

    return subprocess.call(plan["cmd"])


if __name__ == "__main__":
    raise SystemExit(main())
