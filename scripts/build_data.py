#!/usr/bin/env python3
"""Build the dashboard data file from the buoys listed in stations.json.

For each station this script downloads hourly significant wave height (Hs),
removes flagged and implausible values, puts the record on a regular hourly
UTC grid and writes everything to

    data/wave_data.js    (loaded by index.html; works from file:// and GitHub Pages)
    data/wave_data.json  (same content, for other tools)

Run from the repository root:

    python scripts/build_data.py

To add a buoy, add an entry to stations.json. Stations served by the CIOOS
Pacific ERDDAP dataset DFO_MEDS_BUOYS need only "source": "cioos_dfo_meds" and
the MEDS station id (e.g. "C46207"). Other data sources can be added by writing
a fetch function and registering it in SOURCES below.
"""
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
ERDDAP = "https://data.cioospacific.ca/erddap/tabledap/DFO_MEDS_BUOYS.csv"

# Quality control
HS_MIN, HS_MAX = 0.2, 20.0     # m; outside this range = placeholder / stuck sensor
BAD_FLAGS = {4, 7}             # MEDS Q_FLAG: 4 erroneous, 7 off position


def fetch_cioos_dfo_meds(station, start):
    """Hourly Hs from DFO MEDS via CIOOS Pacific ERDDAP.

    Uses VCAR (MEDS QC'd spectral Hs) where present, otherwise VWH
    (buoy-reported Hs). Returns a Series of Hs (m) indexed by UTC time.
    """
    query = (f"?time,Q_FLAG,VCAR,VWH&STN_ID=%22{station['source_station_id']}%22"
             f"&time>={start}T00:00:00Z")
    r = requests.get(ERDDAP + query, timeout=600)
    if r.status_code == 404:          # ERDDAP returns 404 when no rows match
        return pd.Series(dtype=float)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), skiprows=[1], parse_dates=["time"])
    df = df[~df["Q_FLAG"].isin(BAD_FLAGS)]
    vcar = df["VCAR"].where(df["VCAR"].between(HS_MIN, HS_MAX))
    vwh = df["VWH"].where(df["VWH"].between(HS_MIN, HS_MAX))
    hs = vcar.fillna(vwh)
    s = pd.Series(hs.values, index=df["time"].dt.tz_convert("UTC")).dropna()
    return s.sort_index()


SOURCES = {"cioos_dfo_meds": fetch_cioos_dfo_meds}


def to_hourly_grid(s):
    """Place samples on a regular hourly grid (sample time floored to the hour).

    Returns (t0 ISO string, list of Hs in decimetres as int, None for missing).
    """
    if s.empty:
        return None, []
    hourly = s.groupby(s.index.floor("h")).mean()
    grid = pd.date_range(hourly.index.min(), hourly.index.max(), freq="h")
    hourly = hourly.reindex(grid)
    dm = [None if np.isnan(v) else int(round(v * 10)) for v in hourly.values]
    return grid[0].strftime("%Y-%m-%dT%H:%MZ"), dm


def main():
    cfg = json.loads((ROOT / "stations.json").read_text())
    out = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "record_start": cfg["record_start"],
        "season": cfg["season"],
        "map": cfg.get("map", {}),
        "units": "Hs in decimetres on an hourly UTC grid starting at t0; null = no data",
        "stations": [],
    }
    for st in cfg["stations"]:
        fetch = SOURCES[st["source"]]
        s = fetch(st, cfg["record_start"])
        t0, dm = to_hourly_grid(s)
        n_valid = sum(v is not None for v in dm)
        last = s.index.max().strftime("%Y-%m-%d %H:%M UTC") if not s.empty else None
        print(f"{st['id']} {st['name']}: {n_valid} hourly values, t0={t0}, last={last}")
        out["stations"].append({
            "id": st["id"], "name": st["name"], "lat": st["lat"], "lon": st["lon"],
            "source": st["source"], "t0": t0, "last_obs_utc": last, "hs_dm": dm,
        })
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    js = json.dumps(out, separators=(",", ":"))
    (data_dir / "wave_data.json").write_text(js)
    (data_dir / "wave_data.js").write_text("window.WAVE_DATA = " + js + ";\n")
    print(f"wrote data/wave_data.js ({len(js) / 1e3:.0f} kB)")


if __name__ == "__main__":
    sys.exit(main())
