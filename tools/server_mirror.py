#!/usr/bin/env python3
"""FTP ↔ local mirror of the dedicated server (configs/world, not java/media)."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ftp_client import client_from_env, load_dotenv  # noqa: E402


def _mirror_files() -> tuple[Path, Path, Path]:
    try:
        from panel.servers import mirror_root

        root = mirror_root()
    except Exception:
        root = ROOT / ".mirror"
    return root, root / "status.json", root / "checksums.json"


def _root() -> Path:
    return _mirror_files()[0]


def _status_file() -> Path:
    return _mirror_files()[1]


def _checksums_file() -> Path:
    return _mirror_files()[2]


def __getattr__(name: str) -> Any:
    if name == "MIRROR_ROOT":
        return _root()
    if name == "STATUS_FILE":
        return _status_file()
    if name == "CHECKSUMS_FILE":
        return _checksums_file()
    raise AttributeError(name)


DEFAULT_REMOTE = "/ServerWorld"


def default_remote() -> str:
    try:
        from panel.servers import active_profile

        root = str((active_profile().get("files") or {}).get("root") or "")
        if root.startswith("/"):
            return root
    except Exception:
        pass
    return DEFAULT_REMOTE
SKIP_DIRS = {
    "java",
    "media",
    "steamapps",
    "workshop",
    "jre",
    "natives",
    "linux64",
    "win64",
    "macos",
    "backup",
}

_pull_lock = threading.Lock()
_pause_flag = threading.Event()


def _read_json(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _count_local() -> tuple[int, int]:
    files = 0
    size = 0
    root = _root()
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file() and path.name not in {"status.json", "checksums.json"} and not path.name.endswith(".part"):
                files += 1
                size += path.stat().st_size
    return files, size


def _merge_checksums(verified: list[dict[str, Any]]) -> dict[str, Any]:
    store = _read_json(_checksums_file())
    now = datetime.now().isoformat(timespec="seconds")
    for item in verified:
        prev = store.get(item["remote"]) or {}
        digest = item.get("md5") or prev.get("md5")
        store[item["remote"]] = {
            "md5": digest,
            "size": item.get("size", prev.get("size")),
            "local": item.get("local", prev.get("local")),
            "verified_at": now if item.get("md5") else prev.get("verified_at") or now,
            "unchanged": bool(item.get("skipped_ok")),
        }
    _write_json(_checksums_file(), store)
    return store


def status() -> dict[str, Any]:
    stored = _read_json(_status_file())
    files, size = _count_local()
    checksums = _read_json(_checksums_file())
    progress = dict(stored.get("progress") or {})
    progress.setdefault("phase", "idle")
    progress.setdefault("done", 0)
    progress.setdefault("verified", progress.get("done", 0))
    progress.setdefault("total", 0)
    total = int(progress.get("total") or 0)
    verified = int(progress.get("verified") or progress.get("done") or 0)
    progress["remaining"] = max(0, total - verified)
    if total:
        progress["percent"] = min(100, int(verified * 100 / total))

    pulling = bool(stored.get("pulling"))
    paused = bool(stored.get("paused"))
    stale = False
    if pulling and not _pull_lock.locked():
        stale = True
        pulling = False
        paused = True
        stored["pulling"] = False
        stored["paused"] = True
        stored["last_error"] = (
            "Pull оборвался (панель перезапущена или FTP отвалился). "
            "Нажмите Pull заново — докачает недостающее."
        )
        progress["phase"] = "paused"
        stored["progress"] = progress
        _write_json(_status_file(), stored)

    root = _root()
    return {
        "exists": root.exists(),
        "path": str(root),
        "files": stored.get("files", files),
        "bytes": size,
        "last_pull": stored.get("last_pull"),
        "last_error": stored.get("last_error"),
        "remote_path": stored.get("remote_path", DEFAULT_REMOTE),
        "local_dir": stored.get("local_dir"),
        "pulling": pulling,
        "paused": paused,
        "stale": stale,
        "complete": bool(stored.get("complete")),
        "progress": progress,
        "corrupt": stored.get("corrupt"),
        "verified_count": len(checksums) or verified,
        "checksums_file": str(_checksums_file()),
        "last_transferred": stored.get("last_transferred", 0),
        "last_unchanged": stored.get("last_unchanged", 0),
    }


def _write_status(extra: dict[str, Any]) -> dict[str, Any]:
    data = _read_json(_status_file())
    data.update(extra)
    files, size = _count_local()
    data["exists"] = _root().exists()
    if "files" not in extra:
        data["files"] = files
    data["bytes"] = size
    _write_json(_status_file(), data)
    return status()


def _on_progress(info: dict[str, Any]) -> None:
    paused = info.get("phase") == "paused"
    pulling = info.get("phase") not in {"done", "error", "paused", "idle"}
    extra: dict[str, Any] = {
        "pulling": pulling,
        "paused": paused,
        "progress": info,
    }
    if info.get("corrupt"):
        extra["corrupt"] = info["corrupt"]
        extra["last_error"] = info["corrupt"].get("reason")
    _write_status(extra)
    try:
        from panel.services.event_bus import emit

        emit("pull_progress", info)
    except Exception:
        pass


def _run_pull(
    remote_path: str,
    queue: list[dict] | None = None,
    mode: str = "incremental",
) -> dict[str, Any]:
    dest = _root() / remote_path.strip("/").replace("/", "_")
    if remote_path in ("/", ""):
        dest = _root() / "root"
    _write_status(
        {
            "pulling": True,
            "paused": False,
            "complete": False,
            "remote_path": remote_path,
            "local_dir": str(dest),
            "last_error": None,
            "corrupt": None,
            "progress": {
                "phase": "connecting",
                "current": remote_path,
                "done": 0,
                "verified": 0,
                "total": len(queue or []),
                "percent": 0,
                "errors": 0,
                "remaining": len(queue or []),
            },
        }
    )
    known_sizes: dict[str, int] = {}
    for remote, meta in _read_json(_checksums_file()).items():
        size = meta.get("size") if isinstance(meta, dict) else None
        if size is not None:
            known_sizes[remote] = int(size)
    try:
        from panel.servers import active_files_client

        client = active_files_client()
    except Exception:
        client = client_from_env()
    result = client.pull_tree(
        remote_path,
        dest,
        skip_dirs=SKIP_DIRS,
        on_progress=_on_progress,
        queue=queue,
        pause_check=_pause_flag.is_set,
        mode=mode,
        known_sizes=known_sizes,
    )
    if result.get("verified"):
        _merge_checksums(result["verified"])
    if result.get("paused"):
        stored = _read_json(_status_file())
        stored["remaining_queue"] = result.get("remaining") or []
        stored["pulling"] = False
        stored["paused"] = True
        stored["complete"] = False
        stored["corrupt"] = result.get("corrupt")
        stored["last_error"] = (result.get("corrupt") or {}).get("reason") or "Paused"
        _write_json(_status_file(), stored)
        return status()

    err = "; ".join(result["errors"][:5]) if result["errors"] else None
    planned = result.get("planned", result["count"])
    complete = result["count"] == planned and not result["errors"]
    transferred = len(result.get("downloaded") or [])
    unchanged = len(result.get("unchanged") or [])
    if complete:
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from panel.prefs import remember_watched_from_dir

            remember_watched_from_dir(Path(result["local_dir"]), remote_path)
        except Exception:
            pass
    return _write_status(
        {
            "pulling": False,
            "paused": False,
            "complete": complete,
            "last_pull": datetime.now().isoformat(timespec="seconds"),
            "last_error": err,
            "remote_path": remote_path,
            "local_dir": result["local_dir"],
            "files": result["count"],
            "last_transferred": transferred,
            "last_unchanged": unchanged,
            "remaining_queue": [],
            "corrupt": None,
            "progress": {
                "phase": "done" if complete else "error",
                "current": "",
                "done": transferred,
                "unchanged": unchanged,
                "verified": result["count"],
                "total": planned,
                "percent": 100 if complete else 0,
                "errors": len(result["errors"]),
                "remaining": 0,
            },
        }
    )


def pull(remote_path: str = DEFAULT_REMOTE, mode: str = "incremental") -> dict[str, Any]:
    if not _pull_lock.acquire(blocking=False):
        return {**status(), "ok": False, "message": "Pull already running"}
    _pause_flag.clear()
    try:
        load_dotenv()
        return _run_pull(remote_path, mode=mode)
    except Exception as exc:
        _write_status(
            {
                "pulling": False,
                "paused": False,
                "complete": False,
                "last_error": str(exc),
                "progress": {
                    "phase": "error",
                    "current": str(exc),
                    "done": 0,
                    "verified": 0,
                    "total": 0,
                    "percent": 0,
                    "errors": 1,
                    "remaining": 0,
                },
            }
        )
        raise
    finally:
        _pull_lock.release()


def resume(retry_corrupt: bool = True) -> dict[str, Any]:
    stored = _read_json(_status_file())
    queue = list(stored.get("remaining_queue") or [])
    if not queue and stored.get("corrupt"):
        queue = [stored["corrupt"]]
    if not queue:
        return {**status(), "ok": False, "message": "Nothing to resume"}
    if not retry_corrupt and stored.get("corrupt"):
        bad = stored["corrupt"].get("remote")
        queue = [q for q in queue if q.get("remote") != bad]
    if not _pull_lock.acquire(blocking=False):
        return {**status(), "ok": False, "message": "Pull already running"}
    _pause_flag.clear()
    try:
        load_dotenv()
        remote = stored.get("remote_path") or DEFAULT_REMOTE
        return _run_pull(remote, queue)
    finally:
        _pull_lock.release()


def verify(remote_path: str = DEFAULT_REMOTE) -> dict[str, Any]:
    """SIZE compare + local MD5 vs checksums.json. Does not RETR unchanged files."""
    if not _pull_lock.acquire(blocking=False):
        return {**status(), "ok": False, "message": "Pull already running"}
    _pause_flag.clear()
    try:
        load_dotenv()
        return _run_pull(remote_path, mode="verify")
    finally:
        _pull_lock.release()


def abort() -> dict[str, Any]:
    _pause_flag.set()
    stored = _read_json(_status_file())
    stored["pulling"] = False
    stored["paused"] = False
    stored["complete"] = False
    stored["remaining_queue"] = []
    if stored.get("progress"):
        stored["progress"]["phase"] = "idle"
    _write_json(_status_file(), stored)
    return status()


def find_mirror_ini(name: str = "world.ini") -> Path | None:
    if not _root().exists():
        return None
    matches = list(_root().rglob(name))
    return matches[0] if matches else None


def cache_dir_for_local() -> Path | None:
    """PZ -cachedir should contain Server/ and Saves/."""
    if status().get("paused") or status().get("corrupt"):
        return None
    server_dir = next(_root().rglob("Server"), None) if _root().exists() else None
    if server_dir and server_dir.is_dir():
        return server_dir.parent
    named = _root() / "ServerWorld"
    if named.exists():
        return named
    return _root() if _root().exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull/push PZ server FTP mirror")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    pull_p = sub.add_parser("pull")
    pull_p.add_argument("--remote", default=DEFAULT_REMOTE)
    pull_p.add_argument("--mode", default="incremental", choices=["incremental", "verify", "force"])
    sub.add_parser("verify")
    sub.add_parser("resume")
    sub.add_parser("abort")
    args = parser.parse_args()
    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "resume":
        print(json.dumps(resume(), indent=2))
        return 0
    if args.cmd == "abort":
        print(json.dumps(abort(), indent=2))
        return 0
    if args.cmd == "verify":
        print(json.dumps(verify(), indent=2))
        return 0
    print(json.dumps(pull(args.remote, mode=args.mode), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
