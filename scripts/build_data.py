#!/usr/bin/env python3
"""Build the dashboard data file from the buoys listed in stations.json.

For each station this script downloads hourly significant wave height (Hs), removes flagged and
implausible values (rules in wavecommon.py), puts the record on a regular hourly UTC grid, works
out the "data facts" (complete seasons, gaps, comparison with the other buoys) and writes

    data/wave_data.js    (loaded by index.html; works from file:// and on the web)
    data/wave_data.json  (same content, for other tools)
    data/raw/<ID>.csv    (the downloads, reused by reports/wavereports.py)

Run from the repository root:

    python scripts/build_data.py              # download fresh data
    python scripts/build_data.py --from-raw   # reuse the files in data/raw (no download)

To add a buoy, add an entry to stations.json. Any buoy in the CIOOS Pacific ERDDAP dataset
DFO_MEDS_BUOYS needs only "source": "cioos_dfo_meds" and its MEDS station id (e.g. "C46207").
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wavecommon as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def load_station(st, start, raw_dir, from_raw):
    if st.get("source", "cioos_dfo_meds") != "cioos_dfo_meds":
        raise ValueError(f"{st['id']}: unknown source {st.get('source')!r}")
    raw = raw_dir / f"{st['id']}.csv"
    if from_raw:
        df = W.read_raw(raw)
    else:
        df = W.download_raw(st["source_station_id"], start, raw)
    df = df[df["time"] >= pd.Timestamp(start, tz="UTC")]
    return df, W.clean(df)


def to_dm(h):
    """(t0 string, Hs in integer decimetres, None for missing) from an hourly Series."""
    if h.empty:
        return None, []
    return h.index[0].strftime("%Y-%m-%dT%H:%MZ"), [None if np.isnan(v) else int(round(v * 10)) for v in h.values]


def facts_text(sid, facts, names):
    """Plain-language data facts for the dashboard notes (same wording as the reports)."""
    out = []
    cs = facts["coverage"]["complete_seasons"]
    out.append("Complete March–November seasons: " + ", ".join(map(str, cs)) + "." if cs
               else "No complete March–November season yet.")
    for g in facts["coverage"]["gaps"]:
        span = f"about {g['days'] / 30.4:.0f} months" if g["days"] >= 60 else f"{g['days']} days"
        out.append(f"No wave data from {W.month_year(g['from'])} to {W.month_year(g['to'])} ({span}).")
    comps = facts["comparisons"]
    if comps:
        out.append("Wave heights run " + _join([W.ratio_phrase(c, names[o]) for o, c in comps.items()]) + ".")
        lags = [W.lag_phrase(c, names[o]) for o, c in comps.items()]
        lags = [x for x in lags if x]
        if lags:
            out.append("Sea states " + _join(lags) + ".")
        period = next(iter(comps.values()))["period"]
        out.append(f"(Comparisons use hourly Hs where both buoys have data, {period}: median ratio, "
                   f"and the time shift that best lines up the two records.)")
    return out


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


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


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build data/wave_data.js for the dashboard.")
    ap.add_argument("--out-dir", default=str(ROOT / "data"), help="where to write wave_data.js/.json")
    ap.add_argument("--raw-dir", default=None, help="where raw downloads are saved / read (default <out-dir>/raw)")
    ap.add_argument("--from-raw", action="store_true", help="read the raw CSVs instead of downloading")
    a = ap.parse_args(argv)
    out_dir = Path(a.out_dir)
    raw_dir = Path(a.raw_dir) if a.raw_dir else out_dir / "raw"

    cfg = json.loads((ROOT / "stations.json").read_text())
    start = cfg["record_start"]
    months = range(cfg["season"]["first_month"], cfg["season"]["last_month"] + 1)
    out = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "record_start": start,
        "season": cfg["season"],
        "map": build_map_image(cfg),
        "units": "Hs in decimetres on an hourly UTC grid starting at t0; null = no data",
        "stations": [],
    }
    hourly, last = {}, {}
    for st in cfg["stations"]:
        _, d = load_station(st, start, raw_dir, a.from_raw)
        hourly[st["id"]] = W.hourly(d)
        last[st["id"]] = d["time"].max() if not d.empty else None
    if all(v is None for v in last.values()):
        # Never publish an empty dashboard: this almost certainly means the server returned
        # nothing useful rather than that every buoy stopped reporting.
        raise W.DownloadError("no data for any station - refusing to write wave_data.js")
    names = {s["id"]: s["name"] for s in cfg["stations"]}
    for st in cfg["stations"]:
        sid, h = st["id"], hourly[st["id"]]
        years = list(range(int(start[:4]), (last[sid].year if last[sid] is not None else int(start[:4])) + 1))
        others = sorted((o for o in cfg["stations"] if o["id"] != sid),
                        key=lambda o: W.distance_km((st["lat"], st["lon"]), (o["lat"], o["lon"])))
        comps = {}
        for o in others:
            c = W.compare(h, hourly[o["id"]])
            if c:
                comps[o["id"]] = c
        facts = {"coverage": W.coverage(h, years, months), "comparisons": comps}
        t0, dm = to_dm(h)
        print(f"{sid} {st['name']}: {sum(v is not None for v in dm)} hourly values, t0={t0}, "
              f"last={last[sid]:%Y-%m-%d %H:%M UTC}" if last[sid] is not None else f"{sid}: no data")
        out["stations"].append({
            "id": sid, "name": st["name"], "lat": st["lat"], "lon": st["lon"],
            "source": st.get("source", "cioos_dfo_meds"), "t0": t0,
            "last_obs_utc": last[sid].strftime("%Y-%m-%d %H:%M UTC") if last[sid] is not None else None,
            "hs_dm": dm, "facts": facts, "facts_text": facts_text(sid, facts, names),
            **{k: st[k] for k in ("default_selected", "summary", "notes") if k in st},
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    js = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
    (out_dir / "wave_data.json").write_text(js, encoding="utf-8")
    (out_dir / "wave_data.js").write_text("window.WAVE_DATA = " + js + ";\n", encoding="utf-8")
    print(f"wrote {out_dir / 'wave_data.js'} ({len(js) / 1e3:.0f} kB)")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except W.DownloadError as e:
        sys.exit(f"BUILD STOPPED: {e}")
