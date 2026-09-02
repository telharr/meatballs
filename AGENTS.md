# Agent Guide — Project Zomboid Workspace

## Mission

Maintain this repo as a **modding framework + distribution pipeline** for Project Zomboid **and** a hosting-agnostic PZ control panel. Prefer environment, tooling, and docs work until the user asks for specific mods.

## Entry points

| Need | Go to |
|------|--------|
| **Product memo (read first)** | `docs/PRODUCT.md` |
| **Session facts (read second)** | `docs/SESSION.md` |
| Panel sprints | `docs/SPRINTS.md` |
| Local machine setup | `docs/setup.md`, `scripts/setup.ps1` / `scripts/setup.sh` |
| Game/Lua architecture | `docs/architecture.md`, `docs/lua-api.md` |
| Workshop download | `tools/workshop_downloader.py` |
| **Deployment (A/B/C)** | `docs/DEPLOYMENT.md` |
| **Packaging / installer** | `packaging/build_exe.py`, `packaging/installer.iss` |
| Conflict / merge | `tools/pack_merger.py` |
| Workshop VDF / publish | `tools/uploader.py` |
| FTP pull / push mods | `tools/ftp_manager.py`, `.cursor/rules/ftp-deploy.mdc` |
| New mod skeleton | Copy `templates/mod/` → `src/mods/<ModId>/` or `python tools/mod_catalog.py scaffold --id MyMod` |
| Mod / library catalog | `tools/mod_catalog.py`, panel **Моды**, `src/modpacks/meatballs.catalog.json` |
| FTP server mirror | `tools/server_mirror.py`, panel **Зеркало**, `.mirror/` |
| Local dedicated test | `tools/local_server.py`, set `PZ_DEDICATED_DIR` |
| Launch invites / adduser | `tools/launch_invite.py`, panel **Игроки** |
| Empty test / NPC slots | `tools/slots_ctl.py`, `src/mods/MeatballsSlots`, panel **Игроки** |
| Cursor Lua agent | `.cursor/rules/pz-coder.mdc` |
| Cursor Steam agent | `.cursor/rules/steam-pipeline.mdc` |
| Cursor FTP deploy agent | `.cursor/rules/ftp-deploy.mdc` |
| MCP | `.cursor/mcp.json`, `mcp/README.md` |
| CI | `.github/workflows/lint.yml`, `deploy.yml` |

## Do / Don't

- **Do** keep `definitions/pz/` as LSP stubs only.
- **Do** use Conventional Commits (`CONTRIBUTING.md`).
- **Don't** commit `.env`, SteamCMD binaries, or Workshop passwords.
- **Don't** put world mutations in client Lua for multiplayer mods.
- **Don't** invent a second tools layout; extend `tools/` and `docs/`.

## Verify after env changes

```text
scripts/setup.ps1   # or setup.sh
python tools/pack_merger.py --help
```
