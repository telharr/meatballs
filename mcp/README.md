# MCP Server Integrations

This directory holds configuration and wrappers for Model Context Protocol servers used in the PZ modding workflow.

## Configured Servers (`.cursor/mcp.json`)

| Server | Scope | Purpose |
|--------|-------|---------|
| **filesystem** | `.cache/`, `src/modpacks/` | Workshop cache and merged pack manipulation |
| **git** | Repository root | Automated release commits, branch management |

## Adding a Command-Runner MCP

For triggering test dry-runs (luacheck, pack_merger) via MCP, add a custom server:

```json
{
  "command-runner": {
    "command": "npx",
    "args": ["-y", "@your-org/mcp-command-runner"],
    "env": {
      "ALLOWED_COMMANDS": "luacheck,python"
    }
  }
}
```

## SteamCMD ops CLI (MCP-ready)

`mcp/steamcmd_ops.py` exposes named operations for wrappers / command-runners:

```bash
python mcp/steamcmd_ops.py --dry-run download 1234567890
python mcp/steamcmd_ops.py --dry-run validate --source src/mods
python mcp/steamcmd_ops.py --dry-run generate_vdf --content src/mods/MyMod --title "My Mod"
```

Without `--dry-run`, the planned command is executed. Wire this into an MCP command-runner when available.

Underlying CLIs: `tools/workshop_downloader.py`, `tools/pack_merger.py`, `tools/uploader.py`.

## FTP MCP (`ftp-sync`)

Configured in `.cursor/mcp.json` → runs `tools/ftp_mcp_server.py` (FastMCP).

Tools: `ftp_list_files`, `ftp_list_tree`, `ftp_read_file`, `ftp_upload_file`, `ftp_sync_modpack`.

Credentials: `.env` (`FTP_*`). Restart MCP after config changes.
