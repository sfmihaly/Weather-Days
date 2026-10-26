#!/usr/bin/env python3
"""Build everything for the website in one go.

    python scripts/build_site.py              # download fresh data, build data + reports + _site/
    python scripts/build_site.py --from-raw   # reuse data/raw/ (no download)
    python scripts/build_site.py --no-reports # dashboard data only (quicker)

Steps:
  1. scripts/build_data.py     -> data/wave_data.js (+ data/raw/<ID>.csv)
  2. reports/wavereports.py    -> reports/pdf/<ID>_wave_exceedance_report.pdf (+ reports/output/)
  3. assemble _site/           -> exactly what GitHub Pages publishes

After step 2 you can also open index.html straight from this folder: the dashboard, the data and
the report links all work locally.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"


def run(*args):
    print("+", " ".join(str(a) for a in args), flush=True)
    rc = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT).returncode
    if rc:
        sys.exit(f"{args[0]} failed (exit code {rc}); see the message above. The site was not rebuilt.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build data, reports and the _site folder.")
    ap.add_argument("--from-raw", action="store_true", help="reuse data/raw instead of downloading")
    ap.add_argument("--no-reports", action="store_true", help="skip the PDF reports")
    ap.add_argument("--site-dir", default=str(ROOT / "_site"), help="where to assemble the site (default: _site)")
    a = ap.parse_args(argv)
    global SITE
    SITE = Path(a.site_dir)
    if SITE.exists() and not (SITE / ".nojekyll").exists():
        sys.exit(f"{SITE} exists but was not made by this script; refusing to replace it")

    run("scripts/build_data.py", *(["--from-raw"] if a.from_raw else []))
    if not a.no_reports:
        run("reports/wavereports.py", "--from-raw")          # reuse the download from step 1

    if SITE.exists():
        shutil.rmtree(SITE)                                 # _site/ is generated, never edited by hand
    (SITE / "data").mkdir(parents=True)
    shutil.copy2(ROOT / "index.html", SITE / "index.html")
    shutil.copytree(ROOT / "assets", SITE / "assets")
    for f in ("wave_data.js", "wave_data.json"):
        shutil.copy2(ROOT / "data" / f, SITE / "data" / f)
    pdf_dir = ROOT / "reports" / "pdf"
    if pdf_dir.exists():
        shutil.copytree(pdf_dir, SITE / "reports" / "pdf")
    (SITE / ".nojekyll").write_text("")
    n = sum(1 for _ in SITE.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"_site/ ready: {n} files, {size:.1f} MB")


if __name__ == "__main__":
    main()
