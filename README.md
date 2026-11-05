# Sea-state weather days for cruise planning

A static web dashboard for estimating how much of a planned research cruise is likely to be lost to
sea state off the west coast of Vancouver Island.

You enter:
- the cruise start date (any day of the year);
- the cruise length;
- a significant wave height (Hs) limit between 2.00 and 5.00 m;
- the buoys to use.

The dashboard applies that calendar window to every year with buoy data and shows:
- the hourly Hs in the window for each year, with the limit marked;
- the hours above the limit, the percentage of measured time, the equivalent days lost and the
  longest calm spell, per buoy and year, plus all years pooled;
- how the percentage of time above the limit changes between 1 and 6 m;
- a PDF report for each buoy (below).

It is a planning aid based on a short record (from 2024), not a forecast.

## Buoys

| ID | Name | Position |
|---|---|---|
| C46206 | La Perouse Bank | 48.83 N, 126.00 W |
| C46132 | South Brooks | 49.78 N, 127.88 W |
| C46036 | South Nomad (open ocean; not included by default) | 48.35 N, 133.94 W |

Facts such as complete years, data gaps and how each buoy compares with the others are
calculated every week, and shown in the dashboard notes and the reports.

## Repository layout

```
index.html                  the dashboard
assets/app.js               interface, table and plots
assets/calc.js              exceedance calculations (also runs under Node for testing)
assets/style.css
assets/plotly.min.js        Plotly.js 4.1.2, bundled so the page needs no external CDN (MIT, see PLOTLY_LICENSE.txt)
assets/bathymetry.jpg/.json GEBCO background image for the map, and the extent it covers
assets/neptune_cable.geojson NEPTUNE backbone cable drawn on the map (from ONC's 2015 KML)
stations.json               the buoys, map settings and hand-written report notes (one list for everything)
scripts/wavecommon.py       download, cleaning and data facts, shared by the dashboard and the reports
scripts/build_data.py       builds data/wave_data.js for the dashboard
scripts/build_site.py       builds everything: data, reports and the _site/ folder that is published
scripts/make_cable_geojson.py  converts ONC's cable KML to assets/neptune_cable.geojson (run by hand)
reports/wavereports.py      builds the PDF report for each buoy
requirements.txt            Python packages (versions pinned)
.github/workflows/update-data.yml   "Build and publish": weekly, and after every push
```

Generated, and not stored in git:
- `data/` (`wave_data.js`, `wave_data.json`, `raw/`);
- `reports/pdf/` (latest PDFs, fixed names);
- `reports/output/` (PDFs, figures and CSV tables per buoy);
- `_site/`.

## Publishing

See [PUBLISHING.md](PUBLISHING.md) for GitHub, GitHub Pages and the day-to-day git routine.

## Building and viewing locally

```
pip install -r requirements.txt     # once
python scripts/build_site.py        # download fresh data; build data, reports and _site/ (about 1–2 min)
```

Then open `index.html` in a browser. The data and the report links all work from the folder; no
server is needed. Options:
- `--no-reports`: only the dashboard data (quicker).
- `--from-raw`: reuse the last download in `data/raw/`.

On GitHub, the workflow **Build and publish** does the same every Monday, and after every push to
`main`, and publishes `_site/` to GitHub Pages. Nothing is committed back. If a step fails (for
example the data server is down), nothing is published and the previous site stays online. GitHub
emails the repository owner about the failed run.

## Reports

`reports/wavereports.py` makes a 9-page PDF for each buoy:
- the daily time with Hs above 2.00, 2.25, 2.50, 2.75, 3.00, 3.50 and 4.00 m, for 1 January –
  31 December of every year (season figure and twelve monthly figures);
- a monthly summary table (above 2, 3 and 4 m);
- key results, in three groups: March–November (the main ship-time season), December–February
  (per winter: December and the following January and February), and data coverage;
- data and method;
- caveats.

Calculated on every run:
- the key results;
- the coverage of each year and any gaps longer than 30 days;
- the automated screening (low values, spikes, sudden jumps, stuck values);
- the comparison with the three nearest other buoys: median ratio of hourly Hs, correlation, and the
  lead or lag that best lines up the two records.

Hand-written text, which is not recalculated, lives under `report` in `stations.json`:
- `data_notes`: added to the data-quality bullet, e.g. an explanation of a storm spike;
- `key_results_extra`: extra key-result bullets;
- `caveats_extra`: buoy-specific caveats, e.g. exposure.

Check this text from time to time, as the data grow.

```
python reports/wavereports.py               # all buoys (downloads fresh data)
python reports/wavereports.py --from-raw    # reuse data/raw (after build_data.py)
python reports/wavereports.py C46132        # one buoy (the others are still loaded for comparisons)
```

## Adding a buoy

