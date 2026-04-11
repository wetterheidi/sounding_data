#!/usr/bin/env python3
"""
fetch_sounding.py  —  ICON Hybrid-Level Sounding Fetcher (Korrigiert)
=========================================================
"""

import argparse
import bz2
import json
import logging
import math
import sys
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import eccodes
except ImportError:
    print("FEHLER: eccodes nicht gefunden.")
    sys.exit(1)

try:
    import numpy as np
    import requests
except ImportError as e:
    print(f"FEHLER: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modell-Konfigurationen (Parameter 'p' hinzugefügt!)
# ---------------------------------------------------------------------------
MODEL_CFG = {
    "icon-d2": {
        "url_base":    "https://opendata.dwd.de/weather/nwp/icon-d2/grib",
        "scope":       "germany",
        "gridtype":    "icosahedral",
        "n_levels":    65,
        "runs":        ["00", "03", "06", "09", "12", "15", "18", "21"],
        "max_step":    48,
        "params":      ["t", "qv", "u", "v", "p"],
        "ps_param":    "ps",
        "var_case":    "lower",      # Dateinamen: kleingeschrieben (t, ps)
        "sl_level":    "2d",         # Single-Level-Dateien haben Extra-Feld "2d"
        "lag_h":       2,            # DWD stellt Daten ~2h nach Laufstart bereit
    },
    "icon-eu": {
        "url_base":    "https://opendata.dwd.de/weather/nwp/icon-eu/grib",
        "scope":       "europe",
        "gridtype":    "regular-lat-lon",
        "n_levels":    74,
        "runs":        ["00", "03", "06", "09", "12", "15", "18", "21"],
        "max_step":    120,
        "params":      ["t", "qv", "u", "v", "p"],
        "ps_param":    "ps",
        "var_case":    "upper",      # Dateinamen: großgeschrieben (T, PS)
        "sl_level":    None,
        "lag_h":       2,            # DWD stellt Daten ~2h nach Laufstart bereit
    },
    "icon": {
        "url_base":    "https://opendata.dwd.de/weather/nwp/icon/grib",
        "scope":       "global",
        "gridtype":    "icosahedral",
        "n_levels":    120,
        "runs":        ["00", "06", "12", "18"],
        "max_step":    180,
        "params":      ["t", "qv", "u", "v", "p"],
        "ps_param":    "ps",
        "var_case":    "upper",      # Dateinamen: großgeschrieben (T, PS)
        "sl_level":    None,
        "lag_h":       4,            # DWD stellt Daten ~4h nach Laufstart bereit
    }
}

def _var_filename(param: str, cfg: dict) -> str:
    """Variablenname im Dateinamen: je nach Modell groß oder klein."""
    return param.upper() if cfg["var_case"] == "upper" else param.lower()

def model_level_url(model: str, run: str, run_date: datetime, step: int, level: int, param: str) -> str:
    cfg  = MODEL_CFG[model]
    date = run_date.strftime("%Y%m%d") + run
    vn   = _var_filename(param, cfg)
    fn   = f"{model}_{cfg['scope']}_{cfg['gridtype']}_model-level_{date}_{step:03d}_{level}_{vn}.grib2.bz2"
    return f"{cfg['url_base']}/{run}/{param}/{fn}"

def surface_url(model: str, run: str, run_date: datetime, step: int) -> str:
    cfg   = MODEL_CFG[model]
    date  = run_date.strftime("%Y%m%d") + run
    param = cfg["ps_param"]
    vn    = _var_filename(param, cfg)
    sl    = cfg.get("sl_level")
    if sl:
        fn = f"{model}_{cfg['scope']}_{cfg['gridtype']}_single-level_{date}_{step:03d}_{sl}_{vn}.grib2.bz2"
    else:
        fn = f"{model}_{cfg['scope']}_{cfg['gridtype']}_single-level_{date}_{step:03d}_{vn}.grib2.bz2"
    return f"{cfg['url_base']}/{run}/{param}/{fn}"

# ---------------------------------------------------------------------------
# Nearest-Neighbor für unstrukturierte Gitter (ICON, ICON-D2)
# ---------------------------------------------------------------------------
# Cache: model → (lats_array, lons_array)
_grid_coords: dict[str, tuple[np.ndarray, np.ndarray]] = {}
# Cache: (model, lat, lon) → flat_idx
_nn_cache: dict[tuple, int] = {}

def _clat_clon_url(model: str, run: str, run_date: datetime) -> tuple[str, str]:
    """URLs für CLAT/CLON time-invariant Gitter-Dateien."""
    cfg  = MODEL_CFG[model]
    base = cfg["url_base"]
    date = run_date.strftime("%Y%m%d") + run
    if model == "icon-d2":
        clat = f"{base}/{run}/clat/{model}_{cfg['scope']}_icosahedral_time-invariant_{date}_000_0_clat.grib2.bz2"
        clon = f"{base}/{run}/clon/{model}_{cfg['scope']}_icosahedral_time-invariant_{date}_000_0_clon.grib2.bz2"
    else:  # icon global
        clat = f"{base}/{run}/clat/{model}_{cfg['scope']}_icosahedral_time-invariant_{date}_CLAT.grib2.bz2"
        clon = f"{base}/{run}/clon/{model}_{cfg['scope']}_icosahedral_time-invariant_{date}_CLON.grib2.bz2"
    return clat, clon

def _extract_all_values(url: str, timeout: int = 60) -> np.ndarray | None:
    """Alle Werte aus einer GRIB-Datei als numpy-Array."""
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            raw = bz2.decompress(r.content)
            break
        except requests.RequestException:
            if attempt < 2:
                time.sleep(1 + attempt * 2)
                continue
            return None
    else:
        return None

    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as fh:
            gid = eccodes.codes_grib_new_from_file(fh)
        if not gid:
            return None
        vals = np.array(eccodes.codes_get_values(gid))
        eccodes.codes_release(gid)
        return vals
    finally:
        Path(tmp_path).unlink(missing_ok=True)

def _load_grid(model: str, run: str, run_date: datetime) -> bool:
    """CLAT/CLON laden und im Cache speichern."""
    if model in _grid_coords:
        return True
    clat_url, clon_url = _clat_clon_url(model, run, run_date)
    log.info(f"  Lade Gitter-Koordinaten für {model.upper()} …")
    lats = _extract_all_values(clat_url)
    lons = _extract_all_values(clon_url)
    if lats is None or lons is None:
        log.error(f"  CLAT/CLON nicht abrufbar für {model.upper()}")
        return False
    # CLAT/CLON sind bereits in Grad
    _grid_coords[model] = (lats, lons)
    log.info(f"  Gitter geladen: {len(lats)} Punkte")
    return True

def _nearest_index(model: str, lat: float, lon: float) -> int | None:
    """Nächster Gitterpunkt per Haversine-Distanz."""
    cache_key = (model, round(lat, 4), round(lon, 4))
    if cache_key in _nn_cache:
        return _nn_cache[cache_key]
    if model not in _grid_coords:
        return None
    grid_lats, grid_lons = _grid_coords[model]
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    lats_r = np.radians(grid_lats)
    lons_r = np.radians(grid_lons)
    dlat = lats_r - lat_r
    dlon = lons_r - lon_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat_r) * np.cos(lats_r) * np.sin(dlon / 2) ** 2
    idx = int(np.argmin(a))
    _nn_cache[cache_key] = idx
    return idx

