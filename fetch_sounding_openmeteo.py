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
import math
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


def _e_to_dewpoint_water(e_Pa: float) -> float:
    """Magnus-Inversion über Wasser, e in Pa -> Td in °C."""
    e = max(e_Pa, 0.01)
    ln_e = math.log(e / 611.2)
    return max(-99.0, min(60.0, (243.5 * ln_e) / (17.67 - ln_e)))


def _saturation_vapor_pressure_mixed_phase_Pa(T_C: float) -> float:
    """Sättigungsdampfdruck nach Murphy & Koop (2005), Mixed-Phase wie
    Meteorology.swift::specificToRelativeHumidity (ECMWF-Konvention,
    Übergang flüssig/Eis zwischen -23°C und 0.01°C). Identische Formel wie
    serverseitig zur Berechnung von relative_humidity_levelN verwendet, damit
    das aus RH zurückgerechnete e exakt zum Server-Wert passt.
    """
    T0 = 273.16
    Tice = 250.16
    T = T_C + 273.15

    ln_esi = 9.550426 - (5723.265 / T) + 3.53068 * math.log(T) - 0.00728332 * T
    esi = math.exp(ln_esi)

    term1 = 54.842763 - 6763.22 / T - 4.210 * math.log(T) + 0.000367 * T
    term2 = math.tanh(0.0415 * (T - 218.8)) * (53.878 - 1331.22 / T - 9.44523 * math.log(T) + 0.014025 * T)
    esw = math.exp(term1 + term2)

    if T <= Tice:
        f_liquid = 0.0
    elif T >= T0:
        f_liquid = 1.0
    else:
        f_liquid = ((T - Tice) / (T0 - Tice)) ** 2

    return f_liquid * esw + (1.0 - f_liquid) * esi


def humidity_to_dewpoint(qv_gkg: float | None, rh_pct: float | None,
                          T_C: float | None, p_hPa: float | None) -> float | None:
    """Taupunkt über Wasser (Magnus-Formel), primär aus specific_humidity_levelN.

    Open-Meteo liefert dew_point_levelN über Eis gesättigt (Absprache mit
    Michael); für die TEMP-Darstellung ist konventionsgemäß der Taupunkt
    über Wasser korrekt, daher hier aus specific_humidity_levelN selbst
    berechnet — identische Formel wie qv_to_dewpoint() in fetch_sounding.py,
    damit beide Pfade (opendata/OM) konsistent sind.

    specific_humidity_levelN wird von der API aber nur mit 2 Nachkommastellen
    in g/kg ausgegeben. In der Stratosphäre (qv ~ 1e-4...1e-2 g/kg) rundet
    das auf angezeigte 0.0 — genau der Dynamikbereich, den Michaels
    log-int16-Fix im OM-File eigentlich retten sollte, geht hier auf der
    JSON-Ausgabeebene wieder verloren. Fallback in diesem Fall: e aus
    relative_humidity_levelN + Temperatur rekonstruieren (RH bleibt relativ
    zur exponentiell fallenden Sättigungsfeuchte auflösungsfähig, gleiches
    Prinzip wie die log-Kompression). relative_humidity_levelN wird
    serverseitig über _saturation_vapor_pressure_mixed_phase_Pa() (Murphy &
    Koop 2005, mixed-phase) berechnet, hier exakt nachgebildet für die
    Rückrechnung auf e; e selbst ist konventionsfrei, die Td-Inversion
    danach bleibt unverändert über Wasser.
    """
    if p_hPa is None:
        return None
    if qv_gkg and qv_gkg > 1e-9:
        qv = qv_gkg / 1000.0
        eps = 0.622
        e_Pa = (qv * p_hPa * 100) / (eps + qv * (1.0 - eps))
        return _e_to_dewpoint_water(e_Pa)
    if rh_pct is not None and rh_pct > 0 and T_C is not None:
        es_Pa = _saturation_vapor_pressure_mixed_phase_Pa(T_C)
        e_Pa = (rh_pct / 100.0) * es_Pa
        return _e_to_dewpoint_water(e_Pa)
    return None


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
                         f"specific_humidity_level{n}", f"relative_humidity_level{n}",
                         f"wind_speed_level{n}", f"wind_direction_level{n}"]

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
            qv  = H.get(f"specific_humidity_level{n}", [None] * len(times))[idx]
            rh  = H.get(f"relative_humidity_level{n}", [None] * len(times))[idx]
            td  = humidity_to_dewpoint(qv, rh, T, p)
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
