"""Server profiles: hosting-agnostic connection records. Secrets stay out of git."""

from __future__ import annotations

import json
import os
import re
import socket
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from ftp_client import FtpClient, FtpConfig, load_dotenv
from panel.prefs import load_prefs, save_prefs
from panel.rcon_client import RconClient, RconConfig

PANEL = Path(__file__).resolve().parent
ROOT = PANEL.parent
INDEX_FILE = PANEL / "data" / "servers.json"
PROFILES_DIR = PANEL / "data" / "servers"
SECRETS_DIR = PANEL / "data" / "secrets"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")

VIEW_REQUIREMENTS: dict[str, str] = {
    "console": "rcon",
    "players": "rcon",
    "scheduler": "rcon",
    "logs": "files",
    "chat": "files",
    "bans": "files",
    "privates": "files",
    "files": "files",
    "mods": "files",
    "workshop": "files",
    "mirror": "files",
    "wipe": "files",
    "npc": "files",
    "smoke": "files",
}

MEATBALLS_VIEWS = frozenset({"npc", "privates"})

CAP_HINTS: dict[str, str] = {
    "rcon": "нужен RCON",
    "files": "нужен FTP, SFTP или локальный путь",
    "query": "нужен Query UDP",
    "process": "нужен process.kind=local — иначе открой панель хостера",
    "meatballs": "Включите модуль MEATBALLS в профиле",
}

HOSTER_PRESETS: dict[str, dict[str, Any]] = {
    "xlgames": {
        "hoster": "xlgames",
        "plugins": {"meatballs": True},
        "rcon": {"port": 16284, "timeout": 10},
        "files": {
            "kind": "ftp",
            "port": 21,
            "tls": False,
            "root": "/ServerWorld",
            "mods": "/ServerWorld/mods",
            "ini": "world.ini",
        },
        "public": {"game_port": 16282, "query_port": 16281, "max_players": 32},
        "process": {"kind": "none"},
        "authority": "host_wins",
    },
    "vps": {
        "hoster": "vps",
        "plugins": {"meatballs": False},
        "rcon": {"port": 16262, "timeout": 10},
        "files": {
            "kind": "ftp",
            "port": 21,
            "tls": False,
            "root": "/Zomboid",
            "mods": "/Zomboid/mods",
            "ini": "servertest.ini",
        },
        "public": {"game_port": 16261, "query_port": 16261, "max_players": 32},
        "process": {"kind": "none"},
        "authority": "panel_wins",
    },
    "local": {
        "hoster": "local",
        "plugins": {"meatballs": False},
        "rcon": {"host": "127.0.0.1", "port": 16284, "timeout": 5},
        "files": {
            "kind": "local",
            "root": str(ROOT / ".cache" / "dedi-test"),
            "mods": "",
            "ini": "world.ini",
        },
        "public": {
            "host": "127.0.0.1",
            "game_port": 16261,
            "query_port": 16261,
            "max_players": 8,
            "name": "Local dedi",
        },
        "process": {"kind": "local"},
        "authority": "panel_wins",
    },
}


def _empty_index() -> dict[str, Any]:
    return {"active": None, "ids": []}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _slug(name: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (name or "server").lower()).strip("-")
    return raw[:40] or "server"


def load_index() -> dict[str, Any]:
    data = _read_json(INDEX_FILE)
    if not data:
        return _empty_index()
    data.setdefault("ids", [])
    data.setdefault("active", None)
    return data


def profile_ids_on_disk() -> list[str]:
    if not PROFILES_DIR.is_dir():
        return []
    found: list[str] = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        sid = path.stem
        if sid.startswith("."):
            continue
        if ID_RE.match(sid):
            found.append(sid)
    return found


def reconcile_index() -> dict[str, Any]:
    """Keep servers.json in sync with panel/data/servers/*.json."""
    index = load_index()
    disk_ids = profile_ids_on_disk()
    if not disk_ids:
        if index.get("ids"):
            index = _empty_index()
            save_index(index)
        return index
    changed = False
    if list(index.get("ids") or []) != disk_ids:
        index["ids"] = disk_ids
        changed = True
    active = index.get("active")
    if active not in disk_ids:
        index["active"] = disk_ids[0]
        changed = True
    if changed:
        save_index(index)
    return index


