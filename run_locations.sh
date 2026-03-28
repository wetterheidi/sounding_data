#!/bin/bash
mkdir -p ./data

# --- NEU: Intelligentes Aufräumen von Dateien, die älter als 3 Tage sind ---
python3 -c '
import os, datetime, glob, re
# Grenze: Vor 3 Tagen
limit = datetime.datetime.utcnow() - datetime.timedelta(days=3)

for f in glob.glob("./data/*.json"):
    # Suche das Datum im Dateinamen (8 Ziffern am Stück, z.B. 20260327)
    match = re.search(r"_(\d{8})_", f)
    if match:
        file_date = datetime.datetime.strptime(match.group(1), "%Y%m%d")
        if file_date < limit:
            os.remove(f)
            print(f"🧹 Alte Datei gelöscht: {f}")
'
# ---------------------------------------------------------------------------

# Ort 1: München (MUC) - Vorhersage für 48 Stunden im 6-Stunden-Takt
#python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-eu --step 0:48:6 --outdir ./data

# Ort 2: Bishop 33.113, -112.270
python3 fetch_sounding.py --lat 33.113 --lon -112.270 --model icon --step 0:6:6 --outdir ./data

# Ort 3: Startplatz 47.981, 11.235
#python3 fetch_sounding.py --lat 47.981 --lon 11.235 --model icon-d2 --step 0:24:1 --outdir ./data

# Ort 4: Muckberg
#python3 fetch_sounding.py --lat 48.710 --lon 8.784 --model icon-d2 --step 0:24:1 --outdir ./data
