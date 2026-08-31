#!/usr/bin/env python3
"""Run WinSCP scripted FTP test using credentials from .env."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from ftp_client import FtpConfig, load_dotenv  # noqa: E402


def find_winscp() -> Path:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WinSCP" / "WinSCP.com",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "WinSCP" / "WinSCP.com",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "WinSCP" / "WinSCP.com",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("WinSCP.com not found. Install WinSCP first.")


def run_test(winscp: Path, cfg: FtpConfig, *, passive: bool, protocol: str = "ftp") -> int:
    cache = ROOT / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    mode = "on" if passive else "off"
    script_path = cache / f"winscp_{protocol}_{mode}.txt"
    log_path = cache / f"winscp_{protocol}_{mode}.log"

    if protocol == "sftp":
        open_line = (
            f"open sftp://{cfg.user}@{cfg.host}:22/ "
            f"-password={cfg.password}"
        )
    else:
        open_line = (
            f"open ftp://{cfg.user}@{cfg.host}:{cfg.port}/ "
            f"-password={cfg.password} -passive={mode}"
        )

    script_path.write_text(
        "\n".join(
            [
                "option batch on",
                "option confirm off",
                open_line,
                "ls",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"\n=== {protocol.upper()} passive={passive} ===")
    result = subprocess.run(
        [str(winscp), f"/log={log_path}", "/loglevel=2", "/ini=nul", f"/script={script_path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout.strip())
    if log_path.is_file():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-6:]:
            if cfg.password and cfg.password in line:
                line = line.replace(cfg.password, "***")
            print(line)
    script_path.unlink(missing_ok=True)
    return result.returncode


def main() -> int:
    load_dotenv()
    cfg = FtpConfig.from_env()
    cfg.validate()
    winscp = find_winscp()
    print(f"Using {winscp}")
    print(f"Host: {cfg.host}:{cfg.port} user: {cfg.user}")

    codes = [
        run_test(winscp, cfg, passive=True, protocol="ftp"),
        run_test(winscp, cfg, passive=False, protocol="ftp"),
        run_test(winscp, cfg, passive=True, protocol="sftp"),
    ]
    return 0 if any(code == 0 for code in codes) else codes[0]


if __name__ == "__main__":
    raise SystemExit(main())
