#!/usr/bin/env bash
#
# Setzt die Server-Pipeline des TLogP-Viewers auf den Commit vor dem letzten
# npm run deploy:backend zurück (gemerkt in /apps/TLogPViewer/.backend-prev-commit)
# und übernimmt admin_api.py und systemd-Units dieses Stands.
#
# Der Klon steht danach hinter origin/main; das nächste deploy:backend zieht
# ihn wieder nach vorn.
#
# Aufruf: npm run rollback:backend

set -euo pipefail

SERVER="root@178.104.206.136"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Setze Server-Pipeline zurück ..."
ssh "$SERVER" bash -s -- rollback < "$PROJECT_DIR/scripts/backend-remote.sh"

echo "==> Zurückgesetzt."
