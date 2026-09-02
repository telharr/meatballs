"""Sandbox clean-install validation for v3.19.7 (Scenario A)."""
from __future__ import annotations

import http.cookiejar
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL_DATA = ROOT / "panel" / "data"
ENV_FILE = ROOT / ".env"
DATA_BAK = ROOT / "panel" / "data_sandbox_bak"
ENV_BAK = ROOT / ".env_sandbox_bak"
TEST_CACHE = ROOT / ".cache" / "test-world"
PORT = 8001
BASE = f"http://127.0.0.1:{PORT}"
PY = sys.executable

_opener: urllib.request.OpenerDirector | None = None


def _ensure_local_session() -> None:
    global _opener
    jar = http.cookiejar.CookieJar()
    _opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        BASE + "/api/auth/local",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _opener.open(req, timeout=15) as resp:
        json.loads(resp.read().decode())


def http_get(path: str) -> dict:
    assert _opener is not None
    with _opener.open(BASE + path, timeout=15) as resp:
        return json.loads(resp.read().decode())


def http_post(path: str, body: dict) -> dict:
    assert _opener is not None
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def backup() -> None:
    if PANEL_DATA.exists():
        if DATA_BAK.exists():
            shutil.rmtree(DATA_BAK)
        shutil.move(str(PANEL_DATA), str(DATA_BAK))
    if ENV_FILE.exists():
        if ENV_BAK.exists():
            ENV_BAK.unlink()
        shutil.move(str(ENV_FILE), str(ENV_BAK))
    PANEL_DATA.mkdir(parents=True, exist_ok=True)
    (PANEL_DATA / "servers").mkdir(parents=True, exist_ok=True)


def restore() -> None:
    if PANEL_DATA.exists():
        shutil.rmtree(PANEL_DATA, ignore_errors=True)
    if DATA_BAK.exists():
        shutil.move(str(DATA_BAK), str(PANEL_DATA))
    if ENV_BAK.exists():
        if ENV_FILE.exists():
            ENV_FILE.unlink()
        shutil.move(str(ENV_BAK), str(ENV_FILE))
    if TEST_CACHE.exists():
        shutil.rmtree(TEST_CACHE, ignore_errors=True)


def wait_health(proc: subprocess.Popen, seconds: float = 25.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=3) as resp:
                data = json.loads(resp.read().decode())
                if data.get("version"):
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.5)
    return False


def main() -> int:
    proc: subprocess.Popen | None = None
    results: dict[str, object] = {"ok": True, "checks": []}

    def record(name: str, ok: bool, detail: object) -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            results["ok"] = False
        print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")

    try:
        backup()
        record("backup", True, "panel/data and .env moved aside")

        proc = subprocess.Popen(
            [
                PY,
                "-m",
                "uvicorn",
                "panel.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
            ],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_health(proc):
            record("server_start", False, "uvicorn did not become healthy")
            return 1
        record("server_start", True, f"listening on {PORT}")

        _ensure_local_session()
        record("local_auth", True, "POST /api/auth/local")

        auth = http_get("/api/auth/status")
        record(
            "auth_status",
            auth.get("auth_disabled") is False and auth.get("local_bypass") is True,
            auth,
        )

        onboarding = http_get("/api/onboarding")
        record(
            "onboarding_empty",
            onboarding.get("needs_wizard") is True and onboarding.get("servers_count") == 0,
            onboarding,
        )

        steamcmd = http_get("/api/workshop/steamcmd/status")
        install = steamcmd.get("install") or {}
        record(
            "steamcmd_status",
            "installed" in steamcmd and install.get("running") is False,
            {"installed": steamcmd.get("installed"), "install": install},
        )

        created = http_post(
            "/api/servers",
            {
                "name": "Test Clean Server",
                "hoster": "local",
                "files": {"kind": "local", "root": ".cache/test-world"},
                "rcon": {"host": "127.0.0.1", "port": 16284},
                "public": {"host": "127.0.0.1"},
            },
        )
        server_id = created.get("id") or created.get("server", {}).get("id")
        record("create_server", bool(server_id), created)

        if server_id:
            activated = http_post(f"/api/servers/{server_id}/activate", {})
            record("activate_server", activated.get("active") == server_id, activated)

            onboarding2 = http_get("/api/onboarding")
            record(
                "onboarding_after",
                onboarding2.get("needs_wizard") is False and onboarding2.get("servers_count") == 1,
                onboarding2,
            )

        health = http_get("/api/health")
        record("health_version", health.get("version") == "3.19.7", health.get("version"))

    except Exception as exc:
        record("exception", False, str(exc))
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        restore()
        record("restore", not PANEL_DATA.exists() or (DATA_BAK.exists() is False and PANEL_DATA.exists()), "restored")

    print("\nSUMMARY:", json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
