/* Wave exceedance calculations for the cruise-planning dashboard.
 *
 * Hs is linearly interpolated between consecutive hourly samples, but only
 * across gaps of at most MAX_GAP_H hours; longer gaps count as "no data".
 * Time above a limit is integrated exactly along each interpolated segment.
 *
 * Works in the browser (window.WaveCalc) and in Node (module.exports) so the
 * numbers can be tested outside the page.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.WaveCalc = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const HOUR = 3600e3, DAY = 86400e3;
  const MAX_GAP_H = 2;

  /** Valid samples of one station: {t: ms UTC[], h: metres[]} */
  function stationSeries(st) {
    const t0 = Date.parse(st.t0), t = [], h = [];
    st.hs_dm.forEach((v, i) => { if (v !== null) { t.push(t0 + i * HOUR); h.push(v / 10); } });
    return { t, h };
  }

  /** First index with t[i] >= x */
  function lowerBound(t, x) {
    let lo = 0, hi = t.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (t[m] < x) lo = m + 1; else hi = m; }
    return lo;
  }

  /** Cruise window in a given year: [start, end) in ms UTC, clipped to the season end. */
  function cruiseWindow(year, month, day, nDays, lastMonth) {
    const start = Date.UTC(year, month - 1, day);
    const seasonEnd = Date.UTC(year, lastMonth, 1);          // 00:00 on the 1st of the month after lastMonth
    const end = Math.min(start + nDays * DAY, seasonEnd);
    return { start, end, clipped: start + nDays * DAY > seasonEnd };
  }

  /** Hours of data and hours with Hs > limit inside [a, b). */
  function exceedance(series, a, b, limit) {
    const { t, h } = series;
    let cov = 0, above = 0;
    for (let i = Math.max(0, lowerBound(t, a) - 1); i < t.length - 1 && t[i] < b; i++) {
      const t1 = t[i], t2 = t[i + 1];
      if (t2 - t1 > MAX_GAP_H * HOUR) continue;
      const s = Math.max(a, t1), e = Math.min(b, t2);
      if (e <= s) continue;
      cov += e - s;
      const h1 = h[i], h2 = h[i + 1];
      let as, ae;
      if (h1 > limit && h2 > limit) { as = t1; ae = t2; }
      else if (h1 <= limit && h2 <= limit) continue;
      else {
        const tc = t1 + (limit - h1) / (h2 - h1) * (t2 - t1);
        if (h1 > limit) { as = t1; ae = tc; } else { as = tc; ae = t2; }
      }
      const os = Math.max(as, s), oe = Math.min(ae, e);
      if (oe > os) above += oe - os;
    }
    return { coverage_h: cov / HOUR, above_h: above / HOUR };
  }

  /** Longest continuous spell (h) with data and Hs <= limit inside [a, b), 10-min resolution. */
  function longestCalm(series, a, b, limit) {
    const { t, h } = series, step = 10 * 60e3;
    let best = 0, run = 0, i = Math.max(0, lowerBound(t, a) - 1);
    for (let x = a; x < b; x += step) {
      while (i < t.length - 1 && t[i + 1] <= x) i++;
      let ok = false;
      if (i < t.length - 1 && t[i] <= x && t[i + 1] - t[i] <= MAX_GAP_H * HOUR) {
        const v = h[i] + (h[i + 1] - h[i]) * (x - t[i]) / (t[i + 1] - t[i]);
        ok = v <= limit;
      }
      run = ok ? run + step : 0;
      if (run > best) best = run;
    }
    return best / HOUR;
  }

  /** Points for plotting: x in ms, y in m, with null inserted at gaps > MAX_GAP_H. */
  function plotPoints(series, a, b) {
    const { t, h } = series, x = [], y = [];
    for (let i = Math.max(0, lowerBound(t, a)); i < t.length && t[i] < b; i++) {
      if (x.length && t[i] - x[x.length - 1] > MAX_GAP_H * HOUR) { x.push(t[i] - HOUR); y.push(null); }
      x.push(t[i]); y.push(h[i]);
    }
    return { x, y };
  }

  return { HOUR, DAY, MAX_GAP_H, stationSeries, cruiseWindow, exceedance, longestCalm, plotPoints };
});
