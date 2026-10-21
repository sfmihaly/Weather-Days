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
        traces.push({ x: p.x.map(t => new Date(t - off).toISOString()), y: p.y, name: String(y), type: "scatter", mode: "lines",
          line: { color: yearColour(y), width: 1.6 }, connectgaps: false,
          hovertemplate: `${y} %{x|%d %b %H:%M} UTC<br>Hs %{y:.1f} m<extra></extra>` });
      }
      const layout = {
        title: { text: `${st.name} (${st.id})`, x: 0, xanchor: "left", font: { size: 14 } },
        height: 300, margin: { l: 55, r: 20, t: 36, b: 40 },
        xaxis: { type: "date", tickformat: "%d %b", range: [new Date(ref.start).toISOString(), new Date(ref.end).toISOString()] },
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

  // ---- update loop ------------------------------------------------------------
  let pending = false;
  function update() {
    if (pending) return; pending = true;
    requestAnimationFrame(() => {
      pending = false;
      const inp = readInputs();
      el("limitOut").textContent = inp.limit.toFixed(2);
      renderWindowNote(inp);
      renderTable(evaluate(inp));
      renderTimeSeries(inp);
      renderCurve(inp);
    });
  }
  [startMonth, startDay, nDaysIn, limitIn].forEach(x => x.addEventListener("input", update));
  boxes.addEventListener("change", update);
  update();
})();
