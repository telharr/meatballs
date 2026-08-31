#!/usr/bin/env python3
"""One-shot v1 validation harness (local). Prints JSON report, no secrets."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "panel" / "data"
BACKUP = ROOT / "panel" / "data._v1validate_backup"
BASE = "http://127.0.0.1:8000"


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def wait_panel(timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            code, data = http("GET", "/api/health")
            if code == 200 and isinstance(data, dict):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def backup_data() -> None:
    if BACKUP.exists():
        shutil.rmtree(BACKUP)
    BACKUP.mkdir()
    for name in ("servers.json", "prefs.json", "scheduler.json", "slots.json"):
        src = DATA / name
        if src.exists():
            shutil.copy2(src, BACKUP / name)
    if (DATA / "servers").exists():
        shutil.copytree(DATA / "servers", BACKUP / "servers")
    if (DATA / "secrets").exists():
        shutil.copytree(DATA / "secrets", BACKUP / "secrets")
    env = ROOT / ".env"
    if env.exists():
        shutil.copy2(env, BACKUP / ".env")


def restore_data() -> None:
    if not BACKUP.exists():
        return
    for name in ("servers.json", "prefs.json", "scheduler.json", "slots.json"):
        src = BACKUP / name
        if src.exists():
            shutil.copy2(src, DATA / name)
    if (BACKUP / "servers").exists():
        dst = DATA / "servers"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(BACKUP / "servers", dst)
    if (BACKUP / "secrets").exists():
        dst = DATA / "secrets"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(BACKUP / "secrets", dst)
    env_backup = BACKUP / ".env"
    env = ROOT / ".env"
    if env_backup.exists():
        shutil.copy2(env_backup, env)
    elif env.exists():
        env.unlink(missing_ok=True)


def clear_profiles() -> None:
    (DATA / "servers.json").write_text('{"active": null, "ids": []}\n', encoding="utf-8")
    servers = DATA / "servers"
    if servers.exists():
        shutil.rmtree(servers)
    servers.mkdir()
    secrets = DATA / "secrets"
    if secrets.exists():
        shutil.rmtree(secrets)
    secrets.mkdir()
    env = ROOT / ".env"
    if env.exists():
        env.rename(ROOT / ".env._v1validate_hidden")


def main() -> int:
    report: dict = {"steps": [], "pass": True}
    backup_data()

    def step(name: str, ok: bool, detail: dict | str):
        report["steps"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            report["pass"] = False
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # --- onboarding (empty state) ---
    clear_profiles()
    if not wait_panel():
        step("panel reachable", False, "http://127.0.0.1:8000 not responding — start panel first")
        restore_data()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    code, health = http("GET", "/api/health")
    step("health", code == 200, {"version": health.get("version") if isinstance(health, dict) else health})

    code, onboarding = http("GET", "/api/onboarding")
    needs = isinstance(onboarding, dict) and onboarding.get("needs_wizard") is True
    step("onboarding API", code == 200 and needs, onboarding)

    code, html = http("GET", "/")
    has_modal = isinstance(html, str) and "onboarding-modal" in html
    has_smoke = isinstance(html, str) and "view-smoke" in html
    step("index onboarding modal markup", has_modal, {"has_smoke_tab": has_smoke})

    # --- restore + probe XLGAMES profile ---
    restore_data()
    time.sleep(1.5)  # uvicorn reload
    if not wait_panel():
        step("panel after restore", False, "not reachable")
    else:
        code, health2 = http("GET", "/api/health")
        step("health after restore", code == 200, {"version": health2.get("version") if isinstance(health2, dict) else health2})

    # Load credentials from secrets (not logged)
    secrets_path = DATA / "secrets" / "meatballs-xl.json"
    profile_path = DATA / "servers" / "meatballs-xl.json"
    if secrets_path.exists() and profile_path.exists():
        secrets = json.loads(secrets_path.read_text(encoding="utf-8"))
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        files = profile.get("files") or {}
        probe_body = {
            "kind": "ftp",
            "host": files.get("host"),
            "port": files.get("port", 21),
            "user": files.get("user"),
            "password": secrets.get("ftp_password", ""),
            "root": files.get("root", "/ServerWorld"),
        }
        code, probe = http("POST", "/api/servers/probe/files", probe_body)
        ok_probe = code == 200 and isinstance(probe, dict) and probe.get("ok")
        checks = probe.get("checks") if isinstance(probe, dict) else {}
        step(
            "deep file probe (FTP XLGAMES)",
            ok_probe,
            {
                "checks": checks,
                "entries_count": len(probe.get("entries") or []) if isinstance(probe, dict) else 0,
                "error": probe.get("error") if isinstance(probe, dict) else probe,
            },
        )
    else:
        step("deep file probe (FTP XLGAMES)", False, "meatballs-xl profile/secrets missing after restore")

    # --- smoke status / start-stop ---
    code, smoke = http("GET", "/api/smoke/status")
    has_smoke_api = code == 200 and isinstance(smoke, dict) and "smoke" in smoke
    step("smoke status API", has_smoke_api, {
        "verdict": (smoke.get("smoke") or {}).get("verdict") if isinstance(smoke, dict) else None,
        "cache_dir": smoke.get("cache_dir") if isinstance(smoke, dict) else None,
        "mirror_root": smoke.get("mirror_root") if isinstance(smoke, dict) else None,
    })

    cache = smoke.get("cache_dir") if isinstance(smoke, dict) else None
    if cache and Path(cache).is_dir():
        code, started = http("POST", "/api/smoke/start", {})
        running = isinstance(started, dict) and (started.get("running") or (started.get("smoke") or {}).get("verdict") == "running")
        step("smoke start", code in (200, 409) and isinstance(started, dict), {
            "running": started.get("running") if isinstance(started, dict) else None,
            "verdict": (started.get("smoke") or {}).get("verdict") if isinstance(started, dict) else started,
            "error": started.get("detail") if isinstance(started, dict) else None,
        })
        time.sleep(3)
        code, mid = http("GET", "/api/smoke/status")
        log_tail = (mid.get("smoke") or {}).get("log_tail") if isinstance(mid, dict) else []
        errors = (mid.get("smoke") or {}).get("errors") if isinstance(mid, dict) else []
        step("smoke log streaming", code == 200 and (len(log_tail) > 0 or mid.get("running")), {
            "log_lines": len(log_tail),
            "errors": len(errors),
            "sample_errors": errors[:3],
        })
        code, stopped = http("POST", "/api/smoke/stop", {})
        step("smoke stop", code == 200, {
            "running_after": stopped.get("running") if isinstance(stopped, dict) else stopped,
        })
    else:
        step("smoke start", False, "cache_dir empty — run Mirror Pull first (.mirror/<id>/)")
        step("smoke log streaming", False, "skipped")
        step("smoke stop", False, "skipped")

    # cleanup hidden env if left
    hidden = ROOT / ".env._v1validate_hidden"
    if hidden.exists() and not (ROOT / ".env").exists():
        hidden.rename(ROOT / ".env")

    print("\n=== REPORT ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
