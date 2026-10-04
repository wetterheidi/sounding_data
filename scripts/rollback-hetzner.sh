#!/usr/bin/env bash
#
# Setzt https://tlogpviewer.wetterheidi.de auf den Stand vor dem letzten
# Deploy zurück (Sicherung in /apps/tlogpviewer-web.prev).
#
# Enthält die Sicherung keine index.html (also der Stand vor dem ersten
# npm-Deploy, als der Vhost noch auf den Git-Klon /apps/TLogPViewer/sounding_data
# zeigte), wird auch der nginx-Vhost auf die gesicherte Fassung zurückgestellt.
#
# Aufruf: npm run rollback

set -euo pipefail

SERVER="root@178.104.206.136"
DOMAIN="tlogpviewer.wetterheidi.de"
REMOTE_DIR="/apps/tlogpviewer-web"
VHOST="/etc/nginx/sites-available/tlogpviewer.wetterheidi.de"

ssh "$SERVER" bash -s -- "$REMOTE_DIR" "$VHOST" <<'REMOTE'
set -euo pipefail
REMOTE_DIR="$1"
VHOST="$2"

if [ ! -d "$REMOTE_DIR.prev" ]; then
    echo "Keine Sicherung $REMOTE_DIR.prev vorhanden." >&2
    exit 1
fi

echo "==> Stelle $REMOTE_DIR aus $REMOTE_DIR.prev wieder her ..."
rsync -a --delete "$REMOTE_DIR.prev/" "$REMOTE_DIR/"

if [ ! -f "$REMOTE_DIR/index.html" ] && [ -f "$VHOST.vor-npm-deploy" ]; then
    echo "==> Stelle nginx-Vhost wieder her ..."
    cp "$VHOST.vor-npm-deploy" "$VHOST"
    nginx -t
    systemctl reload nginx
fi
REMOTE

echo "==> Zurückgesetzt: https://$DOMAIN"
