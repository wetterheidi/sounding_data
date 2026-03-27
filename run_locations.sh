#!/bin/bash
# Erstelle den Ausgabeordner und leere ihn (damit wir keinen Datenmüll ansammeln)
mkdir -p ./data
rm -rf ./data/*

# Ort 1: München (MUC) - Vorhersage für 48 Stunden im 6-Stunden-Takt
python3 fetch_sounding.py --lat 48.35 --lon 11.79 --model icon-eu --step 0:48:6 --outdir ./data

# Ort 2: Frankfurt (FRA)
python3 fetch_sounding.py --lat 50.03 --lon 8.54 --model icon-eu --step 0:48:6 --outdir ./data

# Ort 3: Berlin (BER)
python3 fetch_sounding.py --lat 52.36 --lon 13.50 --model icon-eu --step 0:48:6 --outdir ./data
