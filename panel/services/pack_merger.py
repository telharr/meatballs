"""Panel wrapper around tools.pack_merger for unified ModPack compile."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from panel.servers import active_id, active_profile, mirror_root

ROOT = Path(__file__).resolve().parents[2]
PANEL = Path(__file__).resolve().parents[1]
BACKUPS = PANEL / "backups"
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")

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


def list_available_mods(server_id: str | None = None) -> list[dict[str, Any]]:
    from pack_merger import scan_mods

    mods = scan_mods(_sources_for_server(server_id))
    return [
        {
            "id": m.id,
            "name": m.name,
            "workshop_id": m.workshop_id,
            "path": str(m.path),
            "tiledefs": m.tiledefs,
            "textures": len(m.textures),
            "lua_hooks": m.lua_hooks[:20],
        }
        for m in mods
    ]


def analyze_mods(mod_ids: list[str] | None = None, server_id: str | None = None) -> dict[str, Any]:
    from pack_merger import detect_conflicts, scan_mods

    mods = scan_mods(_sources_for_server(server_id))
    if mod_ids:
        wanted = {m.strip() for m in mod_ids if m.strip()}
        mods = [m for m in mods if m.id in wanted]
    conflicts = detect_conflicts(mods)
    return {
        "mods": [{"id": m.id, "name": m.name, "workshop_id": m.workshop_id} for m in mods],
        "conflicts": [c.to_dict() for c in conflicts],
        "count": len(mods),
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
    from mod_catalog import apply_lists_to_ini
    from panel.services.workshop_downloader import parse_ini_list

    mods = parse_ini_list(content, "Mods")
    workshop = parse_ini_list(content, "WorkshopItems")
    if pack_id not in mods:
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
    from pack_merger import compile_unified_pack, scan_mods

    pack_id = (pack_id or "").strip()
    if not ID_RE.match(pack_id):
        raise ValueError("pack_id must be alphanumeric (start with letter), e.g. ServerModPack_v1")
    wanted = [m.strip() for m in mod_ids if m.strip()]
    if not wanted:
        raise ValueError("Select at least one mod to compile")

    all_mods = scan_mods(_sources_for_server(server_id))
    by_id = {m.id: m for m in all_mods}
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
