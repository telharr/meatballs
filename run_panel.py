#!/usr/bin/env python3
"""One-click launcher for the PZ Server Control Panel."""

from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}/"


def main() -> int:
    print("Starting PZ Server Control Panel…")
    print(f"  URL: {URL}")
    print("  Press Ctrl+C to stop\n")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "panel.server:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--reload",
        ],
        cwd=str(ROOT),
    )

    time.sleep(1.2)
    webbrowser.open(URL)

    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait(timeout=5)
        print("\nPanel stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
