# Project Zomboid Modding Workspace

A production-ready development environment for Project Zomboid standalone mods and server modpacks — with Lua tooling, conflict detection, Steam Workshop pipelines, and CI/CD.

## Quick Start (environment first)

Full machine setup: **[docs/setup.md](docs/setup.md)**.

```powershell
# Windows
.\scripts\setup.ps1
```

```bash
# Linux / macOS
./scripts/setup.sh
```

### Prerequisites

- [Cursor](https://cursor.com) or VS Code + [Lua Language Server](https://marketplace.visualstudio.com/items?itemName=sumneko.lua)
- Python 3.10+
- Optional: [SteamCMD](https://developer.valvesoftware.com/wiki/SteamCMD), [luacheck](https://github.com/lunarmodules/luacheck)

### When ready to develop mods

Copy the skeleton (do not edit `templates/` in place):

```text
templates/mod/  →  src/mods/<YourMod>/
```

Then lint / pack:

```bash
luacheck src/mods/
python tools/pack_merger.py --fail-on-conflict
python tools/workshop_downloader.py <workshop_id>
```

## Repository Layout

```text
├── .cursor/rules/             # Cursor sub-agent rules (@pz-coder, @steam-pipeline)
├── .github/workflows/         # CI/CD (lint, pack, release)
├── definitions/pz/            # Lua LSP stubs for PZ APIs
├── docs/                      # Architecture and hook guides
├── mcp/                       # MCP server integrations
├── src/
│   ├── mods/                  # Custom mods
│   └── modpacks/              # Merged server packs
└── tools/
    ├── workshop_downloader.py # SteamCMD Workshop pull
    ├── pack_merger.py         # Modpack compiler & validator
    └── uploader.py            # Workshop VDF generator & publisher
```

## Cursor Sub-Agents

| Agent | Purpose |
|-------|---------|
| `@pz-coder` | Lua code generation (multiplayer-safe, nil-checks, network commands) |
| `@steam-pipeline` | SteamCMD Workshop download and VDF publish workflows |

Invoke in Cursor chat: *"@pz-coder add a server-validated item pickup command"*

## Documentation

- [Environment Setup](docs/setup.md)
- [Architecture & Event Lifecycle](docs/architecture.md)
- [Lua API Quick Reference](docs/lua-api.md)
- [Agent Guide](AGENTS.md)
- [Tool Reference](tools/README.md)
- [Contributing & Commit Standards](CONTRIBUTING.md)

## CI/CD

Tagged releases (`v*`) trigger GitHub Actions to:
1. Run `luacheck` on all mod Lua
2. Validate modpack with `pack_merger.py`
3. Bundle `.zip` artifacts for GitHub Releases

Steam Workshop publishing uses encrypted repository secrets (`STEAM_USERNAME`, `STEAM_PASSWORD`).

## License

[MIT](LICENSE)
