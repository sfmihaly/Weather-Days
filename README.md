# Sea-state weather days for cruise planning

A static web dashboard for estimating how much of a planned research cruise is likely to be lost to
sea state off the west coast of Vancouver Island.

You enter:
- the cruise start date (March–November);
- the cruise length;
- a significant wave height (Hs) limit between 2.00 and 3.00 m;
- the buoys to use.

The dashboard applies that calendar window to every year with buoy data and shows:
- the hourly Hs in the window for each year, with the limit marked;
- the hours above the limit, the percentage of measured time, the equivalent days lost and the
  longest calm spell, per buoy and year, plus all years pooled;
- how the percentage of time above the limit changes between 1 and 4 m.

It is a planning aid based on a short record (from 2024), not a forecast.

## Buoys

| ID | Name | Position |
|---|---|---|
| C46206 | La Perouse Bank | 48.83 N, 126.00 W |
| C46132 | South Brooks | 49.78 N, 127.88 W |

## Repository layout

```
index.html                  the dashboard (open directly in a browser, or serve with GitHub Pages)
assets/app.js               interface, table and plots
assets/calc.js              exceedance calculations (also runs under Node for testing)
assets/style.css
assets/plotly.min.js        Plotly.js 4.1.2, bundled so the page needs no external CDN (MIT, see PLOTLY_LICENSE.txt)
data/wave_data.js           hourly Hs for all buoys (generated; loaded by index.html)
data/wave_data.json         same content as JSON (generated)
stations.json               list of buoys and the record start date
scripts/build_data.py       downloads, cleans and writes the data files
.github/workflows/update-data.yml   weekly job that refreshes the data
```

## Viewing locally

Open `index.html` in a browser. All data is loaded from local files, so no server is needed.

## Updating the data

```
pip install -r requirements.txt
python scripts/build_data.py
```

On GitHub the workflow `Update buoy data` does this every Monday and commits the new data. You can
also run it by hand from the Actions tab.

## Adding a buoy

1. Add an entry to `stations.json`. For any buoy in the DFO MEDS archive this is enough:
   ```json
   {"id": "C46207", "name": "East Dellwood", "source": "cioos_dfo_meds",
    "source_station_id": "C46207", "lat": 50.87, "lon": -129.92}
   ```
   (Check the station's position before adding it.)
2. Run `python scripts/build_data.py`, or let the weekly workflow run.

The new buoy appears in the dashboard automatically. A buoy from another data source (for example
NOAA NDBC) needs a fetch function in `scripts/build_data.py`, registered in `SOURCES`.

To include earlier years, change `record_start` in `stations.json`. New years get colours
automatically.

## Map

The map beside the inputs shows the buoys (circles; click one to include or exclude it) and the
ONC NEPTUNE nodes (squares) on GEBCO shaded bathymetry.

- The node list is in `stations.json` under `map.reference_sites`. Positions come from the ONC
  Oceans 3.0 API (`/api/locations`).
- The initial view is set by `map.center` and `map.zoom`.
- After editing these, run `python scripts/build_data.py`.
- The bathymetry tiles load from the GEBCO Web Map Service, so they need an internet connection.
  Offline, the markers still show on a plain background.

## Method

- Hs comes from Fisheries and Oceans Canada, Marine Environmental Data Section (MEDS), via the CIOOS
  Pacific ERDDAP dataset `DFO_MEDS_BUOYS`.
  - The MEDS quality-controlled value (VCAR) is used where available, otherwise the buoy-reported
    value (VWH).
  - Since mid-2022 only buoy-reported values exist, and these have not been quality-controlled.
- Values flagged erroneous (4) or off position (7), and values outside 0.2–20 m, are removed.
- Samples are placed on an hourly UTC grid.
- Hs is interpolated linearly between samples across gaps of up to 2 h; longer gaps are treated as
  missing.
- The time above the limit is integrated exactly along each interpolated segment. Exceedances that
  start and end between two hourly readings are not seen.
- Percentages and days lost use measured time only.
  - Equivalent days lost = fraction of measured time above the limit × cruise length.
  - Years with data for less than 80% of the window are marked "partial".
- Cruise windows are limited to the March–November season. A cruise that runs past 30 November is
  evaluated only up to 30 November.

## Data licence and attribution

Data: Fisheries and Oceans Canada (MEDS) via CIOOS Pacific. Contains information licensed under the
Open Government Licence – Canada.

Code licence: to be decided by ONC.
