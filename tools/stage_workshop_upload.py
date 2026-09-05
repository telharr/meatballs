#!/usr/bin/env python3
"""Stage PZ Workshop + SteamCMD folders for the five unified MEATBALLS mods."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / ".cache/workshop-packs/unified"
ASSETS = Path(r"C:\Users\zvaa\.cursor\projects\c-Users-zvaa-Desktop-MB\assets")
ZWORK = Path.home() / "Zomboid" / "Workshop"
STEAMCMD_OUT = ROOT / ".cache/workshop-upload"
README = STEAMCMD_OUT / "КАК_ЗАЛИТЬ.txt"

SERVER_NAME = "[RU] MEATBALLS [PVE] [MODS] 24/7"
SERVER_IP = "195.18.27.101:16281"
DISCORD = "https://discord.com/channels/1543576743170801664"
TELEGRAM = "https://t.me/meatballpz"
PANEL = "https://github.com/telharr/meatballs"
LIBRARIES_WS = "3796197817"
LIBRARIES_PAGE = f"https://steamcommunity.com/sharedfiles/filedetails/?id={LIBRARIES_WS}"
CORE_WS = "3796206775"
KI5_WS = "3796212345"
CHARACTER_WS = "3796217229"
PUBLISHED = {
    "MeatballsLibraries": LIBRARIES_WS,
    "MeatballsCore": CORE_WS,
    "MeatballsKI5": KI5_WS,
    "MeatballsCharacter": CHARACTER_WS,
}

PACKS = (
    {
        "id": "MeatballsLibraries",
        "title": "MEATBALLS Libraries (B42.20)",
        "preview": "preview-libraries.png",
        "blurb_ru": "Каркас сервера: библиотеки UI, TchernoLib, EasyConfig, YAPZLib. Ставь ПЕРВЫМ. Без него остальные четыре мода не загрузятся.",
        "blurb_en": "Framework pack: UI libs, TchernoLib, EasyConfig, YAPZLib. Subscribe FIRST. The other four mods require this id.",
        "tags": "Build 42;Multiplayer;Framework",
        "require_ws": None,
    },
    {
        "id": "MeatballsCore",
        "title": "MEATBALLS Core (B42.20)",
        "preview": "preview-core.png",
        "blurb_ru": "Ядро dedicated: логи, слоты тренеров, админ-инструменты, Better Safehouse + мост панели приватов. require=MeatballsLibraries.",
        "blurb_en": "Dedicated core: logs, trainer slots, admin tools, Better Safehouse + panel safehouse bridge. Requires MeatballsLibraries.",
        "tags": "Build 42;Multiplayer",
        "require_ws": "MeatballsLibraries",
    },
    {
        "id": "MeatballsKI5",
        "title": "MEATBALLS KI5 Garage (B42.20)",
        "preview": "preview-ki5.png",
        "blurb_ru": "Гараж KI5: damnlib, машины, трейлеры, VVR, Seat UI, фиксы bob. Замороженный снимок, не подписка на сотни Workshop. require=MeatballsLibraries.",
        "blurb_en": "KI5 garage snapshot: damnlib, vehicles, trailers, VVR, seat UI, bob last. Frozen copy, not live KI5 Workshop updates. Requires MeatballsLibraries.",
        "tags": "Build 42;Multiplayer;Vehicles",
        "require_ws": "MeatballsLibraries",
    },
    {
        "id": "MeatballsCharacter",
        "title": "MEATBALLS Character (B42.20)",
        "preview": "preview-character.png",
        "blurb_ru": "Персонаж и одежда: Spongie CC/Hair/Cloth, Fluffy Hair, ботинки, ALICE, ванильные расширенные наборы. require=MeatballsLibraries.",
        "blurb_en": "Character & clothing: Spongie CC/Hair/Cloth, Fluffy Hair, boots, ALICE, vanilla outfit expansions. Requires MeatballsLibraries.",
        "tags": "Build 42;Multiplayer;Clothes",
        "require_ws": "MeatballsLibraries",
    },
    {
        "id": "MeatballsGameplay",
        "title": "MEATBALLS Gameplay (B42.20)",
        "preview": "preview-gameplay.png",
        "blurb_ru": "QoL и мир: CleanUI, Common Sense, аирдропы, солнечная сеть PSR, двери, лут, бой. require=MeatballsLibraries.",
        "blurb_en": "QoL & world: CleanUI, Common Sense, airdrops, PSR solar, doors, loot, combat QoL. Requires MeatballsLibraries.",
        "tags": "Build 42;Multiplayer",
        "require_ws": "MeatballsLibraries",
    },
)

STEAM_DESC_MAX = 8000
WS_PAGE = "https://steamcommunity.com/sharedfiles/filedetails/?id="


def _url(href: str, label: str) -> str:
    return f"[url={href}]{label}[/url]"


def _parse_credits(credits: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for raw in credits.splitlines():
        line = raw.strip()
        if not line or line.startswith("id\t") or "copyright" in line.lower():
            continue
        if line.startswith("MEATBALLS ") or line.startswith("This item"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        mid, name, ws = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if name.endswith(")") and " (" in name:
            name = name[: name.rfind(" (")].strip()
        key = ws if ws.isdigit() else mid
        if key in seen:
            continue
        seen.add(key)
        rows.append((mid, name, ws))
    return rows


def _credits_bbcode(credits: str, *, clickable: bool) -> str:
    items = []
    for _mid, name, ws in _parse_credits(credits):
        if ws.isdigit():
            if clickable:
                items.append(f"[*] {_url(WS_PAGE + ws, name)}")
            else:
                items.append(f"[*] {name} ({ws})")
        else:
            items.append(f"[*] {name} ({_mid})")
    if not items:
        return ""
    return "[h1]Состав[/h1]\n[list]\n" + "\n".join(items) + "\n[/list]\n"


FOOTER = f"""
[h1]Сервер MEATBALLS[/h1]
[list]
[*] [b]Название:[/b] {SERVER_NAME}
[*] [b]Режим:[/b] PvE · моды · 24/7 · Muldraugh KY · Build 42.20
[*] [b]IP:[/b] {SERVER_IP}
[/list]
Зайти: клиент → Join → этот IP. Нужны все 5 модов набора, [b]Libraries первым[/b].

