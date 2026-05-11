# Push-Anleitung: Lokale Code-Änderungen auf den Server deployen

## Warum es ohne Vorbereitung nicht klappt

Der Server committet automatisch alle ~3 Stunden neue Wetterdaten ins Repo
und pusht sie nach GitHub. Wenn du danach lokal eine Code-Änderung machst,
hat dein lokaler Branch andere Commits als `origin/main` → Git verweigert
den Push.

---

## Schritt-für-Schritt: Code-Änderung deployen

### 1. Lokale Änderungen fertigstellen und committen

```bash
git add <geänderte Datei(en)>
git commit -m "Kurzbeschreibung der Änderung"
```

### 2. Server-Commits holen und darunter rebasen

```bash
git pull --rebase origin main
```

> Das legt deinen lokalen Commit *auf* die neuesten Server-Commits.
> Keine Merge-Commits, saubere History.

### 3. Pushen

```bash
git push origin main
```

### 4. Auf dem Server deployen

```bash
ssh <user>@<server-ip>
cd /apps/TLogPViewer/sounding_data
git pull --ff-only
```

`--ff-only` stellt sicher, dass nur Fast-Forward-Pulls erlaubt sind —
als Sicherheitsnetz, falls etwas nicht sauber rebased wurde.

---

## Kurzform (alles in einem)

```bash
git add <datei> && git commit -m "..." && git pull --rebase origin main && git push origin main
```

Danach auf dem Server:
```bash
cd /apps/TLogPViewer/sounding_data && git pull --ff-only
```

---

## Dauerhafte Lösung: Datendateien aus Git herausnehmen (empfohlen)

Das eigentliche Problem ist, dass `data/*.json` überhaupt in Git liegt.
Wetterdaten gehören nicht ins Code-Repo — sie sind temporär, groß und
erzeugen ständig Divergenz-Konflikte.

### Einmalig: .gitignore anlegen und Dateien aus Tracking entfernen

```bash
# 1. .gitignore anlegen
echo "data/*.json" >> .gitignore
echo "data/index.json" >> .gitignore

# 2. Alle data/-Dateien aus dem Git-Index entfernen (Dateien bleiben erhalten)
git rm --cached data/*.json data/index.json 2>/dev/null || true

# 3. Committen
git add .gitignore
git commit -m "git: data-Verzeichnis aus Tracking entfernen"
git push origin main
```

### Auf dem Server: Auto-Commit abschalten

Den Teil im Server-Skript entfernen, der `git add data/` + `git commit` + `git push` macht.
Nach dem Pull läuft der Server weiter — er schreibt Daten lokal, commitet sie aber
nicht mehr ins Repo.

### Ergebnis

- Kein Divergenz-Problem mehr
- Code-Änderungen können jederzeit gepusht werden
- `git log` zeigt nur noch sinnvolle Code-Commits
- Daten liegen nur lokal auf dem Server (wo sie hingehören)
