#!/usr/bin/env python3
"""Steam Workshop VDF generator and publisher for Project Zomboid mods."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

PZ_APP_ID = "108600"
DEFAULT_STEAMCMD = Path("steamcmd") / ("steamcmd.exe" if os.name == "nt" else "steamcmd.sh")


def generate_vdf(
    content_path: Path,
    title: str,
    description: str,
    published_file_id: str | None = None,
    visibility: str = "0",
    tags: list[str] | None = None,
) -> str:
    tag_block = ""
    if tags:
        tag_lines = "\n".join(f'            "{tag}" ""' for tag in tags)
        tag_block = f"""
        "tags"
        {{
{tag_lines}
        }}"""

    update_block = ""
    if published_file_id:
        update_block = f'\n        "publishedfileid" "{published_file_id}"'

    return dedent(f"""\
        "workshopitem"
        {{
            "appid" "{PZ_APP_ID}"
            "publishedfileid" "{published_file_id or "0"}"
            "contentfolder" "{content_path.resolve().as_posix()}"
            "previewfile" ""
            "visibility" "{visibility}"
            "title" "{title}"
            "description" "{description}"
            "changenote" "Automated update via uploader.py"{update_block}{tag_block}
        }}
    """)


def publish(
    vdf_path: Path,
    steamcmd: Path,
    username: str,
    password_env: str = "STEAM_PASSWORD",
) -> int:
    password = os.environ.get(password_env)
    if not password:
        print(f"ERROR: Set {password_env} environment variable.", file=sys.stderr)
        return 1

    if not steamcmd.exists():
        print(f"ERROR: SteamCMD not found at {steamcmd}", file=sys.stderr)
        return 1

    cmd = [
        str(steamcmd),
        f"+login {username} {password}",
        f"+workshop_build_item {vdf_path.resolve()}",
        "+quit",
    ]
    print(f"[uploader] Publishing via {vdf_path}")
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and publish PZ Workshop VDF")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate workshop.vdf")
    gen.add_argument("--content", required=True, help="Path to mod content folder")
    gen.add_argument("--title", required=True)
    gen.add_argument("--description", default="")
    gen.add_argument("--output", default="workshop.vdf")
    gen.add_argument("--published-file-id", help="Existing Workshop ID for updates")
    gen.add_argument("--tag", action="append", default=[], help="Workshop tag (repeatable)")

    pub = sub.add_parser("publish", help="Publish workshop.vdf via SteamCMD")
    pub.add_argument("--vdf", default="workshop.vdf")
    pub.add_argument("--steamcmd", default=str(DEFAULT_STEAMCMD))
    pub.add_argument("--username", required=True)

    args = parser.parse_args()

    if args.command == "generate":
        vdf = generate_vdf(
            content_path=Path(args.content),
            title=args.title,
            description=args.description,
            published_file_id=args.published_file_id,
            tags=args.tag,
        )
        out = Path(args.output)
        out.write_text(vdf, encoding="utf-8")
        print(f"Generated {out}")
        return 0

    if args.command == "publish":
        return publish(Path(args.vdf), Path(args.steamcmd), args.username)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
