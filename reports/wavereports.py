#!/usr/bin/env python3
"""Wave-height exceedance reports for moored buoys (the months set in stations.json, normally all year).

For each buoy in stations.json (repository root) this script

  1. downloads hourly significant wave height (Hs) from the DFO MEDS archive (CIOOS Pacific ERDDAP
     dataset DFO_MEDS_BUOYS), or reuses the dashboard's downloads in data/raw;
  2. removes flagged and implausible values (rules in scripts/wavecommon.py, shared with the dashboard);
  3. computes, for every day of the season (stations.json; normally 1 January – 31 December), the time (decimal hours) with Hs above
     2.00, 2.25, 2.50, 2.75 and 3.00 m;
  4. computes the data facts: complete seasons, gaps, automated screening, and comparison with the
     other buoys (ratio, correlation, lead/lag);
  5. writes a season figure, one figure per month, daily and monthly CSV tables and a PDF report.

Usage (from the repository root):

    python reports/wavereports.py                 # every station (downloads fresh data)
    python reports/wavereports.py --from-raw      # reuse data/raw/<ID>.csv (e.g. after build_data.py)
    python reports/wavereports.py C46132          # one station (all are still loaded for comparisons)

Outputs:
    reports/output/<id>/report/<id>_wave_exceedance_report_<y0>-<y1>.pdf
    reports/output/<id>/figures/  season figure and one figure per month
    reports/output/<id>/data/     daily and monthly CSV tables
    reports/pdf/<id>_wave_exceedance_report.pdf   latest report under a fixed name (linked from the dashboard)

Method:
  * Hs = VCAR (MEDS QC'd spectral Hs) where valid, otherwise VWH (buoy-reported).
  * Removed: Q_FLAG 4 (erroneous) or 7 (off position); values outside 0.2–20 m.
  * Hs is interpolated linearly between samples across gaps of at most 2 h and evaluated on a
    1-minute grid; time above each threshold is summed per UTC day.
  * Days with at least 20 h of data are scaled to 24 h ("full days"). Days with less are hatched in
    the figures, their measured hours are drawn in grey, and they are left out of the monthly table.
"""
import argparse
import calendar
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch, Rectangle
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
import wavecommon as W  # noqa: E402

# ---- analysis settings ---------------------------------------------------------
THRESHOLDS = [2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0]   # m
SEASON = range(1, 13)                       # months analysed; set from stations.json "season" in main()
SUMMER_SEASON = range(3, 12)                # March–November: the ship-time season summarised in the key results
WINTER = (12, 1, 2)                         # December–February, summarised per winter (Dec + following Jan, Feb)
HS_MIN, HS_MAX, BAD_FLAGS = W.HS_MIN, W.HS_MAX, W.BAD_FLAGS
MAX_GAP_MIN = 120                           # interpolate across gaps up to 2 h
FULL_DAY_H = W.FULL_DAY_H                   # hours of data needed for a "full" day
COMPLETE_MONTH_DAYS = W.COMPLETE_MONTH_DAYS # full days for a month to count as well covered
N_COMPARE = 3                               # compare with up to this many nearest buoys
TH_RANGE = f"{THRESHOLDS[0]:.2f}–{THRESHOLDS[-1]:.2f} m"


def season_names():
    """('January–December', 'Jan–Dec') for the months analysed."""
    a, b = SEASON[0], SEASON[-1]
    return (f"{calendar.month_name[a]}–{calendar.month_name[b]}", f"{calendar.month_abbr[a]}–{calendar.month_abbr[b]}")

# ---- plot style ------------------------------------------------------------------
YEAR_COLOURS = {2024: "#1f5fa8", 2025: "#d9661f", 2026: "#6a3d9a"}
EXTRA_COLOURS = ["#2a9d8f", "#b5179e", "#8c564b", "#c9a227", "#264653", "#e76f51"]
# Lighter = lower threshold. Index 0 is > 2.00 m (lightest), last is > 4.00 m (darkest).
# Positive: mix with white; 0: the year colour; negative: mix with black (the 3.50 and 4.00 m levels),
# so the 2.00–3.00 m shades look the same as in the original five-threshold reports.
WHITE_MIX = [0.74, 0.61, 0.46, 0.28, 0.0, -0.30, -0.55]
GREYS = ["0.86", "0.79", "0.71", "0.62", "0.52", "0.40", "0.27"]
HATCH = dict(facecolor="white", edgecolor="0.72", hatch="////", lw=0)


def year_colour(y):
    if y in YEAR_COLOURS:
        return YEAR_COLOURS[y]
    return EXTRA_COLOURS[(y - 2027) % len(EXTRA_COLOURS)]


