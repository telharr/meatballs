"""SFTP/SSH file transport — same surface as tools.ftp_client.FtpClient for mirror + panel."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ftp_client import (
    IntegrityError,
    RemoteEntry,
    is_protected_remote,
    join_remote,
    md5_bytes,
    md5_file,
    normalize_remote,
)

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class SftpConfig:
    host: str
    port: int = 22
    user: str = ""
    password: str = ""
    key_path: str = ""
    key_text: str = ""
    key_passphrase: str = ""
    remote_dir: str = "/"
    timeout: int = 60

    def validate(self) -> None:
        if not self.host:
            raise ValueError("SFTP host is not set")
        if not self.user:
            raise ValueError("SFTP user is not set")
        if not self.password and not self.key_path and not self.key_text:
            raise ValueError("SFTP password or private key required")


def _load_private_key(config: SftpConfig):
    import paramiko

    passphrase = config.key_passphrase or None
    if config.key_text.strip():
        for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                return loader.from_private_key(io.StringIO(config.key_text), password=passphrase)
            except Exception:
                continue
        raise ValueError("Invalid inline SFTP private key")
    path = Path(config.key_path.strip())
    if path.is_file():
        for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                return loader.from_private_key_file(str(path), password=passphrase)
            except Exception:
                continue
        raise ValueError(f"Cannot load SFTP key: {path}")
    return None


class SftpClient:
    def __init__(self, config: SftpConfig) -> None:
        self.config = config

    @contextmanager
    def connect(self) -> Iterator[Any]:
        import paramiko

        self.config.validate()
        transport = paramiko.Transport((self.config.host, int(self.config.port)))
        transport.banner_timeout = int(self.config.timeout)
        pkey = _load_private_key(self.config)
        if pkey is not None:
            transport.connect(username=self.config.user, pkey=pkey)
        else:
            transport.connect(username=self.config.user, password=self.config.password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        if sftp is None:
            transport.close()
            raise RuntimeError("SFTP session failed")
        base = normalize_remote(self.config.remote_dir or "/")
        if base not in ("/", ""):
            try:
                sftp.chdir(base)
            except OSError:
                pass
        try:
            yield sftp
        finally:
            try:
                sftp.close()
            except Exception:
                pass
            try:
                transport.close()
            except Exception:
                pass

    def _remote_path(self, sftp, remote_path: str) -> str:
        remote_path = normalize_remote(remote_path)
        if remote_path == "/":
            return "."
        return remote_path.lstrip("/")

    def list_dir(self, sftp, remote_path: str) -> list[RemoteEntry]:
        remote_path = normalize_remote(remote_path)
        path = self._remote_path(sftp, remote_path)
        entries: list[RemoteEntry] = []
        try:
            for attr in sftp.listdir_attr(path):
                name = attr.filename
                if name in (".", ".."):
                    continue
                is_dir = stat.S_ISDIR(attr.st_mode)
                full = join_remote(remote_path, name)
                entries.append(
                    RemoteEntry(
                        name=name,
                        path=full,
                        type="dir" if is_dir else "file",
                        size=None if is_dir else int(attr.st_size),
                        mtime=float(attr.st_mtime) if attr.st_mtime else None,
                    )
                )
        except OSError:
            return entries
        return entries

    def list_files(self, remote_path: str, recursive: bool = False) -> list[dict]:
        with self.connect() as sftp:
            return self._list_files(sftp, remote_path, recursive)

    def _list_files(self, sftp, remote_path: str, recursive: bool) -> list[dict]:
        remote_path = normalize_remote(remote_path)
        result: list[dict] = []
        for entry in self.list_dir(sftp, remote_path):
            result.append(
                {
                    "name": entry.name,
                    "path": entry.path,
                    "type": entry.type,
                    "size": entry.size,
                    "mtime": entry.mtime,
                }
            )
            if recursive and entry.type == "dir":
                result.extend(self._list_files(sftp, entry.path, True))
        return result

    def read_file(self, remote_path: str, binary: bool = False) -> str | bytes:
        remote_path = normalize_remote(remote_path)
        with self.connect() as sftp:
            with sftp.open(self._remote_path(sftp, remote_path), "rb") as handle:
                data = handle.read()
        if binary:
            return data
        for encoding in ("utf-8", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def download_file(self, remote_path: str, local_path: Path) -> Path:
        remote_path = normalize_remote(remote_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as sftp:
            sftp.get(self._remote_path(sftp, remote_path), str(local_path))
        return local_path

    def _ensure_remote_dirs(self, sftp, remote_path: str) -> None:
        remote_path = normalize_remote(remote_path)
        parent = str(Path(remote_path).parent).replace("\\", "/")
        if parent in ("/", "", "."):
            return
        parts = parent.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            try:
                sftp.mkdir(current)
            except OSError:
                pass

    def upload_file(
        self,
        local_path: str | Path,
        remote_path: str,
        *,
        allow_protected: bool = False,
    ) -> dict:
        local = Path(local_path)
        if not local.is_file():
            raise FileNotFoundError(f"Local file not found: {local}")
        remote_path = normalize_remote(remote_path)
        if is_protected_remote(remote_path, allow_protected):
            raise PermissionError(f"Refusing to upload to protected remote path: {remote_path}")
        local_hash = md5_file(local)
        local_size = local.stat().st_size
        with self.connect() as sftp:
            self._ensure_remote_dirs(sftp, remote_path)
            sftp.put(str(local), self._remote_path(sftp, remote_path))
            remote_hash = self._remote_md5(sftp, remote_path)
            try:
                remote_size = sftp.stat(self._remote_path(sftp, remote_path)).st_size
            except OSError:
                remote_size = None
        if remote_hash != local_hash or (remote_size is not None and remote_size != local_size):
            raise IntegrityError(
                f"Upload checksum mismatch: {remote_path} "
                f"local={local_hash[:8]} remote={remote_hash or 'none'} "
                f"size {local_size}/{remote_size}"
            )
        return {
            "local_path": str(local),
            "remote_path": remote_path,
            "size": local_size,
            "md5": local_hash,
            "verified": True,
        }

    def delete_file(self, remote_path: str, *, allow_protected: bool = False) -> None:
        remote_path = normalize_remote(remote_path)
        if "worlddictionary" in remote_path.lower():
            raise PermissionError(f"Refusing to delete WorldDictionary: {remote_path}")
        if is_protected_remote(remote_path, allow_protected):
            raise PermissionError(f"Refusing to delete protected remote path: {remote_path}")
        with self.connect() as sftp:
            sftp.remove(self._remote_path(sftp, remote_path))

    def _remote_md5(self, sftp, remote_path: str) -> str | None:
        try:
            with sftp.open(self._remote_path(sftp, remote_path), "rb") as handle:
                return md5_bytes(handle.read())
        except OSError:
            return None

    def sync_modpack(
        self,
        local_dir: str | Path,
        remote_dir: str,
        *,
        allow_protected: bool = False,
    ):
        from ftp_client import IntegrityError, SyncResult, is_protected_remote, join_remote, md5_file, normalize_remote

        local_root = Path(local_dir)
        if not local_root.is_dir():
            raise NotADirectoryError(f"Local directory not found: {local_root}")

        remote_dir = normalize_remote(remote_dir)
        result = SyncResult()

        with self.connect() as sftp:
            for path in sorted(local_root.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(local_root).as_posix()
                remote_path = join_remote(remote_dir, rel)
                if is_protected_remote(remote_path, allow_protected):
                    result.skipped.append(f"{rel} (protected)")
                    continue
                local_hash = md5_file(path)
                remote_hash = self._remote_md5(sftp, remote_path)
                if remote_hash == local_hash:
                    result.skipped.append(rel)
                    continue
                try:
                    self._ensure_remote_dirs(sftp, remote_path)
                    sftp.put(str(path), self._remote_path(sftp, remote_path))
                    verify = self._remote_md5(sftp, remote_path)
                    if verify != local_hash:
                        raise IntegrityError(
                            f"Upload checksum mismatch: {remote_path} local={local_hash[:8]} remote={verify or 'none'}"
                        )
                    result.uploaded.append(rel)
                except Exception as exc:
                    result.errors.append(f"{rel}: {exc}")

        return result

    def pull_tree(
        self,
        remote_path: str,
        local_dir: Path,
        *,
        skip_dirs: set[str] | None = None,
        max_depth: int = 8,
        max_files: int = 4000,
        on_progress=None,
        queue: list[dict] | None = None,
        pause_check=None,
        mode: str = "incremental",
        known_sizes: dict[str, int] | None = None,
    ) -> dict:
        skip = {n.lower() for n in (skip_dirs or set())}
        local_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[str] = []
        verified: list[dict] = []
        skipped: list[str] = []
        unchanged: list[str] = []
        errors: list[str] = []
        planned: list[dict] = list(queue) if queue else []
        mode_norm = (mode or "incremental").lower()

        def collect(sftp, remote: str, dest: Path, depth: int) -> None:
            if depth > max_depth or len(planned) >= max_files:
                return
            try:
                entries = self.list_dir(sftp, remote)
            except Exception as exc:
                errors.append(f"{remote}: {exc}")
                return
            for entry in entries:
                if entry.type == "dir":
                    if entry.name.lower() in skip:
                        skipped.append(entry.path)
                        continue
                    child = dest / entry.name
                    child.mkdir(parents=True, exist_ok=True)
                    collect(sftp, entry.path, child, depth + 1)
                    continue
                if len(planned) >= max_files:
                    skipped.append(f"{entry.path} (max files)")
                    continue
                planned.append(
                    {
                        "remote": entry.path,
                        "local": str(dest / entry.name),
                        "size": entry.size,
                    }
                )

        def emit(phase: str, current: str = "", extra: dict | None = None) -> None:
            if not on_progress:
                return
            total = len(planned) or 1
            payload = {
                "phase": phase,
                "current": current,
                "done": len(downloaded),
                "unchanged": len(unchanged),
                "verified": len(verified),
                "total": len(planned),
                "percent": min(100, int(len(verified) * 100 / total)) if planned else 0,
                "errors": len(errors),
                "remaining": max(0, len(planned) - len(verified)),
                "heartbeat": time.time(),
            }
            if extra:
                payload.update(extra)
            on_progress(payload)

        known = known_sizes or {}

        def fetch_one(sftp, item: dict) -> dict:
            remote = item["remote"]
            target = Path(item["local"])
            target.parent.mkdir(parents=True, exist_ok=True)
            remote_size = item.get("size")
            if remote_size is None:
                remote_size = known.get(remote)
            if remote_size is None:
                try:
                    remote_size = sftp.stat(self._remote_path(sftp, remote)).st_size
                except OSError:
                    pass
            local_exists = target.exists()
            local_size = target.stat().st_size if local_exists else None
            same_size = local_exists and remote_size is not None and local_size == int(remote_size)
            if mode_norm != "force" and local_exists and (same_size or remote_size is None):
                digest = md5_file(target) if mode_norm == "verify" else ""
                return {
                    "remote": remote,
                    "local": str(target),
                    "size": int(remote_size) if remote_size is not None else local_size,
                    "md5": digest,
                    "skipped_ok": True,
                }
            part = target.with_name(target.name + ".part")
            digest = hashlib.md5()
            with sftp.open(self._remote_path(sftp, remote), "rb") as handle:
                with part.open("wb") as out:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        digest.update(chunk)
            local_size = part.stat().st_size
            local_hash = digest.hexdigest()
            try:
                remote_size = sftp.stat(self._remote_path(sftp, remote)).st_size
            except OSError:
                remote_size = None
            if remote_size is not None and int(remote_size) != local_size:
                part.unlink(missing_ok=True)
                raise IntegrityError(
                    f"SIZE mismatch {remote}: local={local_size} remote={remote_size}"
                )
            part.replace(target)
            return {
                "remote": remote,
                "local": str(target),
                "size": local_size,
                "md5": local_hash,
            }

        remaining: list[dict] = []
        paused = False
        corrupt: dict | None = None

        with self.connect() as sftp:
            if not planned:
                emit("scanning", remote_path)
                collect(sftp, normalize_remote(remote_path), local_dir, 0)
            emit("comparing" if mode_norm != "force" else "downloading", extra={"total": len(planned)})
            for idx, item in enumerate(planned):
                if pause_check and pause_check():
                    remaining = planned[idx:]
                    paused = True
                    emit("paused", item["remote"], {"remaining": len(remaining)})
                    break
                emit("comparing" if mode_norm != "force" else "downloading", item["remote"])
                try:
                    info = fetch_one(sftp, item)
                except IntegrityError as exc:
                    remaining = planned[idx:]
                    paused = True
                    corrupt = {"remote": item["remote"], "local": item["local"], "reason": str(exc)}
                    errors.append(str(exc))
                    emit("paused", item["remote"], {"corrupt": corrupt, "remaining": len(remaining)})
                    break
                except Exception as exc:
                    remaining = planned[idx:]
                    paused = True
                    corrupt = {"remote": item["remote"], "local": item["local"], "reason": str(exc)}
                    errors.append(f"{item['remote']}: {exc}")
                    emit("paused", item["remote"], {"corrupt": corrupt, "remaining": len(remaining)})
                    break
                if info.get("skipped_ok"):
                    unchanged.append(item["remote"])
                else:
                    downloaded.append(item["remote"])
                verified.append(info)
                emit(
                    "verifying" if info.get("md5") else "comparing",
                    item["remote"],
                    {"last_md5": info.get("md5") or "", "unchanged": len(unchanged)},
                )

        if not paused:
            emit("done")
        return {
            "downloaded": downloaded,
            "verified": verified,
            "unchanged": unchanged,
            "skipped": skipped,
            "errors": errors,
            "local_dir": str(local_dir),
            "count": len(verified),
            "planned": len(planned),
            "paused": paused,
            "corrupt": corrupt,
            "remaining": remaining,
        }

    def exec_command(self, command: str, timeout: int = 12) -> tuple[str, str, int]:
        import paramiko

        self.config.validate()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = _load_private_key(self.config)
        connect_kwargs: dict[str, Any] = {
            "hostname": self.config.host,
            "port": int(self.config.port),
            "username": self.config.user,
            "timeout": int(self.config.timeout),
            "allow_agent": False,
            "look_for_keys": False,
        }
        if pkey is not None:
            connect_kwargs["pkey"] = pkey
        else:
            connect_kwargs["password"] = self.config.password
        client.connect(**connect_kwargs)
        try:
            _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            code = stdout.channel.recv_exit_status()
            return out, err, code
        finally:
            try:
                client.close()
            except Exception:
                pass


def sftp_config_from_payload(payload: dict[str, Any]) -> SftpConfig:
    return SftpConfig(
        host=str(payload.get("host") or ""),
        port=int(payload.get("port") or payload.get("sftp_port") or 22),
        user=str(payload.get("user") or ""),
        password=str(payload.get("password") or payload.get("sftp_pass") or ""),
        key_path=str(payload.get("sftp_key_path") or payload.get("key_path") or ""),
        key_text=str(payload.get("sftp_private_key") or payload.get("key_text") or ""),
        key_passphrase=str(payload.get("sftp_key_passphrase") or ""),
        remote_dir="/",
        timeout=int(payload.get("timeout") or os.environ.get("SFTP_TIMEOUT", "60") or "60"),
    )