def fetch_and_extract(url: str, lat: float, lon: float, model: str = "icon-eu", timeout: int = 45) -> float | None:
    # 4 Versuche für den Download mit "Exponential Backoff" (Wartezeit)
    raw_grib = None
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 404: 
                return None # Datei existiert wirklich nicht
            
            # Bei Rate-Limiting (429) oder Server-Überlastung (5xx) kurz warten und neu versuchen
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1 + attempt * 2)
                continue
                
            r.raise_for_status()
            raw_grib = bz2.decompress(r.content)
            break # Download erfolgreich, Schleife abbrechen
            
        except requests.RequestException:
            if attempt < 3:
                time.sleep(1 + attempt * 2)
                continue
            return None # Nach 4 Versuchen endgültig aufgeben

    # Wenn nach allen Versuchen nichts da ist
    if raw_grib is None:
        return None

    value = None
    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as tmp:
        tmp.write(raw_grib)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as fh:
            gid = eccodes.codes_grib_new_from_file(fh)
        if gid:
            grid_type = eccodes.codes_get_string(gid, "gridType")
            values = eccodes.codes_get_values(gid)

            if grid_type in ("regular_ll", "regular_gg"):
                # Regular grid: einfache Index-Berechnung
                lat_first = eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees")
                lon_first = eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees")
                lat_last  = eccodes.codes_get(gid, "latitudeOfLastGridPointInDegrees")
                lon_last  = eccodes.codes_get(gid, "longitudeOfLastGridPointInDegrees")
                n_lat     = eccodes.codes_get(gid, "Nj")
                n_lon     = eccodes.codes_get(gid, "Ni")
                dlat = (lat_last - lat_first) / (n_lat - 1)
                lon_last_adj = lon_last if lon_last >= lon_first else lon_last + 360.0
                dlon = (lon_last_adj - lon_first) / (n_lon - 1)
                lon_q = lon
                while lon_q < lon_first: lon_q += 360.0
                while lon_q >= lon_first + 360.0: lon_q -= 360.0
                i_lat = max(0, min(int(round((lat - lat_first) / dlat)), n_lat - 1))
                i_lon = max(0, min(int(round((lon_q - lon_first) / dlon)), n_lon - 1))
                flat_idx = i_lat * n_lon + i_lon
            else:
                # Unstrukturiertes Gitter (icosahedral etc.): Nearest-Neighbor
                flat_idx = _nearest_index(model, lat, lon)

            if flat_idx is not None and flat_idx < len(values):
                v = float(values[flat_idx])
                value = v if math.isfinite(v) else None
            eccodes.codes_release(gid)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return value

