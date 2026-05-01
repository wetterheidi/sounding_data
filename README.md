# TlogP Sounding Viewer & DWD Data Fetcher

Dieses Projekt stellt meteorologische Vertikalprofile (Temps) aus DWD-Modelldaten bereit und visualisiert sie interaktiv als Skew-T Log-P Diagramm.

**Live:** https://tlogpviewer.wetterheidi.de/
**Admin:** https://tlogpviewer.wetterheidi.de/admin.html *(Passwortgeschützt)*

---

## Architektur-Überblick

```
DWD OpenData-Server
        │
        ▼
Hetzner Server (wetterheidi-server)
  /apps/TLogPViewer/
  ├── sounding_data/     ← Git-Repo (nur Code, keine Daten)
  │   ├── fetch_sounding.py
  │   ├── run_locations.sh
  │   ├── locations.json
  │   ├── admin_api.py
  │   ├── sounding_viewer.html
  │   └── admin.html
  ├── data/              ← Generierte JSON-Dateien (von nginx ausgeliefert)
  ├── venv/              ← Python-Umgebung
  └── backups/           ← Automatische Backups von locations.json
        │
        ▼
nginx → https://tlogpviewer.wetterheidi.de/
```

**Datenpfad:**
- Zwei `systemd`-Timer starten `run_locations.sh` pünktlich zur DWD-Verfügbarkeit
- Das Skript lädt GRIB2-Dateien vom DWD, konvertiert sie in JSON und schreibt sie nach `/apps/TLogPViewer/data/`
- nginx liefert die JSON-Dateien direkt aus – kein GitHub im Datenpfad

**GitHub** wird nur noch für Code-Versionierung genutzt. Keine Wetterdaten im Repo.

---

## Orte verwalten (Admin-Oberfläche)

Öffne https://tlogpviewer.wetterheidi.de/admin.html im Browser.
- Browser fragt nach Benutzername und Passwort (nginx Basic Auth)
- Orte hinzufügen, bearbeiten, aktivieren/deaktivieren per UI
- Änderungen werden sofort in `/apps/TLogPViewer/sounding_data/locations.json` gespeichert
- Beim nächsten Timer-Lauf werden die neuen Orte automatisch heruntergeladen

Die Konfiguration pro Ort (`locations.json`):
```json
{
  "alias": "Startplatz",
  "lat": 47.981,
  "lon": 11.235,
  "enabled": true,
  "models": {
    "icon-d2": { "step": "0:24:1" }
  }
}
```

---

## Download-Zeiten (systemd-Timer)

Die Timer liegen auf dem Server unter `/etc/systemd/system/`.

| Timer | Modelle | Auslösung (UTC) | Grund |
|---|---|---|---|
| `tlogp-d2eu.timer` | ICON-D2 + ICON-EU | 02:15, 05:15, 08:15, 11:15, 14:15, 17:15, 20:15, 23:15 | DWD-Verfügbarkeit ~2h nach Laufstart |
| `tlogp-icon.timer` | ICON global | 04:15, 10:15, 16:15, 22:15 | DWD-Verfügbarkeit ~4h nach Laufstart |

Timer-Status prüfen:
```bash
systemctl list-timers tlogp*
```

Download manuell anstoßen (z.B. nach Server-Neustart):
```bash
systemctl start tlogp-d2eu.service
journalctl -u tlogp-d2eu.service -f
```

---

## Server-Wartung

### Code-Update einspielen
Nach einem `git push` vom Mac:
```bash
git -C /apps/TLogPViewer/sounding_data pull
```
Für Änderungen an `run_locations.sh`, `fetch_sounding.py` oder `locations.json` ist kein Service-Neustart nötig – sie werden beim nächsten Timer-Lauf automatisch verwendet.

Wenn `admin_api.py` geändert wurde:
```bash
systemctl restart tlogp-api.service
```

### Logs ansehen
```bash
# Download-Logs
journalctl -u tlogp-d2eu.service -n 100
journalctl -u tlogp-icon.service -n 100

# Admin-API
journalctl -u tlogp-api.service -f

# nginx
tail -f /var/log/nginx/error.log
```

### Datendateien
```bash
ls /apps/TLogPViewer/data/          # aktuelle JSON-Dateien
cat /apps/TLogPViewer/data/index.json  # Index der verfügbaren Dateien
```

