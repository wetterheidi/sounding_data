#!/bin/bash
# Erstelle den Ausgabeordner und leere ihn (damit wir keinen Datenmüll ansammeln)
mkdir -p ./data
rm -rf ./data/*

# Ort 1: München (MUC) - Vorhersage für 48 Stunden im 6-Stunden-Takt
python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-eu --step 0:48:6 --outdir ./data

# Ort 2: Bishop 33.113, -112.270
# python3 fetch_sounding.py --lat 33.113 --lon -112.270 --model icon --step 0:24:3 --outdir ./data

# Ort 3: Startplatz 47.981, 11.235
python3 fetch_sounding.py --lat 47.981 --lon 11.235 --model icon-d2 --step 0:24:1 --outdir ./data

# Ort 4: Muckberg
python3 fetch_sounding.py --lat 48.710 --lon 8.784 --model icon-d2 --step 0:24:1 --outdir ./data
