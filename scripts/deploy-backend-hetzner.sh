#!/usr/bin/env bash
#
# Aktualisiert die Server-Pipeline des TLogP-Viewers (Download-Skripte,
# run_locations.sh, Admin-API, systemd-Units) auf den gepushten Stand von main.
#
# - Prüft lokal: Arbeitsstand sauber, auf main, main nach GitHub gepusht.
#   Der Server holt den Code von GitHub, nicht vom Mac.
# - Auf dem Server (scripts/backend-remote.sh): bisherigen Commit merken,
#   git pull --ff-only in /apps/TLogPViewer/sounding_data, dann admin_api.py
#   und systemd-Units übernehmen, wo sie sich geändert haben.
# - Zurück mit: npm run rollback:backend
#
# Das Web-Frontend gehört NICHT dazu, dafür: npm run deploy
#
# Aufruf: npm run deploy:backend

set -euo pipefail

SERVER="root@178.104.206.136"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_DIR"

echo "==> Prüfe lokalen Stand ..."
if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then
    echo "    Nicht auf main." >&2
    exit 1
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "    Nicht committete Änderungen vorhanden – erst committen und pushen." >&2
    exit 1
fi
git fetch -q origin main
LOCAL="$(git rev-parse HEAD)"
if [ "$LOCAL" != "$(git rev-parse origin/main)" ]; then
    echo "    main ist nicht auf dem Stand von origin/main – erst pushen (bzw. pullen)." >&2
    exit 1
fi
echo "    main = origin/main = $(git log -1 --oneline)"

echo "==> Aktualisiere Server-Pipeline ..."
ssh "$SERVER" bash -s -- pull "$LOCAL" < "$PROJECT_DIR/scripts/backend-remote.sh"

echo "==> Fertig."
