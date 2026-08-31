# Environment Setup

Guide to prepare a machine for Project Zomboid mod and modpack development in this repository.

## Checklist

| Step | Required | Status cue |
|------|----------|------------|
| Python 3.10+ (real install, not Windows Store stub) | Yes | `python --version` |
| Cursor / VS Code + Lua LS | Yes | Extension `sumneko.lua` |
| EditorConfig | Recommended | Extension `EditorConfig.EditorConfig` |
| luacheck | Recommended for CI parity | `luacheck --version` |
| SteamCMD | Only for Workshop pull/publish | `./steamcmd/steamcmd.exe` or `.sh` |
| Steam credentials | Only for publish | `.env` from `.env.example` |
| Product memo + session facts | Yes for panel / host / mods | `docs/PRODUCT.md`, then `docs/SESSION.md` |

### Windows: install Python

The Microsoft Store `python.exe` stub is **not** enough. Install a real build:

```powershell
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
```

Then **open a new terminal** (PATH refresh) and re-run `.\scripts\setup.ps1`.

## One-command bootstrap

**Windows (PowerShell):**

```powershell
.\scripts\setup.ps1
```

**Linux / macOS:**

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

The script creates `.cache/`, `steamcmd/`, `dist/`, copies `.env.example` → `.env`, and smoke-tests Python tools.

## Python tools

```bash
python -m pip install -r tools/requirements.txt
python tools/pack_merger.py --help
python tools/workshop_downloader.py --help
python tools/uploader.py --help
```

Scripts currently use the standard library only; `requirements.txt` is reserved for future optional packages.

## Lua Language Server

Workspace settings live in:

- `.vscode/settings.json`
- `.luarc.json`
- `definitions/pz/*.lua` (stubs for Events, IsoObjects, Traits/Perks/WorldDictionary)

Install / verify the **Lua** extension (`sumneko.lua`):

```powershell
cursor --install-extension sumneko.lua
cursor --list-extensions | Select-String lua
```

Reload the Cursor window after install.

## luacheck

On this Windows workspace luacheck is installed via LuaRocks against Lua 5.4:

```powershell
# After install, User PATH includes:
#   %LOCALAPPDATA%\Programs\Lua\bin
#   %APPDATA%\luarocks\bin
# Open a NEW terminal, then:
luacheck --version
luacheck src/mods/
```

If `luacheck` is missing in an old terminal:

```powershell
.\scripts\env.ps1
```

Reinstall manually (needs `gcc` on PATH, e.g. WinLibs):

```powershell
luarocks install luacheck
```

Config: `.luacheckrc`.

## SteamCMD

1. Download from [Valve SteamCMD wiki](https://developer.valvesoftware.com/wiki/SteamCMD).
2. Extract into `./steamcmd/` so that:
   - Windows: `steamcmd/steamcmd.exe`
   - Linux: `steamcmd/steamcmd.sh`
3. Download Workshop items:

```bash
python tools/workshop_downloader.py <workshop_id>
```

Content lands in `.cache/workshop/` (gitignored).

## Secrets

1. Copy `.env.example` to `.env`.
2. Fill `STEAM_USERNAME` / `STEAM_PASSWORD` only if you will publish.
3. For GitHub Actions, set the same names as repository secrets.

Never commit `.env`, SteamCMD installs, or password-bearing VDF files.

## Directory roles

```text
src/mods/          Your mods (add when ready to develop)
src/modpacks/      Locked merged packs + manifests
.cache/workshop/   Downloaded Workshop content
templates/mod/     Empty mod skeleton (copy, don't edit in place)
definitions/pz/    LSP stubs only — not loaded by the game
tools/             Pipeline CLIs
scripts/           Local setup helpers
```

## Cursor agents & MCP

- Rules: `.cursor/rules/pz-coder.mdc`, `.cursor/rules/steam-pipeline.mdc`
- MCP: `.cursor/mcp.json` (filesystem on `.cache` + `src/modpacks`, git on repo root)
- After changing MCP config, restart Cursor MCP servers

## Verify readiness

```powershell
.\scripts\setup.ps1
python tools/pack_merger.py
# Expect: "No mods found" until you add src/mods/<Mod>/mod.info
```

When this succeeds, the environment is ready; mod authoring can start from `templates/mod/`.
