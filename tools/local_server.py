#!/usr/bin/env python3
"""Start a local PZ dedicated server against the FTP mirror (-cachedir)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ftp_client import load_dotenv  # noqa: E402
from server_mirror import cache_dir_for_local, status as mirror_status  # noqa: E402

STATE_FILE = ROOT / "panel" / "data" / "local_server.json"
LOG_FILE = ROOT / ".mirror" / "local-console.txt"

_WORLD_STAGES = (
    ("starting", ("starting server", "loading server", "log file created", "loading networking")),
    ("lua", ("loading lua", "lua manager", "kahlua", "loading scripts", "loading servertweaker", "loading logextender")),
    ("world", ("loading world", "loading map", "loading cell", "worlddictionary", "loading save")),
    ("ready", ("*** server started", "server started ****", "server is listening", "steam is initialised")),
)

_FAIL_MARKERS = ("fatal", "error: java", "could not start", "failed to start")
_VERSION_RE = re.compile(r"version=([0-9]+\.[0-9.]+)")
_NOISE = (
    "missing thumpsound",
    "sanitizing container name",
    "missing uiconfigscript",
    "property name not found: ladder",
    "property name not found: windowshape",
    "slf4j",
    "duplicate texture",
    "extents != physicschassisshape",
    "no slf4j providers",
    "unknown option",
    "visitfilefailed",
    "nosuchfileexception",
)


def _dedicated_dir() -> Path | None:
    load_dotenv()
    explicit = os.environ.get("PZ_DEDICATED_DIR", "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.is_dir() else None
    guesses: list[Path] = []
    pf = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    if pf:
        steam = Path(pf) / "Steam" / "steamapps" / "common"
        guesses.append(steam / "Project Zomboid Dedicated Server")
        guesses.append(steam / "ProjectZomboid")
    home = Path.home()
    guesses.append(home / "Steam" / "steamapps" / "common" / "Project Zomboid Dedicated Server")
    guesses.append(home / "Steam" / "steamapps" / "common" / "ProjectZomboid")
    for g in guesses:
        if g.is_dir() and (_java(g) or _launcher(g)):
            return g
    return None


def _java(dedicated: Path) -> Path | None:
    for rel in ("jre64/bin/java.exe", "jre64/bin/java"):
        path = dedicated / rel
        if path.exists():
            return path
    return None


def _launcher(dedicated: Path) -> Path | None:
    names = (
        "StartServer64.bat",
        "StartServer64.sh",
        "start-server.sh",
        "ProjectZomboidServer.bat",
    )
    for name in names:
        path = dedicated / name
        if path.exists():
            return path
    return _java(dedicated)


def _kind(dedicated: Path | None) -> str:
    if not dedicated:
        return "missing"
    name = dedicated.name.lower()
    if "dedicated" in name:
        return "dedicated"
    if (dedicated / "ProjectZomboidServer.bat").exists() or (dedicated / "projectzomboid.jar").exists():
        return "client-gameserver"
    return "unknown"


def _tail_log(path: Path, limit: int = 80) -> list[str]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()][-limit:]


def _newest_debug_log(cache: Path | None) -> Path | None:
    roots = []
    if cache:
        roots.append(cache / "Logs")
    roots.append(ROOT / ".cache" / "dedi-test" / "Logs")
    newest: Path | None = None
    newest_mtime = 0.0
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*DebugLog-server.txt"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime > newest_mtime:
                newest, newest_mtime = path, mtime
    return newest


def _collect_log_lines(cache: Path | None) -> tuple[list[str], str | None]:
    candidates: list[Path] = []
    if LOG_FILE.exists():
        candidates.append(LOG_FILE)
    debug = _newest_debug_log(cache)
    if debug:
        candidates.append(debug)
    test_console = ROOT / ".cache" / "dedi-test" / "console.txt"
    if test_console.exists():
        candidates.append(test_console)
    best_path: Path | None = None
    best_lines: list[str] = []
    best_mtime = -1.0
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        lines = _tail_log(path, 200)
        if lines and mtime >= best_mtime:
            best_path, best_lines, best_mtime = path, lines, mtime
    return best_lines, str(best_path) if best_path else None


def extract_issues(lines: list[str], limit: int = 40) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for raw in lines:
        lower = raw.lower()
        if any(noise in lower for noise in _NOISE):
            continue
        is_mod = "mod:" in lower or "servertweaker" in lower or "logextender" in lower
        is_error = "error" in lower or "exception" in lower or "fatal" in lower
        is_warn = "warn" in lower or "require(" in lower and "failed" in lower
        if is_error or (is_mod and is_warn):
            text = raw.strip()
            if len(text) > 280:
                text = text[:277] + "…"
            if is_error:
                if text not in errors:
                    errors.append(text)
            elif text not in warnings:
                warnings.append(text)
    return {"errors": errors[-limit:], "warnings": warnings[-limit:]}


def parse_world_status(lines: list[str], running: bool) -> dict[str, Any]:
    blob = "\n".join(lines).lower()
    stage = "idle"
    for key, markers in _WORLD_STAGES:
        if any(m in blob for m in markers):
            stage = key
    failed = any(m in blob for m in _FAIL_MARKERS) and stage != "ready"
    issues = extract_issues(lines)
    if issues["errors"] and stage != "ready" and not running:
        failed = True

    labels = {
        "idle": "Мир не запущен",
        "starting": "Старт JVM / сервер",
        "lua": "Загрузка Lua / скриптов",
        "world": "Загрузка мира (Start World)",
        "ready": "Мир запущен",
        "failed": "Ошибка старта",
        "stopped": "Остановлен",
    }
    if failed:
        stage = "failed"
    elif running and stage == "idle":
        stage = "starting"
    elif not running and stage == "ready":
        stage = "stopped"
    elif not running and stage in {"starting", "lua", "world"}:
        stage = "failed"

    version = None
    match = _VERSION_RE.search("\n".join(lines))
    if match:
        version = match.group(1)

    return {
        "stage": stage,
        "label": labels.get(stage, stage),
        "ready": stage == "ready" and running,
        "failed": stage == "failed",
        "log_tail": lines[-40:],
        "errors": issues["errors"],
        "warnings": issues["warnings"],
        "version": version,
    }


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _gameserver_processes() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if os.name != "nt":
        return found
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" |"
                " Where-Object { $_.CommandLine -match 'GameServer' } |"
                " Select-Object ProcessId, CommandLine |"
                " ConvertTo-Json -Compress",
            ],
            timeout=8,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out.strip() or "[]")
        if isinstance(data, dict):
            data = [data]
        for row in data:
            pid = int(row.get("ProcessId") or 0)
            if not pid:
                continue
            cmd = str(row.get("CommandLine") or "")
            found.append({"pid": pid, "cmd": cmd[:240]})
    except Exception:
        return found
    return found


def inspect() -> dict[str, Any]:
    load_dotenv()
    dedicated = _dedicated_dir()
    launcher = _launcher(dedicated) if dedicated else None
    java = _java(dedicated) if dedicated else None
    cache = cache_dir_for_local()
    processes = _gameserver_processes()
    tracked_pid = None
    running = False
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            tracked_pid = state.get("pid")
            if tracked_pid and _pid_alive(int(tracked_pid)):
                running = True
        except (json.JSONDecodeError, ValueError, OSError):
            running = False
    if processes:
        running = True
        if not tracked_pid:
            tracked_pid = processes[0]["pid"]

    lines, log_source = _collect_log_lines(Path(cache) if cache else None)
    world = parse_world_status(lines, running)
    if log_source:
        world["source"] = log_source
    if not world.get("version"):
        for extra in (
            ROOT / ".cache" / "dedi-test" / "console.txt",
            ROOT / ".cache" / "dedi-test" / "console-verify.txt",
            LOG_FILE,
        ):
            blob = "\n".join(_tail_log(extra, 80))
            match = _VERSION_RE.search(blob)
            if match:
                world["version"] = match.group(1)
                break

    kind = _kind(dedicated)
    hint = None
    if not dedicated or not (launcher or java):
        hint = (
            "Клиентский ProjectZomboid с jre64 тоже подходит как дедик. "
            "Поставь Steam → Project Zomboid Dedicated Server или укажи PZ_DEDICATED_DIR."
        )
    elif kind == "client-gameserver":
        hint = "Отдельный Dedicated Server не установлен — используется клиентский GameServer (тот же 42.x)."

    return {
        "dedicated_dir": str(dedicated) if dedicated else None,
        "kind": kind,
        "kind_label": {
            "dedicated": "Project Zomboid Dedicated Server",
            "client-gameserver": "Клиентский GameServer",
            "missing": "не найден",
            "unknown": "найден каталог",
        }.get(kind, kind),
        "launcher": str(launcher) if launcher else None,
        "java": str(java) if java else None,
        "cache_dir": str(cache) if cache else None,
        "server_name": os.environ.get("PZ_SERVER_NAME", "world"),
        "ready": bool(dedicated and (launcher or java) and cache),
        "running": running,
        "pid": int(tracked_pid) if running and tracked_pid else None,
        "processes": processes,
        "world": world,
        "log": log_source,
        "version": world.get("version"),
        "hint": hint,
    }


def start(server_name: str | None = None) -> dict[str, Any]:
    info = inspect()
    if info["running"]:
        return {**info, "ok": True, "message": "Already running"}
    if not info["dedicated_dir"] or not (info["launcher"] or info["java"]):
        raise FileNotFoundError(info.get("hint") or "Dedicated server not found")
    if not info["cache_dir"]:
        ms = mirror_status()
        if ms.get("paused") or ms.get("corrupt"):
            raise FileNotFoundError(
                "Зеркало на паузе: повреждённый файл. Перекачайте его, затем запускайте мир."
            )
        raise FileNotFoundError("Mirror is empty — pull /ServerWorld first")

    name = server_name or info["server_name"]
    dedicated = Path(info["dedicated_dir"])
    cache = Path(info["cache_dir"]).resolve()
    log = LOG_FILE
    log.parent.mkdir(parents=True, exist_ok=True)
    admin = os.environ.get("PZ_ADMIN_PASSWORD", "").strip() or "localadmin"

    java = _java(dedicated)
    if java:
        cmd = [
            str(java),
            "--enable-native-access=ALL-UNNAMED",
            "--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED",
            "-XX:+UseZGC",
            "-XX:-CreateCoredumpOnCrash",
            "-XX:-OmitStackTraceInFastThrow",
            "-Xmx3072m",
            "-Djava.library.path=./natives/;./natives/win64/;./",
            "-cp",
            "./;projectzomboid.jar",
            "zombie.network.GameServer",
            f"-cachedir={cache}",
            "-servername",
            name,
            "-adminpassword",
            admin,
            "-nosteam",
        ]
    else:
        launcher = Path(info["launcher"])
        if launcher.suffix.lower() == ".bat":
            cmd = ["cmd", "/c", str(launcher), "-servername", name, f"-cachedir={cache}"]
        elif launcher.suffix.lower() == ".sh":
            cmd = ["bash", str(launcher), "-servername", name, f"-cachedir={cache}"]
        else:
            cmd = [str(launcher), "-servername", name, f"-cachedir={cache}"]

    handle = log.open("ab")
    proc = subprocess.Popen(
        cmd,
        cwd=str(dedicated),
        stdout=handle,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0,
    )
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"pid": proc.pid, "cmd": cmd}, indent=2),
        encoding="utf-8",
    )
    return {**inspect(), "ok": True, "pid": proc.pid, "log": str(log), "message": f"Started PID {proc.pid}"}


def stop() -> dict[str, Any]:
    info = inspect()
    pids = {info.get("pid")}
    for proc in info.get("processes") or []:
        pids.add(proc.get("pid"))
    pids.discard(None)
    if not pids:
        return {**info, "ok": True, "message": "Not running"}
    for pid in pids:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.kill(int(pid), 15)
            except OSError:
                pass
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    return {**inspect(), "ok": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Local PZ dedicated server (mirror cachedir)")
    parser.add_argument("cmd", choices=["status", "start", "stop"])
    args = parser.parse_args()
    if args.cmd == "status":
        print(json.dumps(inspect(), indent=2))
        return 0
    if args.cmd == "start":
        print(json.dumps(start(), indent=2))
        return 0
    print(json.dumps(stop(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
