# TlogP Sounding Viewer & DWD Data Fetcher

Dieses Projekt besteht aus zwei Hauptkomponenten, um meteorologische Vertikalprofile (Temps) zu laden und interaktiv zu analysieren:
1. **Data Fetcher (`fetch_sounding.py`)**: Ein Python-Skript, das hochauflösende Modelldaten (GRIB2) vom Deutschen Wetterdienst (DWD) herunterlädt und als leicht lesbares JSON speichert.
2. **HTML-Viewer (`sounding_viewer.html`)**: Ein Frontend, das diese JSON-Dateien interaktiv als Skew-T Log-P Diagramm direkt im Webbrowser darstellt.

---

## 1. Lokaler / Manueller Daten-Download (Kommandozeile)

Wenn du Spezial-Analysen (z. B. historische Daten, bestimmte Unwetterlagen oder exotische Koordinaten) erstellen möchtest, kannst du das Skript jederzeit lokal auf deinem Rechner ausführen.

### Voraussetzungen
* Python 3.11 oder neuer
* Die C-Bibliothek `eccodes` (unter Linux via `sudo apt-get install libeccodes0`, unter macOS via `brew install eccodes`).
* Python-Pakete: `pip install numpy requests eccodes`
* Python-Umgebung: `python3 -m venv ~/sounding-env`
                   `source ~/sounding-env/bin/activate`

### Nutzung
Das Python-Skript wird über das Terminal aufgerufen. Es benötigt zwingend Koordinaten und erlaubt weitreichende Anpassungen:

```bash
# Basis-Befehl (lädt ICON-EU für den aktuellen Lauf, nur Schritt 0):
python3 fetch_sounding.py --lat 48.35 --lon 11.79

# Profi-Befehl (bestimmtes Modell, Zeitreihe und Ausgabeordner):
python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-d2 --step 0:48:1 --outdir ./data
```

**Wichtige Parameter:**
* `--lat` / `--lon`: Breitengrad / Längengrad (Dezimalgrad).
* `--model`: `icon-d2`, `icon-eu` oder `icon` (Standard: `icon-eu`).
* `--step`: Vorhersagestunden. Erlaubt sind Einzelwerte (`0`), Listen (`0,12,24`) oder Bereiche (`0:48:1` = von 0 bis 48 in 1er-Schritten).
* `--date` / `--run`: Für historische Läufe (z. B. `--date 20240515 --run 12`).

---

## 2. Automatischer Cloud-Download (GitHub Actions)

Das System ist so konfiguriert, dass es täglich automatisch vordefinierte Orte berechnet und als JSON im Ordner `/data/` dieses GitHub-Repositories speichert. 

### Orte hinzufügen oder ändern
Wenn du neue Stationen (Flugplätze, Städte) für den täglichen Abruf hinzufügen möchtest, musst du **nur eine Datei bearbeiten**:
👉 **Datei:** `run_locations.sh`

1. Öffne die Datei in GitHub und bearbeite sie.
2. Füge eine neue Zeile für deinen gewünschten Ort hinzu:
   `python3 fetch_sounding.py --lat 53.55 --lon 9.99 --model icon-eu --step 0:48:3 --outdir ./data`
3. Speichere die Datei ("Commit changes"). Beim nächsten planmäßigen Lauf wird dieser Ort automatisch mitberechnet.

### Download-Zeiten (Cronjob) anpassen
Wenn du anpassen möchtest, *wann* der Server losläuft (z. B. um ICON-D2 statt ICON-EU abzugreifen), musst du den Workflow bearbeiten:
👉 **Datei:** `.github/workflows/download.yml`

Ändere die `cron`-Zeile unter `schedule:` entsprechend der UTC-Zeiten. 
*Beispiel für ICON-EU (Verfügbar ca. 3h nach Modellstart):* `cron: '15 3,9,15,21 * * *'`
*(Hinweis: Du kannst den Workflow unter dem Reiter "Actions" in GitHub jederzeit auch manuell über den Button "Run workflow" starten).*

---

## 3. Bedienung des TlogP-Viewers

Der Viewer ist eine reine HTML/JS-Datei (`sounding_viewer.html`) und benötigt keinen Webserver. Er kann einfach im Browser per Doppelklick geöffnet werden.

### Daten laden
* **Cloud:** Klicke im Menü auf **"☁️ Aktuelle Daten laden"**, um die neuesten JSON-Dateien automatisch aus diesem GitHub-Repository zu ziehen.
* **Lokal:** Klicke auf **"Lokal laden ↑"** oder ziehe eine fertige JSON-Datei per Drag & Drop in das Fenster.