def save_index(data: dict[str, Any]) -> dict[str, Any]:
    _write_json(INDEX_FILE, data)
    return data


def _profile_path(server_id: str) -> Path:
    return PROFILES_DIR / f"{server_id}.json"


def _secrets_path(server_id: str) -> Path:
    return SECRETS_DIR / f"{server_id}.json"


def load_secrets(server_id: str) -> dict[str, str]:
    from panel.security_hardening import decrypt_secret

    data = _read_json(_secrets_path(server_id))
    out = {
        "rcon_password": str(data.get("rcon_password") or ""),
        "ftp_password": str(data.get("ftp_password") or ""),
        "sftp_private_key": str(data.get("sftp_private_key") or ""),
        "sftp_key_passphrase": str(data.get("sftp_key_passphrase") or ""),
        "server_password": str(data.get("server_password") or ""),
        "discord_webhook": str(data.get("discord_webhook") or ""),
    }
    for key, val in list(out.items()):
        try:
            out[key] = decrypt_secret(val)
        except Exception:
            # Legacy / wrong key — leave as stored so operator can re-save
            out[key] = val
    return out


def save_secrets(server_id: str, patch: dict[str, Any]) -> dict[str, str]:
    from panel.security_hardening import encrypt_secret

    merged = load_secrets(server_id)
    for key in (
        "rcon_password",
        "ftp_password",
        "sftp_private_key",
        "sftp_key_passphrase",
        "server_password",
        "discord_webhook",
    ):
        if key in patch and patch[key] is not None and patch[key] != "":
            merged[key] = str(patch[key])
    stored = {k: encrypt_secret(v) if v else "" for k, v in merged.items()}
    path = _secrets_path(server_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    _write_json(path, stored)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return merged


def _default_profile(server_id: str, name: str) -> dict[str, Any]:
    return {
        "id": server_id,
        "name": name,
        "hoster": "vps",
        "game_version": "",
        "rcon": {"host": "", "port": 16284, "timeout": 10},
        "files": {
            "kind": "ftp",
            "host": "",
            "port": 21,
            "user": "",
            "tls": False,
            "root": "/ServerWorld",
            "mods": "/ServerWorld/mods",
            "ini": "world.ini",
        },
        "public": {
            "host": "",
            "game_port": 16282,
            "query_port": 16281,
            "max_players": 32,
            "name": name,
        },
        "process": {"kind": "none"},
        "authority": "host_wins",
        "plugins": {},
        "capabilities": {
            "rcon": False,
            "files": False,
            "query": False,
            "process": False,
            "probed_at": None,
            "inferred": True,
            "notes": {},
        },
    }


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_profile(server_id: str) -> dict[str, Any]:
    path = _profile_path(server_id)
    if not path.exists():
        raise KeyError(server_id)
    data = _read_json(path)
    merged = _deep_merge(_default_profile(server_id, server_id), data)
    merged["id"] = server_id
    return merged


def empty_capabilities() -> dict[str, Any]:
    return {
        "rcon": False,
        "files": False,
        "query": False,
        "process": False,
        "probed_at": None,
        "inferred": True,
        "notes": {},
    }


def normalize_capabilities(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = raw or {}
    notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    return {
        "rcon": bool(data.get("rcon")),
        "files": bool(data.get("files")),
        "query": bool(data.get("query")),
        "process": bool(data.get("process")),
        "probed_at": data.get("probed_at"),
        "inferred": bool(data.get("inferred")),
        "notes": {str(k): str(v)[:240] for k, v in notes.items()},
    }


def effective_plugins(profile: dict[str, Any]) -> dict[str, bool]:
    plugins = profile.get("plugins") if isinstance(profile.get("plugins"), dict) else {}
    meatballs = plugins.get("meatballs")
    if meatballs is None:
        meatballs = str(profile.get("hoster") or "") == "xlgames"
    return {"meatballs": bool(meatballs)}


def infer_capabilities(profile: dict[str, Any], secrets: dict[str, str] | None = None) -> dict[str, Any]:
    files = profile.get("files") or {}
    rcon = profile.get("rcon") or {}
    pub = profile.get("public") or {}
    proc = profile.get("process") or {}
    sid = str(profile.get("id") or "")
    secrets = secrets if secrets is not None else (load_secrets(sid) if sid else {})
    kind = str(files.get("kind") or "")
    files_ok = False
    if kind == "local" and files.get("root"):
        files_ok = Path(str(files["root"])).is_dir()
    elif kind == "ftp":
        files_ok = bool(files.get("host") and (files.get("user") or (secrets or {}).get("ftp_password")))
    elif kind == "sftp":
        has_auth = bool(
            (secrets or {}).get("ftp_password")
            or (secrets or {}).get("sftp_private_key")
            or files.get("sftp_key_path")
        )
        files_ok = bool(files.get("host") and files.get("user") and has_auth)
    return {
        "rcon": bool(rcon.get("host") and (secrets or {}).get("rcon_password")),
        "files": files_ok,
        "query": bool((pub.get("host") or rcon.get("host")) and pub.get("query_port")),
        "process": str(proc.get("kind") or "none") == "local",
        "probed_at": None,
        "inferred": True,
        "notes": {
            "rcon": "host + пароль заданы" if rcon.get("host") and (secrets or {}).get("rcon_password") else "нет RCON",
            "files": "каталог есть" if files_ok else "канал файлов не задан",
            "query": "порт указан" if pub.get("query_port") else "нет query",
            "process": "local JVM" if str(proc.get("kind") or "") == "local" else "none — открой панель хостера",
        },
    }


def effective_capabilities(profile: dict[str, Any], secrets: dict[str, str] | None = None) -> dict[str, Any]:
    inferred = infer_capabilities(profile, secrets)
    stored = normalize_capabilities(profile.get("capabilities"))
    if stored.get("probed_at") or stored.get("inferred") is False:
        return {
            **stored,
            "inferred": False,
            "notes": stored.get("notes") or inferred.get("notes") or {},
        }
    return inferred


def views_state(caps: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    plugins = effective_plugins(profile or {})
    views: dict[str, Any] = {}
    for view, need in VIEW_REQUIREMENTS.items():
        ok = bool(caps.get(need))
        hint = CAP_HINTS.get(need, need)
        if view in MEATBALLS_VIEWS and not plugins.get("meatballs"):
            ok = False
            hint = CAP_HINTS["meatballs"]
        views[view] = {"ok": ok, "need": need, "hint": hint}
    return views


def evaluate_draft_capabilities(payload: dict[str, Any]) -> dict[str, Any]:
    notes: dict[str, str] = {}
    rcon = payload.get("rcon") or {}
    files = payload.get("files") or {}
    pub = payload.get("public") or {}
    secrets = payload.get("secrets") or {}
    rcon_ok = False
    if rcon.get("host") and secrets.get("rcon_password"):
        try:
            probe_rcon(
                {
                    "host": rcon.get("host"),
                    "port": rcon.get("port") or 16284,
                    "password": secrets.get("rcon_password"),
                    "timeout": rcon.get("timeout") or 8,
                }
            )
            rcon_ok = True
            notes["rcon"] = "players ok"
        except Exception as exc:
            notes["rcon"] = str(exc)[:200]
    elif rcon.get("host"):
        notes["rcon"] = "нет пароля — не проверяли"
    else:
        notes["rcon"] = "host не задан"

    files_ok = False
    kind = str(files.get("kind") or "ftp")
    has_target = (kind == "local" and files.get("root")) or (
        kind in ("ftp", "sftp") and files.get("host")
    )
    if has_target:
        try:
            probe_payload: dict[str, Any] = {
                "kind": kind,
                "host": files.get("host"),
                "user": files.get("user"),
                "password": secrets.get("ftp_password"),
                "root": files.get("root"),
                "tls": files.get("tls"),
                "sftp_key_path": files.get("sftp_key_path"),
                "sftp_private_key": secrets.get("sftp_private_key"),
                "sftp_key_passphrase": secrets.get("sftp_key_passphrase"),
            }
            if kind == "sftp":
                probe_payload["port"] = int(files.get("port") or files.get("sftp_port") or 22)
            else:
                probe_payload["port"] = int(files.get("port") or 21)
            result = probe_files(probe_payload)
            files_ok = bool(result.get("ok"))
            names = ", ".join((result.get("entries") or [])[:6])
            notes["files"] = names or result.get("error") or ("ok" if files_ok else "нет каталога")
        except Exception as exc:
            notes["files"] = str(exc)[:200]
    else:
        notes["files"] = "канал не задан"

    query_ok = False
    qhost = str(pub.get("host") or rcon.get("host") or "").strip()
    qport = pub.get("query_port")
    if qhost and qport:
        result = probe_query(qhost, int(qport))
        query_ok = bool(result.get("ok"))
        notes["query"] = "A2S ok" if query_ok else str(result.get("error") or "нет ответа")
    else:
        notes["query"] = "не указан"

    process_ok = str((payload.get("process") or {}).get("kind") or "none") == "local"
    notes["process"] = "local JVM на этой машине" if process_ok else "none — открой панель хостера"

    caps = {
        "rcon": rcon_ok,
        "files": files_ok,
        "query": query_ok,
        "process": process_ok,
        "probed_at": datetime.now().isoformat(timespec="seconds"),
        "inferred": False,
        "notes": notes,
    }
    draft_profile = {"plugins": payload.get("plugins") or {}, "hoster": payload.get("hoster")}
    return {**caps, "views": views_state(caps, draft_profile)}


def public_profile(server_id: str) -> dict[str, Any]:
    profile = load_profile(server_id)
    secrets = load_secrets(server_id)
    files = dict(profile.get("files") or {})
    files.pop("password", None)
    caps = effective_capabilities(profile, secrets)
    plugins = effective_plugins(profile)
    return {
        **profile,
        "files": files,
        "plugins": plugins,
        "capabilities": caps,
        "views": views_state(caps, profile),
        "has_rcon_password": bool(secrets["rcon_password"]),
        "has_ftp_password": bool(secrets["ftp_password"]),
        "has_sftp_key": bool(secrets["sftp_private_key"] or files.get("sftp_key_path")),
        "active": load_index().get("active") == server_id,
        "mirror": str(mirror_root(server_id)),
    }


def list_servers() -> dict[str, Any]:
    ensure_migrated()
    index = reconcile_index()
    rows = []
    for server_id in index.get("ids") or []:
        try:
            rows.append(public_profile(server_id))
        except Exception:
            continue
    if not rows and profile_ids_on_disk():
        for server_id in profile_ids_on_disk():
            try:
                rows.append(public_profile(server_id))
            except Exception:
                continue
    active = index.get("active")
    if rows and active not in {r.get("id") for r in rows}:
        active = rows[0]["id"]
    return {
        "active": active,
        "servers": rows,
        "presets": {key: _preset_public(key) for key in HOSTER_PRESETS},
    }


def _preset_public(hoster: str) -> dict[str, Any]:
    preset = deepcopy(HOSTER_PRESETS[hoster])
    return preset


def active_id() -> str | None:
    ensure_migrated()
    return load_index().get("active")


def active_profile() -> dict[str, Any]:
    server_id = active_id()
    if not server_id:
        raise RuntimeError("No active server profile")
    return load_profile(server_id)


def active_capabilities() -> dict[str, Any]:
    try:
        profile = active_profile()
        return effective_capabilities(profile)
    except Exception:
        return empty_capabilities()


def mirror_root(server_id: str | None = None) -> Path:
    sid = server_id or active_id() or "default"
    return ROOT / ".mirror" / sid


def cachedir_paths(server_id: str | None = None) -> list[Path]:
    """Local folders that look like a PZ cachedir (Logs/, server-console.txt)."""
    found: list[Path] = []
    try:
        profile = load_profile(server_id) if server_id else active_profile()
    except (KeyError, RuntimeError):
        profile = None
    if profile:
        files = profile.get("files") or {}
        if files.get("kind") == "local" and files.get("root"):
            local = Path(str(files["root"]))
            if local.is_dir():
                found.append(local)
        world = mirror_root(profile["id"]) / (str(files.get("root") or "ServerWorld").strip("/").split("/")[-1] or "ServerWorld")
        if world.is_dir():
            found.append(world)
        # Legacy flat pull: .mirror/ServerWorld
        legacy = ROOT / ".mirror" / "ServerWorld"
        if profile.get("hoster") == "xlgames" and legacy.is_dir() and legacy not in found:
            found.append(legacy)
    dedi = ROOT / ".cache" / "dedi-test"
    if dedi.is_dir() and dedi not in found:
        found.append(dedi)
    return found


def resolve_local_path(remote_path: str, server_id: str | None = None) -> Path:
    profile = load_profile(server_id) if server_id else active_profile()
    root = Path(str((profile.get("files") or {}).get("root") or "."))
    rel = remote_path.replace("\\", "/").lstrip("/")
    for prefix in ("ServerWorld/", "Zomboid/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix) :]
            break
    return root / rel


def ftp_config(server_id: str | None = None) -> FtpConfig:
    load_dotenv()
    profile = load_profile(server_id) if server_id else active_profile()
    files = profile.get("files") or {}
    secrets = load_secrets(profile["id"])
    return FtpConfig(
        host=str(files.get("host") or ""),
        port=int(files.get("port") or 21),
        user=str(files.get("user") or ""),
        password=secrets["ftp_password"],
        remote_dir="/",
        use_tls=bool(files.get("tls")),
        timeout=int(os.environ.get("FTP_TIMEOUT", "60") or "60"),
    )


def rcon_config(server_id: str | None = None) -> RconConfig:
    load_dotenv()
    profile = load_profile(server_id) if server_id else active_profile()
    rcon = profile.get("rcon") or {}
    secrets = load_secrets(profile["id"])
    return RconConfig(
        host=str(rcon.get("host") or ""),
        port=int(rcon.get("port") or 16284),
        password=secrets["rcon_password"],
        timeout=float(rcon.get("timeout") or 10),
    )


def sftp_config(server_id: str | None = None):
    from panel.services.sftp_client import SftpConfig

    load_dotenv()
    profile = load_profile(server_id) if server_id else active_profile()
    files = profile.get("files") or {}
    secrets = load_secrets(profile["id"])
    return SftpConfig(
        host=str(files.get("host") or ""),
        port=int(files.get("port") or files.get("sftp_port") or 22),
        user=str(files.get("user") or ""),
        password=secrets["ftp_password"],
        key_path=str(files.get("sftp_key_path") or ""),
        key_text=secrets["sftp_private_key"],
        key_passphrase=secrets["sftp_key_passphrase"],
        remote_dir="/",
        timeout=int(os.environ.get("SFTP_TIMEOUT", "60") or "60"),
    )


def active_files_client():
    profile = active_profile()
    kind = str((profile.get("files") or {}).get("kind") or "ftp")
    if kind == "ftp":
        return FtpClient(ftp_config())
    if kind == "sftp":
        from panel.services.sftp_client import SftpClient

        return SftpClient(sftp_config())
    raise ValueError(f"Active server files.kind={kind!r} has no remote file client")


def active_ftp_client() -> FtpClient:
    profile = active_profile()
    if (profile.get("files") or {}).get("kind") != "ftp":
        raise ValueError("Active server files.kind is not ftp")
    return FtpClient(ftp_config())


def public_endpoints() -> dict[str, Any]:
    load_dotenv()
    try:
        profile = active_profile()
        pub = profile.get("public") or {}
        rcon = profile.get("rcon") or {}
        files = profile.get("files") or {}
        secrets = load_secrets(profile["id"])
        host = str(pub.get("host") or rcon.get("host") or files.get("host") or "").strip()
        return {
            "public_name": str(pub.get("name") or profile.get("name") or "PZ"),
            "host": host,
            "game_port": int(pub.get("game_port") or 16282),
            "query_port": int(pub.get("query_port") or 16281),
            "max_players": int(pub.get("max_players") or 32),
            "discord": (os.environ.get("DISCORD_INVITE") or "").strip(),
            "password_required": bool(secrets["server_password"] or os.environ.get("SERVER_PASSWORD")),
            "webhook_configured": bool(secrets["discord_webhook"] or os.environ.get("DISCORD_WEBHOOK")),
            "server_id": profile["id"],
            "server_name": profile.get("name"),
        }
    except Exception:
        return {
            "public_name": (os.environ.get("PUBLIC_NAME") or "MEATBALLS PZ").strip(),
            "host": (os.environ.get("PUBLIC_HOST") or os.environ.get("RCON_HOST") or "").strip(),
            "game_port": int(os.environ.get("GAME_PORT", "16282") or "16282"),
            "query_port": int(os.environ.get("QUERY_PORT", "16281") or "16281"),
            "max_players": int(os.environ.get("MAX_PLAYERS", "32") or "32"),
            "discord": (os.environ.get("DISCORD_INVITE") or "").strip(),
            "password_required": bool((os.environ.get("SERVER_PASSWORD") or "").strip()),
            "webhook_configured": bool((os.environ.get("DISCORD_WEBHOOK") or "").strip()),
        }


def invite_password() -> str:
    try:
        sid = active_id()
        if sid:
            pwd = load_secrets(sid)["server_password"]
            if pwd:
                return pwd
    except Exception:
        pass
    return (os.environ.get("SERVER_PASSWORD") or "").strip()


def ensure_migrated() -> dict[str, Any]:
    load_dotenv()
    index = reconcile_index()
    if index.get("ids"):
        return index
    rcon_host = (os.environ.get("RCON_HOST") or os.environ.get("FTP_HOST") or "").strip()
    ftp_host = (os.environ.get("FTP_HOST") or "").strip()
    if not rcon_host and not ftp_host:
        return index
    server_id = "meatballs-xl"
    name = (os.environ.get("PUBLIC_NAME") or "MEATBALLS").strip()
    profile = _deep_merge(
        _default_profile(server_id, name),
        {
            "hoster": "xlgames",
            "game_version": "42.20.4",
            "rcon": {
                "host": rcon_host,
                "port": int(os.environ.get("RCON_PORT", "16284") or "16284"),
                "timeout": float(os.environ.get("RCON_TIMEOUT", "10") or "10"),
            },
            "files": {
                "kind": "ftp",
                "host": ftp_host or rcon_host,
                "port": int(os.environ.get("FTP_PORT", "21") or "21"),
                "user": os.environ.get("FTP_USER") or "",
                "tls": os.environ.get("FTP_USE_TLS", "").lower() in ("1", "true", "yes"),
                "root": "/ServerWorld",
                "mods": os.environ.get("FTP_REMOTE_MODS_DIR") or "/ServerWorld/mods",
                "ini": "world.ini",
            },
            "public": {
                "host": (os.environ.get("PUBLIC_HOST") or rcon_host).strip(),
                "game_port": int(os.environ.get("GAME_PORT", "16282") or "16282"),
                "query_port": int(os.environ.get("QUERY_PORT", "16281") or "16281"),
                "max_players": int(os.environ.get("MAX_PLAYERS", "32") or "32"),
                "name": name,
            },
            "process": {"kind": "none"},
            "authority": "host_wins",
            "plugins": {"meatballs": True},
        },
    )
    _write_json(_profile_path(server_id), profile)
    save_secrets(
        server_id,
        {
            "rcon_password": os.environ.get("RCON_PASS") or "",
            "ftp_password": os.environ.get("FTP_PASS") or "",
            "server_password": os.environ.get("SERVER_PASSWORD") or "",
            "discord_webhook": os.environ.get("DISCORD_WEBHOOK") or "",
        },
    )
    index = {"active": server_id, "ids": [server_id]}
    save_index(index)
    save_prefs({"active_server": server_id, "host_panel_wins": True})
    return index


def validate_profile_fields(payload: dict[str, Any], *, draft: bool = False) -> None:
    rcon = payload.get("rcon") or {}
    if not str(rcon.get("host") or "").strip():
        raise ValueError("RCON host обязателен")
    if int(rcon.get("port") or 0) <= 0:
        raise ValueError("RCON port обязателен")
    files = payload.get("files") or {}
    kind = str(files.get("kind") or "ftp")
    if kind == "local":
        if not str(files.get("root") or "").strip():
            raise ValueError("Local path (cachedir) обязателен")
    elif kind == "ftp":
        if not str(files.get("host") or "").strip():
            raise ValueError("FTP host обязателен")
        if not draft and not str(files.get("user") or "").strip():
            raise ValueError("FTP user обязателен (или сохраните как черновик)")
    elif kind == "sftp":
        if not str(files.get("host") or "").strip():
            raise ValueError("SFTP host обязателен")
        if not draft and not str(files.get("user") or "").strip():
            raise ValueError("SFTP user обязателен (или сохраните как черновик)")


def _deep_file_checks(root: Path, max_depth: int = 4) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "server_console": False,
        "ini_files": [],
        "logs_dir": False,
        "server_dir": False,
    }
    if not root.is_dir():
        return checks
    for name in ("Logs", "Server", "Saves"):
        if (root / name).is_dir():
            if name == "Logs":
                checks["logs_dir"] = True
            if name == "Server":
                checks["server_dir"] = True
    try:
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(root)
            if len(rel.parts) > max_depth:
                continue
            lower = path.name.lower()
            if lower == "server-console.txt" or lower.endswith("server-console.txt"):
                checks["server_console"] = True
            if lower.endswith(".ini") and len(checks["ini_files"]) < 8:
                checks["ini_files"].append(str(rel).replace("\\", "/"))
            if path.parent.name == "Logs" and not checks["logs_dir"]:
                checks["logs_dir"] = True
    except OSError:
        pass
    checks["ok"] = bool(
        checks["server_console"] or checks["ini_files"] or checks["logs_dir"] or checks["server_dir"]
    )
    return checks


def onboarding_state() -> dict[str, Any]:
    load_dotenv()
    index = load_index()
    ids = index.get("ids") or []
    has_env = bool(
        (os.environ.get("RCON_HOST") or os.environ.get("FTP_HOST") or "").strip()
    )
    return {
        "needs_wizard": len(ids) == 0 and not has_env,
        "servers_count": len(ids),
        "has_env_fallback": has_env,
        "active": index.get("active"),
    }


def upsert_server(payload: dict[str, Any], server_id: str | None = None) -> dict[str, Any]:
    ensure_migrated()
    draft = bool(payload.get("draft"))
    validate_profile_fields(payload, draft=draft)
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    hoster = str(payload.get("hoster") or "vps")
    preset = deepcopy(HOSTER_PRESETS.get(hoster) or {})
    if server_id:
        if not ID_RE.match(server_id):
            raise ValueError("invalid server id")
        base = load_profile(server_id) if _profile_path(server_id).exists() else _default_profile(server_id, name)
    else:
        server_id = _slug(str(payload.get("id") or name))
        n = 2
        while _profile_path(server_id).exists():
            server_id = f"{_slug(name)}-{n}"
            n += 1
        base = _deep_merge(_default_profile(server_id, name), preset)
    merged = _deep_merge(base, {k: v for k, v in payload.items() if k not in {"secrets", "capabilities", "draft"}})
    merged["id"] = server_id
    merged["name"] = name
    if draft:
        merged["draft"] = True
    elif "draft" in merged:
        merged.pop("draft", None)
    secrets_in = payload.get("secrets") or {}
    if any(
        secrets_in.get(k)
        for k in (
            "rcon_password",
            "ftp_password",
            "sftp_private_key",
            "sftp_key_passphrase",
            "server_password",
            "discord_webhook",
        )
    ):
        save_secrets(server_id, secrets_in)
    if payload.get("capabilities"):
        merged["capabilities"] = normalize_capabilities(payload.get("capabilities"))
        merged["capabilities"]["inferred"] = False
        merged["capabilities"]["probed_at"] = merged["capabilities"].get("probed_at") or datetime.now().isoformat(
            timespec="seconds"
        )
    else:
        merged["capabilities"] = infer_capabilities(merged, load_secrets(server_id))
    _write_json(_profile_path(server_id), merged)
    index = load_index()
    if server_id not in index["ids"]:
        index["ids"].append(server_id)
    if not index.get("active"):
        index["active"] = server_id
    save_index(index)
    return public_profile(server_id)


def activate_server(server_id: str) -> dict[str, Any]:
    profile = load_profile(server_id)
    index = load_index()
    if server_id not in index.get("ids", []):
        index.setdefault("ids", []).append(server_id)
    index["active"] = server_id
    save_index(index)
    save_prefs(
        {
            "active_server": server_id,
            "host_panel_wins": profile.get("authority") != "panel_wins",
        }
    )
    return public_profile(server_id)


def delete_server(server_id: str) -> dict[str, Any]:
    index = load_index()
    if server_id not in (index.get("ids") or []):
        raise KeyError(server_id)
    if len(index["ids"]) <= 1:
        raise ValueError("Cannot delete the last server profile")
    index["ids"] = [i for i in index["ids"] if i != server_id]
    switched = index.get("active") == server_id
    if switched:
        index["active"] = index["ids"][0]
    save_index(index)
    _profile_path(server_id).unlink(missing_ok=True)
    if switched:
        activate_server(index["active"])
    return list_servers()


def probe_rcon(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = RconConfig(
        host=str(payload.get("host") or ""),
        port=int(payload.get("port") or 16284),
        password=str(payload.get("password") or ""),
        timeout=float(payload.get("timeout") or 8),
    )
    output = RconClient(cfg).execute("players")
    return {"ok": True, "output": output[:500]}


def _remote_deep_checks(client, root: str) -> dict[str, Any]:
    entries = client.list_files(root or "/", recursive=False)
    names = [e["name"] for e in entries[:30]]
    checks: dict[str, Any] = {"server_console": False, "ini_files": [], "logs_dir": False, "server_dir": False}
    lower_names = {e["name"].lower(): e for e in entries}
    if "logs" in lower_names:
        checks["logs_dir"] = True
    if "server" in lower_names:
        checks["server_dir"] = True
    for probe in (
        f"{root.rstrip('/')}/server-console.txt",
        f"{root.rstrip('/')}/Logs",
        f"{root.rstrip('/')}/Server",
    ):
        try:
            sub = client.list_files(probe, recursive=False)
            if sub and "server-console" in probe:
                checks["server_console"] = True
            if sub and probe.endswith("Logs"):
                checks["logs_dir"] = True
            if sub and probe.endswith("Server"):
                checks["server_dir"] = True
                for e in sub:
                    if e["name"].lower().endswith(".ini") and len(checks["ini_files"]) < 8:
                        checks["ini_files"].append(e["name"])
        except Exception:
            pass
    checks["ok"] = bool(checks["server_console"] or checks["ini_files"] or checks["logs_dir"] or checks["server_dir"])
    return checks, names


def probe_files(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or "ftp")
    root = str(payload.get("root") or "")
    if kind == "local":
        path = Path(root)
        checks = _deep_file_checks(path) if path.is_dir() else {"ok": False}
        names = sorted(p.name for p in path.iterdir())[:20] if path.is_dir() else []
        return {
            "ok": bool(path.is_dir() and checks.get("ok")),
            "kind": "local",
            "root": str(path),
            "entries": names,
            "checks": checks,
        }
    if kind == "sftp":
        from panel.services.sftp_client import SftpClient, sftp_config_from_payload

        client = SftpClient(sftp_config_from_payload(payload))
        try:
            checks, names = _remote_deep_checks(client, root)
        except Exception as exc:
            return {"ok": False, "kind": "sftp", "root": root, "error": str(exc)[:240]}
        return {
            "ok": bool(checks.get("ok")),
            "kind": "sftp",
            "root": root,
            "entries": names,
            "checks": checks,
        }
    cfg = FtpConfig(
        host=str(payload.get("host") or ""),
        port=int(payload.get("port") or 21),
        user=str(payload.get("user") or ""),
        password=str(payload.get("password") or ""),
        remote_dir="/",
        use_tls=bool(payload.get("tls")),
        timeout=20,
    )
    client = FtpClient(cfg)
    try:
        checks, names = _remote_deep_checks(client, root)
    except Exception as exc:
        return {"ok": False, "kind": "ftp", "root": root, "error": str(exc)[:240]}
    return {
        "ok": bool(checks.get("ok")),
        "kind": "ftp",
        "root": root,
        "entries": names,
        "checks": checks,
    }


def probe_query(host: str, port: int) -> dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)
    try:
        sock.sendto(b"\xff\xff\xff\xffTSource Engine Query\x00", (host, int(port)))
        data, _ = sock.recvfrom(4096)
        return {"ok": bool(data), "bytes": len(data)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        sock.close()