def shade(c, f):
    c = np.array(mpl.colors.to_rgb(c))
    return tuple(c + (1 - c) * f) if f >= 0 else tuple(c * (1 + f))


def apply_style():
    mpl.rcParams.update({
        "font.family": "sans-serif", "font.size": 10, "axes.labelsize": 10, "axes.titlesize": 10,
        "legend.fontsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.linewidth": 0.6, "xtick.direction": "out", "ytick.direction": "out",
        "xtick.major.size": 3, "ytick.major.size": 3, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
        "legend.frameon": False, "figure.dpi": 200, "savefig.dpi": 300, "savefig.bbox": "tight",
        "axes.titleweight": "normal", "axes.titlelocation": "left", "lines.linewidth": 1.2,
        "patch.linewidth": 0.6, "pdf.fonttype": 42, "ps.fonttype": 42,
    })


# ---- data ------------------------------------------------------------------------
# download, cleaning and data facts live in scripts/wavecommon.py (shared with the dashboard)
clean = W.clean


def daily_exceedance(d, years):
    """Daily decimal hours above each threshold, for the season months of the given years."""
    t = d["time"].dt.tz_convert(None).values.astype("datetime64[m]").astype("int64")
    v = d["Hs"].values
    g0 = np.datetime64(f"{min(years)}-{SEASON[0]:02d}-01T00:00", "m").astype("int64")
    ye, me = (max(years) + 1, 1) if SEASON[-1] == 12 else (max(years), SEASON[-1] + 1)
    g1 = np.datetime64(f"{ye}-{me:02d}-01T00:00", "m").astype("int64")
    grid = np.arange(g0, g1)
    j = np.searchsorted(t, grid, side="right")
    ok = (j > 0) & (j < len(t))
    jp = np.clip(j - 1, 0, len(t) - 1)
    jn = np.clip(j, 0, len(t) - 1)
    gap = t[jn] - t[jp]
    ok &= gap <= MAX_GAP_MIN
    hs = v[jp] + (v[jn] - v[jp]) * np.where(gap > 0, (grid - t[jp]) / np.maximum(gap, 1), 0)
    G = pd.DataFrame({"ok": ok, "hs": np.where(ok, hs, np.nan)},
                     index=pd.to_datetime(grid.astype("datetime64[m]")))
    G = G[G.index.month.isin(SEASON) & G.index.year.isin(years)]
    key = G.index.floor("D")
    day = pd.DataFrame({"coverage_h": G.groupby(key)["ok"].sum() / 60})
    full = day["coverage_h"] >= FULL_DAY_H
    for th in THRESHOLDS:
        above = (G["hs"] > th).groupby(key).sum() / 60
        day[f"h_gt_{th:.2f}"] = np.where(full, 24 * above / day["coverage_h"], np.nan)
        day[f"obs_h_gt_{th:.2f}"] = np.where(~full & (day["coverage_h"] > 0), above, np.nan)
    day.index.name = "date"
    return day


def monthly_table(day, years):
    f = day[day["h_gt_2.00"].notna()]
    cols = [f"h_gt_{th:.2f}" for th in THRESHOLDS]
    t = f[cols].groupby([f.index.year, f.index.month]).mean().round(1)
    t["n_days"] = f["h_gt_2.00"].groupby([f.index.year, f.index.month]).count()
    idx = pd.MultiIndex.from_tuples([(y, m) for y in years for m in SEASON], names=["year", "month"])
    t = t.reindex(idx)
    t["n_days"] = t["n_days"].fillna(0).astype(int)
    return t


# ---- figures ---------------------------------------------------------------------
class _GreyRamp:
    pass


class _GreyRampHandler:
    def legend_artist(self, legend, orig, fontsize, hb):
        x0, y0, w, h = hb.xdescent, hb.ydescent, hb.width, hb.height
        n = len(GREYS)
        arts = [Rectangle((x0 + k * w / n, y0), w / n, h, facecolor=GREYS[k], edgecolor="none",
                          transform=hb.get_transform()) for k in range(n)]
        for a in arts:
            hb.add_artist(a)
        return arts[0]


