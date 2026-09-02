#!/usr/bin/env python3
"""Build standalone PZ Control Panel bundle via PyInstaller.

Output: dist/PZControlPanel/  (onedir, recommended for FastAPI + static assets)

Usage:
  python -m pip install pyinstaller
  python packaging/build_exe.py
  python packaging/build_exe.py --clean
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = Path(__file__).resolve().parent
DIST_NAME = "PZControlPanel"
DIST_DIR = ROOT / "dist" / DIST_NAME
BUILD_DIR = ROOT / "build"
SPEC_DIR = PACKAGING / "pyinstaller-spec"


def _data_sep() -> str:
    return ";" if os.name == "nt" else ":"


def _require_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller not installed. Run: python -m pip install pyinstaller"
        ) from exc


def _copy_runtime_extras(target: Path) -> None:
    """Copy files that PyInstaller datas may miss or that should stay editable."""
    for rel in (
        ".env.example",
        "docs/DEPLOYMENT.md",
        "docs/ONBOARDING.md",
    ):
        src = ROOT / rel
        if src.is_file():
            shutil.copy2(src, target / src.name if rel.endswith(".md") else target / ".env.example")

    panel_data = target / "panel" / "data"
    panel_data.mkdir(parents=True, exist_ok=True)
    for keep in ("servers/.gitkeep",):
        src = ROOT / "panel" / "data" / keep
        if src.is_file():
            dest = panel_data / keep
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def build(*, clean: bool) -> Path:
    import os

    _require_pyinstaller()
    sep = _data_sep()

    if clean:
        for path in (DIST_DIR, BUILD_DIR, ROOT / "dist" / f"{DIST_NAME}.exe"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)

    static = ROOT / "panel" / "static"
    tools = ROOT / "tools"
    templates = ROOT / "templates"
    datas: list[str] = [
        f"{static}{sep}panel/static",
        f"{tools}{sep}tools",
    ]
    if templates.is_dir():
        datas.append(f"{templates}{sep}templates")

    hidden = [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "engineio.async_drivers.threading",
        "multipart",
        "jwt",
        "paramiko",
        "psutil",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        DIST_NAME,
        "--onedir",
        "--console",
        "--noconfirm",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(SPEC_DIR),
    ]
    for item in datas:
        cmd.extend(["--add-data", item])
    for mod in hidden:
        cmd.extend(["--hidden-import", mod])
    cmd.extend(
        [
            "--collect-submodules",
            "panel",
            str(PACKAGING / "panel_launcher.py"),
        ]
    )

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)

    if not DIST_DIR.is_dir():
        raise SystemExit(f"Expected output directory missing: {DIST_DIR}")

    _copy_runtime_extras(DIST_DIR)
    print(f"\nBuild OK → {DIST_DIR}")
    print("Run: dist/PZControlPanel/PZControlPanel.exe  (Windows)")
    print("     dist/PZControlPanel/PZControlPanel       (Linux/macOS)")
    return DIST_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PZ Control Panel standalone bundle")
    parser.add_argument("--clean", action="store_true", help="Remove previous build artifacts")
    args = parser.parse_args()
    build(clean=args.clean)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
