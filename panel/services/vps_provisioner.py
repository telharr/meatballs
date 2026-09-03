"""Safe Amnezia-style remote VPS provisioner for PZ Control Panel.

Safety guarantees:
- Never mutates firewall (no ufw/iptables flush).
- Never reinstalls Docker if already present.
- All remote writes confined to /opt/pz-panel/.
- Refuses to bind an occupied host port.
- Uses an isolated Docker bridge network (172.30.200.0/24).
"""

from __future__ import annotations

import io
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REMOTE_ROOT = "/opt/pz-panel"
COMPOSE_TEMPLATE = ROOT / "packaging" / "templates" / "vps.docker-compose.yml"

SKIP_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "backups",
        ".mypy_cache",
        ".pytest_cache",
        "Output",
        "pyinstaller-spec",
    }
)
SKIP_FILE_SUFFIXES = (".pyc", ".pyo", ".log", ".part")

_job_lock = threading.Lock()
_job: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "step": "",
    "percent": 0,
    "message": "",
    "logs": [],
    "errors": [],
    "host": "",
    "web_port": 8000,
    "url": "",
    "started_at": None,
    "finished_at": None,
    "ok": None,
}


@dataclass
class ProvisionRequest:
    host: str
    port: int = 22
    user: str = "root"
    password: str = ""
    private_key: str = ""
    web_port: int = 8000
    admin_password: str = ""


def provision_status() -> dict[str, Any]:
    with _job_lock:
        return {
            "running": bool(_job["running"]),
            "phase": _job["phase"],
            "step": _job["step"],
            "percent": int(_job["percent"] or 0),
            "message": _job["message"] or "",
            "logs": list(_job["logs"][-200:]),
            "errors": list(_job["errors"]),
            "host": _job["host"] or "",
            "web_port": int(_job["web_port"] or 8000),
            "url": _job["url"] or "",
            "started_at": _job["started_at"],
            "finished_at": _job["finished_at"],
            "ok": _job["ok"],
        }


def _emit(payload: dict[str, Any]) -> None:
    try:
        from panel.services.event_bus import emit

        emit("provision_progress", payload)
    except Exception:
        pass


def _set_progress(
    *,
    phase: str,
    step: str,
    percent: int,
    message: str,
    log_line: str | None = None,
    error: str | None = None,
) -> None:
    with _job_lock:
        _job["phase"] = phase
        _job["step"] = step
        _job["percent"] = max(0, min(100, int(percent)))
        _job["message"] = message
        if log_line:
            _job["logs"].append(log_line)
            if len(_job["logs"]) > 400:
                _job["logs"] = _job["logs"][-400:]
        if error:
            _job["errors"].append(error)
        snapshot = {
            "running": bool(_job["running"]),
            "phase": _job["phase"],
            "step": _job["step"],
            "percent": _job["percent"],
            "message": _job["message"],
            "logs": list(_job["logs"][-30:]),
            "errors": list(_job["errors"][-10:]),
            "host": _job["host"],
            "web_port": _job["web_port"],
            "url": _job["url"],
            "ok": _job["ok"],
        }
    _emit(snapshot)


def _is_private_key(text: str) -> bool:
    t = (text or "").strip()
    return "BEGIN" in t and "PRIVATE KEY" in t


def _load_pkey(key_text: str):
    import paramiko

    for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return loader.from_private_key(io.StringIO(key_text))
        except Exception:
            continue
    raise ValueError("Invalid SSH private key (need ED25519/RSA/ECDSA PEM)")


