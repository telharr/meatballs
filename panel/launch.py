"""Launch roster + invite text. Real players only — no query spoof / fake clients."""

from __future__ import annotations

import json
import os
import re
import secrets
import string
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

PANEL = Path(__file__).resolve().parent
from panel.paths import DATA_DIR  # noqa: E402

FOUNDERS_FILE = DATA_DIR / "founders.json"

NAME_RE = re.compile(r"^[A-Za-z0-9_\-.]{2,24}$")
STEAM_RE = re.compile(r"^7656\d{13}$")


def _empty() -> dict[str, Any]:
    return {"founders": []}


def load_roster() -> dict[str, Any]:
    if not FOUNDERS_FILE.exists():
        return _empty()
    try:
        data = json.loads(FOUNDERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty()
    data.setdefault("founders", [])
    return data


def save_roster(data: dict[str, Any]) -> dict[str, Any]:
    FOUNDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FOUNDERS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return data


def public_endpoints() -> dict[str, Any]:
    try:
        from panel.servers import public_endpoints as profile_endpoints

        return profile_endpoints()
    except Exception:
        pass
    host = (
        os.environ.get("PUBLIC_HOST")
        or os.environ.get("RCON_HOST")
        or os.environ.get("FTP_HOST")
        or ""
    ).strip()
    game_port = int(os.environ.get("GAME_PORT", "16282") or "16282")
    query_port = int(os.environ.get("QUERY_PORT", "16281") or "16281")
    max_players = int(os.environ.get("MAX_PLAYERS", "32") or "32")
    name = (os.environ.get("PUBLIC_NAME") or "MEATBALLS PZ").strip()
    discord = (os.environ.get("DISCORD_INVITE") or "").strip()
    password_set = bool((os.environ.get("SERVER_PASSWORD") or "").strip())
    return {
        "public_name": name,
        "host": host,
        "game_port": game_port,
        "query_port": query_port,
        "max_players": max_players,
        "discord": discord,
        "password_required": password_set,
        "webhook_configured": bool((os.environ.get("DISCORD_WEBHOOK") or "").strip()),
    }


def invite_text(*, include_password: bool = False) -> str:
    info = public_endpoints()
    lines = [
        f"{info['public_name']} — открытие сервера",
        "",
        f"Имя в браузере Steam: {info['public_name']}",
        f"IP: {info['host'] or '—'}",
        f"Порт игры: {info['game_port']}",
        f"Слоты: {info['max_players']}",
    ]
    if include_password:
        try:
            from panel.servers import invite_password

            pwd = invite_password()
        except Exception:
            pwd = (os.environ.get("SERVER_PASSWORD") or "").strip()
        if pwd:
            lines.append(f"Пароль: {pwd}")
        else:
            lines.append("Пароль: (не задан в SERVER_PASSWORD)")
    elif info["password_required"]:
        lines.append("Пароль: спроси у админа / в Discord")
    if info["discord"]:
        lines.append(f"Discord: {info['discord']}")
    lines.extend(
        [
            "",
            "Клиент Project Zomboid 42.20, те же моды что на сервере.",
            "Favorites -> Add -> IP и порт, либо имя в Public.",
        ]
    )
    return "\n".join(lines)


def generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(8, min(length, 24))))


def validate_username(name: str) -> str:
    cleaned = (name or "").strip()
    if not NAME_RE.match(cleaned):
        raise ValueError("Ник: 2–24 символа, латиница, цифры, _ - .")
    return cleaned


def validate_steamid(steamid: str) -> str:
    cleaned = (steamid or "").strip()
    if not cleaned:
        return ""
    if not STEAM_RE.match(cleaned):
        raise ValueError("SteamID64 должен быть 17 цифр и начинаться с 7656")
    return cleaned


def add_founder(name: str, steamid: str = "", note: str = "") -> dict[str, Any]:
    username = validate_username(name)
    sid = validate_steamid(steamid)
    roster = load_roster()
    for row in roster["founders"]:
        if row.get("name", "").lower() == username.lower():
            raise ValueError(f"Уже в списке: {username}")
        if sid and row.get("steamid") == sid:
            raise ValueError(f"SteamID уже есть: {sid}")
    row = {
        "id": uuid.uuid4().hex[:12],
        "name": username,
        "steamid": sid,
        "note": (note or "").strip()[:200],
        "invited_at": datetime.now().isoformat(timespec="seconds"),
        "joined_at": None,
        "account_created": False,
    }
    roster["founders"].append(row)
    save_roster(roster)
    return row


def remove_founder(founder_id: str) -> bool:
    roster = load_roster()
    before = len(roster["founders"])
    roster["founders"] = [r for r in roster["founders"] if r.get("id") != founder_id]
    if len(roster["founders"]) == before:
        return False
    save_roster(roster)
    return True


def mark_account_created(name: str) -> dict[str, Any] | None:
    roster = load_roster()
    for row in roster["founders"]:
        if row.get("name", "").lower() == name.lower():
            row["account_created"] = True
            save_roster(roster)
            return row
    return None


def mark_joined(online: list[dict[str, str]]) -> list[dict[str, Any]]:
    roster = load_roster()
    names = {p.get("name", "").lower() for p in online}
    ids = {p.get("steamid") or p.get("id") or "" for p in online}
    now = datetime.now().isoformat(timespec="seconds")
    changed = False
    for row in roster["founders"]:
        hit = row.get("name", "").lower() in names
        sid = row.get("steamid") or ""
        if sid and sid in ids:
            hit = True
        if hit and not row.get("joined_at"):
            row["joined_at"] = now
            changed = True
    if changed:
        save_roster(roster)
    return roster["founders"]


def adduser_command(name: str, password: str | None = None) -> tuple[str, str]:
    username = validate_username(name)
    pwd = (password or "").strip() or generate_password()
    if any(ch in pwd for ch in '"\\'):
        raise ValueError("Пароль не должен содержать кавычки")
    return f'adduser "{username}" "{pwd}"', pwd


def announce_command(message: str) -> str:
    text = " ".join((message or "").split())
    if not text:
        raise ValueError("Пустое сообщение")
    if len(text) > 280:
        raise ValueError("Сообщение длиннее 280 символов")
    if '"' in text:
        raise ValueError("В servermsg нельзя кавычки — PZ RCON")
    return f'servermsg "{text}"'


def post_discord(content: str) -> dict[str, Any]:
    url = (os.environ.get("DISCORD_WEBHOOK") or "").strip()
    if not url.startswith("https://"):
        raise ValueError("DISCORD_WEBHOOK не задан в .env")
    body = json.dumps({"content": content[:1900]}, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=12) as resp:
            return {"ok": True, "status": resp.status}
    except URLError as exc:
        raise ValueError(f"Discord webhook: {exc}") from exc
