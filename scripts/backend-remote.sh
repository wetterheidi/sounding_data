#!/usr/bin/env bash
#
# Läuft AUF DEM SERVER (per ssh ... bash -s), aufgerufen von
# deploy-backend-hetzner.sh und rollback-backend-hetzner.sh.
#
#   pull <commit>   Klon per git pull --ff-only aktualisieren; vorher den
#                   aktuellen Commit nach $APP_DIR/.backend-prev-commit merken.
#                   Danach muss HEAD == <commit> sein (= lokal gepushter Stand).
#   rollback        Klon auf den gemerkten Commit zurücksetzen.
#
# In beiden Fällen danach: admin_api.py und systemd-Units aus dem Klon
# übernehmen, aber nur, wenn sie sich unterscheiden. Laufende Downloads werden
# nicht unterbrochen; geänderte Skripte greifen beim nächsten Timer-Lauf.
#
# git reset --keep (statt --hard) lässt die per Admin-UI geänderte
# locations.json stehen; würde der Rollback sie überschreiben, bricht er ab.

set -euo pipefail

APP_DIR="/apps/TLogPViewer"
REPO="$APP_DIR/sounding_data"
PREV_FILE="$APP_DIR/.backend-prev-commit"
UNIT_DIR="/etc/systemd/system"

MODE="$1"
cd "$REPO"

case "$MODE" in
pull)
    EXPECTED="$2"
    git rev-parse HEAD > "$PREV_FILE"
    echo "    Bisheriger Stand: $(git log -1 --oneline) (gemerkt für Rollback)"
    git pull --ff-only
    if [ "$(git rev-parse HEAD)" != "$EXPECTED" ]; then
        echo "    Server steht auf $(git rev-parse --short HEAD), erwartet ${EXPECTED:0:7}." >&2
        exit 1
    fi
    ;;
rollback)
    if [ ! -s "$PREV_FILE" ]; then
        echo "    Kein gemerkter Stand in $PREV_FILE." >&2
        exit 1
    fi
    PREV="$(cat "$PREV_FILE")"
    echo "    Setze Klon von $(git log -1 --oneline) zurück auf $(git log -1 --oneline "$PREV") ..."
    git reset --keep "$PREV"
    ;;
*)
    echo "Unbekannter Modus: $MODE" >&2
    exit 1
    ;;
esac
echo "    Klon steht auf: $(git log -1 --oneline)"

# --- Admin-API ---------------------------------------------------------------
API_CHANGED=0
if ! cmp -s admin_api.py "$APP_DIR/admin_api.py"; then
    echo "    admin_api.py geändert, aktualisiere Kopie ..."
    cp admin_api.py "$APP_DIR/admin_api.py"
    chown www-data:www-data "$APP_DIR/admin_api.py"
    API_CHANGED=1
fi

# --- systemd-Units -----------------------------------------------------------
CHANGED_UNITS=()
for f in deploy/*.service deploy/*.timer; do
    name="$(basename "$f")"
    if ! cmp -s "$f" "$UNIT_DIR/$name"; then
        echo "    $name geändert, kopiere nach $UNIT_DIR ..."
        cp "$f" "$UNIT_DIR/$name"
        CHANGED_UNITS+=("$name")
    fi
done

if [ ${#CHANGED_UNITS[@]} -gt 0 ]; then
    systemctl daemon-reload
    for name in "${CHANGED_UNITS[@]}"; do
        case "$name" in
            tlogp-api.service) API_CHANGED=1 ;;
            # Timer neu starten, damit ein geänderter OnCalendar gilt. Ein
            # gerade laufender Download wird dadurch nicht abgebrochen.
            *.timer) systemctl restart "$name" ;;
        esac
    done
fi

if [ "$API_CHANGED" = 1 ]; then
    systemctl restart tlogp-api.service
    echo "    tlogp-api.service neu gestartet."
fi

if [ "$API_CHANGED" = 0 ] && [ ${#CHANGED_UNITS[@]} -eq 0 ]; then
    echo "    admin_api.py und systemd-Units unverändert."
fi
