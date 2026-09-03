"""RCON task scheduler with 5-field cron support."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from panel.paths import DATA_DIR

SCHEDULER_FILE = DATA_DIR / "scheduler.json"

DEFAULT_TASKS: list[dict[str, Any]] = [
    {
        "id": "seed-hourly-save",
        "name": "Сохранение мира (каждый час)",
        "enabled": True,
        "cron": "0 * * * *",
        "command": "save",
        "preset": "save",
    },
    {
        "id": "seed-announce-2h",
        "name": "Анонс (каждые 2 часа)",
        "enabled": False,
        "cron": "0 */2 * * *",
        "command": 'servermsg "MEATBALLS PZ — discord.gg/yourlink"',
        "preset": "announce",
    },
    {
        "id": "seed-restart-warn-350",
        "name": "Предупреждение о рестарте (3:50)",
        "enabled": False,
        "cron": "50 3 * * *",
        "command": 'servermsg "Рестарт сервера через 10 минут"',
        "preset": "announce",
    },
    {
        "id": "seed-restart-warn-355",
        "name": "Предупреждение о рестарте (3:55)",
        "enabled": False,
        "cron": "55 3 * * *",
        "command": 'servermsg "Рестарт сервера через 5 минут"',
        "preset": "announce",
    },
    {
        "id": "seed-save-before-restart",
        "name": "Сохранение перед рестартом (3:59)",
        "enabled": False,
        "cron": "59 3 * * *",
        "command": "save",
        "preset": "save",
    },
    {
        "id": "seed-restart-400",
        "name": "Рестарт (4:00)",
        "enabled": False,
        "cron": "0 4 * * *",
        "command": "quit",
        "preset": "restart",
    },
]


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SCHEDULER_FILE.exists():
        try:
            data = json.loads(SCHEDULER_FILE.read_text(encoding="utf-8"))
            if data.get("tasks"):
                return
        except (json.JSONDecodeError, OSError):
            pass
    now = datetime.now().isoformat(timespec="seconds")
    tasks = []
    for t in DEFAULT_TASKS:
        tasks.append({**t, "last_run": None, "last_result": None, "created_at": now})
    SCHEDULER_FILE.write_text(json.dumps({"tasks": tasks}, indent=2), encoding="utf-8")


def load_tasks() -> list[dict[str, Any]]:
    _ensure_store()
    data = json.loads(SCHEDULER_FILE.read_text(encoding="utf-8"))
    return data.get("tasks", [])


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    _ensure_store()
    SCHEDULER_FILE.write_text(json.dumps({"tasks": tasks}, indent=2), encoding="utf-8")


def get_task(task_id: str) -> dict[str, Any] | None:
    for task in load_tasks():
        if task["id"] == task_id:
            return task
    return None


def add_task(payload: dict[str, Any]) -> dict[str, Any]:
    tasks = load_tasks()
    now = datetime.now().isoformat(timespec="seconds")
    task = {
        "id": str(uuid.uuid4()),
        "name": payload["name"],
        "enabled": payload.get("enabled", True),
        "cron": payload["cron"],
        "command": payload["command"],
        "preset": payload.get("preset", "custom"),
        "last_run": None,
        "last_result": None,
        "created_at": now,
    }
    tasks.append(task)
    save_tasks(tasks)
    return task


def update_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    tasks = load_tasks()
    for i, task in enumerate(tasks):
        if task["id"] != task_id:
            continue
        for key in ("name", "enabled", "cron", "command", "preset"):
            if key in payload:
                task[key] = payload[key]
        tasks[i] = task
        save_tasks(tasks)
        return task
    raise KeyError(task_id)


def delete_task(task_id: str) -> None:
    tasks = [t for t in load_tasks() if t["id"] != task_id]
    save_tasks(tasks)


def mark_task_run(task_id: str, result: str) -> None:
    tasks = load_tasks()
    now = datetime.now().isoformat(timespec="seconds")
    for i, task in enumerate(tasks):
        if task["id"] == task_id:
            task["last_run"] = now
            task["last_result"] = result
            tasks[i] = task
            save_tasks(tasks)
            return


def _parse_field(field: str, value: int, min_v: int, max_v: int) -> bool:
    field = field.strip()
    if field == "*":
        return True
    if field.startswith("*/"):
        step = int(field[2:])
        return value % step == 0
    for part in field.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            if int(a) <= value <= int(b):
                return True
        elif int(part) == value:
            return True
    return False


def cron_matches(cron: str, dt: datetime | None = None) -> bool:
    """Match standard 5-field cron: minute hour day month weekday."""
    dt = dt or datetime.now()
    parts = cron.split()
    if len(parts) != 5:
        return False
    weekday = dt.weekday()  # Mon=0
    cron_wd = (weekday + 1) % 7  # Sun=0 style
    return (
        _parse_field(parts[0], dt.minute, 0, 59)
        and _parse_field(parts[1], dt.hour, 0, 23)
        and _parse_field(parts[2], dt.day, 1, 31)
        and _parse_field(parts[3], dt.month, 1, 12)
        and _parse_field(parts[4], cron_wd, 0, 6)
    )


def parse_cron_fields(cron: str) -> dict[str, str]:
    parts = (cron + " * * * * *").split()[:5]
    labels = ("minute", "hour", "day", "month", "weekday")
    return dict(zip(labels, parts))


def format_last_run(iso: str | None) -> str:
    if not iso:
        return "Никогда"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return iso


def tasks_due_now(dt: datetime | None = None) -> list[dict[str, Any]]:
    dt = dt or datetime.now()
    due = []
    for task in load_tasks():
        if not task.get("enabled"):
            continue
        if not cron_matches(task["cron"], dt):
            continue
        last_run = task.get("last_run")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                if last_dt.replace(second=0, microsecond=0) == dt.replace(second=0, microsecond=0):
                    continue
            except ValueError:
                pass
        due.append(task)
    return due


CRON_RE = re.compile(r"^(\S+\s+){4}\S+$")


def validate_cron(cron: str) -> bool:
    return bool(CRON_RE.match(cron.strip()))
