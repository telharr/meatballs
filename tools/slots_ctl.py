#!/usr/bin/env python3
"""Set empty test/NPC slot count. Writes local Lua/mb_slots.txt; optional FTP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ftp_client import client_from_env, load_dotenv  # noqa: E402
from panel.slots import iter_mod_files, set_slots, snapshot, write_temp_line  # noqa: E402


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Empty PZ slots for tests / future NPC")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    set_p = sub.add_parser("set")
    set_p.add_argument("count", type=int)
    set_p.add_argument("--x", type=int, default=0)
    set_p.add_argument("--y", type=int, default=0)
    set_p.add_argument("--z", type=int, default=0)
    set_p.add_argument("--ftp", action="store_true")
    set_p.add_argument("--upload-mod", action="store_true")
    args = parser.parse_args()

    if args.cmd == "show":
        print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
        return 0

    snap = set_slots(args.count, args.x, args.y, args.z)
    if args.ftp:
        temp = write_temp_line(snap)
        try:
            print(json.dumps(client_from_env().upload_file(temp, snap["remote"]), indent=2))
        finally:
            temp.unlink(missing_ok=True)
    if args.upload_mod:
        client = client_from_env()
        for local, remote in iter_mod_files():
            client.upload_file(local, remote)
            print(remote)
    print(json.dumps(snap, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