Dateien älter als 3 Tage werden automatisch von `run_locations.sh` gelöscht.

---

## Fallback auf GitHub Actions

Falls der Server ausfällt oder Probleme auftreten:

**1. Viewer auf GitHub-Daten umstellen** – in `sounding_viewer.html` die zwei Zeilen tauschen:
```js
// Aktiv (Server):
const DATA_BASE = '/data';

// Auf GitHub umschalten:
// const DATA_BASE = '/data';
const DATA_BASE = 'https://raw.githubusercontent.com/wetterheidi/sounding_data/main/data';
```

**2. GitHub Actions reaktivieren** – unter https://github.com/wetterheidi/sounding_data/actions
den Workflow `TlogP Data Fetcher` über den Button "Enable workflow" reaktivieren.

---

## Lokaler / Manueller Daten-Download

Für Spezial-Analysen (historische Daten, bestimmte Lagen, exotische Koordinaten) kann `fetch_sounding.py` lokal auf dem Mac ausgeführt werden.

### Voraussetzungen
```bash
brew install eccodes
python3 -m venv ~/sounding-env
source ~/sounding-env/bin/activate
pip install numpy requests eccodes
```

### Nutzung
```bash
# Aktueller Lauf, ICON-EU, nur Schritt 0:
python3 fetch_sounding.py --lat 48.35 --lon 11.79

# ICON-D2, Zeitreihe 0–24h, stündlich, in ./data/ speichern:
python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-d2 --step 0:24:1 --outdir ./data

# Historischer Lauf (z.B. 12Z vom 15. Mai 2024):
python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-eu --date 20240515 --run 12 --step 0:48:3
```

**Parameter:**
| Parameter | Beschreibung |
|---|---|
| `--lat` / `--lon` | Koordinaten in Dezimalgrad |
| `--model` | `icon-d2`, `icon-eu` oder `icon` |
| `--step` | Vorhersagestunden: Einzelwert `0`, Liste `0,12,24` oder Bereich `0:48:1` |
| `--date` / `--run` | Für historische Läufe, z.B. `--date 20240515 --run 12` |
| `--alias` | Kurzname für die Ausgabedatei |
| `--outdir` | Ausgabeverzeichnis (Standard: `.`) |

---

## Bedienung des TlogP-Viewers

Der Viewer unter https://tlogpviewer.wetterheidi.de/ benötigt keinen lokalen Webserver.
Die HTML-Datei kann auch per Doppelklick lokal geöffnet werden (dann "Lokal laden" verwenden).

### Daten laden
- **Cloud:** Button "☁️ Aktuelle Daten laden" – lädt alle JSON-Dateien vom Server
- **Lokal:** Button "Lokal laden ↑" oder Drag & Drop einer JSON-Datei ins Fenster

### Navigation
- **Ort:** Dropdown oben links
- **Zeit:** Schieberegler unten oder Pfeiltasten Links/Rechts
- **Animation:** Leertaste startet/stoppt die Zeitleiste

### Diagramm
- **Maus:** Zeigt exakte Werte des nächsten Modell-Levels; berechnet dynamisch Trockenadiabate, Feuchtadiabate und Sättigungsmischungsverhältnislinie
- **Mausrad:** Zoom
- **Klicken & Ziehen:** Verschieben im Zoom
- **Doppelklick:** Zoom zurücksetzen

---

## Referenz: DWD ICON Modelle

Alle Zeiten in UTC.

### ICON-D2 (Lokalmodell Deutschland/Alpen)
- Läufe: alle 3h (00, 03, 06, 09, 12, 15, 18, 21Z)
- Verfügbarkeit: ~1,5–2h nach Laufstart
- Vorhersagezeitraum: bis +48h, stündliche Auflösung
- Vertikale Level: 65

### ICON-EU (Europa)
- Läufe: alle 3h (00, 03, 06, 09, 12, 15, 18, 21Z)
- Verfügbarkeit: ~2h nach Laufstart
- Vorhersagezeitraum: bis +120h (bis +78h stündlich, danach 3-stündlich)
- Vertikale Level: 74

### ICON Global
- Läufe: alle 6h (00, 06, 12, 18Z)
- Verfügbarkeit: ~4h nach Laufstart
- Vorhersagezeitraum: bis +180h (00Z/12Z bis +384h)
- Vertikale Level: 120
