#!/usr/bin/env python3
"""Frozen / dev entrypoint for PZ Control Panel (used by PyInstaller bundle)."""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path


def _resolve_root() -> Path:
    if getattr(sys, "frozen", False):
        # onedir: exe lives in dist/PZControlPanel/; _MEIPASS is _internal
        exe_dir = Path(sys.executable).resolve().parent
        os.chdir(exe_dir)
        return exe_dir
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = _resolve_root()
    tools = root / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    host = os.environ.get("PANEL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("PANEL_PORT", "8000") or "8000")
    url = f"http://{host}:{port}/"

    open_browser = os.environ.get("PANEL_OPEN_BROWSER", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if open_browser and host in ("127.0.0.1", "localhost", "::1"):
        try:
            webbrowser.open(url)
        except OSError:
            pass

    import uvicorn

    uvicorn.run(
        "panel.server:app",
        host=host,
        port=port,
        log_level=os.environ.get("PANEL_LOG_LEVEL", "info"),
        access_log=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
