# PZ Modpack Tools

Python utilities for Workshop download, modpack merging, and Steam publishing.

## Requirements

- Python 3.10+
- SteamCMD installed to `./steamcmd/` (or pass `--steamcmd`)

## workshop_downloader.py

Download Workshop mods by ID:

```bash
python tools/workshop_downloader.py 1234567890 9876543210
python tools/workshop_downloader.py 1234567890 --output .cache/workshop --username myuser
```

## pack_merger.py

Scan, validate, and merge mods into a locked modpack:

```bash
python tools/pack_merger.py --source src/mods --source .cache/workshop --output src/modpacks/my-pack
python tools/pack_merger.py --fail-on-conflict
```

Detects:
- Duplicate `mod.info` IDs
- Tiledef number collisions (runtime texture/entity registration errors)

## uploader.py

Generate and publish Workshop VDF:

```bash
python tools/uploader.py generate --content src/mods/MyMod --title "My Mod" --description "..."
python tools/uploader.py publish --vdf workshop.vdf --username myuser
# Requires STEAM_PASSWORD environment variable
```

## FTP sync (dedicated server)

Configure `.env` (`FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_REMOTE_DIR`, `FTP_REMOTE_MODS_DIR`).

```bash
python tools/ftp_manager.py list / --tree
python tools/ftp_manager.py pull-configs
python tools/ftp_manager.py push-mods --pack my-server-pack
python tools/ftp_manager.py read /mods/SomeMod/mod.info
```

## Mod catalog

```bash
python tools/mod_catalog.py list
python tools/mod_catalog.py add --id tsarslib --kind library --workshop-id 2392709985
python tools/mod_catalog.py scaffold --id MeatballsCore --name "MEATBALLS Core"
python tools/mod_catalog.py download 2392709985
```

Catalog file: `src/modpacks/meatballs.catalog.json` (committed). Workshop binaries stay in `.cache/workshop/`.

## Server FTP mirror + local test

Pulls `/ServerWorld` into `.mirror/` (skips `java` / `media` / `steamapps`).

```bash
python tools/server_mirror.py pull
python tools/local_server.py status
# Set PZ_DEDICATED_DIR in .env, then:
python tools/local_server.py start
```

Local start uses `-cachedir` on the mirrored `Server/` + `Saves/` tree. Do not use this process as the public server.

MCP server (`ftp-sync` in `.cursor/mcp.json`): `tools/ftp_mcp_server.py` exposes
`ftp_list_files`, `ftp_read_file`, `ftp_upload_file`, `ftp_sync_modpack`.

Protected remote paths: `.cache/Saves/`, `WorldDictionary.bin` (blocked unless overridden).

