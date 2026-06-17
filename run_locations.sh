#!/bin/bash
# run_locations.sh – parallelisierter Sounding-Fetcher
# Verwendung: bash run_locations.sh [modell-filter]
#   modell-filter: icon-d2 | icon-eu | icon | (leer = alle)

set -euo pipefail

MODEL_FILTER="${1:-}"
JOBS=4          # max. gleichzeitige fetch_sounding.py-Prozesse
OUTDIR="${OUTDIR:-./data}"   # überschreibbar per Umgebungsvariable (systemd: Environment=OUTDIR=...)

# ---------------------------------------------------------------------------
# index.json immer regenerieren – auch bei Fehler-Exit (set -e / Netzwerkfehler)
# ---------------------------------------------------------------------------
_generate_index() {
  python3 - <<PYEOF
import json, pathlib
out = pathlib.Path("${OUTDIR}")
files = sorted(
    f.name for f in out.iterdir()
    if f.name.startswith('sounding_') and f.name.endswith('.json')
)
(out / 'index.json').write_text(json.dumps(files, indent=2) + '\n')
print(f"  index.json: {len(files)} Dateien eingetragen")
PYEOF
}
trap _generate_index EXIT
LOCATIONS="./locations.json"

mkdir -p "$OUTDIR"

# ---------------------------------------------------------------------------
# Aufräumen: JSON-Dateien älter als 3 Tage löschen
# ---------------------------------------------------------------------------
python3 - <<EOF
import os, datetime, glob, re
data_dir = "${OUTDIR}"
limit = datetime.datetime.utcnow() - datetime.timedelta(days=3)
for f in glob.glob(os.path.join(data_dir, "*.json")):
    m = re.search(r"_(\d{8})_", f)
    if m and datetime.datetime.strptime(m.group(1), "%Y%m%d") < limit:
        os.remove(f)
        print(f"  cleanup: {f}")
EOF

# Index sofort nach Cleanup aktualisieren – gelöschte Dateien raus, bevor Downloads starten
_generate_index

# ---------------------------------------------------------------------------
# Alle aktiven Orte + Modelle aus locations.json einlesen und in eine
# flache Aufgabenliste umwandeln: "alias lat lon model step"
# ---------------------------------------------------------------------------
TASKS=$(python3 - <<EOF
import json, sys

with open("$LOCATIONS") as fh:
    locs = json.load(fh)

filter_model = "$MODEL_FILTER"

for loc in locs:
    if loc.get("enabled") is not True:
        continue
    for model, cfg in loc.get("models", {}).items():
        if filter_model and filter_model != model:
            continue
        print(loc["alias"], loc["lat"], loc["lon"], model, cfg["step"])
EOF
)

if [[ -z "$TASKS" ]]; then
    echo "Keine passenden Orte für Filter '${MODEL_FILTER:-alle}' gefunden."
    exit 0
fi

# ---------------------------------------------------------------------------
# Aufgaben parallel ausführen (max. $JOBS gleichzeitig via xargs)
# ---------------------------------------------------------------------------
echo "$TASKS" | xargs -P "$JOBS" -L 1 bash -c '
    ALIAS=$1; LAT=$2; LON=$3; MODEL=$4; STEP=$5
    echo "  → $MODEL $ALIAS ($LAT, $LON) step=$STEP"
    python3 fetch_sounding.py \
        --lat "$LAT" --lon "$LON" \
        --model "$MODEL" --step "$STEP" \
        --outdir "'"$OUTDIR"'" \
        --alias "$ALIAS" \
    && echo "  ✓ $MODEL $ALIAS fertig" \
    || echo "  ✗ $MODEL $ALIAS FEHLGESCHLAGEN" >&2
' _

echo "Alle Orte abgearbeitet."

echo "Index wird aktualisiert..."
_generate_index
# (Wird bei normalem Exit durch den trap oben nochmals aufgerufen – das ist harmlos.)