def qv_to_dewpoint(qv: float | None, p_pa: float) -> float | None:
    if not qv or qv <= 1e-9: return None 
    eps  = 0.622
    e    = max((qv * p_pa) / (eps + qv * (1.0 - eps)), 0.01)
    ln_e = math.log(e / 611.2)
    return max(-99.0, min(60.0, (243.5 * ln_e) / (17.67 - ln_e)))

def geopotential_heights_ground_first(p_pa: list[float], T_K: list[float], ps_pa: float, zs: float = 0.0) -> list[float]:
    R_d, g = 287.058, 9.80665
    n = len(p_pa)
    z = [0.0] * n
    p_prev = ps_pa
    z_prev = zs
    for i in range(n):
        p_c = p_pa[i]
        T   = T_K[i] if (T_K[i] and T_K[i] > 100) else 255.0
        if 0 < p_c < p_prev:
            z_prev += (R_d * T / g) * math.log(p_prev / p_c)
        z[i]   = z_prev
        p_prev = p_c
    return z

def fetch_sounding(lat: float, lon: float, model: str, run: str, run_date: datetime, step: int, jobs: int = 20, alias: str | None = None) -> dict | None:
    cfg   = MODEL_CFG[model]
    n_lev = cfg["n_levels"]
    n_par = len(cfg["params"])

    log.info(f"━━ {model.upper()}  {run_date.strftime('%Y%m%d')}/{run}Z  +{step:03d}h  ({lat}, {lon})  {n_lev} Level × {n_par} Parameter = {n_lev * n_par + 1} Downloads ━━")

    # Für unstrukturierte Gitter: Koordinaten einmalig laden
    if cfg["gridtype"] != "regular-lat-lon":
        if not _load_grid(model, run, run_date):
            return None

    ps_url = surface_url(model, run, run_date, step)
    ps_pa  = fetch_and_extract(ps_url, lat, lon, model=model)

    if ps_pa is None:
        log.error("Oberflächendruck nicht abrufbar.")
        return None

    log.info(f"  PS = {ps_pa / 100:.1f} hPa")

    tasks = {
        (p, lv): model_level_url(model, run, run_date, step, lv, p)
        for p in cfg["params"] for lv in range(1, n_lev + 1)
    }
    n_total = len(tasks)
    raw, n_done, n_fail = {}, 0, 0

    log.info(f"  Starte {n_total} parallele Downloads (jobs={jobs}) …")

    def _fetch(item):
        (param, lev), url = item
        return (param, lev), fetch_and_extract(url, lat, lon, model=model)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futs = {pool.submit(_fetch, item): item for item in tasks.items()}
        for fut in as_completed(futs):
            (param, lev), val = fut.result()
            n_done += 1
            if val is not None: raw[(param, lev)] = val
            else: n_fail += 1
            if n_done % 60 == 0 or n_done == n_total:
                log.info(f"  {n_done}/{n_total}  ({n_fail} fehlgeschlagen)")

    # Exaktes Druckprofil über den mitgeladenen Parameter 'p'
    p_toa = []
    for i in range(n_lev):
        li_t = n_lev - i  # 60, 59 ... 1
        p_val = raw.get(("p", li_t))
        if p_val is None: # Sicherheits-Fallback
            p_val = ps_pa * math.exp(-i / n_lev * math.log(ps_pa / 1000.0))
        p_toa.append(p_val)

    T_K_toa = [raw.get(("t", n_lev - i), 255.0) or 255.0 for i in range(n_lev)]
    z_toa   = geopotential_heights_ground_first(p_toa, T_K_toa, ps_pa)

    levels = []
    for i in range(n_lev):
        li_t = n_lev - i  # Echtes GRIB-Level (60 = Boden)
        T   = raw.get(("t",  li_t))
        qv  = raw.get(("qv", li_t))
        u   = raw.get(("u",  li_t))
        v   = raw.get(("v",  li_t))

        if T is None: continue

        spd = dir = None
        if u is not None and v is not None:
            spd = math.sqrt(u * u + v * v) * 1.94384
            dir = (270.0 - math.degrees(math.atan2(v, u))) % 360.0

        # Taupunkt berechnen und prüfen, ob er None ist
        td_val = qv_to_dewpoint(qv, p_toa[i])

        levels.append({
            "level_idx": li_t,
            "p_hPa":    round(p_toa[i] / 100.0, 3),
            "z_m":      round(z_toa[i], 1),
            "T_C":      round(T - 273.15, 2),
            "Td_C":     round(td_val, 2) if td_val is not None else None, # <--- Sauberer Null-Wert
            "wspd_kn":  round(spd, 1) if spd is not None else None,
            "wdir_deg": round(dir, 1) if dir is not None else None,
        })

    valid_dt = run_date.replace(hour=int(run), tzinfo=timezone.utc) + timedelta(hours=step)
    sounding = {
        "model": "ICON-EU" if model == "icon-eu" else model.upper(),
        "run_date": run_date.strftime("%Y%m%d"),
        "run_hour": run,
        "step_h": step,
        "valid_time": valid_dt.strftime("%Y-%m-%dT%H:%MZ"),
        "target_lat": lat, "target_lon": lon,
        "grid_lat": lat, "grid_lon": lon,
        **({"location_alias": alias} if alias else {}),
        "surface_p_hPa": round(ps_pa / 100.0, 2),
        "n_levels_loaded": len(levels),
        "levels": levels,
    }

    log.info(f"  ✓  +{step:03d}h  ({len(levels)} Level)")
    return sounding

