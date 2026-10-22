"""Shared buoy-data code for the dashboard (scripts/build_data.py) and the reports (reports/wavereports.py).

Keeping download, cleaning and the computed "data facts" in one place means the dashboard and the
reports always use the same rules and agree on the numbers.
"""
import io
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ERDDAP = "https://data.cioospacific.ca/erddap/tabledap/DFO_MEDS_BUOYS.csv"

# ---- quality control --------------------------------------------------------------
HS_MIN, HS_MAX = 0.2, 20.0     # m; outside this range = placeholder / stuck sensor
BAD_FLAGS = {4, 7}             # MEDS Q_FLAG: 4 erroneous, 7 off position

# ---- coverage rules (same as the reports) -------------------------------------------
FULL_DAY_H = 20                # hours of data for a day to count as "full"
COMPLETE_MONTH_DAYS = 25       # full days for a month to count as well covered
GAP_REPORT_DAYS = 30           # report gaps longer than this
MAX_LAG_H = 36                 # search window for the lead/lag between buoys


# ---- download -----------------------------------------------------------------------
def download_raw(station_id, start, dest=None):
    """Hourly MEDS record for one station from CIOOS ERDDAP, as a DataFrame.

    If dest is given, the CSV is also saved there (so other scripts can reuse the same download).
    """
    q = (f"?STN_ID,time,Q_FLAG,latitude,longitude,VCAR,VWH"
         f"&STN_ID=%22{station_id}%22&time>={start}T00:00:00Z")
    r = requests.get(ERDDAP + q, timeout=600)
    if r.status_code == 404:                  # ERDDAP answers 404 when no rows match
        return pd.DataFrame(columns=["STN_ID", "time", "Q_FLAG", "latitude", "longitude", "VCAR", "VWH"])
    r.raise_for_status()
    if dest is not None:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(r.content)
    return read_raw(io.StringIO(r.text))


def read_raw(path_or_buf):
    """Read an ERDDAP CSV (second line holds units)."""
    df = pd.read_csv(path_or_buf, skiprows=[1], parse_dates=["time"])
    if df["time"].dt.tz is None:
        df["time"] = df["time"].dt.tz_localize("UTC")
    return df


# ---- cleaning -----------------------------------------------------------------------
def clean(df):
    """Merged Hs: VCAR (MEDS QC'd) where valid, else VWH (buoy-reported); flagged rows removed.

    Returns a DataFrame with time, Hs and from_vcar, sorted, one row per time stamp.
    """
    d = df[df["Q_FLAG"].isna() | ~df["Q_FLAG"].isin(BAD_FLAGS)].copy()
    vcar = d["VCAR"].where(d["VCAR"].between(HS_MIN, HS_MAX))
    vwh = d["VWH"].where(d["VWH"].between(HS_MIN, HS_MAX))
    d["Hs"] = vcar.fillna(vwh)
    d["from_vcar"] = vcar.notna()
    d = d.dropna(subset=["Hs"]).sort_values("time").drop_duplicates("time")
    return d[["time", "Hs", "from_vcar"]].reset_index(drop=True)


def hourly(d):
    """Cleaned Hs on a regular hourly UTC grid (sample time floored to the hour); NaN = no data."""
    if d.empty:
        return pd.Series(dtype=float)
    s = d.set_index(d["time"].dt.floor("h"))["Hs"]
    s = s.groupby(level=0).mean()
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="h"))


# ---- data facts ---------------------------------------------------------------------
def distance_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    c = (math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(lo1 - lo2))
    return 6371.0 * math.acos(max(-1.0, min(1.0, c)))


def coverage(h, years, months=range(3, 12)):
    """Years whose every season month has >= COMPLETE_MONTH_DAYS full days, and gaps > GAP_REPORT_DAYS."""
    if h.empty:
        return {"complete_seasons": [], "gaps": []}
    per_day = h.notna().groupby(h.index.floor("D")).sum()
    full = per_day[per_day >= FULL_DAY_H]
    complete = []
    for y in years:
        ok = True
        for m in months:
            n = int(((full.index.year == y) & (full.index.month == m)).sum())
            if n < COMPLETE_MONTH_DAYS:
                ok = False
                break
        if ok:
            complete.append(y)
    t = h.dropna().index
    gaps = []
    if len(t) > 1:
        dt = np.diff(t.values).astype("timedelta64[h]").astype(int)
        for i in np.where(dt > GAP_REPORT_DAYS * 24)[0]:
            gaps.append({"from": t[i].strftime("%Y-%m-%d"), "to": t[i + 1].strftime("%Y-%m-%d"),
                         "days": int(round(dt[i] / 24))})
    return {"complete_seasons": complete, "gaps": gaps}


def compare(ha, hb):
    """How buoy A relates to buoy B, from hourly Hs where both have data.

    ratio  : median of A/B
    r0     : correlation at the same hour
    lag_h  : lag (h) of best correlation; > 0 means A leads B (sea states reach A first)
    r_lag  : correlation at that lag
    """
    both = pd.concat({"a": ha, "b": hb}, axis=1).dropna()
    if len(both) < 24 * 30:
        return None
    ratio = float(np.median(both["a"] / both["b"]))
    r0 = float(both["a"].corr(both["b"]))
    grid = pd.concat({"a": ha, "b": hb}, axis=1)
    best_lag, best_r = 0, r0
    for lag in range(-MAX_LAG_H, MAX_LAG_H + 1):
        r = grid["a"].shift(lag).corr(grid["b"])
        if pd.notna(r) and r > best_r + 1e-12:
            best_lag, best_r = lag, float(r)
    return {"n_hours": int(len(both)), "ratio": round(ratio, 3), "r0": round(r0, 3),
            "lag_h": int(best_lag), "r_lag": round(best_r, 3),
            "period": f"{both.index.min():%Y}–{both.index.max():%Y}"}


def screen(df_raw, d):
    """Automated screening counts on the raw record and the cleaned series."""
    low = 0
    for c in ("VCAR", "VWH"):
        low += int((df_raw[c].notna() & (df_raw[c] <= HS_MIN)).sum())
    hs, t = d["Hs"].reset_index(drop=True), d["time"].reset_index(drop=True)
    d1, d2 = hs - hs.shift(1), hs - hs.shift(-1)
    spikes = int((((d1 > 2) & (d2 > 2)) | ((d1 < -2) & (d2 < -2))).sum())
    dtm = t.diff().dt.total_seconds() / 60
    jumps = d[((hs.diff().abs() > 2.5) & (dtm <= 65)).values]
    run = (hs != hs.shift()).cumsum()
    longest = int(hs.groupby(run).size().max()) if len(hs) else 0
    return {"low_values": low, "isolated_spikes": spikes, "jumps": int(len(jumps)),
            "jump_times": [x.strftime("%Y-%m-%d %H:%M") for x in jumps["time"].head(5)],
            "longest_identical_run": longest}


# ---- wording shared by dashboard and reports ------------------------------------------
def month_year(s):
    return pd.Timestamp(s).strftime("%-d %b %Y")


def ratio_phrase(c, other_name):
    pct = (c["ratio"] - 1) * 100
    if abs(pct) < 3:
        return f"about the same as at {other_name}"
    return f"about {abs(pct):.0f}% {'higher' if pct > 0 else 'lower'} than at {other_name}"


def lag_phrase(c, other_name):
    """None when there is no clear lead or lag."""
    if abs(c["lag_h"]) < 3 or c["r_lag"] - c["r0"] < 0.02:
        return None
    word = "lead" if c["lag_h"] > 0 else "lag"
    return f"{word} {other_name} by about {abs(c['lag_h'])} h"
