#!/usr/bin/env python3
"""Launch invite pack: print connect card, manage founders, RCON adduser.

Does not spoof Steam Query or spawn fake clients.
"""

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

from ftp_client import load_dotenv  # noqa: E402

from panel.launch import (  # noqa: E402
    add_founder,
    adduser_command,
    invite_text,
    load_roster,
    public_endpoints,
    remove_founder,
)
from panel.rcon_client import rcon_execute  # noqa: E402


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="PZ launch invites (real players)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("print", help="Invite text for Discord / VK")
    sub.add_parser("print-secret", help="Invite text including SERVER_PASSWORD")
    sub.add_parser("info", help="Public endpoints JSON")
    sub.add_parser("list", help="Founder roster")
    add_p = sub.add_parser("add", help="Add founder to local roster")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--steamid", default="")
    add_p.add_argument("--note", default="")
    rm_p = sub.add_parser("remove", help="Remove founder by id")
    rm_p.add_argument("id")
    user_p = sub.add_parser("adduser", help="RCON adduser (creates a real account)")
    user_p.add_argument("--name", required=True)
    user_p.add_argument("--password", default="")
    args = parser.parse_args()

    if args.cmd == "print":
        print(invite_text(include_password=False))
        return 0
    if args.cmd == "print-secret":
        print(invite_text(include_password=True))
        return 0
    if args.cmd == "info":
        print(json.dumps(public_endpoints(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "list":
        print(json.dumps(load_roster(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "add":
        row = add_founder(args.name, args.steamid, args.note)
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "remove":
        ok = remove_founder(args.id)
        print(json.dumps({"ok": ok}))
        return 0 if ok else 1
    cmd, pwd = adduser_command(args.name, args.password or None)
    output = rcon_execute(cmd)
    print(json.dumps({"command": cmd, "password": pwd, "output": output}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
