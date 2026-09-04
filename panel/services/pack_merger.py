"""Panel wrapper around tools.pack_merger for unified ModPack compile."""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
PANEL = Path(__file__).resolve().parents[1]
BACKUPS = PANEL / "backups"
TOOLS = ROOT / "tools"
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")
_SOURCE_RANK = {"repo": 0, "mirror": 1, "workshop": 2}

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panel.servers import active_id, active_profile, mirror_root  # noqa: E402

LogFn = Callable[[str, int | None], None]


def _sources_for_server(server_id: str | None = None) -> list[Path]:
    sid = server_id or active_id() or "default"
    mirror = mirror_root(sid)
    return [
        mirror / "mods",
        mirror / "steamapps" / "workshop" / "content" / "108600",
        ROOT / "src" / "mods",
        ROOT / ".cache" / "workshop",
    ]


def pack_folder_for_mod(mod_path: Path) -> Path:
    """B42 keeps mod.info under 42/; the folder PZ loads is the parent."""
    path = Path(mod_path)
    if path.name == "42":
        return path.parent
    return path


def source_kind(path: Path) -> str:
    text = str(Path(path).resolve()).replace("\\", "/").lower()
    if "/src/mods/" in text:
        return "repo"
    if "/.cache/workshop" in text or "/steamapps/workshop/" in text:
        return "workshop"
    return "mirror"


def dedupe_mods_by_id(mods: list[Any]) -> list[Any]:
    """One folder per mod.id — prefer repo (src/mods) over mirror copies."""
    best: dict[str, Any] = {}
    order: list[str] = []
    for mod in mods:
        prev = best.get(mod.id)
        if prev is None:
            best[mod.id] = mod
            order.append(mod.id)
            continue
        if _SOURCE_RANK.get(source_kind(mod.path), 9) < _SOURCE_RANK.get(source_kind(prev.path), 9):
            best[mod.id] = mod
    return [best[mid] for mid in order]


def _scan_unique(server_id: str | None = None) -> list[Any]:
    from pack_merger import scan_mods

    return dedupe_mods_by_id(scan_mods(_sources_for_server(server_id)))


def list_available_mods(server_id: str | None = None) -> list[dict[str, Any]]:
    return [
        {
            "id": m.id,
            "name": m.name,
            "workshop_id": m.workshop_id,
            "path": str(pack_folder_for_mod(m.path)),
            "source": source_kind(m.path),
            "tiledefs": m.tiledefs,
            "textures": len(m.textures),
            "lua_hooks": m.lua_hooks[:20],
        }
        for m in _scan_unique(server_id)
    ]


def analyze_mods(mod_ids: list[str] | None = None, server_id: str | None = None) -> dict[str, Any]:
    from pack_merger import detect_conflicts, scan_mods

    mods = dedupe_mods_by_id(scan_mods(_sources_for_server(server_id)))
    if mod_ids:
        wanted = {mid.strip() for mid in mod_ids if mid.strip()}
        mods = [m for m in mods if m.id in wanted]
    conflicts = detect_conflicts(mods)
    return {
        "mods": [
            {"id": m.id, "name": m.name, "workshop_id": m.workshop_id, "source": source_kind(m.path)}
            for m in mods
        ],
        "conflicts": [c.to_dict() for c in conflicts],
        "count": len(mods),
        "note": "duplicate_lua_hook / duplicate_texture only block unified compile, not as-is upload",
    }


def _append_log(log: list[str], message: str, *, progress: LogFn | None = None, percent: int | None = None) -> None:
    log.append(message)
    if progress:
        progress(message, percent)
    try:
        from panel.services.event_bus import emit

        emit(
            "compile_progress",
            {"message": message, "percent": percent, "lines": len(log)},
        )
    except Exception:
        pass


def _remote_paths(server_id: str | None = None) -> dict[str, str]:
    from panel.servers import load_profile

    sid = server_id or active_id() or "default"
    profile = load_profile(sid) if sid else active_profile()
    files = profile.get("files") or {}
    kind = str(files.get("kind") or "ftp")
    if kind == "local":
        raise ValueError("Deploy requires FTP or SFTP profile — local path cannot push to remote host")
    root = str(files.get("root") or "/ServerWorld").replace("\\", "/").rstrip("/")
    if not root.startswith("/"):
        root = "/" + root
    ini_name = str(files.get("ini") or "world.ini")
    try:
        from ftp_client import join_remote, normalize_remote

        mods_dir = join_remote(normalize_remote(root), "mods")
        ini_remote = join_remote(normalize_remote(root), "Server", ini_name)
    except Exception:
        mods_dir = f"{root}/mods"
        ini_remote = f"{root}/Server/{ini_name}"
    return {
        "root": root,
        "mods_dir": mods_dir,
        "ini_remote": ini_remote,
        "ini_name": ini_name,
        "files_kind": kind,
    }


