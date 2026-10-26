#!/usr/bin/env python3
"""Convert the ONC backbone-cable KML into the small GeoJSON drawn on the dashboard map.

    python scripts/make_cable_geojson.py /path/to/ONC_BackboneCables_20150120.kml

Run by hand only when ONC issues a new cable file; the output (assets/neptune_cable.geojson) is
committed, so the weekly build never needs the KML. Only named NEPTUNE pieces are kept (the
unnamed VENUS segments in the Strait of Georgia lie outside the map), and each line is simplified
(Douglas-Peucker) so the file stays small; the tolerance is far below one screen pixel.
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "neptune_cable.geojson"
TOL_DEG = 0.0015          # ~150 m; the map shows ~10 degrees across ~1000 px (0.01 deg per px)


def simplify(pts, tol):
    """Douglas-Peucker on (lon, lat) points, keeping the first and last point."""
    pts = np.asarray(pts, float)
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), bool); keep[[0, -1]] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        a, b = pts[i], pts[j]
        seg = pts[i + 1:j]
        if not len(seg):
            continue
        d = b - a
        L = np.hypot(*d)
        dist = (np.abs(d[0] * (seg[:, 1] - a[1]) - d[1] * (seg[:, 0] - a[0])) / L) if L else np.hypot(*(seg - a).T)
        k = int(np.argmax(dist))
        if dist[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return pts[keep]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("kml")
    a = ap.parse_args()
    root = ET.parse(a.kml).getroot()
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    feats, n_in, n_out = [], 0, 0
    for pm in root.iter(ns + "Placemark"):
        name = (pm.findtext(ns + "name") or "").strip()
        if not name or name.upper() == "NULL":
            continue
        for c in pm.iter(ns + "coordinates"):
            pts = [tuple(map(float, p.split(",")[:2])) for p in c.text.split()]
            s = simplify(pts, TOL_DEG)
            n_in += len(pts); n_out += len(s)
            feats.append({"type": "Feature", "properties": {"name": name},
                          "geometry": {"type": "LineString",
                                       "coordinates": [[round(x, 5), round(y, 5)] for x, y in s]}})
    src = Path(a.kml).name
    date = re.search(r"(\d{8})", src)
    gj = {"type": "FeatureCollection",
          "properties": {"source": f"Ocean Networks Canada, {src}",
                         "source_date": f"{date.group(1)[:4]}-{date.group(1)[4:6]}-{date.group(1)[6:]}" if date else None,
                         "simplified_tolerance_deg": TOL_DEG},
          "features": feats}
    OUT.write_text(json.dumps(gj, separators=(",", ":")) + "\n")
    print(f"{len(feats)} lines, {n_in} -> {n_out} points; wrote {OUT} ({OUT.stat().st_size / 1e3:.1f} kB)")


if __name__ == "__main__":
    main()
