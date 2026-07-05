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
import json, os, pathlib, tempfile
out = pathlib.Path("${OUTDIR}")
files = sorted(
    f.name for f in out.iterdir()
    if f.name.startswith('sounding_') and f.name.endswith('.json')
)
# Atomar schreiben (temp-file + rename): mehrere parallele Aufrufe
# (einer pro Location) dürfen sich nicht gegenseitig eine halb
# geschriebene index.json zeigen.
fd, tmp_path = tempfile.mkstemp(dir=out, prefix=".index.json.")
with os.fdopen(fd, "w") as fh:
    fh.write(json.dumps(files, indent=2) + "\n")
os.chmod(tmp_path, 0o644)  # mkstemp gibt 0600 -> sonst kann nginx nicht mehr lesen
os.replace(tmp_path, out / "index.json")
print(f"  index.json: {len(files)} Dateien eingetragen")
PYEOF
}
trap _generate_index EXIT
export OUTDIR
export -f _generate_index
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
# flache Aufgabenliste umwandeln: "alias<TAB>lat<TAB>lon<TAB>model<TAB>step"
# Tab als Trenner, damit Aliase Leerzeichen enthalten dürfen.
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
        print("\t".join(str(v) for v in (loc["alias"], loc["lat"], loc["lon"], model, cfg["step"])))
EOF
)

if [[ -z "$TASKS" ]]; then
    echo "Keine passenden Orte für Filter '${MODEL_FILTER:-alle}' gefunden."
    exit 0
fi

# ---------------------------------------------------------------------------
# Aufgaben parallel ausführen (max. $JOBS gleichzeitig via xargs)
# Jede Zeile wird NUL-terminiert als EIN Argument übergeben und erst im
# Subprozess per Tab zerlegt — xargs-Wortsplitting/Quote-Interpretation
# kann Aliase mit Leerzeichen oder Sonderzeichen so nicht mehr verschieben.
# ---------------------------------------------------------------------------
printf '%s\n' "$TASKS" | tr '\n' '\0' | xargs -0 -P "$JOBS" -n 1 bash -c '
    IFS=$(printf "\t") read -r ALIAS LAT LON MODEL STEP <<< "$1"
    echo "  → $MODEL $ALIAS ($LAT, $LON) step=$STEP  [OM]"
    python3 fetch_sounding_openmeteo.py \
        --lat "$LAT" --lon "$LON" \
        --model "$MODEL" --step "$STEP" \
        --outdir "'"$OUTDIR"'" \
        --alias "$ALIAS" \
    && echo "  ✓ $MODEL $ALIAS fertig  [OM]" \
    || echo "  ✗ $MODEL $ALIAS FEHLGESCHLAGEN  [OM]" >&2
    _generate_index

    echo "  → $MODEL $ALIAS ($LAT, $LON) step=$STEP  [opendata]"
    python3 fetch_sounding.py \
        --lat "$LAT" --lon "$LON" \
        --model "$MODEL" --step "$STEP" \
        --outdir "'"$OUTDIR"'" \
        --alias "$ALIAS" \
    && echo "  ✓ $MODEL $ALIAS fertig  [opendata]" \
    || echo "  ✗ $MODEL $ALIAS FEHLGESCHLAGEN  [opendata]" >&2
    _generate_index
' _

echo "Alle Orte abgearbeitet."

echo "Index wird aktualisiert..."
_generate_index
# (Wird bei normalem Exit durch den trap oben nochmals aufgerufen – das ist harmlos.)