def _backup_ini_content(filename: str, content: str) -> Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe = filename.replace("/", "_").replace("\\", "_")
    path = BACKUPS / f"{stamp}_{safe}"
    path.write_text(content, encoding="utf-8")
    return path


def append_pack_to_ini(content: str, pack_id: str) -> tuple[str, list[str]]:
    return append_ids_to_ini(content, [pack_id])


def append_ids_to_ini(content: str, pack_ids: list[str]) -> tuple[str, list[str]]:
    from mod_catalog import apply_lists_to_ini
    from panel.services.workshop_downloader import parse_ini_list

    mods = parse_ini_list(content, "Mods")
    workshop = parse_ini_list(content, "WorkshopItems")
    for pack_id in pack_ids:
        if pack_id and pack_id not in mods:
            mods.append(pack_id)
    return apply_lists_to_ini(content, mods, workshop), mods


def deploy_pack_to_server(
    *,
    local_pack_dir: Path,
    pack_id: str,
    server_id: str | None = None,
    update_ini: bool = True,
    log: list[str] | None = None,
    on_progress: LogFn | None = None,
) -> dict[str, Any]:
    from panel.servers import active_files_client

    stages: list[str] = log if log is not None else []
    paths = _remote_paths(server_id)
    remote_mod = f"{paths['mods_dir'].rstrip('/')}/{pack_id}"

    _append_log(stages, f"[upload] Connecting via {paths['files_kind'].upper()}…", progress=on_progress, percent=55)
    client = active_files_client()
    if not hasattr(client, "sync_modpack"):
        raise RuntimeError(f"File client {type(client).__name__} does not support modpack sync")

    _append_log(stages, f"[upload] Sync → {remote_mod}", progress=on_progress, percent=60)
    sync = client.sync_modpack(local_pack_dir, remote_mod)
    if sync.errors:
        raise RuntimeError(f"Upload failed: {'; '.join(sync.errors[:5])}")

    _append_log(
        stages,
        f"[upload] Done · uploaded {len(sync.uploaded)} · skipped {len(sync.skipped)}",
        progress=on_progress,
        percent=80,
    )

    ini_result: dict[str, Any] | None = None
    if update_ini:
        _append_log(stages, f"[ini] Reading {paths['ini_remote']}…", progress=on_progress, percent=85)
        previous = client.read_file(paths["ini_remote"])
        if isinstance(previous, bytes):
            previous = previous.decode("utf-8", errors="replace")
        backup_path = _backup_ini_content(paths["ini_name"], previous)
        updated, mods = append_pack_to_ini(previous, pack_id)
        temp = BACKUPS / f".upload_{paths['ini_name']}"
        temp.write_text(updated, encoding="utf-8")
        try:
            upload = client.upload_file(temp, paths["ini_remote"])
        finally:
            temp.unlink(missing_ok=True)
        _append_log(
            stages,
            f"[ini] Mods= updated ({pack_id}) · backup {backup_path.name}",
            progress=on_progress,
            percent=95,
        )
        ini_result = {
            "remote_path": paths["ini_remote"],
            "backup": str(backup_path.relative_to(ROOT)),
            "mods": mods,
            "upload": upload,
        }

    verify_ok = len(sync.uploaded) + len(sync.skipped) > 0 and not sync.errors
    _append_log(stages, "[verify] Remote sync OK", progress=on_progress, percent=100)
    return {
        "ok": verify_ok,
        "remote_mod_dir": remote_mod,
        "uploaded": sync.uploaded,
        "skipped": sync.skipped,
        "errors": sync.errors,
        "ini": ini_result,
        "log": stages,
    }


