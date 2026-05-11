# Deploy-Anleitung: Lokale Code-Änderungen auf den Server bringen

## Architektur (Stand Mai 2026)

| Was | Wo |
|-----|----|
| Code-Repo | GitHub: `wetterheidi/sounding_data` |
| Server-Verzeichnis | `/apps/TLogPViewer/sounding_data/` |
| Datendateien | `/apps/TLogPViewer/data/` (von git ignoriert) |
| Daten-Fetching | systemd-Timer auf dem Server (`tlogp-d2eu.timer`, `tlogp-icon.timer`) |

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