def draw(day, years, start, end, title, fname, bar_w, label_cov, monthly):
    cols = {y: [shade(year_colour(y), f) for f in WHITE_MIX] for y in years}
    idx = pd.date_range(start, end, freq="D")
    fig_w, fig_h = (9, 6.4) if monthly else (11, 8.6)     # height per 3 years; room for the 7-level legends
    fig, axs = plt.subplots(len(years), 1, figsize=(fig_w, fig_h * len(years) / 3), sharex=True,
                            gridspec_kw={"hspace": 0.14}, squeeze=False)
    axs = axs[:, 0]
    for ax, y in zip(axs, years):
        sub = day.reindex(idx.map(lambda q: q.replace(year=y)))
        partial = sub["h_gt_2.00"].isna().values
        has_part = partial & (sub["coverage_h"].fillna(0).values > 0)
        if partial.any():
            ax.bar(idx[partial], 24, width=1.0, zorder=0, **HATCH)
        for k, th in enumerate(THRESHOLDS):
            ax.bar(idx, np.nan_to_num(sub[f"h_gt_{th:.2f}"].values), width=bar_w,
                   color=cols[y][k], edgecolor="none", zorder=1 + k)
            ax.bar(idx, np.nan_to_num(sub[f"obs_h_gt_{th:.2f}"].values), width=bar_w,
                   color=GREYS[k], edgecolor="none", zorder=1 + k)
        if label_cov:
            for xi, c, p in zip(idx, sub["coverage_h"].values, has_part):
                if p:
                    ax.text(xi, 23.6, f"{c:.0f} h" if c >= 0.5 else "<1 h", ha="center", va="top",
                            fontsize=6.5, color="0.2", rotation=90, zorder=10,
                            bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none"))
        ax.set_ylim(0, 24.5)
        ax.set_yticks([0, 6, 12, 18, 24])
        ax.grid(axis="y", color="0.88", lw=0.5)
        ax.set_axisbelow(True)
        handles = [Patch(color=cols[y][k], label=f"> {th:.2f} m") for k, th in enumerate(THRESHOLDS)]
        labels = [h.get_label() for h in handles]
        hmap = {}
        if partial.any():
            handles.append(Patch(label="", **HATCH))
            labels.append("< 20 h of data" + (" (label:\nhours of data)" if label_cov and has_part.any() else ""))
        if np.nansum(sub["obs_h_gt_2.00"].values) > 0:
            handles.append(_GreyRamp())
            labels.append(f"Measured hours on\n< 20 h days\n(> {THRESHOLDS[0]:.2f} … > {THRESHOLDS[-1]:.2f} m)")
            hmap[_GreyRamp] = _GreyRampHandler()
        lg = ax.legend(handles=handles, labels=labels, handler_map=hmap, title=str(y), loc="center left",
                       bbox_to_anchor=(1.005, 0.5), frameon=False, handlelength=1.6, handleheight=0.9,
                       labelspacing=0.25, alignment="left")
        lg.get_title().set_color(year_colour(y))
        lg.get_title().set_fontweight("bold")
    axs[-1].set_xlim(idx[0] - pd.Timedelta(hours=12), idx[-1] + pd.Timedelta(hours=12))
    if monthly:
        axs[-1].xaxis.set_major_locator(mdates.DayLocator(bymonthday=[1, 5, 10, 15, 20, 25, 30]))
        axs[-1].xaxis.set_major_formatter(mdates.DateFormatter("%-d"))
        axs[-1].set_xlabel("Day of month")
    else:
        axs[-1].xaxis.set_major_locator(mdates.MonthLocator())
        axs[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.supylabel("Time with Hs above threshold (decimal hours per day)", x=0.06)
    axs[0].set_title(title, loc="left")
    fig.savefig(fname, dpi=300, bbox_inches="tight")
    plt.close(fig)


def make_figures(day, years, st, figdir):
    figdir.mkdir(parents=True, exist_ok=True)
    sid, name = st["id"], st["name"]
    ref = 2001                                   # non-leap reference year for the date axis
    season_png = figdir / f"{sid}_exceedance_season.png"
    m0, m1 = SEASON[0], SEASON[-1]
    last1 = calendar.monthrange(ref, m1)[1]
    draw(day, years, f"{ref}-{m0:02d}-01", f"{ref}-{m1:02d}-{last1}",
         f"{name} buoy {sid}: daily time with significant wave height above {TH_RANGE}, "
         f"1 {calendar.month_abbr[m0]} – {last1} {calendar.month_abbr[m1]}",
         season_png, 1.0, False, False)
    month_pngs = []
    for m in SEASON:
        nm = calendar.month_name[m]
        last = calendar.monthrange(ref, m)[1]
        p = figdir / f"{sid}_exceedance_{m:02d}_{nm}.png"
        draw(day, years, f"{ref}-{m:02d}-01", f"{ref}-{m:02d}-{last}",
             f"{sid} {nm}: daily time with significant wave height above {TH_RANGE}", p, 0.8, True, True)
        month_pngs.append((m, p))
    return season_png, month_pngs


# ---- report text -----------------------------------------------------------------
def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _rng(t, col, ys, ms):
    v = [t.loc[(y, m), col] for y in ys for m in ms if not pd.isna(t.loc[(y, m), col])]
    return (min(v), max(v)) if v else (np.nan, np.nan)


def key_results(t, day, years, last_obs, st, comp_text=None):
    """Key results in groups: [(heading, [bullets]), ...], plus complete and incomplete years.

    The March–November group uses the years whose March–November months are all well covered
    (the same reference years as the original Mar–Nov reports), so its numbers do not change when
    the winter months are added.
    """
    ms = [m for m in SUMMER_SEASON if m in SEASON]
    mn_complete = [y for y in years if all(t.loc[(y, m), "n_days"] >= COMPLETE_MONTH_DAYS for m in ms)]
    ref = mn_complete or years
    g2 = lambda y, m: t.loc[(y, m), "h_gt_2.00"]
    summer = []
    ja = [y for y in years if not (pd.isna(g2(y, 7)) and pd.isna(g2(y, 8)))]
    parts = [f"{g2(y, 7):.1f} and {g2(y, 8):.1f} h/day in {y}" for y in ja
             if not pd.isna(g2(y, 7)) and not pd.isna(g2(y, 8))]
    _, mx3 = _rng(t, "h_gt_3.00", ja, [7, 8])
    if parts:
        summer.append(f"July–August is the operating window: mean time above 2 m was {_join(parts)}. "
                      f"Time above 3 m was {mx3:.1f} h/day or less.")
    a, b = _rng(t, "h_gt_2.00", ref, [5, 6]); c, d = _rng(t, "h_gt_3.00", ref, [5, 6])
    summer.append(f"May–June is usable but has multi-day rough spells: {a:.1f}–{b:.1f} h/day above 2 m in "
                  f"{_join(map(str, ref))}, and {c:.1f}–{d:.1f} h/day above 3 m.")
    a, b = _rng(t, "h_gt_2.00", ref, [3, 10, 11]); c, d = _rng(t, "h_gt_3.00", ref, [3, 10, 11])
    summer.append(f"March, October and November are mostly lost: {a:.1f}–{b:.1f} h/day above 2 m and "
                  f"{c:.1f}–{d:.1f} h/day above 3 m in {_join(map(str, ref))}.")
    sep = [(y, g2(y, 9)) for y in years if not pd.isna(g2(y, 9))]
    if sep:
        summer.append("September (time above 2 m): " + _join([f"{v:.1f} h/day in {y}" for y, v in sep]) + ".")
    groups = [("March–November", summer)]
    if all(m in SEASON for m in WINTER):
        groups.append(("December–February", winter_text(t, day, years, ja)))

    complete = [y for y in years if all(t.loc[(y, m), "n_days"] >= COMPLETE_MONTH_DAYS for m in SEASON)]
    incomplete = [y for y in years if y not in complete and t.loc[y, "n_days"].sum() > 0]
    lo_c, hi_c = (min(t.loc[(y, m), "n_days"] for y in complete for m in SEASON),
                  max(t.loc[(y, m), "n_days"] for y in complete for m in SEASON)) if complete else (None, None)
    cov = []
    for y in incomplete:
        nd = {m: int(t.loc[(y, m), "n_days"]) for m in SEASON}
        have = [v for v in nd.values() if v > 0]
        none = [calendar.month_name[m] for m, v in nd.items() if v == 0]
        thin = [calendar.month_name[m] for m, v in nd.items() if 0 < v < COMPLETE_MONTH_DAYS]
        x = f"{y} is incomplete"
        if len(thin) == 1:
            x += f": the only month with fewer than {COMPLETE_MONTH_DAYS} full days is {thin[0]}"
        elif thin:
            x += f": months with fewer than {COMPLETE_MONTH_DAYS} full days are {_join(thin)}"
        if none and last_obs is not None and last_obs.year == y and last_obs.month in SEASON:
            x += f"{',' if thin else ':'} and there is no data after {last_obs.day} {calendar.month_name[last_obs.month]}"
        x += (f". In the monthly summary table, its values rest on {min(have)}–{max(have)} full days per month"
              + (f" (none in {_join(none)})" if none else "")
              + (f", against {lo_c}–{hi_c} in {_join(map(str, complete))}" if complete else "")
              + ", so weight them accordingly.")
        cov.append(x)
    if complete and not incomplete:
        cov.append(f"The record is complete: every month has {lo_c}–{hi_c} full days.")
    if comp_text:
        cov.append(comp_text)
    cov += st.get("report", {}).get("key_results_extra", [])
    groups.append(("Data coverage and other buoys", cov))
    return groups, complete, incomplete


def winter_text(t, day, years, ja):
    """December–February bullets, one value per winter (Dec of one year + Jan, Feb of the next).

    A winter is used when all three months have at least COMPLETE_MONTH_DAYS full days; when the
    record starts in January, a well-covered January–February is shown on its own. Means are over
    the full days of those months (daily table, not the rounded monthly means).
    """
    full = day[day["h_gt_2.00"].notna()]
    ok = lambda y, m: (y, m) in t.index and t.loc[(y, m), "n_days"] >= COMPLETE_MONTH_DAYS
    rows = []
    for y in years:
        months = [(y - 1, 12), (y, 1), (y, 2)]
        good = [k for k in months if ok(*k)]
        if len(good) == 3:
            label = f"{y - 1}–{str(y)[2:]}"
        elif good == [(y, 1), (y, 2)]:
            label = f"January–February {y}"
        else:
            continue
        sel = full[[(d.year, d.month) in good for d in full.index]]
        rows.append((label, {th: sel[f"h_gt_{th:.2f}"].mean() for th in (2.0, 3.0, 4.0)}))
    if not rows:
        return [f"No December–February period has at least {COMPLETE_MONTH_DAYS} full days of data in every month yet."]
    lab = lambda r: r[0] if r[0][0].isalpha() else f"winter {r[0]}"
    per = _join([f"{r[1][2.0]:.1f}, {r[1][3.0]:.1f} and {r[1][4.0]:.1f} h/day in {lab(r)}" for r in rows])
    out = [f"Winter is the roughest part of the year. Mean time above 2, 3 and 4 m was {per}."]
    wm = [(y, m, t.loc[(y, m), "h_gt_2.00"]) for y in years for m in WINTER if ok(y, m)]
    if wm:
        y, m, v = min(wm, key=lambda q: q[2])
        lo, hi = _rng(t, "h_gt_2.00", ja, [7, 8])
        x = (f"No well-covered winter month averaged less than {v:.1f} h/day above 2 m "
             f"(the lowest was {calendar.month_name[m]} {y})")
        if not pd.isna(lo):
            x += f", against monthly means of {lo:.1f}–{hi:.1f} h/day in July–August"
        out.append(x + ".")
    return out


def method_text(d, df_raw, st, last_obs, scr=None):
    dt = d["time"].diff().dt.total_seconds().div(60)
    med = dt.median()
    minute = int(d["time"].dt.minute.mode().iloc[0])
    interval = "One significant wave height (Hs) value per hour" if 55 <= med <= 65 else \
        f"Significant wave height (Hs) every {med:.0f} minutes (median)"
    frac_vwh = 1 - d["from_vcar"].mean()
    no_flags = df_raw["Q_FLAG"].isna().all()
    if frac_vwh > 0.999:
        qc = "All values in this record are the buoy-reported Hs (VWH). These have not been quality-controlled by MEDS"
        qc += ", and no quality flags are provided in this record." if no_flags else "."
    elif frac_vwh < 0.001:
        qc = "All values are the MEDS quality-controlled spectral Hs (VCAR)."
    else:
        qc = (f"Values are the MEDS quality-controlled spectral Hs (VCAR) where available; the remaining "
              f"{100 * frac_vwh:.0f}% are buoy-reported Hs (VWH), which have not been quality-controlled.")
    bad = lambda c: int((df_raw[c].notna() & ~df_raw[c].between(HS_MIN, HS_MAX)).sum())
    n_vwh, n_vcar = bad("VWH"), bad("VCAR")
    n_flag = int(df_raw["Q_FLAG"].isin(BAD_FLAGS).sum())
    parts = [p for p in (f"{n_vcar} QC'd (VCAR) values" if n_vcar else "",
                         f"{n_vwh} buoy-reported (VWH) values" if n_vwh else "",
                         f"{n_flag} flagged records" if n_flag else "") if p]
    removed = (f"Removed: values flagged erroneous or off position, and values outside {HS_MIN}–{HS_MAX:.0f} m"
               + (f" ({_join(parts)} in this record)." if parts else " (none occurred in this record)."))
    return [
        f"Source: DFO Marine Environmental Data Section (MEDS) archive for buoy {st['id']} "
        f"({st['lat']:.2f} N, {abs(st['lon']):.2f} W), served by the CIOOS Pacific ERDDAP dataset "
        f"<i>DFO_MEDS_BUOYS</i>. {interval}, stamped at hh:{minute:02d}. Record ends "
        f"{last_obs.day} {calendar.month_abbr[last_obs.month]} {last_obs.year}.",
        " ".join([qc] + ([screening_text(scr)] if scr else []) + st.get("report", {}).get("data_notes", [])),
        removed,
        "Hs is linearly interpolated between samples (across gaps of at most 2 h). The time above each threshold "
        f"({', '.join(f'{th:.2f}' for th in THRESHOLDS)} m) is then summed per UTC day, in decimal hours. "
        "Exceedances that start and end between two readings are missed, so precision finer than about half an "
        "hour is nominal.",
        f"Full days (at least {FULL_DAY_H} h covered) are scaled to 24 h by the covered fraction and drawn in the year colour.",
        f"Partial days (less than {FULL_DAY_H} h covered) are hatched. The hours actually measured above each threshold "
        "on those days are drawn in nested greys, not scaled up. In the monthly figures each partial day is labelled "
        "with its hours of data. Partial days are not included in the monthly summary table.",
        f"Each bar shows all {len(THRESHOLDS)} thresholds nested. The darkest shade is the time above "
        f"{THRESHOLDS[-1]:.2f} m; progressively lighter bands show the time above "
        + _join([f"{th:.2f}" for th in THRESHOLDS[-2::-1]]) + f" m, so the full bar height is the time above "
        f"{THRESHOLDS[0]:.2f} m. The 3.50 and 4.00 m bands are darker than the year colour.",
        "The daily figures use a common 365-day axis, so 29 February 2024 is not drawn; it is included in the "
        "monthly summary table and the CSV files.",
    ]


def caveats_text(years, incomplete, st, cov=None):
    n = len(years)
    part = f", {len(incomplete)} of them partial" if incomplete else ""
    return [f"Only {n} year{'s' if n != 1 else ''} of data{part}. Treat monthly means as indicative.",
            *gap_text(cov),
            *st.get("report", {}).get("caveats_extra", []),
            "Grey (partial-day) values are lower bounds: they count only the hours that were measured.",
            'The "time above threshold" counts every exceedance, however brief. A workable weather window also has '
            "to be long enough for the planned operation (for example a 12 h ROV dive). That is a separate "
            "calculation from these daily totals."]


def _n(k, one, many):
    return f"{k} {one if k == 1 else many}"


def screening_text(scr):
    jumps = _n(scr["jumps"], "hour-to-hour jump", "hour-to-hour jumps") + " larger than 2.5 m"
    if scr["jumps"]:
        jumps += " (" + _join([f"{x} UTC" for x in scr["jump_times"]]) + ")"
    return ("Automated screening: " + _n(scr["low_values"], "value", "values") + " at or below 0.2 m, "
            + _n(scr["isolated_spikes"], "isolated spike", "isolated spikes") + " (more than 2 m above or below "
            "both neighbours), " + jumps + ", and a longest run of "
            + _n(scr["longest_identical_run"], "identical consecutive value", "identical consecutive values") + ".")


def gap_text(cov):
    out = []
    for g in (cov or {}).get("gaps", []):
        span = f"about {g['days'] / 30.4:.0f} months" if g["days"] >= 60 else f"{g['days']} days"
        out.append(f"Coverage gap: no wave data from {W.month_year(g['from'])} to {W.month_year(g['to'])} ({span}).")
    return out


def comparison_text(st, comps, stations_by_id):
    """One bullet comparing this buoy with its nearest neighbours (computed each run)."""
    if not comps:
        return None
    parts = []
    for oid, c in comps.items():
        o = stations_by_id[oid]
        km = W.distance_km((st["lat"], st["lon"]), (o["lat"], o["lon"]))
        x = W.ratio_phrase(c, f"{o['name']}, {km:.0f} km away") + f" (r = {c['r0']:.2f} at the same hour"
        lp = W.lag_phrase(c, "it")
        x += (f"; sea states here {lp}, r = {c['r_lag']:.2f})" if lp else ")")
        parts.append(x)
    period = next(iter(comps.values()))["period"]
    return (f"Compared with the nearest buoys (hourly Hs where both have data, {period}): hourly Hs here is "
            + _join(parts) + ".")


# ---- PDF ---------------------------------------------------------------------------
def build_pdf(fn, st, years, t, kr_groups, method, cav, season_png, month_pngs):
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=15, leading=18, alignment=0, spaceAfter=4)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, leading=14, spaceBefore=6, spaceAfter=3,
                        keepWithNext=1)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.2, leading=12)
    BL = ParagraphStyle("bl", parent=B, leftIndent=10, bulletIndent=0)
    CAP = ParagraphStyle("cap", parent=B, fontSize=8.2, leading=10, textColor=colors.HexColor("#444444"))
    bullets = lambda L: [Paragraph(x, BL, bulletText="•") for x in L]
    H3 = ParagraphStyle("h3", parent=B, fontName="Helvetica-Bold", spaceBefore=4, spaceAfter=1, keepWithNext=1)
    kr = [z for head, L in kr_groups if L for z in [Paragraph(head, H3), *bullets(L)]]
    long_name, short_name = season_names()

    def img(p, w):
        iw, ih = PILImage.open(p).size
        return Image(str(p), width=w, height=w * ih / iw)

    sid, name = st["id"], st["name"]
    y0, y1 = min(years), max(years)
    yrs_txt = _join([f"{y} ({'blue' if y == 2024 else 'orange' if y == 2025 else 'purple' if y == 2026 else 'colour key'})"
                     for y in years])
    fmt = lambda v: "–" if pd.isna(v) else f"{v:.1f}"
    TCOLS = (2.0, 3.0, 4.0)                      # thresholds shown in the monthly table
    hdr = (["Month"] + [f"{y}\n>{th:g} m" for th in TCOLS for y in years] + [f"n {y}" for y in years])
    rows = [hdr] + [[calendar.month_abbr[m]]
                    + [fmt(t.loc[(y, m), f"h_gt_{th:.2f}"]) for th in TCOLS for y in years]
                    + [str(int(t.loc[(y, m), "n_days"])) for y in years] for m in SEASON]
    ny = len(years)
    vw = min(0.62, (7.2 - 0.6) / (len(TCOLS) * ny + 0.8 * ny)) * inch
    tbl = Table(rows, colWidths=[0.6 * inch] + [vw] * (len(TCOLS) * ny) + [0.8 * vw] * ny)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
             ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
             ("LINEBELOW", (0, -1), (-1, -1), 0.6, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")])]
    for k, y in enumerate(years):
        for c in [1 + j * ny + k for j in range(len(TCOLS))]:
            style.append(("TEXTCOLOR", (c, 0), (c, 0), colors.HexColor(year_colour(y))))
    tbl.setStyle(TableStyle(style))

    def footer(c, doc):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.grey)
        c.drawString(0.6 * inch, 0.45 * inch,
                     f"{sid} {name} wave exceedance, {short_name} {y0}–{y1} · data: DFO MEDS via CIOOS Pacific ERDDAP")
        c.drawRightString(letter[0] - 0.6 * inch, 0.45 * inch, f"{doc.page}")

    s = [Paragraph(f"Wave-height exceedance at {name} (buoy {sid}), {long_name} {y0}–{y1}", H1),
         Paragraph("Purpose: estimate how much of each day is lost to sea state, to help size the weather-day "
                   "allowance in ship-time requests off the west coast of Vancouver Island.", B),
         Paragraph("Key results", H2), *kr, Spacer(1, 6), img(season_png, 7.0 * inch),
         Paragraph(f"Figure 1. Daily time with Hs above {TH_RANGE}, 1 {calendar.month_name[SEASON[0]]} – "
                   f"{calendar.monthrange(2001, SEASON[-1])[1]} {calendar.month_name[SEASON[-1]]}, for {yrs_txt}. "
                   f"Darkest band: time above {THRESHOLDS[-1]:.2f} m; full bar: time above {THRESHOLDS[0]:.2f} m. "
                   "Hatched: less than 20 h of data; grey bars on those days are the measured hours above each "
                   "threshold (not scaled).", CAP),
         Spacer(1, 8), Paragraph("Monthly summary", H2),
         Paragraph("Mean decimal hours per day with Hs above 2 m, 3 m and 4 m, over full days only "
                   f"(at least {FULL_DAY_H} h of data), with the number of full days (n). The values for all "
                   f"{len(THRESHOLDS)} thresholds are in the accompanying CSV.", B), Spacer(1, 4), tbl, Spacer(1, 6),
         Paragraph("Data and method", H2), *bullets(method), Paragraph("Caveats", H2), *bullets(cav),
         PageBreak(), Paragraph("Monthly detail", H2)]
    for i, (m, p) in enumerate(month_pngs):
        s.append(KeepTogether([img(p, 6.6 * inch),
                               Paragraph(f"Figure {i + 2}. {calendar.month_name[m]}: daily time with Hs above "
                                         f"{TH_RANGE}, {y0}–{y1}. Darkest band: above {THRESHOLDS[-1]:.2f} m. Hatched: less than "
                                         "20 h of data; grey: measured hours on those days; rotated labels give the "
                                         "hours of data.", CAP), Spacer(1, 8)]))
    SimpleDocTemplate(str(fn), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                      topMargin=0.55 * inch, bottomMargin=0.7 * inch).build(s, onFirstPage=footer, onLaterPages=footer)


