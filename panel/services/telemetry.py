"""Host and dedicated-server telemetry for the control panel."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from panel.servers import active_files_client, active_id, active_profile, mirror_root  # noqa: E402

_FREE_RE = re.compile(
    r"Mem:\s+(?P<total>\d+)\s+(?P<used>\d+)\s+(?P<free>\d+)",
    re.I,
)
_CPU_RE = re.compile(r"(\d+(?:\.\d+)?)\s*id")


def _mirror_disk() -> dict[str, Any]:
    sid = active_id() or "default"
    path = mirror_root(sid)
    try:
        usage = shutil.disk_usage(path if path.exists() else path.parent)
        return {
            "path": str(path),
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "percent_used": round(usage.used * 100 / usage.total, 1) if usage.total else 0,
        }
    except OSError:
        return {"path": str(path), "free_gb": 0, "percent_used": 0}


def _local_host() -> dict[str, Any]:
    import psutil

    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    return {
        "cpu_percent": round(float(cpu), 1),
        "ram_total_mb": int(mem.total // (1024 * 1024)),
        "ram_used_mb": int(mem.used // (1024 * 1024)),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_percent": round(float(mem.percent), 1),
    }


def _gameserver_process() -> dict[str, Any] | None:
    import psutil

    try:
        from local_server import inspect

        info = inspect()
    except Exception:
        return None
    pid = info.get("pid")
    if not pid:
        return None
    try:
        proc = psutil.Process(int(pid))
        mem = proc.memory_info()
        return {
            "pid": int(pid),
            "running": bool(info.get("running")),
            "cpu_percent": round(float(proc.cpu_percent(interval=0.0)), 1),
            "rss_mb": int(mem.rss // (1024 * 1024)),
            "name": proc.name(),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return None


def _parse_free_m(text: str) -> dict[str, Any] | None:
    match = _FREE_RE.search(text or "")
    if not match:
        return None
    total = int(match.group("total"))
    used = int(match.group("used"))
    return {
        "ram_total_mb": total,
        "ram_used_mb": used,
        "ram_free_mb": int(match.group("free")),
        "ram_percent": round(used * 100 / total, 1) if total else 0,
    }


def _parse_top_cpu(text: str) -> float | None:
    for line in (text or "").splitlines():
        if "Cpu(s)" in line or "%Cpu" in line:
            match = _CPU_RE.search(line)
            if match:
                try:
                    idle = float(match.group(1))
                    return round(max(0.0, 100.0 - idle), 1)
                except ValueError:
                    continue
    return None


def _remote_sftp_probe() -> dict[str, Any] | None:
    profile = active_profile()
    files = profile.get("files") or {}
    if str(files.get("kind") or "") != "sftp":
        return None
    client = active_files_client()
    exec_fn = getattr(client, "exec_command", None)
    if not exec_fn:
        return None
    try:
        free_out, _, code = exec_fn("free -m 2>/dev/null || free -m")
        top_out, _, _ = exec_fn("top -bn1 2>/dev/null | head -5")
        remote: dict[str, Any] = {"host": files.get("host") or profile.get("network", {}).get("public_ip")}
        parsed = _parse_free_m(free_out if code == 0 else "")
        if parsed:
            remote.update(parsed)
        cpu = _parse_top_cpu(top_out)
        if cpu is not None:
            remote["cpu_percent"] = cpu
        return remote if len(remote) > 1 else None
    except Exception as exc:
        return {"error": str(exc)[:120]}


def collect_stats() -> dict[str, Any]:
    host = _local_host()
    disk = _mirror_disk()
    gameserver = _gameserver_process()
    remote = _remote_sftp_probe()
    return {
        "host": host,
        "disk": disk,
        "gameserver": gameserver,
        "remote": remote,
        "server_id": active_id(),
    }
