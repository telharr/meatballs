"""Local smoke test against active profile mirror (.mirror/<id>/)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_server import extract_issues, inspect, parse_world_status, start, stop  # noqa: E402
from server_mirror import cache_dir_for_local, status as mirror_status  # noqa: E402

from panel.servers import active_profile, mirror_root  # noqa: E402

SMOKE_ERROR_MARKERS = (
    "illegalargumentexception",
    "duplicate texture",
    "mod id mismatch",
    "nullpointerexception",
    "entity is already registered",
    "failed to start",
    "could not start",
)


def _prioritize_errors(errors: list[str]) -> list[str]:
    out: list[str] = []
    rest: list[str] = []
    for line in errors:
        lower = line.lower()
        if any(m in lower for m in SMOKE_ERROR_MARKERS):
            if line not in out:
                out.append(line)
        else:
            rest.append(line)
    for line in rest:
        if line not in out:
            out.append(line)
    return out[:40]


def smoke_status() -> dict[str, Any]:
    info = inspect()
    world = dict(info.get("world") or {})
    errors = _prioritize_errors(world.get("errors") or [])
    warnings = world.get("warnings") or []
    running = bool(info.get("running"))
    ready = bool(world.get("ready"))
    failed = bool(world.get("failed"))

    if ready and running:
        verdict = "pass"
        label = "PASS — чистый старт"
    elif failed or (errors and not running):
        verdict = "fail"
        label = f"FAIL — ошибок: {len(errors)}"
    elif running:
        verdict = "running"
        label = "Загрузка…"
    else:
        verdict = "idle"
        label = "Остановлен"

    try:
        profile = active_profile()
        sid = profile["id"]
        mirror = str(mirror_root(sid))
        files_kind = (profile.get("files") or {}).get("kind")
    except Exception:
        sid = None
        mirror = None
        files_kind = None

    ms = mirror_status()
    cache = info.get("cache_dir")
    return {
        **info,
        "server_id": sid,
        "mirror_root": mirror,
        "files_kind": files_kind,
        "mirror_status": {
            "files": ms.get("local_files"),
            "pulling": ms.get("pulling"),
            "paused": ms.get("paused"),
        },
        "cache_dir": cache,
        "smoke": {
            "verdict": verdict,
            "label": label,
            "error_count": len(errors),
            "errors": errors,
            "warnings": warnings[:20],
            "log_tail": world.get("log_tail") or [],
        },
    }


def smoke_start(server_name: str | None = None) -> dict[str, Any]:
    cache = cache_dir_for_local()
    if not cache or not cache.is_dir():
        ms = mirror_status()
        if ms.get("paused"):
            raise FileNotFoundError("Зеркало на паузе — исправьте повреждённый файл и Pull заново.")
        raise FileNotFoundError("Зеркало пустое — сначала Pull на вкладке «Зеркало».")
    result = start(server_name=server_name)
    out = smoke_status()
    out["start"] = result
    return out


def smoke_stop() -> dict[str, Any]:
    stop()
    return smoke_status()