def compile_pack(
    *,
    mod_ids: list[str],
    pack_id: str,
    pack_name: str = "",
    server_id: str | None = None,
    fail_on_conflict: bool = False,
    deploy_to_server: bool = False,
    update_ini: bool = True,
) -> dict[str, Any]:
    from pack_merger import compile_unified_pack

    pack_id = (pack_id or "").strip()
    if not ID_RE.match(pack_id):
        raise ValueError("pack_id must be alphanumeric (start with letter), e.g. ServerModPack_v1")
    wanted = list(dict.fromkeys(m.strip() for m in mod_ids if m.strip()))
    if not wanted:
        raise ValueError("Select at least one mod to compile")

    by_id = {m.id: m for m in _scan_unique(server_id)}
    missing = [mid for mid in wanted if mid not in by_id]
    if missing:
        raise ValueError(f"Mods not found: {', '.join(missing[:8])}")
    selected = [by_id[mid] for mid in wanted]

    sid = server_id or active_id() or "default"
    out = mirror_root(sid) / "modpacks" / pack_id
    deploy_log: list[str] = [f"[build] Compiling {pack_id} from {len(selected)} mod(s)…"]

    if fail_on_conflict:
        conflicts = analyze_mods(wanted, server_id=sid).get("conflicts") or []
        if conflicts:
            deploy_log.append(f"[build] Aborted — {len(conflicts)} conflict(s)")
            return {
                "ok": False,
                "aborted": True,
                "reason": "conflicts",
                "conflicts": conflicts,
                "log": deploy_log,
            }

    result = compile_unified_pack(
        selected,
        out,
        mod_id=pack_id,
        mod_name=pack_name.strip() or pack_id,
        fail_on_conflict=fail_on_conflict,
    )
    deploy_log.extend(result.get("log") or [])
    deploy_log.append(f"[build] Output → {out}")

    if not result.get("ok"):
        result["log"] = deploy_log
        return result

    # also expose under mods/ for smoke convenience
    if result.get("ok"):
        mods_link = mirror_root(sid) / "mods" / pack_id
        try:
            from workshop_downloader import link_or_copy

            link_or_copy(out, mods_link)
            result["mods_path"] = str(mods_link)
        except Exception as exc:
            result["mods_link_error"] = str(exc)[:200]

    if deploy_to_server:
        try:
            deploy = deploy_pack_to_server(
                local_pack_dir=out,
                pack_id=pack_id,
                server_id=sid,
                update_ini=update_ini,
                log=deploy_log,
            )
            result["deploy"] = deploy
            result["ok"] = bool(result.get("ok")) and deploy.get("ok")
        except Exception as exc:
            deploy_log.append(f"[deploy] ERROR: {exc}")
            result["deploy_error"] = str(exc)[:400]
            result["ok"] = False

    result["log"] = deploy_log
    result["output_dir"] = str(out)
    return result


def _copy_mod_local(local_dir: Path, pack_id: str) -> dict[str, Any]:
    files = active_profile().get("files") or {}
    if str(files.get("kind") or "") != "local":
        raise ValueError("not local")
    dest = Path(str(files.get("root") or "")) / "mods" / pack_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.copytree(local_dir, dest, dirs_exist_ok=True)
    else:
        shutil.copytree(local_dir, dest)
    count = sum(1 for path in dest.rglob("*") if path.is_file())
    return {"ok": True, "kind": "local", "dest": str(dest), "files": count}


def _append_ids_to_remote_ini(
    pack_ids: list[str],
    *,
    server_id: str | None,
    log: list[str],
) -> dict[str, Any]:
    from panel.prefs import host_conflict, remember_remote
    from panel.servers import active_files_client
    from panel.services.workshop_downloader import parse_ini_list

    paths = _remote_paths(server_id)
    client = active_files_client()
    previous = client.read_file(paths["ini_remote"])
    if isinstance(previous, bytes):
        previous = previous.decode("utf-8", errors="replace")
    previous_mods = parse_ini_list(previous, "Mods")
    updated, mods = append_ids_to_ini(previous, pack_ids)
    if mods == previous_mods:
        _append_log(log, f"[ini] Mods= already has {', '.join(pack_ids)}")
        return {"changed": False, "mods": mods, "remote_path": paths["ini_remote"]}

    clash = host_conflict(paths["ini_name"], previous, updated)
    if clash:
        remember_remote(paths["ini_name"], paths["ini_remote"], previous)
        _append_log(
            log,
            "[ini] Skipped — hoster world.ini changed (host_wins). Add the id in the hoster panel or retry.",
        )
        return {
            "changed": False,
            "skipped": "host_wins",
            "mods": mods,
            "remote_path": paths["ini_remote"],
            "message": "world.ini on the host changed; Mods= was not overwritten.",
        }

    backup_path = _backup_ini_content(paths["ini_name"], previous)
    temp = BACKUPS / f".upload_{paths['ini_name']}"
    temp.write_text(updated, encoding="utf-8")
    try:
        upload = client.upload_file(temp, paths["ini_remote"])
    finally:
        temp.unlink(missing_ok=True)
    remember_remote(paths["ini_name"], paths["ini_remote"], updated)
    _append_log(log, f"[ini] Mods= += {', '.join(pack_ids)} · backup {backup_path.name}")
    return {
        "changed": True,
        "mods": mods,
        "remote_path": paths["ini_remote"],
        "backup": str(backup_path.relative_to(ROOT)),
        "upload": upload,
    }


