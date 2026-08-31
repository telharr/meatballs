#!/usr/bin/env bash
# Bootstrap local Project Zomboid modding workspace (Linux/macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== PZ workspace setup =="
echo "Root: $ROOT"

for d in .cache/workshop .cache/steamcmd_logs src/mods src/modpacks steamcmd dist; do
  mkdir -p "$d"
  echo "  ok      $d"
done

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "  created .env from .env.example"
fi

echo ""
echo "-- Python --"
if command -v python3 >/dev/null 2>&1; then
  python3 --version
  python3 -m pip install -r tools/requirements.txt --quiet
  echo "  tools/requirements.txt applied"
else
  echo "  Python 3 not found on PATH" >&2
fi

echo ""
echo "-- Optional tools --"
for cmd in luacheck steamcmd; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "  found $cmd -> $(command -v "$cmd")"
  else
    echo "  missing $cmd (optional for now)"
  fi
done

if [[ -x steamcmd/steamcmd.sh ]]; then
  echo "  found local SteamCMD: steamcmd/steamcmd.sh"
else
  echo "  SteamCMD not in ./steamcmd/ — see https://developer.valvesoftware.com/wiki/SteamCMD"
fi

echo ""
echo "-- Smoke checks --"
python3 tools/pack_merger.py --help >/dev/null && echo "  pack_merger.py OK"
python3 tools/uploader.py --help >/dev/null && echo "  uploader.py OK"
python3 tools/workshop_downloader.py --help >/dev/null && echo "  workshop_downloader.py OK"

echo ""
echo "Next:"
echo "  1. Install Lua Language Server (sumneko.lua)"
echo "  2. Optional: luarocks install luacheck"
echo "  3. Optional: extract SteamCMD into ./steamcmd/"
echo "  4. See docs/setup.md"
echo "Done."