def latest_run(model: str, lag_h: int | None = None) -> tuple[datetime, str]:
    cfg = MODEL_CFG[model]
    # Modellspezifischen Lag aus der Konfiguration verwenden, falls kein Override übergeben
    effective_lag = lag_h if lag_h is not None else cfg["lag_h"]
    now = datetime.now(timezone.utc)

    # 1. Sammle alle potenziellen Läufe von heute und gestern
    candidates = []
    for r in cfg["runs"]:
        dt_today = now.replace(hour=int(r), minute=0, second=0, microsecond=0)
        candidates.append((dt_today, r))
        candidates.append((dt_today - timedelta(days=1), r))

    # 2. Chronologisch absteigend sortieren (neuester zuerst)
    candidates.sort(key=lambda x: x[0], reverse=True)

    # 3. Den neuesten Lauf finden, der das modellspezifische Delay erfüllt
    for dt, r in candidates:
        if (now - dt).total_seconds() / 3600 >= effective_lag:
            return dt.replace(tzinfo=None), r

    fallback_dt, fallback_r = candidates[-1]
    return fallback_dt.replace(tzinfo=None), fallback_r
    
def parse_steps(s: str) -> list[int]:
    if ":" in s:
        p = s.split(":")
        return list(range(int(p[0]), int(p[1]) + 1, int(p[2]) if len(p) > 2 else 1))
    if "," in s: return [int(x) for x in s.split(",")]
    return [int(s)]