# ---- driver ------------------------------------------------------------------------
def run_station(st, data, out, pdf_dir, stations_by_id):
    sid = st["id"]
    print(f"{sid} {st['name']}")
    root = out / sid
    df_raw, d, h = data[sid]
    if d.empty:
        print("  no valid data; skipped")
        return None
    last_obs = d["time"].max()
    years = list(range(int(RECORD_START[:4]), last_obs.year + 1))
    day = daily_exceedance(d, years)
    years = [y for y in years if day.loc[day.index.year == y, "coverage_h"].sum() > 0]
    t = monthly_table(day, years)
    y0, y1 = min(years), max(years)
    (root / "data").mkdir(parents=True, exist_ok=True)
    day.round(2).to_csv(root / "data" / f"{sid}_daily_hours_above_Hs_thresholds_{y0}-{y1}.csv")
    tm = t.copy()
    tm.columns = [c.replace("h_gt_", "mean_h_per_day_gt_") + ("m" if c.startswith("h_gt") else "") for c in tm.columns]
    tm.to_csv(root / "data" / f"{sid}_monthly_mean_hours_above_Hs_thresholds_{y0}-{y1}.csv")
    season_png, month_pngs = make_figures(day, years, st, root / "figures")
    # computed data facts (same functions as the dashboard)
    cov = W.coverage(h, years, SEASON)
    nearest = sorted((o for o in stations_by_id.values() if o["id"] != sid and not data[o["id"]][1].empty),
                     key=lambda o: W.distance_km((st["lat"], st["lon"]), (o["lat"], o["lon"])))[:N_COMPARE]
    comps = {o["id"]: c for o in nearest if (c := W.compare(h, data[o["id"]][2]))}
    scr = W.screen(df_raw, d)
    kr, complete, incomplete = key_results(t, day, years, last_obs, st, comparison_text(st, comps, stations_by_id))
    method = method_text(d, df_raw, st, last_obs, scr)
    cav = caveats_text(years, incomplete, st, cov)
    (root / "report").mkdir(parents=True, exist_ok=True)
    pdf = root / "report" / f"{sid}_wave_exceedance_report_{y0}-{y1}.pdf"
    build_pdf(pdf, st, years, t, kr, method, cav, season_png, month_pngs)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    fixed = pdf_dir / f"{sid}_wave_exceedance_report.pdf"
    fixed.write_bytes(pdf.read_bytes())
    print(f"  years {years}; complete years {complete}; report -> {fixed}")
    return fixed