[h1]Ссылки[/h1]
[list]
[*] {_url(DISCORD, "Discord")}
[*] {_url(TELEGRAM, "Telegram")}
[*] {_url(PANEL, "Панель управления")}
[/list]

[h1]Как ставить[/h1]
[list=1]
[*] Подпишись на все 5 MEATBALLS: Libraries, Core, KI5, Character, Gameplay.
[*] Не включай в Mods= сразу оригинальный Workshop и этот пак — будет двойная загрузка.
[*] Mods=: MeatballsLibraries;MeatballsCore;MeatballsKI5;MeatballsCharacter;MeatballsGameplay
[/list]

[h1]Авторы[/h1]
Снимок чужих модов для dedicated MEATBALLS. Авторские права остаются у оригинальных авторов (ссылки в составе выше). Обновляем централизованно под вайп, не следим за ночными апдейтами Steam.
"""


def _page_body(pack: dict, credits: str = "", *, clickable_credits: bool = True) -> str:
    require = ""
    if pack["id"] != "MeatballsLibraries":
        require = (
            f"[b]Required:[/b] {_url(LIBRARIES_PAGE, 'MEATBALLS Libraries')} "
            f"(Workshop ID {LIBRARIES_WS})\n\n"
        )
    composition = _credits_bbcode(credits, clickable=clickable_credits)
    return (
        f"[h1]{pack['title']}[/h1]\n"
        f"[b]Mod ID:[/b] {pack['id']}\n\n"
        f"{pack['blurb_ru']}\n\n"
        f"[i]{pack['blurb_en']}[/i]\n\n"
        f"{require}"
        f"{composition}"
        f"{FOOTER}"
    )


def _steam_description(pack: dict, credits: str) -> str:
    text = _page_body(pack, credits, clickable_credits=True).strip() + "\n"
    if len(text) > STEAM_DESC_MAX:
        text = _page_body(pack, credits, clickable_credits=False).strip() + "\n"
    if len(text) > STEAM_DESC_MAX:
        text = text[: STEAM_DESC_MAX - 20].rstrip() + "\n…"
    return text


def _workshop_txt(
    pack: dict,
    credits: str = "",
    *,
    published_id: str = "",
    visibility: str = "2",
    title: str | None = None,
) -> str:
    body = _steam_description(pack, credits)
    lines = [
        "version=1",
        f"id={published_id}",
        f"title={title or pack['title']}",
    ]
    for line in body.strip("\n").splitlines():
        lines.append(f"description={line}")
    lines.append(f"tags={pack['tags']}")
    lines.append(f"visibility={visibility}")
    return "\n".join(lines) + "\n"


def _vdf(content: Path, preview: Path, pack: dict) -> str:
    desc = pack["blurb_en"].replace('"', "'")
    return f'''"workshopitem"
{{
    "appid" "108600"
    "publishedfileid" "0"
    "contentfolder" "{content.resolve().as_posix()}"
    "previewfile" "{preview.resolve().as_posix()}"
    "visibility" "2"
    "title" "{pack['title']}"
    "description" "{desc}"
    "changenote" "MEATBALLS B42.20 snapshot"
}}
'''


def _copy_mod(src_42: Path, dest_42: Path) -> None:
    if dest_42.exists():
        shutil.rmtree(dest_42)
    shutil.copytree(src_42, dest_42)


def main() -> None:
    if STEAMCMD_OUT.exists():
        shutil.rmtree(STEAMCMD_OUT)
    STEAMCMD_OUT.mkdir(parents=True)
    ZWORK.mkdir(parents=True, exist_ok=True)

    lines = [
        "MEATBALLS — как залить 5 модов в Steam Workshop",
        "Аккаунт SteamID 76561198012867660, должен владеть Project Zomboid.",
        "Web API ключ НЕ заливает файлы. Либо клиент PZ, либо SteamCMD.",
        "",
        "Порядок заливки: Libraries → Core → KI5 → Character → Gameplay.",
        "После Libraries скопируй его Workshop ID и в страницах остальных 4 укажи Required item.",
        "",
    ]

    for pack in PACKS:
        src = UNIFIED / pack["id"] / "42"
        if not src.is_dir():
            raise FileNotFoundError(src)
        preview_src = ASSETS / pack["preview"]
        if not preview_src.is_file():
            raise FileNotFoundError(preview_src)
        credits = (UNIFIED / pack["id"] / "credits.txt").read_text(encoding="utf-8", errors="replace")

        # PZ in-game uploader layout
        zroot = ZWORK / pack["id"]
        if zroot.exists():
            shutil.rmtree(zroot)
        dest_42 = zroot / "Contents" / "mods" / pack["id"] / "42"
        _copy_mod(src, dest_42)
        shutil.copy2(preview_src, zroot / "preview.png")
        shutil.copy2(preview_src, dest_42 / "poster.png")
        (zroot / "workshop.txt").write_text(
            _workshop_txt(pack, credits, published_id=PUBLISHED.get(pack["id"], "")),
            encoding="utf-8",
        )
        (zroot / "steam_description.txt").write_text(_steam_description(pack, credits), encoding="utf-8")

        # SteamCMD layout: contentfolder contains mods/<id>/
        croot = STEAMCMD_OUT / pack["id"]
        c42 = croot / "mods" / pack["id"] / "42"
        _copy_mod(src, c42)
        shutil.copy2(preview_src, croot / "preview.png")
        shutil.copy2(preview_src, c42 / "poster.png")
        shutil.copy2(zroot / "steam_description.txt", croot / "steam_description.txt")
        vdf = STEAMCMD_OUT / f"{pack['id']}.vdf"
        vdf.write_text(_vdf(croot, croot / "preview.png", pack), encoding="utf-8")

        lines += [
            f"=== {pack['id']} ===",
            f"Клиент PZ: {zroot}",
            f"  preview.png + workshop.txt + Contents\\mods\\{pack['id']}\\42\\",
            f"Описание для страницы Steam (вставить после Upload): {zroot / 'steam_description.txt'}",
            f"SteamCMD VDF: {vdf}",
            "",
        ]

    lines += [
        "Клиент PZ:",
        "1. Выключи dedicated GameServer.",
        "2. Запусти Project Zomboid (клиент), Steam онлайн.",
        "3. Главное меню → Workshop → создать/загрузить мод.",
        "4. Укажи папку C:\\Users\\zvaa\\Zomboid\\Workshop\\MeatballsLibraries",
        "5. Upload. Дождись id= в workshop.txt.",
        "6. Повтори для Core, KI5, Character, Gameplay.",
        "7. В браузере Steam открой каждый item → вставь steam_description.txt → Required: Libraries.",
        "",
        "SteamCMD (если UI игры не тянет KI5 ~450 МБ):",
        "cd C:\\Users\\zvaa\\Desktop\\MB",
        "steamcmd\\steamcmd.exe +login ЛОГИН +workshop_build_item C:\\Users\\zvaa\\Desktop\\MB\\.cache\\workshop-upload\\MeatballsLibraries.vdf +quit",
        "После успеха впиши publishedfileid в VDF вместо 0.",
        "",
        f"Сервер: {SERVER_NAME}",
        f"IP: {SERVER_IP}",
        f"Discord: {DISCORD}",
        f"Telegram: {TELEGRAM}",
        f"Panel: {PANEL}",
        "На dedicated XLGAMES не пиши WorkshopItems= этих пяти id (Steam-качалка хостера роняет B42).",
        "Mods=\\MeatballsLibraries;\\MeatballsCore;\\MeatballsKI5;\\MeatballsCharacter;\\MeatballsGameplay",
    ]
    README.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(README)
    print("Zomboid Workshop", ZWORK)
    print("SteamCMD", STEAMCMD_OUT)


if __name__ == "__main__":
    main()