def _append_ids_to_local_ini(pack_ids: list[str], log: list[str]) -> dict[str, Any]:
    files = active_profile().get("files") or {}
    ini_name = str(files.get("ini") or "world.ini")
    root = Path(str(files.get("root") or ""))
    ini_path = root / "Server" / ini_name
    if not ini_path.is_file():
        ini_path = root / ini_name
    if not ini_path.is_file():
        raise FileNotFoundError(f"Local INI not found: {ini_path}")
    previous = ini_path.read_text(encoding="utf-8", errors="replace")
    updated, mods = append_ids_to_ini(previous, pack_ids)
    if updated == previous:
        _append_log(log, f"[ini] Mods= already has {', '.join(pack_ids)}")
        return {"changed": False, "mods": mods, "path": str(ini_path)}
    backup_path = _backup_ini_content(ini_name, previous)
    ini_path.write_text(updated, encoding="utf-8")
    _append_log(log, f"[ini] Local Mods= += {', '.join(pack_ids)} · backup {backup_path.name}")
    return {
        "changed": True,
        "mods": mods,
        "path": str(ini_path),
        "backup": str(backup_path.relative_to(ROOT)),
    }


def deploy_mods_as_is(
    *,
    mod_ids: list[str],
    server_id: str | None = None,
    update_ini: bool = True,
) -> dict[str, Any]:
    """Upload each selected mod folder as-is (no unified merge)."""
    wanted = list(dict.fromkeys(mid.strip() for mid in mod_ids if mid.strip()))
    if not wanted:
        raise ValueError("Select at least one mod to upload")

    by_id = {m.id: m for m in _scan_unique(server_id)}
    missing = [mid for mid in wanted if mid not in by_id]
    if missing:
        raise ValueError(f"Mods not found: {', '.join(missing[:8])}")

    files = active_profile().get("files") or {}
    kind = str(files.get("kind") or "ftp")
    log: list[str] = [
        f"[deploy] Uploading {len(wanted)} mod(s) as separate folders (no merge)…",
    ]
    details: list[dict[str, Any]] = []
    errors: list[str] = []

    for mid in wanted:
        folder = pack_folder_for_mod(by_id[mid].path)
        if not folder.is_dir():
            errors.append(f"{mid}: folder missing ({folder})")
            log.append(f"[deploy] ERROR {mid}: folder missing")
            details.append({"id": mid, "ok": False, "error": "folder missing"})
            continue
        log.append(f"[deploy] {mid} <- {folder}")
        try:
            if kind == "local":
                local = _copy_mod_local(folder, mid)
                details.append(
                    {
                        "id": mid,
                        "ok": True,
                        "kind": "local",
                        "dest": local.get("dest"),
                        "files": local.get("files"),
                    }
                )
                log.append(f"[deploy] local copy {local.get('files')} file(s) → {local.get('dest')}")
            else:
                dep = deploy_pack_to_server(
                    local_pack_dir=folder,
                    pack_id=mid,
                    server_id=server_id,
                    update_ini=False,
                    log=log,
                )
                details.append(
                    {
                        "id": mid,
                        "ok": bool(dep.get("ok")),
                        "remote": dep.get("remote_mod_dir"),
                        "uploaded": len(dep.get("uploaded") or []),
                        "skipped": len(dep.get("skipped") or []),
                    }
                )
        except Exception as exc:
            errors.append(f"{mid}: {exc}")
            log.append(f"[deploy] ERROR {mid}: {exc}")
            details.append({"id": mid, "ok": False, "error": str(exc)[:400]})

    ini_result: dict[str, Any] | None = None
    successful = [row["id"] for row in details if row.get("ok")]
    if update_ini and successful:
        try:
            if kind == "local":
                ini_result = _append_ids_to_local_ini(successful, log)
            else:
                ini_result = _append_ids_to_remote_ini(successful, server_id=server_id, log=log)
        except Exception as exc:
            errors.append(f"ini: {exc}")
            log.append(f"[ini] ERROR: {exc}")
            ini_result = {"ok": False, "error": str(exc)[:400]}

    ok = not errors and bool(successful) and all(row.get("ok") for row in details)
    log.append("[deploy] Done" if ok else "[deploy] Finished with errors")
    return {
        "ok": ok,
        "mode": "as_is",
        "mods": details,
        "ini": ini_result,
        "log": log,
        "errors": errors,
        "hint": "Dedicated JVM loads new Mods= only after hoster restart.",
    }
