#!/usr/bin/env python3
"""Upload ResetLua nil-guards already patched in the local Steam workshop cache."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from apply_five_live_ini import FIVE, FIVE_WS, LIVE_ID, log, set_active  # noqa: E402
from ftp_client import load_dotenv  # noqa: E402
from merge_pack_registries import STEAM_WS, write_everywhere  # noqa: E402
from panel.servers import active_files_client, active_id  # noqa: E402

FILES = (
    ("MeatballsCharacter", "42/media/lua/shared/SpongieOpenJackets/BodyLocations_Setup.lua"),
    (
        "MeatballsCharacter",
        "42/media/lua/client/CharacterCustomisation/BodyDetailWindow/CharacterCustomisationPanel.lua",
    ),
    ("MeatballsCore", "42/media/lua/client/AdminToolsClient.lua"),
    ("MeatballsGameplay", "42/media/lua/client/MDFT_CharacterCreationProfession.lua"),
    (
        "MeatballsGameplay",
        "42/media/lua/client/ModManager/OptionScreens/ServerSettingsScreen.lua",
    ),
    (
        "MeatballsGameplay",
        "42/media/lua/client/OptionScreens/MLOS_ServerSettingsScreen_overrides.lua",
    ),
    ("MeatballsGameplay", "42/media/lua/client/WeaponTypeKillCount.lua"),
)


def steam_path(mid: str, rel: str) -> Path:
    ws = FIVE_WS[FIVE.index(mid)]
    return STEAM_WS / ws / "mods" / mid / rel.replace("/", "\\")


def main() -> int:
    load_dotenv()
    prev = active_id() or "local-dedi"
    set_active(LIVE_ID)
    try:
        client = active_files_client()
        client.config.timeout = 120
        for mid, rel in FILES:
            path = steam_path(mid, rel)
            if not path.is_file():
                raise SystemExit(f"missing {path}")
            text = path.read_text(encoding="utf-8")
            write_everywhere(mid, rel.replace("\\", "/"), text, client)
        log("[done] ResetLua guards uploaded. Full-kill PZ client, then Join.")
        return 0
    finally:
        set_active(prev)
        log(f"[profile] restored {prev}")


if __name__ == "__main__":
    raise SystemExit(main())
