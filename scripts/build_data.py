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


GEBCO_WMS = "https://wms.gebco.net/mapserv"
MAP_IMAGE = "assets/bathymetry.jpg"
MAP_IMAGE_META = "assets/bathymetry.json"        # records the extent the image was made for
MAP_WIDTH_PX = 2000


def build_map_image(cfg):
    """Fit the map extent to all buoys and reference sites, and save a GEBCO image of it.

    Returns the map settings for the dashboard, with "image" and "extent" [W, E, S, N] added.
    The image is skipped (and the previous one kept) if GEBCO cannot be reached.
    """
    m = dict(cfg.get("map", {}))
    pts = [(s["lat"], s["lon"]) for s in cfg["stations"]] + \
          [(r["lat"], r["lon"]) for r in m.get("reference_sites", [])]
    pad = m.get("fit_padding_deg", 0.8)
    if "extent" in m:                                   # fixed extent from stations.json
        W, E, S, N = m["extent"]
    else:
        W = min(p[1] for p in pts) - pad; E = max(p[1] for p in pts) + pad
        S = min(p[0] for p in pts) - pad; N = max(p[0] for p in pts) + pad
    W, E, S, N = (round(v, 3) for v in (W, E, S, N))
    lat_c = np.deg2rad((S + N) / 2)
    height = int(round(MAP_WIDTH_PX * (N - S) / ((E - W) * np.cos(lat_c))))
    params = {"request": "GetMap", "service": "WMS", "version": "1.3.0", "layers": "GEBCO_LATEST",
              "styles": "", "crs": "EPSG:4326", "bbox": f"{S},{W},{N},{E}",
              "width": MAP_WIDTH_PX, "height": height, "format": "image/jpeg"}
    img, meta = ROOT / MAP_IMAGE, ROOT / MAP_IMAGE_META
    old = json.loads(meta.read_text()) if meta.exists() else {}
    wanted = {"extent": [W, E, S, N], "width": MAP_WIDTH_PX}
    if img.exists() and old.get("extent") == wanted["extent"] and old.get("width") == MAP_WIDTH_PX:
        print(f"map: {MAP_IMAGE} already covers W{W} E{E} S{S} N{N}; not re-downloaded")
    else:
        try:
            r = requests.get(GEBCO_WMS, params=params, timeout=180)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("image/"):
                raise ValueError(r.text[:200])
            img.write_bytes(r.content)
            meta.write_text(json.dumps(wanted) + "\n")
            print(f"map: extent W{W} E{E} S{S} N{N}; wrote {MAP_IMAGE} ({len(r.content) / 1e3:.0f} kB)")
        except Exception as e:
            # Keep the previous image, and its own extent, so the background still lines up with
            # the markers; points outside it are drawn on the plain background colour.
            print(f"map: GEBCO image not updated ({e})")
            if img.exists() and old.get("extent"):
                W, E, S, N = old["extent"]
                print("map: using the previous image and its extent")
            else:
                m.update({"extent": [W, E, S, N]})
                return m                                 # no image available
    m.update({"image": MAP_IMAGE, "extent": [W, E, S, N]})
    return m


def main():
    cfg = json.loads((ROOT / "stations.json").read_text())
    out = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "record_start": cfg["record_start"],
        "season": cfg["season"],
        "map": build_map_image(cfg),
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
            # optional display fields
            **{k: st[k] for k in ("default_selected", "summary", "notes") if k in st},
        })
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    js = json.dumps(out, separators=(",", ":"))
    (data_dir / "wave_data.json").write_text(js)
    (data_dir / "wave_data.js").write_text("window.WAVE_DATA = " + js + ";\n")
    print(f"wrote data/wave_data.js ({len(js) / 1e3:.0f} kB)")


if __name__ == "__main__":
    sys.exit(main())