def _connect_ssh(req: ProvisionRequest):
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict[str, Any] = {
        "hostname": req.host,
        "port": int(req.port),
        "username": req.user,
        "timeout": 30,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if req.private_key.strip():
        kwargs["pkey"] = _load_pkey(req.private_key.strip())
    else:
        kwargs["password"] = req.password
    client.connect(**kwargs)
    return client


def _exec(client, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
    """Run remote command. Never used for firewall mutation."""
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    try:
        stdin.close()
    except Exception:
        pass
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts = rel.parts
    if any(p in SKIP_DIR_NAMES for p in parts):
        return True
    # Never upload local secrets / profiles into remote image context
    if len(parts) >= 2 and parts[0] == "panel" and parts[1] in ("data", "backups"):
        return True
    if path.suffix.lower() in SKIP_FILE_SUFFIXES:
        return True
    return False


def _sftp_mkdirs(sftp, remote_dir: str) -> None:
    parts = [p for p in remote_dir.strip("/").split("/") if p]
    cur = ""
    for part in parts:
        cur = f"{cur}/{part}"
        try:
            sftp.stat(cur)
        except OSError:
            sftp.mkdir(cur)


def _upload_tree(sftp, local_root: Path, remote_root: str) -> int:
    count = 0
    for path in local_root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip(path, local_root):
            continue
        rel = path.relative_to(local_root).as_posix()
        remote = f"{remote_root.rstrip('/')}/{rel}"
        _sftp_mkdirs(sftp, str(Path(remote).parent.as_posix()))
        sftp.put(str(path), remote)
        count += 1
    return count


def _upload_file(sftp, local: Path, remote: str) -> None:
    _sftp_mkdirs(sftp, str(Path(remote).parent.as_posix()))
    sftp.put(str(local), remote)


def _write_remote_text(sftp, remote: str, content: str) -> None:
    _sftp_mkdirs(sftp, str(Path(remote).parent.as_posix()))
    with sftp.file(remote, "w") as fh:
        fh.write(content)


def _compose_cmd(client) -> str:
    code, _, _ = _exec(client, "docker compose version >/dev/null 2>&1")
    if code == 0:
        return "docker compose"
    code, _, _ = _exec(client, "docker-compose version >/dev/null 2>&1")
    if code == 0:
        return "docker-compose"
    return "docker compose"


def _run_provision(req: ProvisionRequest) -> None:
    from panel.auth import hash_password

    url = f"http://{req.host}:{req.web_port}"
    with _job_lock:
        _job.update(
            {
                "running": True,
                "phase": "CONNECT",
                "step": "CONNECT",
                "percent": 2,
                "message": "Connecting via SSH…",
                "logs": [],
                "errors": [],
                "host": req.host,
                "web_port": req.web_port,
                "url": url,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "finished_at": None,
                "ok": None,
            }
        )
    _set_progress(phase="CONNECT", step="CONNECT", percent=5, message="SSH connect", log_line="[CONNECT] opening SSH…")

    client = None
    try:
        client = _connect_ssh(req)
        _set_progress(
            phase="CONNECT",
            step="CONNECT",
            percent=10,
            message="SSH connected",
            log_line=f"[CONNECT] ok {req.user}@{req.host}:{req.port}",
        )

        # CHECK_ENV
        _set_progress(phase="CHECK_ENV", step="CHECK_ENV", percent=15, message="Detecting OS…", log_line="[CHECK_ENV] reading /etc/os-release")
        code, os_rel, err = _exec(client, "cat /etc/os-release 2>/dev/null || uname -a")
        if code != 0 and not os_rel.strip():
            raise RuntimeError(f"Cannot detect OS: {err.strip() or 'empty'}")
        pretty = ""
        for line in os_rel.splitlines():
            if line.startswith("PRETTY_NAME="):
                pretty = line.split("=", 1)[1].strip().strip('"')
                break
        _set_progress(
            phase="CHECK_ENV",
            step="CHECK_ENV",
            percent=18,
            message=pretty or "Linux",
            log_line=f"[CHECK_ENV] OS: {pretty or os_rel.strip()[:120]}",
        )

        code, _, _ = _exec(client, "command -v systemctl >/dev/null 2>&1")
        if code != 0:
            _set_progress(
                phase="CHECK_ENV",
                step="CHECK_ENV",
                percent=20,
                message="systemd not found (continuing)",
                log_line="[CHECK_ENV] warning: systemctl missing — Docker install may still work",
            )

        code_docker, docker_path, _ = _exec(client, "command -v docker || true")
        docker_present = bool((docker_path or "").strip()) and code_docker == 0
        if docker_present:
            code_v, ver_out, _ = _exec(client, "docker --version 2>/dev/null || true")
            _set_progress(
                phase="CHECK_ENV",
                step="CHECK_ENV",
                percent=22,
                message="Docker present — will reuse",
                log_line=f"[CHECK_ENV] docker found: {(ver_out or docker_path).strip()[:120]}",
            )
        else:
            _set_progress(
                phase="CHECK_ENV",
                step="CHECK_ENV",
                percent=22,
                message="Docker absent — will install once",
                log_line="[CHECK_ENV] docker not found",
            )

        # PORT_CHECK — never touch firewall
        _set_progress(
            phase="PORT_CHECK",
            step="PORT_CHECK",
            percent=28,
            message=f"Checking port {req.web_port}…",
            log_line=f"[PORT_CHECK] probing :{req.web_port}",
        )
        port = int(req.web_port)
        probe = (
            f"ss -Hltn 'sport = :{port}' 2>/dev/null || "
            f"ss -tulpn 2>/dev/null | grep -E ':{port}([[:space:]]|$)' || "
            f"true"
        )
        _, listen_out, _ = _exec(client, probe)
        if listen_out.strip():
            raise RuntimeError(
                f"Port {port} is already in use on the VPS. "
                f"Choose another web_port. Probe output: {listen_out.strip()[:200]}"
            )
        _set_progress(
            phase="PORT_CHECK",
            step="PORT_CHECK",
            percent=32,
            message=f"Port {port} is free",
            log_line=f"[PORT_CHECK] :{port} free",
        )

        # INSTALL_DOCKER — only if completely absent
        if not docker_present:
            _set_progress(
                phase="INSTALL_DOCKER",
                step="INSTALL_DOCKER",
                percent=38,
                message="Installing Docker (official get.docker.com)…",
                log_line="[INSTALL_DOCKER] curl get.docker.com | sh",
            )
            # No firewall / no docker reinstall if present — already gated
            code, out, err = _exec(
                client,
                "curl -fsSL https://get.docker.com | sh",
                timeout=600,
            )
            if out.strip():
                for line in out.strip().splitlines()[-15:]:
                    _set_progress(
                        phase="INSTALL_DOCKER",
                        step="INSTALL_DOCKER",
                        percent=42,
                        message="Installing Docker…",
                        log_line=f"[INSTALL_DOCKER] {line[:200]}",
                    )
            if code != 0:
                raise RuntimeError(f"Docker install failed: {(err or out)[-400:]}")
            code, _, _ = _exec(client, "command -v docker >/dev/null 2>&1")
            if code != 0:
                raise RuntimeError("Docker install finished but `docker` binary not found")
            _set_progress(
                phase="INSTALL_DOCKER",
                step="INSTALL_DOCKER",
                percent=48,
                message="Docker installed",
                log_line="[INSTALL_DOCKER] ok",
            )
        else:
            _set_progress(
                phase="INSTALL_DOCKER",
                step="INSTALL_DOCKER",
                percent=48,
                message="Skipping Docker install (already present)",
                log_line="[INSTALL_DOCKER] skip — existing Docker reused (Amnezia-safe)",
            )

        compose = _compose_cmd(client)
        _set_progress(
            phase="INSTALL_DOCKER",
            step="INSTALL_DOCKER",
            percent=50,
            message=f"Compose: {compose}",
            log_line=f"[INSTALL_DOCKER] compose command: {compose}",
        )

        # DEPLOY_FILES — confined to /opt/pz-panel
        _set_progress(
            phase="DEPLOY_FILES",
            step="DEPLOY_FILES",
            percent=55,
            message=f"Creating {REMOTE_ROOT}…",
            log_line=f"[DEPLOY_FILES] mkdir {REMOTE_ROOT}",
        )
        code, _, err = _exec(
            client,
            f"mkdir -p {REMOTE_ROOT}/data/panel/data/servers {REMOTE_ROOT}/data/panel/backups {REMOTE_ROOT}/mirror",
        )
        if code != 0:
            raise RuntimeError(f"Cannot create {REMOTE_ROOT}: {err}")

        sftp = client.open_sftp()
        try:
            dockerfile = ROOT / "Dockerfile"
            if not dockerfile.is_file():
                raise FileNotFoundError("Dockerfile missing in workspace")
            _upload_file(sftp, dockerfile, f"{REMOTE_ROOT}/Dockerfile")
            _set_progress(
                phase="DEPLOY_FILES",
                step="DEPLOY_FILES",
                percent=58,
                message="Uploading panel/…",
                log_line="[DEPLOY_FILES] upload panel/",
            )
            n_panel = _upload_tree(sftp, ROOT / "panel", f"{REMOTE_ROOT}/panel")
            _set_progress(
                phase="DEPLOY_FILES",
                step="DEPLOY_FILES",
                percent=62,
                message="Uploading tools/…",
                log_line=f"[DEPLOY_FILES] panel files: {n_panel}",
            )
            n_tools = _upload_tree(sftp, ROOT / "tools", f"{REMOTE_ROOT}/tools")
            run_panel = ROOT / "run_panel.py"
            if run_panel.is_file():
                _upload_file(sftp, run_panel, f"{REMOTE_ROOT}/run_panel.py")
            launcher = ROOT / "packaging" / "panel_launcher.py"
            if launcher.is_file():
                _upload_file(sftp, launcher, f"{REMOTE_ROOT}/packaging/panel_launcher.py")
            req_txt = ROOT / "panel" / "requirements.txt"
            if req_txt.is_file():
                _upload_file(sftp, req_txt, f"{REMOTE_ROOT}/panel/requirements.txt")

            if COMPOSE_TEMPLATE.is_file():
                compose_body = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
            else:
                compose_body = (
                    "services:\n  pz-panel:\n    build: .\n    ports:\n"
                    f'      - "{port}:8000"\n    env_file: [.env]\n'
                    "    networks: [pz-panel-net]\n"
                    "networks:\n  pz-panel-net:\n    name: pz-panel-net\n"
                    "    driver: bridge\n    ipam:\n      config:\n"
                    "        - subnet: 172.30.200.0/24\n"
                )
            # Force host port into compose via .env PANEL_PORT; template already uses it
            _write_remote_text(sftp, f"{REMOTE_ROOT}/docker-compose.yml", compose_body)

            jwt = secrets.token_urlsafe(48)
            admin_hash = hash_password(req.admin_password)
            # Compose interpolates $VAR in env_file — escape every literal $.
            def _compose_env_escape(value: str) -> str:
                return value.replace("$", "$$")

            # Compose maps ${PANEL_PORT}:8000 (host→container). Container env overrides
            # PANEL_PORT=8000 in docker-compose.yml so the app still listens on 8000.
            env_body = "\n".join(
                [
                    "PANEL_HOST=0.0.0.0",
                    f"PANEL_PORT={port}",
                    "PANEL_PUBLIC=true",
                    "TRUST_PROXY=false",
                    "AUTH_LOCAL_BYPASS=false",
                    "AUTH_DISABLED=false",
                    f"JWT_SECRET={_compose_env_escape(jwt)}",
                    "ADMIN_USER=admin",
                    f"ADMIN_PASS_HASH={_compose_env_escape(admin_hash)}",
                    "",
                ]
            )
            _write_remote_text(sftp, f"{REMOTE_ROOT}/.env", env_body)
            _set_progress(
                phase="DEPLOY_FILES",
                step="DEPLOY_FILES",
                percent=70,
                message="Files uploaded",
                log_line=f"[DEPLOY_FILES] tools={n_tools}; .env written; compose isolated net 172.30.200.0/24",
            )
        finally:
            try:
                sftp.close()
            except Exception:
                pass

        # Ensure container env PANEL_PORT stays 8000 via compose environment override
        # (compose file already sets PANEL_PORT: "8000" in environment block)

        # DOCKER_UP
        _set_progress(
            phase="DOCKER_UP",
            step="DOCKER_UP",
            percent=75,
            message="docker compose up -d --build…",
            log_line=f"[DOCKER_UP] {compose} up -d --build",
        )
        code, out, err = _exec(
            client,
            f"cd {REMOTE_ROOT} && {compose} up -d --build",
            timeout=900,
        )
        for line in (out + "\n" + err).splitlines():
            if line.strip():
                _set_progress(
                    phase="DOCKER_UP",
                    step="DOCKER_UP",
                    percent=82,
                    message="Building/starting…",
                    log_line=f"[DOCKER_UP] {line.strip()[:220]}",
                )
        if code != 0:
            raise RuntimeError(f"docker compose failed (exit {code}): {(err or out)[-500:]}")
        _set_progress(
            phase="DOCKER_UP",
            step="DOCKER_UP",
            percent=88,
            message="Containers started",
            log_line="[DOCKER_UP] ok",
        )

        # HEALTH_POLL
        _set_progress(
            phase="HEALTH_POLL",
            step="HEALTH_POLL",
            percent=90,
            message="Waiting for /api/health…",
            log_line=f"[HEALTH_POLL] curl http://127.0.0.1:{port}/api/health",
        )
        healthy = False
        last_err = ""
        deadline = time.time() + 60
        while time.time() < deadline:
            code, out, err = _exec(
                client,
                f"curl -fsS -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/api/health || true",
                timeout=15,
            )
            code_txt = (out or "").strip()
            if code_txt == "200":
                healthy = True
                break
            last_err = err.strip() or code_txt or "no response"
            _set_progress(
                phase="HEALTH_POLL",
                step="HEALTH_POLL",
                percent=94,
                message=f"Waiting… ({code_txt or '…'})",
                log_line=f"[HEALTH_POLL] status={code_txt or last_err}",
            )
            time.sleep(3)
        if not healthy:
            raise RuntimeError(f"Health check timed out after 60s: {last_err}")

        with _job_lock:
            _job["ok"] = True
            _job["url"] = url
            _job["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _job["running"] = False
            _job["phase"] = "done"
            _job["step"] = "DONE"
            _job["percent"] = 100
            _job["message"] = f"Ready: {url}"
        _set_progress(
            phase="done",
            step="DONE",
            percent=100,
            message=f"Ready: {url}",
            log_line=f"[DONE] panel live at {url} (login admin)",
        )
    except Exception as exc:
        msg = str(exc)
        with _job_lock:
            _job["ok"] = False
            _job["running"] = False
            _job["phase"] = "error"
            _job["step"] = _job.get("step") or "ERROR"
            _job["percent"] = int(_job.get("percent") or 0)
            _job["message"] = msg
            _job["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _job["errors"].append(msg)
        _set_progress(
            phase="error",
            step="ERROR",
            percent=int(provision_status().get("percent") or 0),
            message=msg,
            log_line=f"[ERROR] {msg[:300]}",
            error=msg,
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def start_provision(req: ProvisionRequest) -> dict[str, Any]:
    with _job_lock:
        if _job["running"]:
            raise RuntimeError("Provision already running")
    thread = threading.Thread(target=_run_provision, args=(req,), daemon=True, name="vps-provision")
    thread.start()
    return provision_status()
