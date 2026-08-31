"""Shared FTP client for PZ server sync (MCP + CLI)."""

from __future__ import annotations

import fnmatch
import hashlib
import io
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from ftplib import FTP, FTP_TLS, error_perm
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]

# Remote paths that must never be overwritten without explicit override.
PROTECTED_REMOTE_GLOBS = (
    "**/.cache/Saves/**",
    "**/Saves/**",
    "**/WorldDictionary.bin",
    "**/worlddictionary.bin",
)

DEFAULT_CONFIG_FILES = (
    "MEATBALLS.ini",
    "start-server.sh",
    "start-server.bat",
    "servertest.ini",
    "server-console.txt",
)


@dataclass
class FtpConfig:
    host: str
    port: int = 21
    user: str = ""
    password: str = ""
    remote_dir: str = "/"
    use_tls: bool = False
    passive: bool = True
    timeout: int = 60

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> FtpConfig:
        source = env or os.environ
        return cls(
            host=source.get("FTP_HOST", "").strip(),
            port=int(source.get("FTP_PORT", "21") or "21"),
            user=source.get("FTP_USER", "").strip(),
            password=source.get("FTP_PASS", "").strip(),
            remote_dir=source.get("FTP_REMOTE_DIR", "/").strip() or "/",
            use_tls=source.get("FTP_USE_TLS", "").lower() in ("1", "true", "yes"),
            passive=source.get("FTP_PASSIVE", "true").lower() not in ("0", "false", "no"),
            timeout=int(source.get("FTP_TIMEOUT", "60") or "60"),
        )

    def validate(self) -> None:
        if not self.host:
            raise ValueError("FTP_HOST is not set")
        if not self.user:
            raise ValueError("FTP_USER is not set")


@dataclass
class RemoteEntry:
    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None
    mtime: float | None = None


@dataclass
class SyncResult:
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class IntegrityError(Exception):
    """Local/remote checksum or size mismatch."""


def load_dotenv() -> None:
    try:
        from dotenv import load_dotenv as _load

        _load(ROOT / ".env")
    except ImportError:
        pass


def normalize_remote(path: str) -> str:
    path = path.replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def join_remote(base: str, *parts: str) -> str:
    segments: list[str] = []
    for chunk in (base, *parts):
        for piece in chunk.replace("\\", "/").split("/"):
            if piece and piece != ".":
                segments.append(piece)
    return "/" + "/".join(segments) if segments else "/"


