#!/usr/bin/env python3
"""MCP toolbridge for Project Zomboid dedicated server FTP sync."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from ftp_client import client_from_env, load_dotenv  # noqa: E402

try:
    from fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit(
        "fastmcp is required. Install: python -m pip install -r tools/requirements.txt"
    ) from exc

mcp = FastMCP(
    name="ftp-sync",
    instructions=(
        "FTP bridge for a Project Zomboid dedicated server. "
        "Read remote configs before editing local copies. "
        "Never overwrite .cache/Saves/ or WorldDictionary.bin without explicit user confirmation."
    ),
)


@mcp.tool()
def ftp_list_files(remote_path: str = "/") -> str:
    """List remote directory contents (recursive). Returns JSON array of entries."""
    client = client_from_env()
    entries = client.list_files(remote_path, recursive=True)
    return json.dumps(entries, indent=2)


@mcp.tool()
def ftp_list_tree(remote_path: str = "/") -> str:
    """Return a human-readable directory tree for a remote path."""
    client = client_from_env()
    return client.list_tree(remote_path)


@mcp.tool()
def ftp_read_file(remote_path: str) -> str:
    """Download and return a remote text file (INI, Lua, shell scripts, logs)."""
    client = client_from_env()
    content = client.read_file(remote_path)
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


@mcp.tool()
def ftp_upload_file(local_path: str, remote_path: str) -> str:
    """Upload a local file to the remote server. Blocks protected save/database paths."""
    client = client_from_env()
    result = client.upload_file(local_path, remote_path)
    return json.dumps(result, indent=2)


@mcp.tool()
def ftp_sync_modpack(local_dir: str, remote_dir: str) -> str:
    """Sync a local modpack directory to FTP using MD5 comparison (changed files only)."""
    client = client_from_env()
    sync = client.sync_modpack(local_dir, remote_dir)
    return json.dumps(
        {
            "uploaded": sync.uploaded,
            "skipped": sync.skipped,
            "errors": sync.errors,
            "uploaded_count": len(sync.uploaded),
            "skipped_count": len(sync.skipped),
            "error_count": len(sync.errors),
        },
        indent=2,
    )


if __name__ == "__main__":
    load_dotenv()
    mcp.run()
