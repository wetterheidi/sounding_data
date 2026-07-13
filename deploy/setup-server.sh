#!/bin/bash
# setup-server.sh — Einmalige Einrichtung von TLogPViewer auf dem Hetzner-Server
# Ausführen als root: bash deploy/setup-server.sh
set -euo pipefail

DOMAIN="tlogpviewer.wetterheidi.de"
APP_DIR="/apps/TLogPViewer"
REPO_URL="https://github.com/wetterheidi/sounding_data.git"
# Login/Adminrechte kommen zentral vom Pförtner (verwaltung.wetterheidi.de);
# der nginx-Vhost braucht dessen Snippet: /etc/nginx/snippets/pfoertner.conf

echo "=== TLogPViewer Server-Setup ==="

# ---------------------------------------------------------------------------
# 1. Verzeichnisse
# ---------------------------------------------------------------------------
echo "[1/7] Verzeichnisse anlegen..."
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/sounding_data"

# ---------------------------------------------------------------------------
# 2. Repo klonen
# ---------------------------------------------------------------------------
echo "[2/7] Repository klonen..."
if [ -d "$APP_DIR/sounding_data/.git" ]; then
    echo "  → Repo existiert bereits, führe git pull aus."
    git -C "$APP_DIR/sounding_data" pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR/sounding_data"
fi

# ---------------------------------------------------------------------------
# 3. Python-Umgebung
# ---------------------------------------------------------------------------
echo "[3/7] Python-Umgebung einrichten..."
apt-get install -y --no-install-recommends python3-venv libeccodes0 libeccodes-dev
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet requests numpy eccodes

# ---------------------------------------------------------------------------
# 4. Berechtigungen
# ---------------------------------------------------------------------------
echo "[4/7] Berechtigungen setzen..."
chown -R www-data:www-data "$APP_DIR"

# ---------------------------------------------------------------------------
# 5. Admin-API deployen
# ---------------------------------------------------------------------------
# Die API läuft aus $APP_DIR (nicht aus dem Repo-Klon), damit git pull sie
# nie im laufenden Betrieb verändert. Login/Adminrechte übernimmt der
# Pförtner (verwaltung.wetterheidi.de) — kein htpasswd mehr nötig.
echo "[5/7] Admin-API nach $APP_DIR kopieren..."
cp "$APP_DIR/sounding_data/admin_api.py" "$APP_DIR/admin_api.py"
chown www-data:www-data "$APP_DIR/admin_api.py"

# ---------------------------------------------------------------------------
# 6. systemd-Dateien installieren
# ---------------------------------------------------------------------------
echo "[6/7] systemd-Services und Timer installieren..."
DEPLOY_DIR="$APP_DIR/sounding_data/deploy"
cp "$DEPLOY_DIR/tlogp-api.service"  /etc/systemd/system/
cp "$DEPLOY_DIR/tlogp-d2eu.service" /etc/systemd/system/
cp "$DEPLOY_DIR/tlogp-d2eu.timer"   /etc/systemd/system/
cp "$DEPLOY_DIR/tlogp-icon.service" /etc/systemd/system/
cp "$DEPLOY_DIR/tlogp-icon.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tlogp-api.service
systemctl enable --now tlogp-d2eu.timer
systemctl enable --now tlogp-icon.timer

# ---------------------------------------------------------------------------
# 7. nginx-Vhost aktivieren
# ---------------------------------------------------------------------------
echo "[7/7] nginx-Vhost aktivieren..."
cp "$DEPLOY_DIR/nginx-tlogpviewer.conf" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
nginx -t && systemctl reload nginx

echo ""
echo "=== Setup abgeschlossen ==="
echo ""
echo "Nächste Schritte:"
echo "  1. SSL einrichten:  certbot --nginx -d $DOMAIN"
echo "  2. Viewer aufrufen: https://$DOMAIN/"
echo "  3. Admin aufrufen:  https://$DOMAIN/admin.html"
echo ""
echo "Logs anzeigen:"
echo "  journalctl -u tlogp-api.service -f"
echo "  journalctl -u tlogp-d2eu.service -f"
echo "  systemctl list-timers tlogp*"