1. Add an entry to `stations.json`. For any buoy in the DFO MEDS archive this is enough:
   ```json
   {"id": "C46207", "name": "East Dellwood", "source": "cioos_dfo_meds",
    "source_station_id": "C46207", "lat": 50.87, "lon": -129.92}
   ```
   (Check the station's position before adding it.)
   Optional fields:
   - `"default_selected": false` leaves the buoy unticked when the page opens.
   - `"summary"` is a one-line description, shown in the map hover and the notes under the inputs.
     Buoys with a summary or notes also show their calculated facts there.
   - `"notes"` is a list of hand-written notes shown under the inputs.
   - `"report"` holds `data_notes`, `key_results_extra` and `caveats_extra` for its PDF (see Reports).
2. Run `python scripts/build_site.py`. A new buoy usually widens the map, so this also downloads a new
   bathymetry image. Commit `stations.json` together with `assets/bathymetry.jpg` and
   `assets/bathymetry.json`, then push.

The new buoy then appears in the dashboard, gets its own report, and is included in the other
buoys' comparisons. A buoy from another data source (for example NOAA NDBC) needs its own download
function in `scripts/wavecommon.py`.

To include earlier years, change `record_start` in `stations.json`. New years get colours
automatically.

## Map

The map beside the inputs shows the buoys (circles; click one to include or exclude it) and the
ONC NEPTUNE nodes (squares) and the NEPTUNE backbone cable on GEBCO shaded bathymetry.

- The node list is in `stations.json` under `map.reference_sites`. Positions come from the ONC
  Oceans 3.0 API (`/api/locations`). Each node is labelled with its name; `label_position`
  (e.g. `"bottom right"`, `"top left"`, `"bottom center"`) sets which side the label goes, so it
  can be moved off the cable or another label.
- The cable is `assets/neptune_cable.geojson`, listed in `stations.json` under `map.lines`. It was
  made from ONC's `ONC_BackboneCables_20150120.kml` with
  `python scripts/make_cable_geojson.py <file.kml>`, which keeps the named NEPTUNE pieces (main
  ring from Port Alberni and the node spurs; the VENUS segments are outside the map) and
  simplifies them to about 150 m. Re-run it only if ONC issues a new cable file. The Endeavour
  spur in the 2015 file ends about 5 km east of the current node position.
- The map extent fits all buoys and nodes automatically, with a margin of `map.fit_padding_deg`
  degrees. To fix the extent instead, set `map.extent` to `[west, east, south, north]`.
- The bathymetry is one image, `assets/bathymetry.jpg`, downloaded from the GEBCO Web Map Service
  by `scripts/build_data.py` for that extent. It is stored in the repository, so the map works
  offline, and the weekly build does not depend on GEBCO's server.
- `assets/bathymetry.json` records the extent the image covers. The image is downloaded again only
  when that extent changes, e.g. after adding a buoy or node. If GEBCO cannot be reached, the
  previous image and its extent are kept, so the background still lines up with the markers.
- The map is drawn as an ordinary longitude–latitude chart, with latitude scaled to the
  mid-latitude so distances look right. Scroll to zoom and drag to pan. Double-click to reset.

## Method

- Hs comes from Fisheries and Oceans Canada, Marine Environmental Data Section (MEDS), via the CIOOS
  Pacific ERDDAP dataset `DFO_MEDS_BUOYS`.
  - The MEDS quality-controlled value (VCAR) is used where available, otherwise the buoy-reported
    value (VWH).
  - Since mid-2022 only buoy-reported values exist, and these have not been quality-controlled.
- Values flagged erroneous (4) or off position (7), and values outside 0.2–20 m, are removed. The
  rules are in `scripts/wavecommon.py` and apply to both the dashboard and the reports.
- Samples are placed on an hourly UTC grid.
- Hs is interpolated linearly between samples across gaps of up to 2 h; longer gaps are treated as
  missing.
- The time above the limit is integrated exactly along each interpolated segment. Exceedances that
  start and end between two hourly readings are not seen.
- Percentages and days lost use measured time only.
  - Equivalent days lost = fraction of measured time above the limit × cruise length.
  - Years with data for less than 80% of the window are marked "partial".
- The season is set in `stations.json` (`season.first_month`, `season.last_month`); it is now the
  whole year (1–12). A cruise that starts in December may run past 31 December; the days in January
  are evaluated with the January data of the following year. With a shorter season (e.g. 3–11) a
  cruise is evaluated only up to the end of the season.
- Days are matched by calendar date (month and day), so 29 February 2024 does not shift the rest of
  that year. The daily report figures use a common 365-day axis and leave 29 February out; it is
  included in the tables and CSV files.

## Data licence and attribution

Data: Fisheries and Oceans Canada (MEDS) via CIOOS Pacific. Contains information licensed under the
Open Government Licence – Canada.

Bathymetry: GEBCO Compilation Group, GEBCO grid, served by the GEBCO Web Map Service
(free to use with attribution). NEPTUNE node positions: Ocean Networks Canada.

Code licence: to be decided by ONC.