def main():
    ap = argparse.ArgumentParser(description="ICON Hybrid-Level Sounding Fetcher")
    ap.add_argument("--lat",     type=float, required=True, help="Breitengrad")
    ap.add_argument("--lon",     type=float, required=True, help="Längengrad")
    ap.add_argument("--model",   default="icon-eu", choices=list(MODEL_CFG), help="Modell")
    ap.add_argument("--run",     default=None, help="UTC Run")
    ap.add_argument("--date",    default=None, help="Datum YYYYMMDD")
    ap.add_argument("--step",    default="0", help="Vorhersagestunden")
    ap.add_argument("--outdir",  default=".", help="Ausgabeverzeichnis")
    ap.add_argument("--jobs",    type=int, default=30, help="Downloads parallel")
    ap.add_argument("--alias",   default=None, help="Kurzname/ICAO für den Ort (optional, z.B. ETHA)")
    args = ap.parse_args()

    run_date_arg = datetime.strptime(args.date, "%Y%m%d") if args.date else None
    if args.run:
        run = args.run.zfill(2)
        run_date = run_date_arg or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    else:
        auto_date, run = latest_run(args.model)
        run_date = run_date_arg or auto_date
        log.info(f"Automatisch gewählt: {run_date.strftime('%Y%m%d')}/{run}Z")

    cfg   = MODEL_CFG[args.model]
    steps = [s for s in parse_steps(args.step) if 0 <= s <= cfg["max_step"]]
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    soundings = []
    for step in steps:
        snd = fetch_sounding(args.lat, args.lon, args.model, run, run_date, step, args.jobs, alias=args.alias)
        if snd:
            soundings.append(snd)

    if soundings:
        lat_s = f"{abs(args.lat):.2f}{'N' if args.lat >= 0 else 'S'}"
        lon_s = f"{abs(args.lon):.2f}{'E' if args.lon >= 0 else 'W'}"
        name  = f"sounding_{args.model.upper()}_{run_date.strftime('%Y%m%d')}_{run}Z_{lat_s}_{lon_s}.json"
        path  = out_dir / name
        path.write_text(json.dumps(soundings, indent=2, ensure_ascii=False))
        log.info(f"Fertig: {len(soundings)}/{len(steps)} Profile → {name}")
    else:
        log.error("Keine Profile erstellt.")

if __name__ == "__main__":
    main()
