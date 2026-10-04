# Deploy-Anleitung: Lokale Code-Änderungen auf den Server bringen

## Architektur (Stand Oktober 2026, nach Umstellung auf npm run deploy)

| Was | Wo |
|-----|----|
| Code-Repo | GitHub: `wetterheidi/sounding_data` |
| Web-Frontend (ausgeliefert) | `/apps/tlogpviewer-web/` — per `npm run deploy` |
| Server-Verzeichnis (Repo-Klon) | `/apps/TLogPViewer/sounding_data/` — Download-Skripte, `locations.json` |
| Admin-API (laufende Kopie) | `/apps/TLogPViewer/admin_api.py` — läuft bewusst **außerhalb** des Repo-Klons |
| Backups von locations.json | `/apps/TLogPViewer/backups/` |
| Datendateien | `/apps/TLogPViewer/data/` (von git ignoriert) |
| Daten-Fetching | systemd-Timer auf dem Server (`tlogp-d2eu.timer`, `tlogp-icon.timer`) |
| Login/Adminrechte | Pförtner (`verwaltung.wetterheidi.de`) per nginx `auth_request` — kein htpasswd mehr |

`data/*.json` steht in `.gitignore` — Wetterdaten werden nie mehr committed.
Es gibt keine GitHub Action mehr. Push-Konflikte durch "Wetter-Update"-Commits
sind dauerhaft Geschichte.

---

## Normaler Workflow: Code-Änderung deployen

### 1. Lokal committen und pushen

```bash
git add <geänderte Datei(en)>
git commit -m "Kurzbeschreibung"
git push origin main
```

Kein Rebase, kein Workaround — direkter Push funktioniert jederzeit.

### 2a. Web-Frontend deployen (sounding_viewer.html, admin.html, om/, leaflet/)

Vom Mac aus, im Repo-Ordner (Node.js nötig, keine npm-Pakete):

```bash
npm run deploy     # baut dist/ und schiebt es nach /apps/tlogpviewer-web
npm run rollback   # zurück auf den Stand vor dem letzten Deploy
```

- Ausgeliefert wird der **lokale Arbeitsstand** – der Push aus Schritt 1 ist
  dafür nicht nötig, sollte aber trotzdem passieren.
- Vor jedem Deploy wird der aktuelle Stand nach `/apps/tlogpviewer-web.prev`
  gesichert; `npm run rollback` holt ihn zurück.
- `--delete` wirkt nur in `/apps/tlogpviewer-web`. Der Git-Klon unter
  `/apps/TLogPViewer` wird vom Deploy nie angefasst.

### 2b. Pipeline aktualisieren (Python-Skripte, run_locations.sh, admin_api.py, systemd-Units)

Vom Mac aus, nachdem Schritt 1 (commit + push) erledigt ist:

```bash
npm run deploy:backend     # Server-Klon per git pull --ff-only auf origin/main
npm run rollback:backend   # zurück auf den Commit vor dem letzten deploy:backend
```

- Bricht ab, wenn lokal nicht committete Änderungen da sind oder `main` nicht
  gepusht ist – der Server holt den Code von GitHub, nicht vom Mac.
- Merkt sich vor dem Pull den bisherigen Commit in
  `/apps/TLogPViewer/.backend-prev-commit` (für den Rollback).
- `admin_api.py`: Die API läuft aus einer Kopie in `/apps/TLogPViewer/` (damit
  `git pull` sie nie im laufenden Betrieb verändert). Hat sie sich geändert,
  wird die Kopie aktualisiert und `tlogp-api.service` neu gestartet.
- `deploy/*.service`, `deploy/*.timer`: geänderte Units werden nach
  `/etc/systemd/system` kopiert, danach `daemon-reload`; geänderte Timer werden
  neu gestartet. Ein laufender Download wird nicht abgebrochen.
- Der Rollback nutzt `git reset --keep`, damit die per Admin-UI geänderte
  `locations.json` stehen bleibt.
- Der nginx-Vhost wird **nicht** automatisch eingespielt (Pförtner-Block und
  Certbot-Zeilen auf dem Server sind maßgeblich), siehe README.

Was die Skripte auf dem Server tun, steht in `scripts/backend-remote.sh`.

---

## Sonderfall: locations.json

`locations.json` ist weiterhin in Git — Änderungen über die Admin-Oberfläche
landen aber nur auf dem Server (nicht lokal). Wenn du `locations.json` lokal
bearbeitest UND der Server sie zwischenzeitlich per Admin-UI geändert hat,
gibt es beim `git pull` einen Konflikt.

**Empfehlung:** `locations.json` immer über die Admin-Oberfläche bearbeiten
(`https://tlogpviewer.wetterheidi.de/admin.html`), nicht lokal.

Falls doch ein Konflikt entsteht (`npm run deploy:backend` bricht dann beim
`git pull` ab, ohne etwas zu überschreiben):
```bash
# Auf dem Server: Server-Version sichern, dann Pull, dann wiederherstellen
cp locations.json /tmp/locations_save.json
git restore locations.json
git pull --ff-only
cp /tmp/locations_save.json locations.json
```

---

## Server-Befehle auf einen Blick

```bash
# systemd-Timer-Status prüfen
systemctl list-timers tlogp*

# Logs des letzten Download-Laufs anzeigen
journalctl -u tlogp-d2eu.service -n 50
journalctl -u tlogp-icon.service -n 50

# Download manuell auslösen (ohne auf den Timer zu warten)
systemctl start tlogp-d2eu.service
systemctl start tlogp-icon.service
```
