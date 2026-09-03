#!/bin/bash
# Apply a panel release tag on a Docker VPS host. Keeps .env, ./data, ./mirror.
# Usage: bash packaging/deploy_vps.sh 3.22.2
set -euo pipefail
TAG="${1:?usage: deploy_vps.sh X.Y.Z}"
cd /tmp
rm -rf "meatballs-${TAG}" "meatballs-${TAG}.tar.gz"
curl -fsSL -o "meatballs-${TAG}.tar.gz" "https://github.com/telharr/meatballs/archive/refs/tags/v${TAG}.tar.gz"
tar xzf "meatballs-${TAG}.tar.gz"
SRC="/tmp/meatballs-${TAG}"
DST=/opt/pz-panel
test -d "$SRC/panel"
test -d "$DST"
cp -a "$DST/docker-compose.yml" "$DST/docker-compose.yml.bak" || true
rsync -a --delete --exclude data --exclude backups "$SRC/panel/" "$DST/panel/"
rsync -a --delete "$SRC/tools/" "$DST/tools/"
mkdir -p "$DST/packaging"
rsync -a "$SRC/packaging/" "$DST/packaging/"
cp -a "$SRC/Dockerfile" "$DST/Dockerfile"
cp -a "$SRC/run_panel.py" "$DST/run_panel.py"
if ! grep -q './data:/data' "$DST/docker-compose.yml" 2>/dev/null; then
  cp -a "$SRC/packaging/templates/vps.docker-compose.yml" "$DST/docker-compose.yml"
fi
rm -rf "$DST/panel/data" "$DST/panel/backups"
mkdir -p "$DST/panel/data/servers" "$DST/data" "$DST/mirror"
find "$DST/data" -name update_check.json -delete 2>/dev/null || true
cd "$DST"
docker compose up -d --build
sleep 6
curl -fsS http://127.0.0.1:8000/api/health
echo
python3 -c 'import json,urllib.request; print("VERSION", json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health")).get("version"))'