def is_protected_remote(remote_path: str, allow_protected: bool = False) -> bool:
    if allow_protected:
        return False
    normalized = normalize_remote(remote_path).lstrip("/")
    for pattern in PROTECTED_REMOTE_GLOBS:
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(
            normalized.lower(), pattern.lower()
        ):
            return True
    return False


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FtpClient:
    def __init__(self, config: FtpConfig) -> None:
        self.config = config

    @contextmanager
    def connect(self) -> Iterator[FTP]:
        self.config.validate()
        ftp: FTP
        if self.config.use_tls:
            ftp = FTP_TLS()
            ftp.connect(self.config.host, self.config.port, timeout=self.config.timeout)
            ftp.login(self.config.user, self.config.password)
            ftp.prot_p()
        else:
            ftp = FTP()
            ftp.connect(self.config.host, self.config.port, timeout=self.config.timeout)
            ftp.login(self.config.user, self.config.password)
        ftp.encoding = "utf-8"
        ftp.set_pasv(self.config.passive)
        base = self.config.remote_dir
        if base and base != "/":
            try:
                ftp.cwd(base)
            except error_perm:
                pass
        try:
            yield ftp
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()

    def _parse_mlsd(self, ftp: FTP, remote_path: str) -> list[RemoteEntry]:
        entries: list[RemoteEntry] = []
        remote_path = normalize_remote(remote_path)
        try:
            for name, facts in ftp.mlsd(remote_path):
                if name in (".", ".."):
                    continue
                entry_type = facts.get("type", "file")
                kind = "dir" if entry_type == "dir" else "file"
                size = int(facts["size"]) if "size" in facts else None
                mtime = None
                if "modify" in facts:
                    try:
                        mtime = time.mktime(
                            time.strptime(facts["modify"], "%Y%m%d%H%M%S")
                        )
                    except ValueError:
                        mtime = None
                entries.append(
                    RemoteEntry(
                        name=name,
                        path=join_remote(remote_path, name),
                        type=kind,
                        size=size,
                        mtime=mtime,
                    )
                )
        except error_perm:
            return entries
        return entries

    def _parse_nlst(self, ftp: FTP, remote_path: str) -> list[RemoteEntry]:
        entries: list[RemoteEntry] = []
        remote_path = normalize_remote(remote_path)
        try:
            names = ftp.nlst(remote_path)
        except error_perm:
            return entries
        for raw in names:
            name = raw.rstrip("/").split("/")[-1]
            if name in (".", ".."):
                continue
            full = join_remote(remote_path, name)
            kind = "dir"
            size = None
            try:
                size = ftp.size(full)
                kind = "file"
            except error_perm:
                kind = "dir"
            entries.append(
                RemoteEntry(name=name, path=full, type=kind, size=size)
            )
        return entries

    def list_dir(self, ftp: FTP, remote_path: str) -> list[RemoteEntry]:
        remote_path = normalize_remote(remote_path)
        try:
            return self._parse_mlsd(ftp, remote_path)
        except error_perm:
            return self._parse_nlst(ftp, remote_path)

    def list_files(self, remote_path: str, recursive: bool = False) -> list[dict]:
        with self.connect() as ftp:
            return self._list_files(ftp, remote_path, recursive)

    def _list_files(
        self, ftp: FTP, remote_path: str, recursive: bool
    ) -> list[dict]:
        remote_path = normalize_remote(remote_path)
        result: list[dict] = []
        for entry in self.list_dir(ftp, remote_path):
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
                result.extend(self._list_files(ftp, entry.path, True))
        return result

    def list_tree(self, remote_path: str, max_depth: int = 4) -> str:
        lines: list[str] = []
        root = normalize_remote(remote_path)
        lines.append(f"{root}/")

        with self.connect() as ftp:
            def walk(path: str, prefix: str, depth: int) -> None:
                if depth > max_depth:
                    lines.append(f"{prefix}... (max depth)")
                    return
                entries = self.list_dir(ftp, path)
                dirs = sorted(
                    [e for e in entries if e.type == "dir"],
                    key=lambda e: e.name.lower(),
                )
                files = sorted(
                    [e for e in entries if e.type == "file"],
                    key=lambda e: e.name.lower(),
                )
                for entry in dirs + files:
                    marker = "/" if entry.type == "dir" else ""
                    size = f" ({entry.size} B)" if entry.size is not None else ""
                    lines.append(f"{prefix}{entry.name}{marker}{size}")
                    if entry.type == "dir":
                        walk(entry.path, prefix + "  ", depth + 1)

            walk(root, "  ", 0)

        return "\n".join(lines)

    def read_file(self, remote_path: str, binary: bool = False) -> str | bytes:
        remote_path = normalize_remote(remote_path)
        buffer = io.BytesIO()
        with self.connect() as ftp:
            ftp.retrbinary(f"RETR {remote_path}", buffer.write)
        data = buffer.getvalue()
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
        with self.connect() as ftp:
            with local_path.open("wb") as handle:
                ftp.retrbinary(f"RETR {remote_path}", handle.write)
        return local_path

    def _ensure_remote_dirs(self, ftp: FTP, remote_path: str) -> None:
        remote_path = normalize_remote(remote_path)
        if remote_path in ("/", ""):
            return
        parts = remote_path.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            try:
                ftp.mkd(current)
            except error_perm:
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
            raise PermissionError(
                f"Refusing to upload to protected remote path: {remote_path}"
            )
        local_hash = md5_file(local)
        local_size = local.stat().st_size
        with self.connect() as ftp:
            self._ensure_remote_dirs(ftp, str(Path(remote_path).parent).replace("\\", "/"))
            with local.open("rb") as handle:
                ftp.storbinary(f"STOR {remote_path}", handle)
            remote_hash = self._remote_md5(ftp, remote_path)
            remote_size = None
            try:
                remote_size = ftp.size(remote_path)
            except Exception:
                pass
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
            raise PermissionError(
                f"Refusing to delete protected remote path: {remote_path}"
            )
        with self.connect() as ftp:
            ftp.delete(remote_path)

    def _remote_md5(self, ftp: FTP, remote_path: str) -> str | None:
        buffer = io.BytesIO()
        try:
            ftp.retrbinary(f"RETR {remote_path}", buffer.write)
        except error_perm:
            return None
        return md5_bytes(buffer.getvalue())

    def sync_modpack(
        self,
        local_dir: str | Path,
        remote_dir: str,
        *,
        allow_protected: bool = False,
    ) -> SyncResult:
        local_root = Path(local_dir)
        if not local_root.is_dir():
            raise NotADirectoryError(f"Local directory not found: {local_root}")

        remote_dir = normalize_remote(remote_dir)
        result = SyncResult()

        with self.connect() as ftp:
            for path in sorted(local_root.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(local_root).as_posix()
                remote_path = join_remote(remote_dir, rel)
                if is_protected_remote(remote_path, allow_protected):
                    result.skipped.append(f"{rel} (protected)")
                    continue
                local_hash = md5_file(path)
                remote_hash = self._remote_md5(ftp, remote_path)
                if remote_hash == local_hash:
                    result.skipped.append(rel)
                    continue
                try:
                    self._ensure_remote_dirs(
                        ftp, str(Path(remote_path).parent).replace("\\", "/")
                    )
                    with path.open("rb") as handle:
                        ftp.storbinary(f"STOR {remote_path}", handle)
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
        """Download a remote tree. mode=incremental skips same-size files (no RETR, no MD5).
        mode=force re-downloads everything. mode=verify hashes locals after size match.
        Incremental never RETRs a local file just because SIZE is missing — use verify."""
        skip = {n.lower() for n in (skip_dirs or set())}
        local_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[str] = []
        verified: list[dict] = []
        skipped: list[str] = []
        unchanged: list[str] = []
        errors: list[str] = []
        planned: list[dict] = list(queue) if queue else []
        mode_norm = (mode or "incremental").lower()

        def collect(ftp: FTP, remote: str, dest: Path, depth: int) -> None:
            if depth > max_depth or len(planned) >= max_files:
                return
            try:
                entries = self.list_dir(ftp, remote)
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
                    collect(ftp, entry.path, child, depth + 1)
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

        def fetch_one(ftp: FTP, item: dict) -> dict:
            remote = item["remote"]
            target = Path(item["local"])
            target.parent.mkdir(parents=True, exist_ok=True)
            remote_size = item.get("size")
            if remote_size is None:
                remote_size = known.get(remote)
            if remote_size is None:
                try:
                    remote_size = ftp.size(remote)
                except Exception:
                    pass
            local_exists = target.exists()
            local_size = target.stat().st_size if local_exists else None
            same_size = (
                local_exists
                and remote_size is not None
                and local_size == int(remote_size)
            )
            # Do not RETR just because LIST/SIZE is missing — verify hashes locals only.
            if mode_norm != "force" and local_exists and (same_size or remote_size is None):
                digest = ""
                if mode_norm == "verify":
                    digest = md5_file(target)
                return {
                    "remote": remote,
                    "local": str(target),
                    "size": int(remote_size) if remote_size is not None else local_size,
                    "md5": digest,
                    "skipped_ok": True,
                }
            part = target.with_name(target.name + ".part")
            digest = hashlib.md5()

            def writer(chunk: bytes) -> None:
                handle.write(chunk)
                digest.update(chunk)

            with part.open("wb") as handle:
                ftp.retrbinary(f"RETR {remote}", writer)
            local_size = part.stat().st_size
            local_hash = digest.hexdigest()
            remote_size = item.get("size")
            try:
                remote_size = ftp.size(remote)
            except Exception:
                pass
            if remote_size is not None and int(remote_size) != local_size:
                part.unlink(missing_ok=True)
                raise IntegrityError(
                    f"SIZE mismatch {remote}: local={local_size} remote={remote_size}"
                )
            # MD5 counted while streaming — second RETR would freeze the UI on 1000+ map bins
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

        with self.connect() as ftp:
            if not planned:
                emit("scanning", remote_path)
                collect(ftp, normalize_remote(remote_path), local_dir, 0)
            emit("comparing" if mode_norm != "force" else "downloading", extra={"total": len(planned)})
            for idx, item in enumerate(planned):
                if pause_check and pause_check():
                    remaining = planned[idx:]
                    paused = True
                    emit("paused", item["remote"], {"remaining": len(remaining)})
                    break
                emit("comparing" if mode_norm != "force" else "downloading", item["remote"])
                try:
                    info = fetch_one(ftp, item)
                except IntegrityError as exc:
                    remaining = planned[idx:]
                    paused = True
                    corrupt = {
                        "remote": item["remote"],
                        "local": item["local"],
                        "reason": str(exc),
                    }
                    errors.append(str(exc))
                    emit(
                        "paused",
                        item["remote"],
                        {"corrupt": corrupt, "remaining": len(remaining)},
                    )
                    break
                except Exception as exc:
                    remaining = planned[idx:]
                    paused = True
                    corrupt = {
                        "remote": item["remote"],
                        "local": item["local"],
                        "reason": str(exc),
                    }
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


def client_from_env() -> FtpClient:
    load_dotenv()
    return FtpClient(FtpConfig.from_env())
