# Deploy-Anleitung: Lokale Code-Änderungen auf den Server bringen

## Architektur (Stand Juli 2026, nach Pförtner-Umstellung)

| Was | Wo |
|-----|----|
| Code-Repo | GitHub: `wetterheidi/sounding_data` |
| Server-Verzeichnis (Repo-Klon) | `/apps/TLogPViewer/sounding_data/` |
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

### 2. Auf dem Server deployen

```bash
ssh root@<server-ip>
cd /apps/TLogPViewer/sounding_data
git pull --ff-only
```

Fertig.

### Sonderfall: Änderung an admin_api.py

Die API läuft aus einer Kopie in `/apps/TLogPViewer/` (damit `git pull` sie nie
im laufenden Betrieb verändert). Nach einer Änderung zusätzlich:

```bash
cp /apps/TLogPViewer/sounding_data/admin_api.py /apps/TLogPViewer/admin_api.py
systemctl restart tlogp-api.service
```

---

## Sonderfall: locations.json

`locations.json` ist weiterhin in Git — Änderungen über die Admin-Oberfläche
landen aber nur auf dem Server (nicht lokal). Wenn du `locations.json` lokal
bearbeitest UND der Server sie zwischenzeitlich per Admin-UI geändert hat,
gibt es beim `git pull` einen Konflikt.

**Empfehlung:** `locations.json` immer über die Admin-Oberfläche bearbeiten
(`https://tlogpviewer.wetterheidi.de/admin.html`), nicht lokal.

Falls doch ein Konflikt entsteht:
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
