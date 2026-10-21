/* Cruise-planning wave dashboard: UI, table and plots. Calculations live in calc.js. */
(function () {
  "use strict";
  const D = window.WAVE_DATA, C = window.WaveCalc;

  // ---- settings that are easy to change -----------------------------------
  const CONFIG = {
    limitMin: 2.0, limitMax: 3.0, limitStep: 0.05, limitDefault: 2.5,
    curveMin: 1.0, curveMax: 4.0, curveStep: 0.1,    // x range of the sensitivity plot
    partialFrac: 0.8,                                 // flag rows with less data than this
    maxDays: 120,
    fullDayH: 20,                                     // overview: a day counts if it has this many hours of data
    runDays: 7,                                       // overview: running-mean length (days)
  };
  const YEAR_COLOURS = { 2024: "#1f5fa8", 2025: "#d9661f", 2026: "#6a3d9a" };
  const EXTRA_COLOURS = ["#2a9d8f", "#b5179e", "#8c564b", "#c9a227", "#264653", "#e76f51"];
  const STATION_DASH = ["solid", "dot", "dash", "longdash", "dashdot"];
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                  "August", "September", "October", "November", "December"];
  const REF_YEAR = 2001;                              // non-leap year used for the shared date axis
  // ---------------------------------------------------------------------------

  const firstMonth = D.season.first_month, lastMonth = D.season.last_month;
  const stations = D.stations.map((s, k) => ({ ...s, series: C.stationSeries(s), dash: STATION_DASH[k % STATION_DASH.length] }));
  const firstYear = parseInt(D.record_start.slice(0, 4), 10);
  const lastYear = Math.max(...stations.filter(s => s.series.t.length)
    .map(s => new Date(s.series.t[s.series.t.length - 1]).getUTCFullYear()));
  const years = []; for (let y = firstYear; y <= lastYear; y++) years.push(y);

  function yearColour(y) {
    if (YEAR_COLOURS[y]) return YEAR_COLOURS[y];
    const k = ((y - 2027) % EXTRA_COLOURS.length + EXTRA_COLOURS.length) % EXTRA_COLOURS.length;
    return EXTRA_COLOURS[k];
  }
  const daysInMonth = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
  const fmtDate = ms => { const d = new Date(ms); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()].slice(0, 3)}`; };
  const f1 = v => (v === null || isNaN(v)) ? "–" : v.toFixed(1);
  // Plotly date strings carry no time zone; all times here are UTC.
  const pdate = ms => new Date(ms).toISOString().slice(0, 19).replace("T", " ");
  const parsePdate = s => {
    if (typeof s === "number") return s;
    let x = String(s).trim().replace(" ", "T");
    if (x.length <= 10) x += "T00:00";
    return Date.parse(x + "Z");
  };
  const SEASON_START = Date.UTC(REF_YEAR, firstMonth - 1, 1);
  const SEASON_END = Date.UTC(REF_YEAR, lastMonth, 1);          // exclusive
  const SEASON_DAYS = Math.round((SEASON_END - SEASON_START) / C.DAY);

  // ---- controls --------------------------------------------------------------
  const el = id => document.getElementById(id);
  const startMonth = el("startMonth"), startDay = el("startDay"), nDaysIn = el("nDays"), limitIn = el("limit");
  for (let m = firstMonth; m <= lastMonth; m++) startMonth.add(new Option(MONTHS[m - 1], m));
  startMonth.value = 6;
  nDaysIn.max = CONFIG.maxDays;
  Object.assign(limitIn, { min: CONFIG.limitMin, max: CONFIG.limitMax, step: CONFIG.limitStep, value: CONFIG.limitDefault });
  const boxes = el("stationBoxes");
  stations.forEach((s, k) => {
    const lab = document.createElement("label"); lab.className = "chk";
    lab.innerHTML = `<input type="checkbox" value="${k}" checked> ${s.name} (${s.id})`;
    boxes.appendChild(lab);
  });
  const last = stations.map(s => s.last_obs_utc).filter(Boolean).sort().pop();
  el("updated").textContent = `Data file built ${D.generated_utc}; latest observation ${last}.`;

  function readInputs() {
    const m = parseInt(startMonth.value, 10);
    const dmax = daysInMonth(REF_YEAR, m);
    let d = Math.min(Math.max(parseInt(startDay.value, 10) || 1, 1), dmax);
    let n = Math.min(Math.max(parseInt(nDaysIn.value, 10) || 1, 1), CONFIG.maxDays);
    startDay.max = dmax;
    const limit = parseFloat(limitIn.value);
    const sel = [...boxes.querySelectorAll("input:checked")].map(b => stations[+b.value]);
    return { m, d, n, limit, sel };
  }

  // ---- calculations ----------------------------------------------------------
  function evaluate(inp) {
    const rows = [];
    for (const st of inp.sel) {
      let sumAbove = 0, sumCov = 0, bestCalm = 0, winH = 0, nYears = 0;
      for (const y of years) {
        const w = C.cruiseWindow(y, inp.m, inp.d, inp.n, lastMonth);
        winH = (w.end - w.start) / C.HOUR;
        const ex = C.exceedance(st.series, w.start, w.end, inp.limit);
        const r = { st, year: y, winH, cov: ex.coverage_h, above: ex.above_h };
        if (ex.coverage_h > 0) {
          r.pct = 100 * ex.above_h / ex.coverage_h;
          r.daysLost = r.pct / 100 * winH / 24;
          r.calm = C.longestCalm(st.series, w.start, w.end, inp.limit);
          sumAbove += ex.above_h; sumCov += ex.coverage_h; bestCalm = Math.max(bestCalm, r.calm); nYears++;
        }
        rows.push(r);
      }
      if (nYears > 1) {
        const pct = 100 * sumAbove / sumCov;
        rows.push({ st, pooled: true, nYears, winH, cov: sumCov, above: sumAbove, pct,
                    daysLost: pct / 100 * winH / 24, calm: bestCalm });
      }
    }
    return rows;
  }

  // ---- rendering -------------------------------------------------------------
  function renderWindowNote(inp) {
    const w = C.cruiseWindow(REF_YEAR, inp.m, inp.d, inp.n, lastMonth);
    const days = (w.end - w.start) / C.DAY;
    const note = el("windowNote");
    note.className = "note" + (w.clipped ? " warn" : "");
    note.textContent = `Window: ${fmtDate(w.start)} – ${fmtDate(w.end - 1)} (${days} days), evaluated in ${years.join(", ")}.` +
      (w.clipped ? ` The cruise runs past 30 November; only the days up to 30 November are evaluated.` : "");
    return days;
  }

  function renderTable(rows) {
    const head = `<thead><tr><th>Buoy</th><th>Year</th><th>Data in window (h)</th><th>Hours above limit</th>
      <th>% of measured time</th><th>Equivalent days lost</th><th>Longest calm spell (h)</th></tr></thead>`;
    const body = rows.map(r => {
      if (r.pooled) {
        return `<tr class="pooled"><td>${r.st.name}</td><td>All ${r.nYears} years</td><td>${f1(r.cov)}</td>
          <td>${f1(r.above)}</td><td>${f1(r.pct)}</td><td>${f1(r.daysLost)}</td><td>${f1(r.calm)}</td></tr>`;
      }
      if (!(r.cov > 0)) {
        return `<tr class="nodata"><td>${r.st.name}</td><td><span class="swatch" style="background:${yearColour(r.year)}"></span>${r.year}</td>
          <td colspan="5" style="text-align:left">no data in this window</td></tr>`;
      }
      const part = r.cov < CONFIG.partialFrac * r.winH ? ` <span class="partial">partial</span>` : "";
      return `<tr><td>${r.st.name}</td><td><span class="swatch" style="background:${yearColour(r.year)}"></span>${r.year}</td>
        <td>${f1(r.cov)} of ${f1(r.winH)}${part}</td><td>${f1(r.above)}</td><td>${f1(r.pct)}</td>
        <td>${f1(r.daysLost)}</td><td>${f1(r.calm)}</td></tr>`;
    }).join("");
    el("results").innerHTML = inp_sel_empty() ? `<p class="note">Select at least one buoy.</p>` : `<table>${head}<tbody>${body}</tbody></table>`;
  }
  const inp_sel_empty = () => !boxes.querySelector("input:checked");

  function renderTimeSeries(inp) {
    const holder = el("tsPlots");
    // keep one plot div per selected station
    const wanted = inp.sel.map(s => "ts_" + s.id);
    [...holder.children].forEach(c => { if (!wanted.includes(c.id)) { Plotly.purge(c); c.remove(); } });
    inp.sel.forEach(st => {
      let div = el("ts_" + st.id);
      if (!div) { div = document.createElement("div"); div.id = "ts_" + st.id; div.className = "plot"; holder.appendChild(div); }
      const traces = []; let ymax = 0;
      const ref = C.cruiseWindow(REF_YEAR, inp.m, inp.d, inp.n, lastMonth);
      for (const y of years) {
        const w = C.cruiseWindow(y, inp.m, inp.d, inp.n, lastMonth);
        const off = w.start - ref.start;
        const p = C.plotPoints(st.series, w.start, w.end);
        if (!p.x.length) continue;
        p.y.forEach(v => { if (v !== null && v > ymax) ymax = v; });
        traces.push({ x: p.x.map(t => pdate(t - off)), y: p.y, name: String(y), type: "scatter", mode: "lines",
          line: { color: yearColour(y), width: 1.6 }, connectgaps: false,
          hovertemplate: `${y} %{x|%d %b %H:%M} UTC<br>Hs %{y:.1f} m<extra></extra>` });
      }
      const layout = {
        title: { text: `${st.name} (${st.id})`, x: 0, xanchor: "left", font: { size: 14 } },
        height: 300, margin: { l: 55, r: 20, t: 36, b: 40 },
        xaxis: { type: "date", tickformat: "%d %b", range: [pdate(ref.start), pdate(ref.end)] },
        yaxis: { title: { text: "Hs (m)" }, rangemode: "tozero", range: [0, Math.max(5, Math.ceil(ymax + 0.5))] },
        shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: inp.limit, y1: inp.limit, line: { color: "#1d2733", width: 1.2, dash: "dash" } }],
        annotations: [{ xref: "paper", x: 1, y: inp.limit, yanchor: "bottom", xanchor: "right", showarrow: false,
          text: `limit ${inp.limit.toFixed(2)} m`, font: { size: 11, color: "#1d2733" } }],
        legend: { orientation: "h", x: 0, y: -0.18 }, hovermode: "closest",
      };
      if (!traces.length) layout.annotations.push({ xref: "paper", yref: "paper", x: 0.5, y: 0.5, showarrow: false, text: "No data in this window", font: { size: 14, color: "#9aa3ad" } });
      Plotly.react(div, traces, layout, { displaylogo: false, responsive: true });
    });
  }

  function renderCurve(inp) {
    const xs = []; for (let v = CONFIG.curveMin; v <= CONFIG.curveMax + 1e-9; v += CONFIG.curveStep) xs.push(+v.toFixed(2));
    const traces = [];
    for (const st of inp.sel) for (const y of years) {
      const w = C.cruiseWindow(y, inp.m, inp.d, inp.n, lastMonth);
      const ys = xs.map(lim => { const ex = C.exceedance(st.series, w.start, w.end, lim); return ex.coverage_h > 0 ? 100 * ex.above_h / ex.coverage_h : null; });
      if (ys.every(v => v === null)) continue;
      traces.push({ x: xs, y: ys, name: `${st.name} ${y}`, type: "scatter", mode: "lines",
        line: { color: yearColour(y), dash: st.dash, width: 1.8 },
        hovertemplate: `${st.name} ${y}<br>limit %{x:.2f} m: %{y:.0f}% of time above<extra></extra>` });
    }
    const layout = {
      height: 340, margin: { l: 60, r: 20, t: 10, b: 45 },
      xaxis: { title: { text: "Hs limit (m)" }, range: [CONFIG.curveMin, CONFIG.curveMax] },
      yaxis: { title: { text: "% of measured time above limit" }, range: [0, 100] },
      shapes: [{ type: "line", yref: "paper", x0: inp.limit, x1: inp.limit, y0: 0, y1: 1, line: { color: "#1d2733", width: 1.2, dash: "dash" } }],
      legend: { orientation: "v", x: 1.02, y: 1 }, hovermode: "closest",
    };
    Plotly.react(el("curvePlot"), traces, layout, { displaylogo: false, responsive: true });
  }

  // ---- overview: average daily hours above the limit, with a draggable cruise window ----
  /** Daily mean (over selected buoys and all years) of hours with Hs above the limit, Mar–Nov. */
  function overviewData(inp) {
    const sum = new Float64Array(SEASON_DAYS), cnt = new Int32Array(SEASON_DAYS);
    for (const st of inp.sel) for (const y of years) {
      const y0 = Date.UTC(y, firstMonth - 1, 1);
      for (let k = 0; k < SEASON_DAYS; k++) {
        const a = y0 + k * C.DAY;
        const ex = C.exceedance(st.series, a, a + C.DAY, inp.limit);
        if (ex.coverage_h >= CONFIG.fullDayH) { sum[k] += 24 * ex.above_h / ex.coverage_h; cnt[k]++; }
      }
    }
    const mean = Array.from(sum, (s, k) => cnt[k] ? s / cnt[k] : null);
    const half = Math.floor(CONFIG.runDays / 2), need = Math.ceil(CONFIG.runDays / 2);
    const run = mean.map((_, k) => {
      let s = 0, n = 0;
      for (let j = Math.max(0, k - half); j <= Math.min(SEASON_DAYS - 1, k + half); j++) if (mean[j] !== null) { s += mean[j]; n++; }
      return n >= need ? s / n : null;
    });
    return { mean, run, cnt: Array.from(cnt) };
  }

  let rendering = false;
  function renderOverview(inp) {
    const div = el("overviewPlot");
    const ov = overviewData(inp);
    const w = C.cruiseWindow(REF_YEAR, inp.m, inp.d, inp.n, lastMonth);
    const xs = ov.mean.map((_, k) => pdate(SEASON_START + k * C.DAY + C.DAY / 2));
    const k0 = Math.round((w.start - SEASON_START) / C.DAY), k1 = Math.round((w.end - SEASON_START) / C.DAY);
    const inWin = ov.mean.slice(k0, k1).filter(v => v !== null);
    const winMean = inWin.length ? inWin.reduce((a, b) => a + b, 0) / inWin.length : null;
    const nDays = k1 - k0;
    const label = winMean === null ? "no data" :
      `${fmtDate(w.start)} – ${fmtDate(w.end - 1)} (${nDays} d)<br>mean ${winMean.toFixed(1)} h/day above limit<br>≈ ${(winMean / 24 * nDays).toFixed(1)} days lost`;
    const traces = [
      { x: xs, y: ov.mean, type: "bar", name: "Daily mean", marker: { color: "#c9ced4" }, width: C.DAY * 0.95,
        customdata: ov.cnt, hovertemplate: "%{x|%d %b}: %{y:.1f} h above limit<br>mean of %{customdata} buoy-years<extra></extra>" },
      { x: xs, y: ov.run, type: "scatter", mode: "lines", name: `${CONFIG.runDays}-day running mean`,
        line: { color: "#1d2733", width: 2.4 }, connectgaps: false, hoverinfo: "skip" },
    ];
    const layout = {
      height: 330, margin: { l: 55, r: 20, t: 10, b: 40 }, bargap: 0,
      xaxis: { type: "date", tickformat: "%b", dtick: "M1", range: [pdate(SEASON_START), pdate(SEASON_END)], fixedrange: true },
      yaxis: { title: { text: `Hours above ${inp.limit.toFixed(2)} m per day` }, range: [0, 24.5], tickvals: [0, 6, 12, 18, 24], fixedrange: true },
      shapes: [{ type: "rect", xref: "x", yref: "paper", x0: pdate(w.start), x1: pdate(w.end), y0: 0, y1: 1,
                 fillcolor: "rgba(242,193,78,0.30)", line: { color: "#b8860b", width: 1.5 }, editable: true, layer: "below" }],
      annotations: [{ xref: "x", yref: "paper", x: pdate((w.start + w.end) / 2), y: 1, yanchor: "top", showarrow: false,
                      text: label, font: { size: 11, color: "#6b4e00" }, bgcolor: "rgba(255,255,255,0.75)" }],
      legend: { orientation: "h", x: 0, y: -0.14 }, hovermode: "closest", dragmode: false,
    };
    rendering = true;
    Plotly.react(div, traces, layout, { displaylogo: false, responsive: true, edits: { shapePosition: true } });
    rendering = false;
    if (!div._cruiseHandler) { div._cruiseHandler = true; div.on("plotly_relayout", onOverviewDrag); }
  }

  /** Dragging or resizing the shaded window sets the start date and length (snapped to whole days). */
  function onOverviewDrag(ev) {
    if (rendering || !ev) return;
    let x0 = ev["shapes[0].x0"], x1 = ev["shapes[0].x1"];
    if (x0 === undefined && x1 === undefined && Array.isArray(ev.shapes) && ev.shapes[0]) { x0 = ev.shapes[0].x0; x1 = ev.shapes[0].x1; }
    if (x0 === undefined && x1 === undefined) return;
    const inp = readInputs();
    const cur = C.cruiseWindow(REF_YEAR, inp.m, inp.d, inp.n, lastMonth);
    const t0 = x0 !== undefined ? parsePdate(x0) : cur.start, t1 = x1 !== undefined ? parsePdate(x1) : cur.end;
    let s = Math.round((Math.min(t0, t1) - SEASON_START) / C.DAY), e = Math.round((Math.max(t0, t1) - SEASON_START) / C.DAY);
    s = Math.min(Math.max(s, 0), SEASON_DAYS - 1);
    e = Math.min(Math.max(e, s + 1), SEASON_DAYS, s + CONFIG.maxDays);
    const d = new Date(SEASON_START + s * C.DAY);
    startMonth.value = d.getUTCMonth() + 1;
    startDay.value = d.getUTCDate();
    nDaysIn.value = e - s;
    update();
  }

  // ---- update loop ------------------------------------------------------------
  let pending = false;
  function update() {
    if (pending) return; pending = true;
    requestAnimationFrame(() => {
      pending = false;
      const inp = readInputs();
      el("limitOut").textContent = inp.limit.toFixed(2);
      renderWindowNote(inp);
      renderOverview(inp);
      renderTable(evaluate(inp));
      renderTimeSeries(inp);
      renderCurve(inp);
    });
  }
  [startMonth, startDay, nDaysIn, limitIn].forEach(x => x.addEventListener("input", update));
  boxes.addEventListener("change", update);
  update();
})();
