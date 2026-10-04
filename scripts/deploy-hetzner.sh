#!/usr/bin/env bash
#
# Deployt das Web-Frontend des TLogP-Viewers nach https://tlogpviewer.wetterheidi.de
#
# - Baut dist/ (sounding_viewer.html als index.html, admin.html, om/, leaflet/)
# - Sichert vorher den aktuellen Stand nach /apps/tlogpviewer-web.prev,
#   zurück mit: npm run rollback
# - Stellt im bestehenden nginx-Vhost (mit Pfoertner-Gate, tool=tlogpviewer)
#   root auf /apps/tlogpviewer-web und den Index auf index.html um
#   (idempotent). Gate, /data/, /om/, /admin.html und /api/ bleiben unverändert.
# - Synchronisiert dist/ nach /apps/tlogpviewer-web (--delete wirkt nur dort).
#
# NICHT betroffen: /apps/TLogPViewer (Git-Klon mit Download-Skripten und
# locations.json, Daten, Admin-API). Die werden weiter per git pull
# aktualisiert, siehe deploy/PUSH-ANLEITUNG.md.
#
# Aufruf: npm run deploy   (oder direkt: bash scripts/deploy-hetzner.sh)

set -euo pipefail

SERVER="root@178.104.206.136"
DOMAIN="tlogpviewer.wetterheidi.de"
REMOTE_DIR="/apps/tlogpviewer-web"
VHOST="/etc/nginx/sites-available/tlogpviewer.wetterheidi.de"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_DIR"
npm run build

echo "==> Sichere aktuellen Stand nach $REMOTE_DIR.prev ..."
ssh "$SERVER" "mkdir -p '$REMOTE_DIR' && rsync -a --delete '$REMOTE_DIR/' '$REMOTE_DIR.prev/'"

echo "==> Prüfe nginx-Vhost ..."
ssh "$SERVER" bash -s -- "$VHOST" "$REMOTE_DIR" <<'REMOTE'
set -euo pipefail
VHOST="$1"
REMOTE_DIR="$2"

if grep -qE "^\s*root\s+$REMOTE_DIR;" "$VHOST" \
   && ! grep -qE '^\s*index\s+sounding_viewer\.html;' "$VHOST"; then
    echo "    Vhost zeigt bereits auf $REMOTE_DIR mit index.html."
else
    echo "    Stelle root auf $REMOTE_DIR und Index auf index.html um ..."
    cp "$VHOST" "$VHOST.vor-npm-deploy"
    sed -i -E \
        -e "s|^(\s*)root\s+[^;]+;|\1root $REMOTE_DIR;|" \
        -e 's/^(\s*)index\s+sounding_viewer\.html;/\1index index.html;/' \
        "$VHOST"
    if ! nginx -t; then
        echo "    nginx -t fehlgeschlagen, stelle alten Vhost wieder her." >&2
        cp "$VHOST.vor-npm-deploy" "$VHOST"
        exit 1
    fi
fi
REMOTE

echo "==> Synchronisiere dist/ nach $SERVER:$REMOTE_DIR ..."
rsync -avz --delete --exclude=.DS_Store "$PROJECT_DIR/dist/" "$SERVER:$REMOTE_DIR/"
ssh "$SERVER" chown -R www-data:www-data "$REMOTE_DIR"

# Erst jetzt neu laden: beim ersten Deploy wäre der neue root vor dem rsync
# noch leer. Ist der Vhost unverändert, schadet das Neuladen nicht.
echo "==> Lade nginx neu ..."
ssh "$SERVER" "nginx -t && systemctl reload nginx"

echo "==> Fertig: https://$DOMAIN"