RECORD_START = "2024-01-01"


def main(argv=None):
    global RECORD_START, SEASON
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stations", nargs="*", help="station ids to report on (default: all in stations.json)")
    ap.add_argument("--config", default=str(ROOT / "stations.json"))
    ap.add_argument("--out", default=str(HERE / "output"), help="full outputs (default: reports/output)")
    ap.add_argument("--pdf-dir", default=str(HERE / "pdf"), help="latest PDFs under fixed names (default: reports/pdf)")
    ap.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"), help="raw downloads (default: data/raw)")
    ap.add_argument("--from-raw", action="store_true", help="read <raw-dir>/<ID>.csv instead of downloading")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text())
    RECORD_START = cfg["record_start"]
    SEASON = range(cfg["season"]["first_month"], cfg["season"]["last_month"] + 1)
    sts = [s for s in cfg["stations"] if not a.stations or s["id"] in a.stations]
    if not sts:
        sys.exit(f"no matching stations in {a.config}")
    raw_dir = Path(a.raw_dir)
    data = {}
    for s in cfg["stations"]:                       # all stations, for the comparisons
        raw = raw_dir / f"{s['id']}.csv"
        if a.from_raw:
            df = W.read_raw(raw)
        else:
            print(f"  downloading {s['id']} from CIOOS ERDDAP ...")
            df = W.download_raw(s["source_station_id"], RECORD_START, raw)
        df = df[df["time"] >= pd.Timestamp(RECORD_START, tz="UTC")]
        d = W.clean(df)
        data[s["id"]] = (df, d, W.hourly(d))
    apply_style()
    out = Path(a.out).resolve()
    by_id = {s["id"]: s for s in cfg["stations"]}
    for st in sts:
        run_station(st, data, out, Path(a.pdf_dir), by_id)
    print(f"done {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")


if __name__ == "__main__":
    try:
        main()
    except W.DownloadError as e:
        sys.exit(f"BUILD STOPPED: {e}")
