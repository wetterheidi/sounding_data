#!/usr/bin/env python3
"""
admin_api.py — Leichtgewichtige REST-API für die TLogP-Admin-Oberfläche.
Ersetzt die GitHub-API als Backend für admin.html.

Endpunkte:
  GET  /locations        → liefert locations.json als JSON
  POST /locations        → überschreibt locations.json (mit Backup)

Authentifizierung übernimmt nginx per Basic Auth (htpasswd).
Diese API lauscht nur auf 127.0.0.1:8765 und ist nie direkt von außen erreichbar.

Starten (manuell zum Testen):
  python3 admin_api.py

Im Betrieb läuft sie als systemd-Service (tlogp-api.service).
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

# http.server aus der Stdlib – keine externe Abhängigkeit nötig
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
LOCATIONS_FILE = Path(__file__).parent / "locations.json"
BACKUP_DIR     = Path(__file__).parent / "backups"
HOST           = "127.0.0.1"
PORT           = 8765

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
class AdminHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # stdlib-Logging unterdrücken, eigenes nutzen
        log.info("%s %s", self.address_string(), fmt % args)

    # -- CORS-Header für lokale Browser-Entwicklung --------------------------
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    # -- GET /locations -------------------------------------------------------
    def do_GET(self):
        if self.path not in ("/locations", "/locations/"):
            self._send_json(404, {"error": "Not found"})
            return
        try:
            data = LOCATIONS_FILE.read_text(encoding="utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(data.encode())
        except FileNotFoundError:
            self._send_json(404, {"error": "locations.json nicht gefunden"})

    # -- POST /locations ------------------------------------------------------
    def do_POST(self):
        if self.path not in ("/locations", "/locations/"):
            self._send_json(404, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        # Validierung: muss gültiges JSON-Array sein
        try:
            locations = json.loads(body)
            if not isinstance(locations, list):
                raise ValueError("Erwartet JSON-Array")
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"error": f"Ungültiges JSON: {exc}"})
            return

        # Backup anlegen bevor überschrieben wird
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            ts      = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup  = BACKUP_DIR / f"locations_{ts}.json"
            if LOCATIONS_FILE.exists():
                shutil.copy2(LOCATIONS_FILE, backup)
                log.info("Backup: %s", backup.name)
        except Exception as exc:
            log.warning("Backup fehlgeschlagen: %s", exc)

        # Atomar schreiben: erst in .tmp, dann umbenennen
        try:
            tmp = LOCATIONS_FILE.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(locations, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(LOCATIONS_FILE)
            log.info("locations.json gespeichert (%d Einträge)", len(locations))
        except Exception as exc:
            log.error("Schreiben fehlgeschlagen: %s", exc)
            self._send_json(500, {"error": str(exc)})
            return

        self._send_json(200, {"ok": True, "count": len(locations)})

    # -- Hilfsmethode ---------------------------------------------------------
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), AdminHandler)
    log.info("TLogP Admin-API läuft auf http://%s:%d", HOST, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Gestoppt.")
