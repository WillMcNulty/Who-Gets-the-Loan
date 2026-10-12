// Who Gets the Loan in Virginia?: renders window.VA (build_va.py) and window.VA_GEO with plain DOM and SVG.
// Every number on the page comes from VA. Blue is always white applicants; orange is always the comparison group.
(function () {
  "use strict";
  const R = window.VA, GEO = window.VA_GEO;
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, el = document) => el.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const Z = 1.959964;
  const GROUPS = R.meta.compare; // Black, Hispanic, Asian
  const ERAS = Object.keys(R.meta.eras);
  const SPEC_LABEL = { raw: "No controls", common: "Common controls + county", lender: "+ same lender", full: "+ underwriting (2018+)" };
  const SPEC_NOTE = {
    raw: "The raw difference in denial rates.",
    common: "Controls every year records: loan type, income, loan amount, loan-to-income, co-applicant, applicant sex, tract minority share and tract income, and the county (county-by-year fixed effects).",
    lender: "The common controls plus lender-by-year fixed effects, so applicants are compared with others at the same lender in the same year. The main comparison across all 22 years.",
    full: "The lender controls plus the fields HMDA added in 2018: debt-to-income band, combined loan-to-value band, property value, credit-score model and automated underwriting system. Shown from 2018 only.",
  };

  // ---- formatting -------------------------------------------------------------------------------------------
  const minus = (s) => String(s).replace(/^-/, "−");
  const pct = (v, d = 1) => (v == null || !isFinite(v) ? "–" : minus((100 * v).toFixed(d)) + "%");
  const pp = (v, d = 1) => (v == null || !isFinite(v) ? "–" : minus((100 * v).toFixed(d)) + " pp");
  const num = (v, d = 0) => (v == null ? "–" : minus(Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })));
  const ci = (lo, hi, f = pp) => `${f(lo)} to ${f(hi)}`;

  function el(tag, attrs = {}, text) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v; else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
    }
    if (text != null) e.textContent = text;
    return e;
  }
  function html(tag, attrs, inner) { const e = el(tag, attrs); e.innerHTML = inner; return e; }
  function sv(tag, attrs = {}, text) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  }
  function niceRange(lo, hi, n = 5) {
    const span = hi - lo || 1;
    const raw = span / n;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw);
    const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
    const out = [];
    for (let t = a; t <= b + step * 0.001; t += step) out.push(+t.toFixed(10));
    return out;
  }

  // ---- tooltip ----------------------------------------------------------------------------------------------
  const tip = $("#tip");
  function showTip(evt, title, rows) {
    tip.replaceChildren(el("div", { class: "t" }, title));
    for (const r of rows) {
      const row = el("div", { class: "r" });
      const k = el("span", { class: "k" });
      if (r.color) { const i = el("i"); i.style.background = r.color; k.append(i); }
      k.append(document.createTextNode(r.label));
      row.append(k, el("b", {}, r.value));
      tip.append(row);
    }
    tip.style.display = "block";
    let x, y;
    if (evt && evt.clientX != null && evt.type !== "focus") { x = evt.clientX; y = evt.clientY; }
    else { const b = evt.target.getBoundingClientRect(); x = b.left + b.width / 2; y = b.top; }
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let left = x + 14, top = y - h - 10;
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    if (top < 8) top = y + 16;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = top + "px";
  }
  const hideTip = () => { tip.style.display = "none"; };
  function hoverable(node, fn, label) {
    node.setAttribute("tabindex", "0");
    node.classList.add("mark");
    if (label) node.setAttribute("aria-label", label);
    node.addEventListener("pointermove", fn);
    node.addEventListener("focus", fn);
    node.addEventListener("pointerleave", hideTip);
    node.addEventListener("blur", hideTip);
  }

  function legend(host, items) {
    host.replaceChildren();
    for (const it of items) {
      const s = el("span");
      const i = el("i", { class: it.shape || "" });
      if (it.dash) { i.style.background = "none"; i.style.borderTop = `2px dashed ${css(it.color)}`; i.style.height = "0"; i.style.width = "16px"; }
      else i.style.background = css(it.color);
      s.append(i, document.createTextNode(it.label));
      host.append(s);
    }
  }
  function table(host, head, rows, opts = {}) {
    const t = el("table");
    const tr = el("tr");
    head.forEach((h, j) => tr.append(el("th", { class: (j && !(opts.textCols || []).includes(j) ? "num" : "") + ((opts.wrapCols || []).includes(j) ? " wrap" : "") }, h)));
    const th = el("thead");
    th.append(tr);
    t.append(th);
    const tb = el("tbody");
    rows.forEach((r) => {
      const row = el("tr");
      r.forEach((c, j) => row.append(el("td", { class: (j && !(opts.textCols || []).includes(j) ? "num" : "") + ((opts.wrapCols || []).includes(j) ? " wrap" : "") }, c)));
      tb.append(row);
    });
    t.append(tb);
    host.replaceChildren(t);
  }
  function seg(host, options, current, onPick) {
    host.replaceChildren();
    for (const [key, label] of options) {
      const b = el("button", { type: "button", "aria-pressed": String(key === current) }, label);
      b.addEventListener("click", () => { host.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); onPick(key); });
      host.append(b);
    }
  }

  // ---- time-series chart with era shading and break marks ------------------------------------------------------
  // series: [{name, color, dash?, band?, pts: [{x, y, lo?, hi?, tip}]}]
  function timeChart(host, series, opts = {}) {
    host.replaceChildren();
    const W = Math.max(280, host.clientWidth || 340), H = opts.height || 230;
    const m = { t: 16, r: 12, b: 30, l: 46 };
    const years = R.meta.years;
    const x0 = years[0] - 0.5, x1 = years[years.length - 1] + 0.5;
    const ys = series.flatMap((s) => s.pts.flatMap((p) => [p.lo ?? p.y, p.hi ?? p.y])).filter((v) => v != null && isFinite(v));
    if (opts.zero) ys.push(0);
    const yt = opts.yTicks || niceRange(Math.min(...ys), Math.max(...ys), 4);
    const x = (v) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r);
    const y = (v) => m.t + (1 - (v - yt[0]) / (yt[yt.length - 1] - yt[0])) * (H - m.t - m.b);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    // eras
    ERAS.forEach((e, i) => {
      const [a, b] = R.meta.eras[e];
      if (i % 2 === 1) svg.append(sv("rect", { x: x(a - 0.5), y: m.t, width: x(b + 0.5) - x(a - 0.5), height: H - m.t - m.b, fill: css("--wash") }));
      svg.append(sv("text", { x: (x(a - 0.5) + x(b + 0.5)) / 2, y: m.t - 4, "text-anchor": "middle", "font-size": 10, fill: css("--muted") }, e.replace("-20", "–")));
    });
    for (const t of yt) {
      svg.append(sv("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: css(t === 0 ? "--axis" : "--grid"), "stroke-width": 1 }));
      svg.append(sv("text", { x: m.l - 6, y: y(t) + 4, "text-anchor": "end", "font-size": 10.5, fill: css("--muted") }, (opts.yFmt || ((v) => minus(String(Math.round(v * 1000) / 10))))(t)));
    }
    for (const yr of [years[0], 2008, 2012, 2016, 2020, 2024].filter((v) => v <= years[years.length - 1])) {
      svg.append(sv("text", { x: x(yr), y: H - m.b + 16, "text-anchor": "middle", "font-size": 10.5, fill: css("--muted") }, String(yr)));
    }
    for (const b of R.meta.breaks) {
      const bx = x(b.year - 0.5);
      const g = sv("g");
      g.append(sv("line", { x1: bx, x2: bx, y1: H - m.b - 6, y2: H - m.b, stroke: css("--ink-2"), "stroke-width": 1.5 }));
      g.append(sv("rect", { x: bx - 6, y: H - m.b - 10, width: 12, height: 12, fill: "transparent" }));
      hoverable(g, (e) => showTip(e, `${b.year}: reporting change`, [{ label: b.what.length > 90 ? b.what.slice(0, 88) + "…" : b.what, value: "" }]), `Reporting change in ${b.year}`);
      svg.append(g);
    }
    for (const s of series) {
      const color = css(s.color);
      const pts = s.pts.filter((p) => p.y != null && isFinite(p.y));
      if (s.band && pts.length && pts[0].lo != null) {
        // break the band at gaps in the years
        let runs = [], cur = [];
        pts.forEach((p, i) => { if (i && p.x !== pts[i - 1].x + 1) { runs.push(cur); cur = []; } cur.push(p); });
        runs.push(cur);
        for (const r of runs) {
          const top = r.map((p) => `${x(p.x)},${y(p.hi)}`).join(" L");
          const bot = r.slice().reverse().map((p) => `${x(p.x)},${y(p.lo)}`).join(" L");
          svg.append(sv("path", { d: `M${top} L${bot} Z`, fill: color, opacity: 0.14 }));
        }
      }
      let d = "", prev = null;
      for (const p of pts) { d += (prev && p.x === prev.x + 1 ? "L" : "M") + `${x(p.x)},${y(p.y)}`; prev = p; }
      svg.append(sv("path", { d, fill: "none", stroke: color, "stroke-width": s.width || 2, "stroke-dasharray": s.dash || null, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      if (s.dots !== false) for (const p of pts) {
        const g = sv("g");
        g.append(sv("circle", { cx: x(p.x), cy: y(p.y), r: s.dash ? 2.5 : 3.5, fill: color, stroke: css("--surface"), "stroke-width": 1.5 }));
        g.append(sv("circle", { cx: x(p.x), cy: y(p.y), r: 9, fill: "transparent" }));
        hoverable(g, (e) => showTip(e, p.title || `${s.name}, ${p.x}`, p.tip), `${s.name} ${p.x}`);
        svg.append(g);
      }
    }
    host.append(svg);
  }

  // Horizontal interval rows (eras chart, reasons chart). rows: [{label, sub, series: [{color, est, lo, hi, tip}]}]
  function intervalChart(host, rows, opts = {}) {
    host.replaceChildren();
    const W = Math.max(280, host.clientWidth || 600);
    const narrow = W < 560;
    const lw = narrow ? 14 : (opts.labelWidth || 190);
    const nS = Math.max(...rows.map((r) => r.series.length));
    const top = narrow ? 18 : 0;
    const rowH = (nS > 1 ? 40 : 30) + top;
    const m = { t: 6, r: 16, b: 34, l: lw };
    const H = m.t + rows.length * rowH + m.b;
    const vals = rows.flatMap((r) => r.series.flatMap((s) => [s.lo ?? s.est, s.hi ?? s.est])).filter((v) => v != null && isFinite(v)).concat(opts.zero === false ? [] : [0]);
    const ticks = opts.ticks || niceRange(Math.min(...vals), Math.max(...vals), narrow ? 4 : 6);
    const lo = ticks[0], hi = ticks[ticks.length - 1];
    const x = (v) => m.l + ((v - lo) / (hi - lo)) * (W - m.l - m.r);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    for (const t of ticks) {
      svg.append(sv("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, stroke: css(t === 0 ? "--axis" : "--grid"), "stroke-width": 1 }));
      svg.append(sv("text", { x: x(t), y: H - m.b + 15, "text-anchor": "middle", "font-size": 10.5, fill: css("--muted") }, (opts.fmt || ((v) => minus(String(Math.round(v * 1000) / 10))))(t)));
    }
    if (opts.xLabel) svg.append(sv("text", { x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle", "font-size": 11, fill: css("--ink-2") }, opts.xLabel));
    rows.forEach((r, i) => {
      const rt = m.t + i * rowH;
      const yc = rt + top + (rowH - top) / 2;
      if (narrow) svg.append(sv("text", { x: m.l - 6, y: rt + 13, "font-size": 12, fill: css("--ink") }, r.label + (r.sub && (r.label + r.sub).length < 44 ? " · " + r.sub : "")));
      else {
        svg.append(sv("text", { x: m.l - 10, y: yc + (r.sub ? -2 : 4), "text-anchor": "end", "font-size": 12, fill: css("--ink") }, r.label));
        if (r.sub) svg.append(sv("text", { x: m.l - 10, y: yc + 12, "text-anchor": "end", "font-size": 10.5, fill: css("--muted") }, r.sub));
      }
      if (i) svg.append(sv("line", { x1: 0, x2: W - m.r, y1: rt, y2: rt, stroke: css("--grid"), "stroke-width": 1 }));
      r.series.forEach((s, j) => {
        if (s.est == null || !isFinite(s.est)) return;
        const yy = yc + (r.series.length > 1 ? (j - (r.series.length - 1) / 2) * 11 : 0);
        const g = sv("g");
        const color = css(s.color);
        if (s.lo != null) g.append(sv("line", { x1: x(s.lo), x2: x(s.hi), y1: yy, y2: yy, stroke: color, "stroke-width": 2, "stroke-linecap": "round" }));
        g.append(sv("circle", { cx: x(s.est), cy: yy, r: 4.5, fill: color, stroke: css("--surface"), "stroke-width": 2 }));
        g.append(sv("rect", { x: x(s.lo ?? s.est) - 8, y: yy - 8, width: Math.max(16, x(s.hi ?? s.est) - x(s.lo ?? s.est) + 16), height: 16, fill: "transparent" }));
        hoverable(g, (e) => showTip(e, r.label + (s.name ? " · " + s.name : ""), s.tip), r.label);
        svg.append(g);
      });
    });
    host.append(svg);
  }

  // Lay out every small-multiple panel before drawing any, so each chart measures its final width.
  function panels(host, titles) {
    host.replaceChildren();
    return titles.map((t) => {
      const box = el("div");
      box.append(el("h3", {}, t));
      const c = el("div");
      box.append(c);
      host.append(box);
      return c;
    });
  }

  // ---- data helpers -----------------------------------------------------------------------------------------
  const rate = (year, purpose, group) => R.rates.find((r) => r.year === year && r.purpose === purpose && r.group === group);
  const gap = (year, purpose, spec, group) => R.yearly.find((r) => r.year === year && r.purpose === purpose && r.spec === spec && r.group === group);
  const eraGap = (era, purpose, spec, group) => R.eras.find((r) => r.era === era && r.purpose === purpose && r.spec === spec && r.group === group);
  const wilson = (p, n) => { const h = Z * Math.sqrt(p * (1 - p) / n); return [p - h, p + h]; };
  const sumRates = (rows) => rows.reduce((a, r) => ({ n: a.n + r.n, denied: a.denied + r.denied }), { n: 0, denied: 0 });

  const totalRecords = R.reconcile.reduce((a, r) => a + r.records, 0);
  const totalCore = R.reconcile.reduce((a, r) => a + r.core_purchase + r.core_refinance, 0);
  const V = { records: num(totalRecords), core: num(totalCore) };
  document.querySelectorAll("[data-v]").forEach((n) => { n.textContent = V[n.dataset.v]; });

  function stat(host, value, label, note) {
    const s = el("div", { class: "stat" });
    s.append(el("div", { class: "label" }, label));
    if (note) s.append(el("div", { class: "note" }, note));
    s.append(el("div", { class: "value" }, value));
    host.append(s);
  }

  // ---- headline ---------------------------------------------------------------------------------------------
  function renderHeadline() {
    const h = $("#headline");
    const last = ERAS[ERAS.length - 1], first = ERAS[0];
    const raw = eraGap(last, "purchase", "raw", "Black"), len = eraGap(last, "purchase", "lender", "Black"), full = eraGap(last, "purchase", "full", "Black");
    const old = eraGap(first, "purchase", "lender", "Black");
    stat(h, num(totalCore), "Decided applications analyzed", `${R.meta.years[0]}-${R.meta.years[R.meta.years.length - 1]}, purchase and refinance, core sample`);
    stat(h, (100 * raw.est).toFixed(1), "Point Black-white purchase denial gap, " + last.replace("-", "–"), "Raw difference in denial rates");
    stat(h, (100 * full.est).toFixed(1), "Points remain with lender and underwriting controls", `Same lender, county and year; DTI, LTV, credit-score model; 95% interval ${ci(full.est - Z * full.se, full.est + Z * full.se)}`);
    stat(h, (100 * old.est).toFixed(1), "Points within the same lender, " + first.replace("-", "–"), `vs ${(100 * len.est).toFixed(1)} in ${last.replace("-", "–")} (same controls)`);
  }

  // ---- overview ---------------------------------------------------------------------------------------------
  function renderRates() {
    legend($("#legend-rates"), [{ label: "White applicants", color: "--s1", shape: "line" }, { label: "Comparison group", color: "--s2", shape: "line" }]);
    const boxes = panels($("#chart-rates"), GROUPS.map((g) => `${g} and white applicants`));
    const maxRate = Math.max(...R.rates.filter((r) => r.purpose === "purchase" && ["White", ...GROUPS].includes(r.group) && r.n >= 100).map((r) => r.rate));
    const yt = niceRange(0, maxRate, 4);
    GROUPS.forEach((g, gi) => {
      const c = boxes[gi];
      const series = [["White", "--s1"], [g, "--s2"]].map(([grp, color]) => ({
        name: grp, color, pts: R.meta.years.map((yr) => {
          const r = rate(yr, "purchase", grp);
          if (!r || r.n < 30) return { x: yr, y: null };
          const [lo, hi] = wilson(r.rate, r.n);
          return { x: yr, y: r.rate, lo, hi, title: `${grp} applicants, ${yr}`, tip: [{ label: "Denied", value: pct(r.rate) }, { label: "Applications", value: num(r.n) }, { label: "95% interval", value: ci(lo, hi, pct) }] };
        }),
      }));
      timeChart(c, series, { yTicks: yt, yFmt: (v) => Math.round(v * 100) + "%", label: `Denial rates, ${g} and white applicants` });
    });
    const groups = R.meta.groups;
    const rows = [];
    for (const purpose of ["purchase", "refinance"]) for (const yr of R.meta.years) {
      rows.push([`${yr} ${purpose}`, ...groups.map((g) => { const r = rate(yr, purpose, g); return r ? `${pct(r.rate)} (${num(r.n)})` : "–"; })]);
    }
    table($("#table-rates"), ["Year", ...groups], rows);
  }

  function renderFindings() {
    const F = ERAS[0], L = ERAS[ERAS.length - 1], M = ERAS[1];
    const g = (era, spec, grp, p = "purchase") => eraGap(era, p, spec, grp);
    const eraRate = (era, grp, p = "purchase") => {
      const [a, b] = R.meta.eras[era];
      const s = sumRates(R.rates.filter((r) => r.purpose === p && r.group === grp && r.year >= a && r.year <= b));
      return s.denied / s.n;
    };
    const items = [
      `<b>Black applicants were denied more often in every year.</b> For home purchase, ${pct(eraRate(F, "Black"))} of Black applicants were denied in ${F} against ${pct(eraRate(F, "White"))} of white applicants; in ${L}, ${pct(eraRate(L, "Black"))} against ${pct(eraRate(L, "White"))}. Hispanic and Asian applicants also faced higher denial rates than white applicants, by less.`,
      `<b>Comparing applicants at the same lender shrinks the gap but doesn't close it.</b> With the controls every year records plus lender and county fixed effects, the Black-white purchase gap is ${pp(g(F, "lender", "Black").est)} in ${F}, ${pp(g(M, "lender", "Black").est)} in ${M} and ${pp(g(L, "lender", "Black").est)} in ${L}.`,
      `<b>The 2018 underwriting fields explain more, still not all.</b> Adding debt-to-income, loan-to-value, property value, credit-score model and underwriting system brings the ${L} Black-white purchase gap to ${pp(g(L, "full", "Black").est)} (95% interval ${ci(g(L, "full", "Black").est - Z * g(L, "full", "Black").se, g(L, "full", "Black").est + Z * g(L, "full", "Black").se)}); Hispanic ${pp(g(L, "full", "Hispanic").est)}, Asian ${pp(g(L, "full", "Asian").est)}. HMDA still has no credit scores, so this remains an association.`,
      `<b>Refinancing shows larger gaps.</b> The ${L} Black-white refinance gap with lender controls is ${pp(g(L, "lender", "Black", "refinance").est)}, against ${pp(g(L, "lender", "Black").est)} for purchases.`,
      `<b>One dataset, checked.</b> ${num(totalRecords)} records from three publishers, each year matched to its official count where one exists, and one rule for groups, samples and geography in every year (see Data &amp; method).`,
    ];
    const ul = el("ul");
    items.forEach((t) => ul.append(html("li", {}, t)));
    $("#findings").replaceChildren(ul);
  }

  // ---- trends -----------------------------------------------------------------------------------------------
  let purpose = "purchase", spec = "lender";
  function renderTrends() {
    seg($("#pick-purpose"), [["purchase", "Home purchase"], ["refinance", "Refinance"]], purpose, (k) => { purpose = k; renderTrends(); });
    seg($("#pick-spec"), Object.entries(SPEC_LABEL), spec, (k) => { spec = k; renderTrends(); });
    $("#spec-note").textContent = SPEC_NOTE[spec];
    const boxes = panels($("#chart-gaps"), GROUPS.map((g) => `${g} minus white`));
    const vals = R.yearly.filter((r) => r.purpose === purpose).flatMap((r) => [r.est - Z * r.se, r.est + Z * r.se]);
    const yt = niceRange(Math.min(0, ...vals), Math.max(...vals), 5);
    GROUPS.forEach((g, gi) => {
      const c = boxes[gi];
      const mk = (sp, color, extra) => ({
        name: SPEC_LABEL[sp], color, ...extra, pts: R.meta.years.map((yr) => {
          const r = gap(yr, purpose, sp, g);
          if (!r) return { x: yr, y: null };
          return { x: yr, y: r.est, lo: r.est - Z * r.se, hi: r.est + Z * r.se, title: `${g} minus white, ${yr}`,
            tip: [{ label: SPEC_LABEL[sp], value: pp(r.est) }, { label: "95% interval", value: ci(r.est - Z * r.se, r.est + Z * r.se) }, { label: "Applications", value: num(r.n) }, { label: "Lenders", value: num(r.clusters) }] };
        }),
      });
      const series = [];
      if (spec !== "raw") series.push(mk("raw", "--muted", { dash: "4 3", width: 1.5, dots: false }));
      series.push(mk(spec, "--s2", { band: true }));
      timeChart(c, series, { yTicks: yt, zero: true, label: `Denial gap, ${g} minus white` });
    });
    const rows = R.meta.years.map((yr) => [String(yr), ...GROUPS.flatMap((g) => { const r = gap(yr, purpose, spec, g); return [r ? pp(r.est) : "–", r ? num(100 * r.se, 1) : "–"]; }), (() => { const r = gap(yr, purpose, spec, "Black"); return r ? num(r.n) : "–"; })()]);
    table($("#table-gaps"), ["Year", ...GROUPS.flatMap((g) => [g, "SE"]), "Applications"], rows);
    $("#gaps-note").innerHTML = `Dashed gray is the raw gap, for reference. Small ticks on the axis mark reporting changes (hover them). The ${purpose === "purchase" ? "purchase" : "refinance"} market in each year is a different mix of borrowers and lenders, so a year-to-year change in the gap is not by itself a change in how any lender treats applicants. ${spec === "full" ? "Applications without the 2018 fields (exempt lenders, or not reported) enter with a 'missing' category." : ""}`;
  }

  // ---- eras -------------------------------------------------------------------------------------------------
  let purposeEra = "purchase";
  function renderEras() {
    seg($("#pick-purpose-era"), [["purchase", "Home purchase"], ["refinance", "Refinance"]], purposeEra, (k) => { purposeEra = k; renderEras(); });
    const boxes = panels($("#chart-eras"), GROUPS.map((g) => `${g} minus white`));
    const vals = R.eras.filter((r) => r.purpose === purposeEra).flatMap((r) => [r.est - Z * r.se, r.est + Z * r.se]);
    const ticks = niceRange(Math.min(0, ...vals), Math.max(...vals), 5);
    GROUPS.forEach((g, gi) => {
      const c = boxes[gi];
      const rows = [];
      for (const era of ERAS) for (const sp of R.meta.specs) {
        const r = eraGap(era, purposeEra, sp, g);
        if (!r) continue;
        rows.push({ label: era.replace("-", "–"), sub: SPEC_LABEL[sp], series: [{ color: sp === "raw" ? "--muted" : "--s2", est: r.est, lo: r.est - Z * r.se, hi: r.est + Z * r.se,
          tip: [{ label: "Gap", value: pp(r.est) }, { label: "95% interval", value: ci(r.est - Z * r.se, r.est + Z * r.se) }, { label: "Applications", value: num(r.n) }] }] });
      }
      intervalChart(c, rows, { ticks, labelWidth: 170, xLabel: "Percentage points", label: `${g} minus white by era` });
    });
    const rows = [];
    for (const era of ERAS) for (const sp of R.meta.specs) {
      const r0 = eraGap(era, purposeEra, sp, "Black");
      if (!r0) continue;
      rows.push([era, SPEC_LABEL[sp], ...GROUPS.map((g) => { const r = eraGap(era, purposeEra, sp, g); return `${pp(r.est)} (${num(100 * r.se, 1)})`; }), num(r0.n), num(r0.clusters)]);
    }
    table($("#table-eras"), ["Era", "Controls", ...GROUPS, "Applications", "Lenders"], rows, { textCols: [1] });
    table($("#table-robust"), ["Variant", ...GROUPS, "Applications"], R.robustness.map((r) => [r.label, ...GROUPS.map((g) => `${pp(r[g].est)} (${num(100 * r[g].se, 1)})`), num(r.n)]));
  }

  // ---- map --------------------------------------------------------------------------------------------------
  let era = ERAS[ERAS.length - 1], measure = "rate", geoLevel = "tract";
  const MEASURES = { rate: "Denial rate", gap: "Black-white gap", share: "Black share of applicants" };
  const MIN_N = 20;
  let bounds = null;
  function geoBounds() {
    if (bounds) return bounds;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const c of Object.values(GEO.counties)) {
      for (const m of c.d.matchAll(/(-?\d+),(-?\d+)/g)) {
        const x = +m[1], y = +m[2];
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
    return (bounds = [x0, y0, x1 - x0, y1 - y0]);
  }
  function scale(measure) {
    const dark = document.documentElement.getAttribute("data-theme") === "dark" || (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
    if (measure === "gap") {
      const cols = dark ? ["#6f86e0", "#3d4a7a", "#2b3454", "#5a3412", "#a8530c", "#ff8f2e"] : ["#495e9d", "#a3afd3", "#e6e9f2", "#f6c896", "#ea8f35", "#a84e00"];
      return { edges: [-0.05, 0, 0.05, 0.1, 0.2], cols, fmt: (v) => pp(v, 0) };
    }
    if (measure === "share") {
      const cols = dark ? ["#1e2746", "#2f3d6b", "#43579a", "#5f78c9", "#8ea3ea"] : ["#e6ebf6", "#bfcae6", "#8fa2d3", "#5f78bb", "#34488a"];
      return { edges: [0.05, 0.15, 0.3, 0.5], cols, fmt: (v) => pct(v, 0) };
    }
    const cols = dark ? ["#2a1e12", "#5a3412", "#8f4d0e", "#c7660a", "#ff9a3d", "#ffc58a"] : ["#fdf0e3", "#f9d3a6", "#f2a961", "#dc7614", "#a95300", "#6e3600"];
    return { edges: [0.05, 0.1, 0.15, 0.2, 0.3], cols, fmt: (v) => pct(v, 0) };
  }
  function bin(v, sc) { let i = 0; while (i < sc.edges.length && v >= sc.edges[i]) i++; return sc.cols[i]; }
  function areaValues() {
    const out = {};
    if (geoLevel === "tract") {
      const T = R.tracts.eras[era] || {};
      for (const [id, a] of Object.entries(T)) {
        const [n, den, nw, dw, nb, db] = a;
        out[id] = { n, rate: n >= MIN_N ? den / n : null, gap: nw >= MIN_N && nb >= MIN_N ? db / nb - dw / nw : null, share: n >= MIN_N ? nb / n : null, nw, nb };
      }
    } else {
      const C = R.counties[era] || {};
      for (const [id, c] of Object.entries(C)) {
        const [n, den] = c.all, [nw, dw] = c.White || [0, 0], [nb, db] = c.Black || [0, 0];
        out[id] = { n, rate: n >= MIN_N ? den / n : null, gap: nw >= MIN_N && nb >= MIN_N ? db / nb - dw / nw : null, share: n >= MIN_N ? nb / n : null, nw, nb };
      }
    }
    return out;
  }
  function renderMap() {
    seg($("#pick-era"), ERAS.map((e) => [e, e.replace("-", "–")]), era, (k) => { era = k; renderMap(); });
    seg($("#pick-measure"), Object.entries(MEASURES), measure, (k) => { measure = k; renderMap(); });
    seg($("#pick-geo"), [["tract", "Census tracts"], ["county", "Counties"]], geoLevel, (k) => { geoLevel = k; renderMap(); });
    const [bx, by, bw, bh] = geoBounds();
    const svg = sv("svg", { viewBox: `${bx - 200} ${by - 200} ${bw + 400} ${bh + 400}`, role: "img", "aria-label": `${MEASURES[measure]}, ${era}` });
    const sc = scale(measure);
    const vals = areaValues();
    const shapes = geoLevel === "tract" ? Object.entries(GEO.tracts).map(([id, d]) => [id, d, null]) : Object.entries(GEO.counties).map(([id, c]) => [id, c.d, c.name]);
    const noData = css("--grid");
    for (const [id, d, name] of shapes) {
      const v = vals[id];
      const val = v ? v[measure] : null;
      const p = sv("path", { d, fill: val == null ? noData : bin(val, sc) });
      const county = GEO.counties[id.slice(0, 5)];
      const title = name || `Tract ${id.slice(5, 9)}.${id.slice(9)}, ${county ? county.name : ""}`;
      hoverable(p, (e) => showTip(e, title, v ? [
        { label: "Denial rate", value: v.rate == null ? "too few" : pct(v.rate) },
        { label: "Black-white gap", value: v.gap == null ? "too few" : pp(v.gap) },
        { label: "Applications", value: num(v.n) },
        { label: "White / Black applicants", value: `${num(v.nw)} / ${num(v.nb)}` },
      ] : [{ label: "No applications", value: "" }]), title);
      svg.append(p);
    }
    if (geoLevel === "tract") for (const c of Object.values(GEO.counties)) svg.append(sv("path", { d: c.d, class: "county-line" }));
    $("#map").replaceChildren(svg);
    // legend ramp
    const ramp = $("#map-ramp");
    ramp.replaceChildren(el("span", {}, MEASURES[measure] + ":"));
    sc.cols.forEach((c, i) => {
      const s = el("span");
      const sw = el("i", { class: "nodata" });
      sw.style.background = c;
      sw.style.marginLeft = "6px";
      const lab = i === 0 ? `< ${sc.fmt(sc.edges[0])}` : i === sc.cols.length - 1 ? `≥ ${sc.fmt(sc.edges[i - 1])}` : `${sc.fmt(sc.edges[i - 1])}–${sc.fmt(sc.edges[i])}`;
      s.append(sw, document.createTextNode(" " + lab));
      ramp.append(s);
    });
    const nd = el("span");
    const ndi = el("i", { class: "nodata" });
    nd.append(ndi, document.createTextNode(` fewer than ${MIN_N} applications`));
    ramp.append(nd);
    const cov = Object.entries(R.tracts.coverage).filter(([y]) => R.meta.eras[era][0] <= +y && +y <= R.meta.eras[era][1]).map(([, s]) => s);
    $("#map-sub").textContent = `Home-purchase applications in the core sample, ${era.replace("-", "–")}, by ${geoLevel === "tract" ? "2020 census tract (earlier years carried onto 2020 tracts by the crosswalk)" : "county or independent city"}. Hover an area for its numbers.`;
    $("#map-note").innerHTML = `${geoLevel === "tract" ? `Tract values for years on older boundaries are allocated to 2020 tracts in proportion to housing (2000 to 2010) and land area (2010 to 2020); at least ${pct(Math.min(...cov), 1)} of each year's applications with a tract code in this era are placed. ` : ""}Areas with fewer than ${MIN_N} applications (or, for the gap, fewer than ${MIN_N} white or ${MIN_N} Black applicants) are left gray. A raw gap in one area mixes lenders, incomes and loan types; it is a place to look, not a finding.`;
    const C = R.counties[era] || {};
    const rows = Object.entries(GEO.counties).map(([id, c]) => {
      const v = C[id];
      if (!v) return [c.name, "0", "–", "–", "–"];
      const [n, den] = v.all, [nw, dw] = v.White || [0, 0], [nb, db] = v.Black || [0, 0];
      return [c.name, num(n), pct(den / n), nw >= MIN_N ? pct(dw / nw) : "–", nb >= MIN_N ? pct(db / nb) : "–"];
    }).sort((a, b) => a[0].localeCompare(b[0]));
    table($("#table-map"), ["County or city", "Applications", "Denied", "White denied", "Black denied"], rows);
  }

  // ---- reasons ----------------------------------------------------------------------------------------------
  let eraR = ERAS[ERAS.length - 1], groupR = "Black";
  function renderReasons() {
    seg($("#pick-era-r"), ERAS.map((e) => [e, e.replace("-", "–")]), eraR, (k) => { eraR = k; renderReasons(); });
    seg($("#pick-group-r"), GROUPS.map((g) => [g, g]), groupR, (k) => { groupR = k; renderReasons(); });
    legend($("#legend-reasons"), [{ label: "White applicants", color: "--s1", shape: "dot" }, { label: `${groupR} applicants`, color: "--s2", shape: "dot" }]);
    const W = R.reasons.find((r) => r.era === eraR && r.group === "White"), G = R.reasons.find((r) => r.era === eraR && r.group === groupR);
    const names = Object.values(R.meta.reasons);
    const rows = names.map((nm) => ({
      label: nm, series: [[W, "--s1", "White"], [G, "--s2", groupR]].map(([r, color, label]) => {
        const p = r[nm], n = r.with_reason;
        const [lo, hi] = wilson(p, n);
        return { name: label, color, est: p, lo: Math.max(0, lo), hi: Math.min(1, hi), tip: [{ label, value: pct(p) }, { label: "Denials with a reason", value: num(n) }] };
      }),
    }));
    const top = Math.max(...rows.flatMap((r) => r.series.map((x) => x.hi)));
    intervalChart($("#chart-reasons"), rows, { ticks: niceRange(0, top, 5), fmt: (v) => Math.round(v * 100) + "%", labelWidth: 200, xLabel: "Share of denials citing the reason (up to 3-4 reasons each)", label: "Denial reasons" });
    const required = R.meta.eras[eraR][0] >= 2018;
    $("#reasons-sub").textContent = `Home purchase and refinance denials, ${eraR.replace("-", "–")}. ${required ? "From 2018 every lender must report reasons" : "Before 2018 most lenders could choose whether to report reasons"}: ${pct(W.with_reason / W.denials, 0)} of white applicants' and ${pct(G.with_reason / G.denials, 0)} of ${groupR} applicants' denials in this era carry one. Shares are among denials that report any reason.`;
    const rowsT = [];
    for (const e of ERAS) for (const g of ["White", ...GROUPS]) {
      const r = R.reasons.find((x) => x.era === e && x.group === g);
      if (r) rowsT.push([e, g, num(r.denials), pct(r.with_reason / r.denials, 0), ...names.map((nm) => pct(r[nm], 0))]);
    }
    table($("#table-reasons"), ["Era", "Group", "Denials", "With reason", ...names], rowsT, { textCols: [1] });
  }

  // ---- data & method ----------------------------------------------------------------------------------------
  function renderData() {
    table($("#table-reconcile"), ["Year", "Era", "Source", "Records", "Official count", "Purchase (core)", "Refinance (core)", "Race/ethnicity not reported (core)", "File SHA-256"],
      R.reconcile.map((r) => [String(r.year), r.era, r.source, num(r.records), r.official == null ? "none published" : (r.official === r.records ? "✓ " : "✗ ") + num(r.official), num(r.core_purchase), num(r.core_refinance), pct(r.not_reported, 0), r.sha256]), { textCols: [1, 2, 8] });
    const ol = $("#breaks");
    ol.replaceChildren(...R.meta.breaks.map((b) => html("li", {}, `<b>${b.year}</b> ${b.what}`)));
    table($("#table-schema"), ["Field", "Meaning", "2004-2006", "2007-2017", "2018-2025", "Watch for"],
      R.meta.schema.map((s) => [s.field, s.meaning, s.src_2004, s.src_2007, s.src_2018, s.note]), { textCols: [1, 2, 3, 4, 5], wrapCols: [1, 5] });
    const mu = Object.entries(R.missing_underwriting).map(([y, v]) => `${y}: ${pct(v, 0)}`).join(", ");
    $("#method").innerHTML = `
      <h2>Method</h2>
      <h3>Sources</h3>
      <p>2004-2006: the Federal Reserve Board's national "Final" loan/application register files, archived by the National
        Archives (series NAID 2456161), fixed-width, filtered to Virginia (state code 51). 2007-2017: the CFPB's historic
        HMDA files, nationwide "all records" with codes, filtered to Virginia (the per-state links on the CFPB page
        returned errors when this was built). 2018-2025: the CFPB HMDA Data Browser's Virginia file for each year. Every
        file's SHA-256 is recorded when it is downloaded, and each year's record count is checked against the
        publisher's (the table above). 2004-2006 have no published Virginia count; there every record is checked
        for a valid action code.</p>
      <h3>One schema</h3>
      <p>Each era has its own reader, and all three feed one function that derives every analysis field: the applicant's
        group (Hispanic of any race first; otherwise the set of major races reported, with 2018's subgroups folded in),
        denial (denied versus originated or approved, among decided applications), the core sample and the county. The
        core sample is decided, first-lien, owner-occupied, site-built 1-4 family, closed-end home-purchase and
        refinance applications; from 2018, open-end lines, reverse mortgages and business-purpose loans are excluded
        because earlier years can't identify them. Tract demographics for 2004-2006 come from the FFIEC values carried
        in the 2007-2011 records for the same 2000-census tracts (they vary across those years for
        ${pct(R.meta.context_check, 1)} of tracts).</p>
      <h3>Models</h3>
      <p>Linear probability models of denial on group indicators (white applicants are the reference; other and
        unreported groups get their own indicators), fit separately by year and loan purpose, and pooled by era with
        county-by-year and lender-by-year fixed effects. Fixed effects are absorbed by alternating projections, singleton
        groups dropped, and standard errors clustered by lender (CR1), as reghdfe does. The 2018 underwriting fields are
        missing for exempt lenders and sometimes not reported (share of core applications without a debt-to-income
        value: ${mu}); they enter with a "missing" category, and the robustness table drops them instead.</p>
      <h3>One geography</h3>
      <p>Counties are harmonized directly (Bedford city, an independent city until 2013, is part of Bedford County in
        every year). Tracts change boundaries in 2012 and 2022; every year's tract counts are carried onto 2020 tracts
        with the Census Bureau's relationship files, weighted by 2010 housing units for 2000-to-2010 and by land area for
        2010-to-2020. Map boundaries are the Census Bureau's 2023 cartographic boundary files.</p>
      <h3>Words used carefully</h3>
      <p>"Gap" and "associated with" describe differences in recorded outcomes. HMDA has no credit scores in any year, so
        no specification here measures creditworthiness fully, and none of these numbers say a lender discriminated or
        didn't.</p>
      <h3>References</h3>
      <ul class="refs">
        <li>Consumer Financial Protection Bureau. HMDA Data Browser and historic HMDA data. ffiec.cfpb.gov; consumerfinance.gov/data-research/hmda.</li>
        <li>National Archives. Home Mortgage Disclosure Act (HMDA) Data Files, 1981-2014 (NAID 2456161).</li>
        <li>U.S. Census Bureau. 2010 and 2020 census tract relationship files; 2023 cartographic boundary files.</li>
        <li>Correia, S. (2017). Linear models with high-dimensional fixed effects: An efficient and feasible estimator. Working paper (reghdfe).</li>
      </ul>`;
  }

  // ---- tabs & boot ------------------------------------------------------------------------------------------
  const VIEWS = ["overview", "trends", "eras", "map", "reasons", "data"];
  const ANCHORS = { limits: "overview", trends: "trends", data: "data" };
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  function select(id, push) {
    for (const t of tabs) {
      const on = t.id === "tab-" + id;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    }
    if (push) history.replaceState(null, "", "#" + id);
    renderVisible();
  }
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => select(t.id.slice(4), true));
    t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      n.focus(); select(n.id.slice(4), true);
    });
  });
  function renderVisible() {
    hideTip();
    if (!$("#view-overview").hidden) renderRates();
    if (!$("#view-trends").hidden) renderTrends();
    if (!$("#view-eras").hidden) renderEras();
    if (!$("#view-map").hidden) renderMap();
    if (!$("#view-reasons").hidden) renderReasons();
  }
  function route(h, scroll) {
    const view = VIEWS.includes(h) ? h : ANCHORS[h];
    if (!view) return;
    select(view, false);
    if (scroll) (document.getElementById(h) || document.querySelector(".tabs")).scrollIntoView({ behavior: "smooth", block: "start" });
  }
  window.addEventListener("hashchange", () => route(location.hash.slice(1), true));
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(renderVisible, 120); });
  window.addEventListener("themechange", renderVisible);

  renderHeadline();
  renderFindings();
  renderData();
  $("#stamp").textContent = `Built ${R.meta.built} from ${R.reconcile.length} yearly files.`;
  const start = location.hash.slice(1);
  if (start) route(start, false); else select("overview", false);
})();