### Interaktive Features
* **Navigation:** Wähle den gewünschten Ort im Dropdown-Menü oben links. Nutze den Schieberegler unten oder die Pfeiltasten (Links/Rechts), um durch die Zeit zu scrollen. Die Leertaste startet eine Animation der Zeitleiste.
* **Maus-Analyse:** Fahre mit der Maus über das Diagramm. Oben rechts in der Seitenleiste werden die exakten Werte des naheliegendsten Modell-Levels angezeigt. Ausgehend von der Mausposition berechnet das Tool dynamisch die Trockenadiabate, Feuchtadiabate und die Sättigungsmischungsverhältnislinie.
* **Zoom & Pan:** * **Mausrad:** In das Diagramm hinein- oder herauszoomen.
  * **Klicken & Ziehen:** Das herangezoomte Diagramm stufenlos verschieben.
  * **Doppelklick:** Ansicht wieder auf 100 % zurücksetzen.

---

## 4. Referenz: DWD ICON Modelle

Alle Zeiten sind in UTC (so wie es auch GitHub Actions erwartet).

### 1. ICON-D2 (Lokalmodell Deutschland/Alpen)
Das hochauflösende Modell für Konvektion und lokale Effekte.

* Modell-Läufe (UTC): Alle 3 Stunden (00, 03, 06, 09, 12, 15, 18, 21Z).
* Reale Verfügbarkeit: ca. 1,5 bis 2 Stunden nach dem Lauf. (Der 00Z-Lauf ist gegen 01:45 UTC komplett online).
* Maximale Vorhersagezeit: +48 Stunden.
* Zeitliche Auflösung: Durchgehend 1-stündig.
* Idealer GitHub Cronjob: 45 1,4,7,10,13,16,19,22 * * *

### 2. ICON-EU (Europa)
Der absolute Allrounder für die meisten Temp-Analysen.

* Modell-Läufe (UTC): Alle 6 Stunden (00, 06, 12, 18Z).
* Reale Verfügbarkeit: ca. 2,5 bis 3 Stunden nach dem Lauf. (Der 00Z-Lauf ist gegen 03:00 UTC komplett online).
* Maximale Vorhersagezeit: +120 Stunden.
* Zeitliche Auflösung: 1-stündig (bis +78h), danach 3-stündig (bis +120h).
* Idealer GitHub Cronjob: 15 3,9,15,21 * * *

### 3. ICON (Global)
Für weltweite Analysen (z.B. USA, Tropen).

* Modell-Läufe (UTC): Alle 6 Stunden (00, 06, 12, 18Z).
* Reale Verfügbarkeit: ca. 3,5 bis 4 Stunden nach dem Lauf. (Der 00Z-Lauf ist gegen 04:00 UTC komplett online).
* Maximale Vorhersagezeit: Standardmäßig +180 Stunden (Die 00Z und 12Z Läufe rechnen sogar bis +384 Stunden, für Vertikalprofile reicht aber meist weniger).
* Zeitliche Auflösung: 1-stündig (bis +78h), danach 3-stündig.
* Idealer GitHub Cronjob: 30 4,10,16,22 * * *

### Mein Tipp für das Setup (run_locations.sh)
Da du im Skript über --step exakt definieren kannst, welche Schritte geladen werden, empfehle ich dir für ICON-EU folgendes kompaktes Setup:

Wenn du z.B. für die nächsten 2 Tage (48 Stunden) eine feine 1-stündige Auflösung und danach für den Trend eine gröbere Auflösung haben willst, kannst du die --step Argumente einfach mischen!

Beispiel für deine run_locations.sh:
python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-eu --step 0:48:1,51:120:3 --outdir ./data

Das lädt:

Die ersten 48 Stunden in feinen 1-Stunden-Schritten.

Die Stunden 51 bis 120 in gröberen 3-Stunden-Schritten.

Damit hast du die perfekte Balance aus hoher Genauigkeit für die nächsten Tage, einem tollen Langzeittrend, und das Ganze läuft in den GitHub Actions extrem ressourcenschonend und schnell durch!

*(Hinweis: Die Modelle unterscheiden sich in ihrer vertikalen Auflösung. ICON-D2 liefert 65 Level, ICON-EU liefert 74 Level und das globale ICON 120 Level. Der Viewer passt seine thermodynamischen Berechnungen automatisch an das jeweilige Gitter an).*

