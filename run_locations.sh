#!/bin/bash
mkdir -p ./data

# Optionaler Modell-Filter: icon-d2, icon-eu, icon (leer = alle)
MODEL_FILTER="${1:-}"

# Hilfsfunktion: gibt 0 (ausführen) zurück, wenn Modell zum Filter passt
run_model() {
  [[ -z "$MODEL_FILTER" || "$MODEL_FILTER" == "$1" ]]
}

# --- Intelligentes Aufräumen von Dateien, die älter als 3 Tage sind ---
python3 -c '
import os, datetime, glob, re
limit = datetime.datetime.utcnow() - datetime.timedelta(days=3)
for f in glob.glob("./data/*.json"):
    match = re.search(r"_(\d{8})_", f)
    if match:
        file_date = datetime.datetime.strptime(match.group(1), "%Y%m%d")
        if file_date < limit:
            os.remove(f)
            print(f"🧹 Alte Datei gelöscht: {f}")
'
# ---------------------------------------------------------------------------

# === ICON-D2 (3-stündlich) ===
if run_model "icon-d2"; then
  # Ort: Startplatz
  python3 fetch_sounding.py --lat 47.981 --lon 11.235 --model icon-d2 --step 0:24:1 --outdir ./data --alias Startplatz

  # Ort: Muckberg
  python3 fetch_sounding.py --lat 48.710 --lon 8.784 --model icon-d2 --step 0:24:1 --outdir ./data --alias Muckberg
fi

# === ICON-EU (3-stündlich) ===
if run_model "icon-eu"; then
  # Ort: München
  # python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-eu --step 0:48:6 --outdir ./data --alias EDDM
  :
fi

# === ICON Global (6-stündlich) ===
if run_model "icon"; then
  # Ort: Phoenix
  # python3 fetch_sounding.py --lat 33.113 --lon -112.270 --model icon --step 0:24:6 --outdir ./data --alias KPHX

  # Ort: Karibik (CAPE Test)
  # python3 fetch_sounding.py --lat 18.036 --lon -72.150 --model icon --step 0:6:6 --outdir ./data
  :
fi
