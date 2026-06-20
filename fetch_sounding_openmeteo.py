#!/usr/bin/env python3
"""
fetch_sounding_openmeteo.py — ICON Sounding Fetcher via Open-Meteo (dev server)
================================================================================
Parallel/Verifikations-Pfad zu fetch_sounding.py: statt rohe GRIB2-Dateien vom
DWD zu laden und mit eccodes selbst zu dekodieren (Höhen-/Taupunktberechnung,
Nearest-Neighbor auf dem icosahedrischen Gitter), fragt dieses Skript die
eigene Open-Meteo-Dev-Instanz ab, die native ICON-Modelllevel (Höhe, Druck,
Temperatur, Taupunkt, Wind) bereits fertig berechnet als JSON liefert.

Erzeugt absichtlich dasselbe Ausgabeschema wie fetch_sounding.py (Dateiname mit
Suffix "_OM", damit beide Pfade nebeneinander existieren und verglichen werden
können). Keine Abhängigkeiten außer der Python-Standardbibliothek.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import parse as urlparse, request as urlrequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# Produktions-Instanz (open-meteo-dev.mah.priv.at hängt an einer kaputten
# Ingestion und blieb auf altem Modelllauf stehen, siehe Absprache mit Michael).
BASE_URL = "https://open-meteo.mah.priv.at/v1/forecast"
META_URL = "https://open-meteo.mah.priv.at/data/{dataset}/static/meta.json"

MODEL_CFG = {
    "icon-d2": {"api_model": "icon_d2", "dataset": "dwd_icon_d2", "n_levels": 65, "label": "ICON-D2"},
    "icon-eu": {"api_model": "icon_eu", "dataset": "dwd_icon_eu", "n_levels": 74, "label": "ICON-EU"},
    "icon":    {"api_model": "icon_global", "dataset": "dwd_icon", "n_levels": 120, "label": "ICON"},
}


def _get_json(url: str, timeout: int = 60) -> dict:
    with urlrequest.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def current_run(dataset: str) -> tuple[datetime, str]:
    """Liest den aktuell auf dem Server geladenen Modelllauf aus meta.json."""
    meta = _get_json(META_URL.format(dataset=dataset))
    dt = datetime.fromtimestamp(meta["last_run_initialisation_time"], tz=timezone.utc)
    return dt, f"{dt.hour:02d}"


def fetch_hourly(lat: float, lon: float, api_model: str, hourly_vars: list[str], forecast_days: int) -> dict:
    query = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(hourly_vars),
        "models": api_model,
        "wind_speed_unit": "kn",     # Server liefert Knoten direkt, keine manuelle Umrechnung nötig
        "timezone": "GMT",
        "forecast_days": forecast_days,
    }
    url = f"{BASE_URL}?{urlparse.urlencode(query)}"
    return _get_json(url, timeout=90)


def build_soundings(lat: float, lon: float, model: str, run_date: datetime, run: str,
                     steps: list[int], alias: str | None = None) -> list[dict]:
    cfg = MODEL_CFG[model]
    n_lev = cfg["n_levels"]

    hourly_vars = ["surface_pressure"]
    for n in range(1, n_lev + 1):
        hourly_vars += [f"height_agl_level{n}", f"pressure_level{n}", f"temperature_level{n}",
                         f"dew_point_level{n}", f"wind_speed_level{n}", f"wind_direction_level{n}"]

    run_start = run_date.replace(hour=int(run), minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    max_step = max(steps)
    forecast_days = max(1, ((run_start - now).days) + (max_step // 24) + 2)

    log.info(f"━━ {cfg['label']}  {run_date.strftime('%Y%m%d')}/{run}Z  ({lat}, {lon})  "
             f"{n_lev} Level, {len(steps)} Schritte, 1 Request ━━")
    data = fetch_hourly(lat, lon, cfg["api_model"], hourly_vars, forecast_days)
    H = data["hourly"]
    times = H["time"]
    elev = data.get("elevation")
    grid_lat = data.get("latitude", lat)
    grid_lon = data.get("longitude", lon)

    soundings = []
    for step in steps:
        valid_dt = run_start + timedelta(hours=step)
        target_t = valid_dt.strftime("%Y-%m-%dT%H:%M")
        try:
            idx = times.index(target_t)
        except ValueError:
            log.warning(f"  ✗  +{step:03d}h  kein Zeitschritt {target_t} in Server-Antwort")
            continue

        surface_p = H.get("surface_pressure", [None] * len(times))[idx]
        if surface_p is None:
            # Dev-Server hat aktuell nur die Modelllevel-Gruppe, keine reguläre
            # Surface-Gruppe ingestiert -> unterstes Modelllevel (~10 m AGL) als
            # Näherung für den Bodendruck verwenden.
            surface_p = H.get(f"pressure_level{n_lev}", [None] * len(times))[idx]

        levels = []
        for n in range(n_lev, 0, -1):  # Boden -> Modelltop, wie fetch_sounding.py
            T = H.get(f"temperature_level{n}", [None] * len(times))[idx]
            if T is None:
                continue
            p   = H.get(f"pressure_level{n}", [None] * len(times))[idx]
            z   = H.get(f"height_agl_level{n}", [None] * len(times))[idx]
            td  = H.get(f"dew_point_level{n}", [None] * len(times))[idx]
            spd = H.get(f"wind_speed_level{n}", [None] * len(times))[idx]
            dr  = H.get(f"wind_direction_level{n}", [None] * len(times))[idx]
            levels.append({
                "level_idx": n,
                "p_hPa":    round(p, 3) if p is not None else None,
                "z_m":      round(z, 1) if z is not None else None,
                "T_C":      round(T, 2),
                "Td_C":     round(td, 2) if td is not None else None,
                "wspd_kn":  round(spd, 1) if spd is not None else None,
                "wdir_deg": round(dr, 1) if dr is not None else None,
            })

        soundings.append({
            "model": cfg["label"],
            "source": "open-meteo-dev",
            "run_date": run_date.strftime("%Y%m%d"),
            "run_hour": run,
            "step_h": step,
            "valid_time": valid_dt.strftime("%Y-%m-%dT%H:%MZ"),
            "target_lat": lat, "target_lon": lon,
            "grid_lat": grid_lat, "grid_lon": grid_lon,
            **({"location_alias": alias} if alias else {}),
            **({"hsurf_m": round(elev, 1)} if elev is not None else {}),
            "surface_p_hPa": round(surface_p, 2) if surface_p is not None else None,
            "n_levels_loaded": len(levels),
            "levels": levels,
        })
        log.info(f"  ✓  +{step:03d}h  ({len(levels)} Level)")

    return soundings


def parse_steps(s: str) -> list[int]:
    if ":" in s:
        p = s.split(":")
        return list(range(int(p[0]), int(p[1]) + 1, int(p[2]) if len(p) > 2 else 1))
    if "," in s:
        return [int(x) for x in s.split(",")]
    return [int(s)]


def main():
    ap = argparse.ArgumentParser(description="ICON Sounding Fetcher via Open-Meteo (dev server)")
    ap.add_argument("--lat",     type=float, required=True, help="Breitengrad")
    ap.add_argument("--lon",     type=float, required=True, help="Längengrad")
    ap.add_argument("--model",   default="icon-d2", choices=list(MODEL_CFG), help="Modell")
    ap.add_argument("--run",     default=None, help="UTC Run (Default: aktueller Lauf laut meta.json)")
    ap.add_argument("--date",    default=None, help="Datum YYYYMMDD (nur zusammen mit --run)")
    ap.add_argument("--step",    default="0", help="Vorhersagestunden")
    ap.add_argument("--outdir",  default=".", help="Ausgabeverzeichnis")
    ap.add_argument("--alias",   default=None, help="Kurzname/ICAO für den Ort (optional)")
    args = ap.parse_args()

    cfg = MODEL_CFG[args.model]

    if args.run:
        run = args.run.zfill(2)
        run_date = datetime.strptime(args.date, "%Y%m%d") if args.date else datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    else:
        run_date, run = current_run(cfg["dataset"])
        run_date = run_date.replace(tzinfo=None)
        log.info(f"Aktueller Lauf laut meta.json: {run_date.strftime('%Y%m%d')}/{run}Z")

    steps = parse_steps(args.step)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    soundings = build_soundings(args.lat, args.lon, args.model, run_date, run, steps, alias=args.alias)

    if soundings:
        lat_s = f"{abs(args.lat):.2f}{'N' if args.lat >= 0 else 'S'}"
        lon_s = f"{abs(args.lon):.2f}{'E' if args.lon >= 0 else 'W'}"
        name = f"sounding_{args.model.upper()}_{run_date.strftime('%Y%m%d')}_{run}Z_{lat_s}_{lon_s}_OM.json"
        path = out_dir / name
        path.write_text(json.dumps(soundings, indent=2, ensure_ascii=False))
        log.info(f"Fertig: {len(soundings)}/{len(steps)} Profile → {name}")
    else:
        log.error("Keine Profile erstellt.")
        sys.exit(1)


if __name__ == "__main__":
    main()
