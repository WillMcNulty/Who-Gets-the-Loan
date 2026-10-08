// Who Gets the Loan?: renders window.RESULTS (built by build.py) with plain DOM and SVG, no libraries.
// Every number on the page comes from RESULTS; none is typed into the HTML.
(function () {
  "use strict";
  const R = window.RESULTS;
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, el = document) => el.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const Z = 1.959964;
  // Two series at most, in this order everywhere: white applicants Link Blue, Black or Hispanic applicants Orange.
  const SERIES = { White: "--s1", "Black or Hispanic": "--s2" };

  // ---- formatting -------------------------------------------------------------------------------------------
  const minus = (s) => s.replace(/^-/, "−");
  const pct = (v, d = 1) => minus((100 * v).toFixed(d)) + "%";
  const pp = (v, d = 1, sign = false) => (sign && v > 0 ? "+" : "") + minus((100 * v).toFixed(d)) + " pp";
  const num = (v, d = 3) => minus(Number(v).toFixed(d));
  const ci = (lo, hi, f = pp) => `${f(lo)} to ${f(hi)}`;
  const int = (v) => Number(v).toLocaleString("en-US");

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

  // ---- shared pieces ----------------------------------------------------------------------------------------
  function legend(host, items) {
    host.replaceChildren();
    for (const it of items) {
      const s = el("span");
      const i = el("i", { class: it.shape || "" });
      i.style.background = css(it.color);
      s.append(i, document.createTextNode(it.label));
      host.append(s);
    }
  }
  const groupLegend = (host, shape = "dot") => legend(host, Object.entries(SERIES).map(([label, color]) => ({ label: label + " applicants", color, shape })));

  function table(host, head, rows, opts = {}) {
    const t = el("table");
    const tr = el("tr");
    head.forEach((h, j) => tr.append(el("th", { class: j && !(opts.textCols || []).includes(j) ? "num" : "" }, h)));
    const th = el("thead");
    th.append(tr);
    t.append(th);
    const tb = el("tbody");
    rows.forEach((r, i) => {
      const row = el("tr", { class: opts.highlight && opts.highlight(i) ? "hl" : "" });
      r.forEach((c, j) => row.append(el("td", { class: j && !(opts.textCols || []).includes(j) ? "num" : "" }, c)));
      tb.append(row);
    });
    t.append(tb);
    host.replaceChildren(t);
  }

  function axisX(svg, x, ticks, y0, y1, fmt, label, W) {
    for (const t of ticks) {
      svg.append(sv("line", { x1: x(t), x2: x(t), y1: y0, y2: y1, stroke: css(t === 0 ? "--axis" : "--grid"), "stroke-width": 1 }));
      svg.append(sv("text", { x: x(t), y: y1 + 16, "text-anchor": "middle", "font-size": 11, fill: css("--muted") }, fmt(t)));
    }
    if (label) svg.append(sv("text", { x: W / 2, y: y1 + 34, "text-anchor": "middle", "font-size": W < 560 ? 10.5 : 11.5, fill: css("--ink-2") }, label));
  }

  // A row's label: left of the row on wide screens, above it (with its sub-label after a dot) on phones.
  function rowLabel(svg, r, narrow, left, rowTop, yc) {
    if (narrow) {
      const label = r.short || r.label;
      const t = sv("text", { x: left - 6, y: rowTop + 14, "font-size": 12, fill: css("--ink") }, label);
      // about 50 characters fit a 343px phone card at these sizes; the table view keeps the full text
      if (r.sub && label.length + r.sub.length <= 46) t.append(sv("tspan", { fill: css("--muted"), "font-size": 10.5 }, " · " + r.sub));
      svg.append(t);
      return;
    }
    svg.append(sv("text", { x: left - 10, y: yc + (r.sub ? -2 : 4), "text-anchor": "end", "font-size": 12.5, fill: css("--ink") }, r.label));
    if (r.sub) svg.append(sv("text", { x: left - 10, y: yc + 12, "text-anchor": "end", "font-size": 10.5, fill: css("--muted") }, r.sub));
  }

  // Horizontal interval chart: one row per item, a dot and a 95% bar per series.
  // rows: [{label, sub, series: [{name, color, est, lo, hi, tip?}]}]
  function intervalChart(host, rows, opts = {}) {
    host.replaceChildren();
    const W = Math.max(300, host.clientWidth || 700);
    const narrow = W < 560;
    // On phones the row labels sit above each row instead of to its left, so long labels never overflow.
    const lw = narrow ? 14 : (opts.labelWidth ? Math.min(opts.labelWidth, W * 0.4) : 210);
    const nS = Math.max(...rows.map((r) => r.series.length));
    const top = narrow ? 18 : 0;
    const rowH = (opts.rowH || (nS > 1 ? 44 : 32)) + top;
    const m = { t: 8, r: 18, b: opts.xLabel ? 44 : 28, l: lw };
    const H = m.t + rows.length * rowH + m.b;
    const vals = rows.flatMap((r) => r.series.flatMap((s) => [s.lo ?? s.est, s.hi ?? s.est]));
    if (opts.ref != null) vals.push(opts.ref);
    if (opts.zero !== false) vals.push(0);
    const ticks = opts.ticks || niceRange(Math.min(...vals), Math.max(...vals), narrow ? 4 : 6);
    const lo = ticks[0], hi = ticks[ticks.length - 1];
    const x = (v) => m.l + ((v - lo) / (hi - lo)) * (W - m.l - m.r);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    axisX(svg, x, ticks, m.t, H - m.b, opts.fmt || ((t) => pct(t, 0)), opts.xLabel, W);
    if (opts.ref != null) svg.append(sv("line", { x1: x(opts.ref), x2: x(opts.ref), y1: m.t, y2: H - m.b, stroke: css("--ink-2"), "stroke-width": 1, "stroke-dasharray": "3 3" }));
    rows.forEach((r, i) => {
      const yc = m.t + i * rowH + top + (rowH - top) / 2;
      rowLabel(svg, r, narrow, m.l, m.t + i * rowH, yc);
      if (i) svg.append(sv("line", { x1: 0, x2: W - m.r, y1: m.t + i * rowH, y2: m.t + i * rowH, stroke: css("--grid"), "stroke-width": 1 }));
      r.series.forEach((s, j) => {
        const off = r.series.length > 1 ? (j - (r.series.length - 1) / 2) * 12 : 0;
        const y = yc + off;
        const g = sv("g");
        const color = css(s.color);
        if (s.lo != null) g.append(sv("line", { x1: x(s.lo), x2: x(s.hi), y1: y, y2: y, stroke: color, "stroke-width": 2, "stroke-linecap": "round" }));
        g.append(sv("circle", { cx: x(s.est), cy: y, r: 5, fill: color, stroke: css("--surface"), "stroke-width": 2 }));
        // hit target bigger than the mark
        g.append(sv("rect", { x: x(s.lo ?? s.est) - 8, y: y - 8, width: Math.max(16, x(s.hi ?? s.est) - x(s.lo ?? s.est) + 16), height: 16, fill: "transparent" }));
        const rowsTip = s.tip || [{ label: "Estimate", value: (opts.fmt || pct)(s.est) }].concat(s.lo != null ? [{ label: "95% interval", value: ci(s.lo, s.hi, opts.fmtTip || opts.fmt || pct) }] : []);
        hoverable(g, (e) => showTip(e, `${r.label}${s.name ? " · " + s.name : ""}`, rowsTip), `${r.label} ${s.name || ""}: ${(opts.fmt || pct)(s.est)}`);
        svg.append(g);
      });
    });
    host.append(svg);
  }

  // Horizontal stacked bars (two parts), rows: [{label, sub, parts: [{name, color, v, tip}]}]
  function stackedBars(host, rows, opts = {}) {
    host.replaceChildren();
    const W = Math.max(300, host.clientWidth || 700);
    const narrow = W < 560;
    const lw = narrow ? 14 : 230;
    const lab = narrow ? 18 : 0;
    const rowH = 40 + lab, bh = 22, GAP = 2, RAD = 4;
    const m = { t: 6, r: 56, b: 44, l: lw };
    const H = m.t + rows.length * rowH + m.b;
    const max = Math.max(...rows.map((r) => r.parts.reduce((a, p) => a + Math.max(0, p.v), 0)));
    const ticks = niceRange(0, max, narrow ? 4 : 5);
    const top = ticks[ticks.length - 1];
    const x = (v) => m.l + (v / top) * (W - m.l - m.r);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    axisX(svg, x, ticks, m.t, H - m.b, (t) => minus((100 * t).toFixed(0)), opts.xLabel, W);
    rows.forEach((r, i) => {
      const yc = m.t + i * rowH + lab + (rowH - lab) / 2;
      rowLabel(svg, r, narrow, m.l, m.t + i * rowH, yc);
      let acc = 0;
      r.parts.forEach((p, j) => {
        const v = Math.max(0, p.v);
        const x0 = x(acc) + (j ? GAP : 0), x1 = x(acc + v);
        acc += v;
        const w = Math.max(0, x1 - x0);
        if (!w) return;
        const last = j === r.parts.length - 1;
        const rad = last ? Math.min(RAD, w) : 0;
        const y0 = yc - bh / 2;
        const d = `M${x0},${y0} H${x1 - rad} Q${x1},${y0} ${x1},${y0 + rad} V${y0 + bh - rad} Q${x1},${y0 + bh} ${x1 - rad},${y0 + bh} H${x0} Z`;
        const path = sv("path", { d, fill: css(p.color) });
        hoverable(path, (e) => showTip(e, r.label, p.tip), `${r.label}, ${p.name}: ${pp(p.v)}`);
        svg.append(path);
      });
      svg.append(sv("text", { x: x(acc) + 6, y: yc + 4, "font-size": 11.5, fill: css("--ink-2"), "font-family": css("--mono") }, minus((100 * acc).toFixed(1))));
    });
    host.append(svg);
  }

  // Line / point chart with optional bands and a diagonal. series: [{name, color, pts: [{x, y, lo?, hi?, tip}]}]
  function xyChart(host, series, opts = {}) {
    host.replaceChildren();
    const W = Math.max(300, host.clientWidth || 700), H = opts.height || 300;
    const m = { t: 12, r: 18, b: 46, l: opts.yLabel ? 72 : 54 };
    const xs = series.flatMap((s) => s.pts.map((p) => p.x)), ys = series.flatMap((s) => s.pts.flatMap((p) => [p.lo ?? p.y, p.hi ?? p.y]));
    const xt = opts.xTicks || niceRange(Math.min(...xs), Math.max(...xs), 5);
    const yt = opts.yTicks || niceRange(Math.min(...ys), Math.max(...ys), 5);
    const x = (v) => m.l + ((v - xt[0]) / (xt[xt.length - 1] - xt[0])) * (W - m.l - m.r);
    const y = (v) => m.t + (1 - (v - yt[0]) / (yt[yt.length - 1] - yt[0])) * (H - m.t - m.b);
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    for (const t of yt) {
      svg.append(sv("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: css("--grid"), "stroke-width": 1 }));
      svg.append(sv("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", "font-size": 11, fill: css("--muted") }, (opts.yFmt || ((v) => pct(v, 0)))(t)));
    }
    axisX(svg, x, xt, m.t, H - m.b, opts.xFmt || String, opts.xLabel, W);
    svg.append(sv("line", { x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, stroke: css("--axis"), "stroke-width": 1 }));
    if (opts.yLabel) svg.append(sv("text", { x: 12, y: (m.t + H - m.b) / 2, transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})`, "text-anchor": "middle", "font-size": 11.5, fill: css("--ink-2") }, opts.yLabel));
    if (opts.diagonal) {
      const a = Math.max(xt[0], yt[0]), b = Math.min(xt[xt.length - 1], yt[yt.length - 1]);
      svg.append(sv("line", { x1: x(a), y1: y(a), x2: x(b), y2: y(b), stroke: css("--ink-2"), "stroke-width": 1, "stroke-dasharray": "4 4" }));
    }
    for (const s of series) {
      const color = css(s.color);
      if (opts.bands && s.pts[0].lo != null) {
        const top = s.pts.map((p) => `${x(p.x)},${y(p.hi)}`).join(" L");
        const bot = s.pts.slice().reverse().map((p) => `${x(p.x)},${y(p.lo)}`).join(" L");
        svg.append(sv("path", { d: `M${top} L${bot} Z`, fill: color, opacity: 0.12 }));
      }
      if (s.line !== false) svg.append(sv("path", { d: "M" + s.pts.map((p) => `${x(p.x)},${y(p.y)}`).join(" L"), fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }
    for (const s of series) {
      const color = css(s.color);
      for (const p of s.pts) {
        const g = sv("g");
        if (!opts.bands && p.lo != null) g.append(sv("line", { x1: x(p.x), x2: x(p.x), y1: y(p.lo), y2: y(p.hi), stroke: color, "stroke-width": 2, "stroke-linecap": "round", opacity: 0.6 }));
        g.append(sv("circle", { cx: x(p.x), cy: y(p.y), r: opts.dotR || 4.5, fill: color, stroke: css("--surface"), "stroke-width": 2 }));
        g.append(sv("circle", { cx: x(p.x), cy: y(p.y), r: 11, fill: "transparent" }));
        hoverable(g, (e) => showTip(e, p.title || s.name, p.tip), p.title || s.name);
        svg.append(g);
      }
      if (opts.endLabels) {
        const p = s.pts[s.pts.length - 1];
        svg.append(sv("text", { x: x(p.x) - 6, y: y(p.y) + (s.labelDy || -10), "text-anchor": "end", "font-size": 12, fill: css("--ink-2") }, s.name));
      }
    }
    host.append(svg);
  }

  // ---- derived numbers --------------------------------------------------------------------------------------
  const S = Object.fromEntries(R.summary.map((r) => [r.group, r]));
  const rateCI = (p, n) => { const h = Z * Math.sqrt(p * (1 - p) / n); return [p - h, p + h]; };
  const gapCI = (a, b) => {
    const se = Math.sqrt(a.rate * (1 - a.rate) / a.n + b.rate * (1 - b.rate) / b.n);
    return [a.rate - b.rate - Z * se, a.rate - b.rate + Z * se];
  };
  const LAD = Object.fromEntries(R.ladder.rows.map((r) => [r.key, r]));
  const OAX = R.oaxaca;
  const ML = R.ml.models;
  const coef = (blk, term, key = "coef") => blk.coefs.find((c) => c.term === term)[key];
  const rawGap = S.White.rate - S["Black or Hispanic"].rate;
  const unexplShare = OAX.pooled.unexplained / OAX.gap;
  const proxyBase = R.proxies.sets.find((s) => s.key === "features");
  const proxyPlace = R.proxies.sets.find((s) => s.key === "features_place");
  const MIT = Object.fromEntries(R.mitigation.rows.map((r) => [r.key, r]));
  const LB = R.label_bias;

  const V = {
    n_all: int(S.All.n), n_white: int(S.White.n), n_black: int(S.Black.n), n_hispan: int(S.Hispanic.n),
    n_nonwhite: int(S["Black or Hispanic"].n), ladder_n: int(R.ladder.n), ps6_n: int(R.ps6.n),
  };
  document.querySelectorAll("[data-v]").forEach((n) => { n.textContent = V[n.dataset.v]; });

  // ---- headline ---------------------------------------------------------------------------------------------
  function stat(host, value, label, note) {
    const s = el("div", { class: "stat" });
    s.append(el("div", { class: "label" }, label));
    if (note) s.append(el("div", { class: "note" }, note));
    s.append(el("div", { class: "value" }, value));
    host.append(s);
  }
  function renderHeadline() {
    const h = $("#headline");
    const credit = LAD.credit;
    stat(h, pp(rawGap).replace(" pp", ""), "Point gap in approval rates", `${pct(S.White.rate)} of white applicants approved vs ${pct(S["Black or Hispanic"].rate)} of Black or Hispanic applicants`);
    stat(h, pp(credit.lpm.est).replace(" pp", ""), "Points remain after credit history", `Linear model, 95% interval ${ci(credit.lpm.est - Z * credit.lpm.se, credit.lpm.est + Z * credit.lpm.se)}`);
    stat(h, pct(unexplShare, 0), "Of the gap the recorded variables don't explain", "Oaxaca-Blinder, pooled reference; not a measure of discrimination by itself");
    stat(h, pp(-ML.logit.gaps.d_selection).replace(" pp", ""), "Point approval gap from a model that never sees race", "Race-blind logistic regression at the lenders' approval volume");
  }

  // ---- overview ---------------------------------------------------------------------------------------------
  function renderRates() {
    const order = ["White", "Black", "Hispanic", "Black or Hispanic", "All"];
    const rows = order.map((g) => {
      const r = S[g];
      const [lo, hi] = rateCI(r.rate, r.n);
      const color = g === "White" ? "--s1" : g === "All" ? "--ink-2" : "--s2";
      return { label: g === "All" ? "All applicants" : g + " applicants", sub: `${int(r.approved)} of ${int(r.n)}`,
        series: [{ color, est: r.rate, lo, hi }] };
    });
    intervalChart($("#chart-rates"), rows, { ticks: [0.5, 0.6, 0.7, 0.8, 0.9, 1], zero: false, label: "Approval rate by group with 95% intervals" });
    table($("#table-rates"), ["Group", "Applications", "Approved", "Approval rate", "95% interval"],
      order.map((g) => { const r = S[g]; const [lo, hi] = rateCI(r.rate, r.n); return [g, int(r.n), int(r.approved), pct(r.rate), ci(lo, hi, pct)]; }));
  }

  function renderFindings() {
    const c = LAD.credit, f = LAD.file, p6 = LAD.ps6;
    const gl = OAX.pooled, refs = [OAX.white_coefs.unexplained, OAX.nonwhite_coefs.unexplained, OAX.pooled.unexplained];
    const [g0, g1] = gapCI(S.White, S["Black or Hispanic"]);
    const lg = ML.logit.gaps, lci = ML.logit.ci;
    const items = [
      `<b>The raw gap is large.</b> Lenders approved ${pct(S.White.rate)} of white applicants and ${pct(S["Black or Hispanic"].rate)} of Black or Hispanic applicants (${pct(S.Black.rate)} Black, ${pct(S.Hispanic.rate)} Hispanic): a ${pp(rawGap)} gap (95% interval ${ci(g0, g1)}).`,
      `<b>The recorded finances and credit histories account for part of it, not most of it.</b> After controlling for the problem set's variables, being white is associated with a ${pp(p6.lpm.est)} higher approval probability; adding credit history brings that to ${pp(c.lpm.est)} (probit: ${pp(c.probit.est)}). The decomposition attributes ${pp(gl.explained)} of the ${pp(OAX.gap)} gap to differences in those variables and leaves ${pp(gl.unexplained)} (${pct(unexplShare, 0)}) unexplained. Depending on the reference coefficients, the unexplained part runs from ${pp(Math.min(...refs))} to ${pp(Math.max(...refs))}.`,
      `<b>What counts as a control decides the answer.</b> Adding the lender's own judgments (meets guidelines, unverifiable information) and finer credit detail cuts the remaining gap to ${pp(f.lpm.est)} (probit ${pp(f.probit.est)}), still above zero. Those judgments were made by the lenders being studied, so this is a lower bound only if they were made without bias.`,
      `<b>Dropping race from a model doesn't remove the gap.</b> A logistic regression trained without race, sex, marital status, age or neighborhood would approve ${pct(ML.logit.groups.White.selection)} of white and ${pct(ML.logit.groups["Black or Hispanic"].selection)} of Black or Hispanic applicants: a ${pp(-lg.d_selection)} gap (95% interval ${ci(-lci.d_selection[1], -lci.d_selection[0])}), about the lenders' own. Its inputs predict race with an AUC of ${num(proxyBase.logit, 2)} (${num(proxyPlace.logit, 2)} with neighborhood).`,
      `<b>The same score didn't mean the same outcome.</b> At every score level, Black and Hispanic applicants were approved less often than the race-blind model predicted, and white applicants as often or more often. That pattern is consistent with the gap the econometrics leave unexplained.`,
      `<b>Fixes cost little agreement but need care.</b> Separate cutoffs by group close the approval gap while matching the 1990 decisions ${pct(MIT.parity.accuracy)} of the time instead of ${pct(MIT.baseline.accuracy)}, but using race at the decision is itself disparate treatment under U.S. fair-lending law. Reweighting the training data barely moves the gap here.`,
      `<b>The yardstick is part of the problem.</b> If the unexplained gap came from biased decisions, a model graded against those decisions looks better than it is: in that what-if, its true-positive-rate gap is ${pp(-LB.original_vs_relabeled["gaps/d_tpr"])}, not the ${pp(-LB.recorded["gaps/d_tpr"])} measured against the recorded labels.`,
    ];
    const ul = el("ul");
    items.forEach((t) => ul.append(html("li", {}, t)));
    $("#findings").replaceChildren(ul);
  }

  // ---- econometrics -----------------------------------------------------------------------------------------
  function renderLadder() {
    const subs = { raw: "the raw difference", ps6: "ratios, LTV, unemployment, family, bankruptcy", credit: "+ school, cosigner, delinquencies, late payments, vacancy", file: "+ guidelines, consumer credit, self-employed, unverified" };
    const names = { raw: "No controls", ps6: "Problem set 6", credit: "+ Credit history", file: "+ Lender's file" };
    const rows = R.ladder.rows.map((r) => ({
      label: names[r.key], sub: subs[r.key],
      series: [
        { name: "Linear probability model", color: "--ink-2", est: r.lpm.est, lo: r.lpm.est - Z * r.lpm.se, hi: r.lpm.est + Z * r.lpm.se },
      ],
    }));
    rows.forEach((r, i) => r.series.forEach((s) => { const pr = R.ladder.rows[i].probit; s.tip = [{ label: "Linear model gap", value: pp(s.est) }, { label: "95% interval", value: ci(s.lo, s.hi) }, { label: "Probit AME", value: pp(pr.est) }]; }));
    intervalChart($("#chart-ladder"), rows, { fmt: (t) => minus((100 * t).toFixed(0)), xLabel: "Approval gap, percentage points (white minus Black or Hispanic)", labelWidth: 330, label: "Approval gap as controls are added" });
    const se = (o) => `${pp(o.est)} (${num(100 * o.se, 1)})`;
    table($("#table-ladder"), ["Controls", "Variables", "LPM", "Probit AME", "Logit AME", "Black vs white", "Hispanic vs white"],
      R.ladder.rows.map((r) => [names[r.key], String(r.k), se(r.lpm), se(r.probit), se(r.logit), se({ est: -r.black.est, se: r.black.se }), se({ est: -r.hispan.est, se: r.hispan.se })]));
    $("#table-ladder").append(el("p", { class: "note" }, "Standard errors in parentheses, in points. The last two columns are probit average marginal effects from a model with Black and Hispanic indicators, shown as white minus each group. Average marginal effects switch the race indicator from 0 to 1 for every applicant."));
    $("#ladder-note").innerHTML = `Each step changes what "comparable applicants" means. The credit-history row matches Wooldridge's textbook specification (Computer Exercise C7.8). The last row adds information the lenders produced themselves, so part of any bias could sit inside those controls. Separately, Black applicants' gap with credit history is ${pp(-LAD.credit.black.est)} and Hispanic applicants' is ${pp(-LAD.credit.hispan.est)}.`;
  }

  function renderInteraction() {
    const I = R.interactions;
    groupLegend($("#legend-inter"), "line");
    const series = [
      { name: "White", color: "--s1", pts: I.curve.map((c) => ({ x: c.x, y: c.p1, lo: c.p1 - Z * c.se1, hi: c.p1 + Z * c.se1, title: `Obligations ratio ${c.x}%`, tip: tipCurve(c) })) },
      { name: "Black or Hispanic", color: "--s2", pts: I.curve.map((c) => ({ x: c.x, y: c.p0, lo: c.p0 - Z * c.se0, hi: c.p0 + Z * c.se0, title: `Obligations ratio ${c.x}%`, tip: tipCurve(c) })) },
    ];
    xyChart($("#chart-inter"), series, { bands: true, xLabel: "Total obligations as % of income (obrat)", yLabel: "Average predicted approval", yTicks: [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1], label: "Predicted approval by obligations ratio" });
    table($("#table-inter"), ["Obligations ratio", "White", "Black or Hispanic", "Gap", "95% interval"],
      I.curve.map((c) => [c.x + "%", pct(c.p1), pct(c.p0), pp(c.gap), ci(c.gap - Z * c.gap_se, c.gap + Z * c.gap_se)]));
    const q = I.obrat_pctiles;
    $("#inter-note").innerHTML = `The curves pull apart as obligations rise, but the interaction itself is not statistically distinguishable from zero (probit Wald p = ${num(I.probit_wald.p, 2)}; in the linear model, white × housing ratio, obligations ratio and loan-to-value jointly p = ${num(I.lpm_wald.p, 3)}). Half of applicants have obligations between ${num(q["25"], 0)}% and ${num(q["75"], 0)}% of income and 95% are below ${num(q["95"], 0)}%, so the right side of the chart rests on few applications.`;
  }
  const tipCurve = (c) => [
    { label: "White", value: pct(c.p1), color: css("--s1") },
    { label: "Black or Hispanic", value: pct(c.p0), color: css("--s2") },
    { label: "Gap", value: pp(c.gap) },
    { label: "95% interval", value: ci(c.gap - Z * c.gap_se, c.gap + Z * c.gap_se) },
  ];

  function renderPS6() {
    const P = R.ps6;
    const terms = ["white", "hrat", "obrat", "loanprc", "unem", "male", "married", "dep", "pubrec", "const"];
    // probit/logit: the information-matrix SEs Stata prints by default, so the table can be checked against Stata
    const c = (blk, t) => `${num(coef(blk, t), 4)} (${num(coef(blk, t, blk === P.lpm ? "se" : "se_oim"), 4)})`;
    const ame = (t) => t === "const" ? "" : `${num(P.probit.ame_derivative[t].est, 4)} (${num(P.probit.ame_derivative[t].se, 4)})`;
    table($("#table-ps6"), ["Variable", "LPM (robust SE)", "Probit (SE)", "Logit (SE)", "Probit AME (SE)"],
      terms.map((t) => [t === "const" ? "constant" : t, c(P.lpm, t), c(P.probit, t), c(P.logit, t), ame(t)]),
      { highlight: (i) => i === 0 || i === 8 });
    const disc = P.probit.ame_discrete.white;
    $("#ps6-note").innerHTML = `R² ${num(P.lpm.r2, 4)}; probit log likelihood ${num(P.probit.ll, 3)}, logit ${num(P.logit.ll, 3)}. Probit and logit SEs here are the information-matrix ones Stata prints by default; the robust versions (used everywhere else on this page) are slightly larger, e.g. ${num(coef(P.probit, "white", "se"), 4)} for the probit's white coefficient. The AMEs treat every regressor as continuous, as <code>margins, dydx(*)</code> does without factor notation; switching <code>white</code> from 0 to 1 for everyone instead gives ${pp(disc.est)} (SE ${num(100 * disc.se, 1)}), the better summary for a 0/1 variable. The linear model's predictions run from ${num(P.lpm.phat_min, 3)} to ${num(P.lpm.phat_max, 3)}, and ${int(P.lpm.n_out_of_range)} of ${int(P.n)} fall outside [0, 1], all above 1. (A Stata <code>count if phat > 1</code> without <code>& !missing(phat)</code> reports ${int(P.lpm.n_out_of_range + (S.All.n - P.n))}, because Stata treats the ${S.All.n - P.n} missing predictions as larger than any number.)`;
  }

  // ---- decomposition ----------------------------------------------------------------------------------------
  function renderOaxaca() {
    legend($("#legend-oaxaca"), [{ label: "Explained by the recorded variables", color: "--muted" }, { label: "Unexplained", color: "--ink" }]);
    const F = R.oaxaca_file;
    const mk = (label, sub, o, gap) => ({
      label, sub, parts: [
        { name: "Explained", color: "--muted", v: o.explained, tip: [{ label: "Explained", value: pp(o.explained), color: css("--muted") }, { label: "Unexplained", value: pp(o.unexplained), color: css("--ink") }, { label: "Total gap", value: pp(gap) }] },
        { name: "Unexplained", color: "--ink", v: o.unexplained, tip: [{ label: "Explained", value: pp(o.explained), color: css("--muted") }, { label: "Unexplained", value: pp(o.unexplained), color: css("--ink") }, { label: "Total gap", value: pp(gap) }] },
      ],
    });
    const rows = [
      mk("Pooled reference", "credit-history model (main)", OAX.pooled, OAX.gap),
      mk("White coefficients", "credit-history model", OAX.white_coefs, OAX.gap),
      mk("Black/Hispanic coefficients", "credit-history model", OAX.nonwhite_coefs, OAX.gap),
      mk("Probit version", "pooled, nonlinear check", OAX.probit_check, OAX.gap),
      mk("+ Lender's file", "pooled reference", F.pooled, F.gap),
    ];
    stackedBars($("#chart-oaxaca"), rows, { xLabel: "Percentage points of the approval gap", label: "Oaxaca-Blinder decomposition" });
    const r = (lab, o, gap) => [lab, pp(gap), pp(o.explained), o.explained_ci ? ci(...o.explained_ci) : "", pp(o.unexplained), o.unexplained_ci ? ci(...o.unexplained_ci) : "", pct(o.unexplained / gap, 0)];
    table($("#table-oaxaca"), ["Reference", "Gap", "Explained", "95% interval", "Unexplained", "95% interval", "Unexplained share"], [
      r("Pooled (main)", OAX.pooled, OAX.gap), r("White coefficients", OAX.white_coefs, OAX.gap), r("Black/Hispanic coefficients", OAX.nonwhite_coefs, OAX.gap),
      r("Probit, pooled", OAX.probit_check, OAX.gap), r("+ Lender's file, pooled", F.pooled, F.gap)]);
    $("#oaxaca-note").innerHTML = `The main split uses coefficients from a pooled regression that includes a group indicator (Jann 2008; Fortin 2008), so the group difference doesn't leak into the reference. Using white applicants' coefficients as the yardstick asks "how would Black or Hispanic applicants fare if treated like white applicants with the same files", and gives the largest unexplained part; using Black and Hispanic applicants' coefficients gives the smallest. Intervals come from ${int(OAX.reps)} bootstrap resamples within each group. The unexplained part also absorbs anything the files don't record.`;
  }

  function renderDetail() {
    const L = R.ml.labels;
    const name = (v) => ({ white: "White", hrat: L.hrat, obrat: L.obrat, loanprc: L.loanprc, unem: L.unem, male: "Male", married: "Married", dep: L.dep, pubrec: L.pubrec, sch: L.sch, cosign: L.cosign, chist: L.chist, mortlat1: L.mortlat1, mortlat2: L.mortlat2, vr: L.vr })[v] || v;
    const rows = OAX.detail.slice().sort((a, b) => b.contrib - a.contrib).map((d) => ({
      label: name(d.var), series: [{ color: "--ink-2", est: d.contrib, lo: d.contrib - Z * d.se, hi: d.contrib + Z * d.se,
        tip: [{ label: "Contribution", value: pp(d.contrib, 2) }, { label: "95% interval", value: ci(d.contrib - Z * d.se, d.contrib + Z * d.se, (v) => pp(v, 2)) }, { label: "Mean, white", value: num(d.mean_white, 3) }, { label: "Mean, Black or Hispanic", value: num(d.mean_nonwhite, 3) }] }],
    }));
    intervalChart($("#chart-detail"), rows, { fmt: (t) => minus((100 * t).toFixed(1)), xLabel: "Percentage points of the explained part", rowH: 28, labelWidth: 270, label: "Contributions to the explained gap" });
    table($("#table-detail"), ["Variable", "Mean, white", "Mean, Black or Hispanic", "Contribution", "SE"],
      OAX.detail.slice().sort((a, b) => b.contrib - a.contrib).map((d) => [name(d.var), num(d.mean_white, 3), num(d.mean_nonwhite, 3), pp(d.contrib, 2), num(100 * d.se, 2)]), { textCols: [] });
  }

  // ---- race-blind models ------------------------------------------------------------------------------------
  const MODELS = {
    logit: { label: "Logistic regression", note: "Trained without race, sex, marital status, age or neighborhood, on 17 finance and credit inputs." },
    gbm: { label: "Gradient boosting", note: "Same 17 inputs as the logistic regression; a nonlinear model (150 depth-2 trees)." },
    logit_lender: { label: "+ Lender's judgments", note: "Adds the lender's own 'meets credit guidelines' and 'unverifiable information' calls. These mimic the decision more closely, and may carry the lenders' biases with them." },
    logit_race: { label: "With race (for contrast)", note: "Adds the white indicator. Shown only to make the point that a model fit to these decisions learns the race gap directly; it is not a candidate model." },
  };
  let model = "logit";
  function renderModels() {
    const pick = $("#pick-model");
    if (!pick.childElementCount) {
      for (const [k, m] of Object.entries(MODELS)) {
        const b = el("button", { type: "button", "aria-pressed": String(k === model) }, m.label);
        b.addEventListener("click", () => { model = k; pick.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); renderModels(); });
        pick.append(b);
      }
    }
    const M = ML[model], G = M.groups, g = M.gaps, c = M.ci;
    $("#models-sub").textContent = `Each applicant scored by a model that never saw them (${R.ml.folds}-fold cross-validation, ${int(R.ml.n)} applications with complete inputs). The cutoff approves ${pct(R.ml.approval_rate)} of applicants, the share the lenders approved. Gaps are white minus Black or Hispanic.`;
    $("#model-note").textContent = MODELS[model].note;
    const tiles = $("#model-tiles");
    tiles.replaceChildren();
    stat(tiles, pp(-g.d_selection), "Approval-rate gap", `95% interval ${ci(-c.d_selection[1], -c.d_selection[0])}; lenders' own gap ${pp(G.White.base_rate - G["Black or Hispanic"].base_rate)}`);
    stat(tiles, num(g.selection_ratio, 2), "Approval ratio", "Black or Hispanic ÷ white; the four-fifths rule of thumb flags values below 0.80");
    stat(tiles, pp(-g.d_tpr), "True-positive-rate gap", `Equal opportunity; 95% interval ${ci(-c.d_tpr[1], -c.d_tpr[0])}`);
    stat(tiles, pp(-g.d_fpr), "False-positive-rate gap", `With TPR, equalized odds; 95% interval ${ci(-c.d_fpr[1], -c.d_fpr[0])}`);
    groupLegend($("#legend-rates"));
    const metric = (key, label, sub, denom) => ({
      label, sub, series: ["White", "Black or Hispanic"].map((grp) => {
        const r = G[grp], n = denom(r), [lo, hi] = rateCI(r[key], n);
        return { name: grp, color: SERIES[grp], est: r[key], lo, hi, tip: [{ label: grp, value: pct(r[key]), color: css(SERIES[grp]) }, { label: "95% interval", value: ci(lo, hi, pct) }, { label: "Out of", value: int(Math.round(n)) }] };
      }),
    });
    const rows = [
      metric("base_rate", "Lenders approved", "the 1990 decisions", (r) => r.n),
      metric("selection", "Model approves", "demographic parity", (r) => r.n),
      metric("tpr", "TPR", "of those lenders approved", (r) => r.n * r.base_rate),
      metric("fpr", "FPR", "of those lenders denied", (r) => r.n * (1 - r.base_rate)),
    ];
    intervalChart($("#chart-fair"), rows, { ticks: [0, 0.2, 0.4, 0.6, 0.8, 1], labelWidth: 200, label: "Fairness rates by group" });
    const order = ["White", "Black or Hispanic", "Black", "Hispanic", "All"];
    table($("#table-fair"), ["Group", "n", "Lenders approved", "Model approves", "TPR", "FPR", "Agreement", "AUC", "Mean score"],
      order.map((k) => { const r = G[k]; return [k, int(r.n), pct(r.base_rate), pct(r.selection), pct(r.tpr), pct(r.fpr), pct(r.accuracy), num(r.auc, 3), num(r.mean_score, 3)]; }), { highlight: (i) => i === 4 });
    renderCalibration();
  }

  function renderCalibration() {
    const cal = ML[model].calibration;
    groupLegend($("#legend-cal"));
    const series = ["White", "Black or Hispanic"].map((grp) => ({
      name: grp, color: SERIES[grp], line: true,
      pts: cal.filter((c) => c.group === grp).map((c) => ({
        x: c.predicted, y: c.observed, lo: Math.max(0, c.observed - Z * c.se), hi: Math.min(1, c.observed + Z * c.se),
        title: `${grp}, score ${num(c.lo, 2)}–${num(c.hi, 2)}`,
        tip: [{ label: "Predicted", value: pct(c.predicted) }, { label: "Observed", value: pct(c.observed) }, { label: "Applications", value: int(c.n) }],
      })),
    }));
    xyChart($("#chart-cal"), series, { diagonal: true, xTicks: [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1], yTicks: [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1], xFmt: (t) => pct(t, 0), xLabel: "Model's average predicted approval", yLabel: "Observed approval", height: 330, label: "Calibration by group" });
    table($("#table-cal"), ["Group", "Score bin", "Applications", "Predicted", "Observed", "95% interval"],
      cal.map((c) => [c.group, `${num(c.lo, 2)}–${num(c.hi, 2)}`, int(c.n), pct(c.predicted), pct(c.observed), ci(Math.max(0, c.observed - Z * c.se), Math.min(1, c.observed + Z * c.se), pct)]), { textCols: [1] });
    const nb = cal.filter((c) => c.group === "Black or Hispanic");
    const below = nb.filter((c) => c.observed < c.predicted).length;
    $("#cal-note").innerHTML = model === "logit_race"
      ? "With race as an input the model can fit each group's level separately, so both groups sit near the diagonal. That is calibration bought by encoding the gap."
      : `In ${below} of ${nb.length} score bins, Black and Hispanic applicants were approved less often than the race-blind model predicted, while white applicants sit on or above it. Put plainly, files the model scores alike were decided differently by group. Each bin holds only ${Math.min(...nb.map((c) => c.n))}–${Math.max(...nb.map((c) => c.n))} Black or Hispanic applications, so single bins are noisy; the pattern across bins is the finding.`;
  }

  // ---- proxies & trade-offs ---------------------------------------------------------------------------------
  function renderProxies() {
    const P = R.proxies;
    const SHORT = { all: "Everything: + judgments, place, sex, marriage, age", features_lender: "+ the lender's judgments" };
    const rows = P.sets.map((s) => ({ label: s.label, short: SHORT[s.key], sub: `${s.k} variables`, series: [{ color: "--ink-2", est: s.logit, tip: [{ label: "Logistic AUC", value: num(s.logit, 3) }, { label: "Gradient boosting AUC", value: num(s.gbm, 3) }] }] }));
    intervalChart($("#chart-proxy"), rows, { ticks: [0.5, 0.6, 0.7, 0.8], zero: false, fmt: (t) => num(t, 1), xLabel: "AUC for predicting Black or Hispanic (0.5 = no information)", labelWidth: 360, label: "How well variable sets predict race" });
    table($("#table-proxy"), ["Variables", "Count", "Logistic AUC", "Gradient boosting AUC"], P.sets.map((s) => [s.label, String(s.k), num(s.logit, 3), num(s.gbm, 3)]));
    const CONT = ["loanprc", "obrat", "hrat", "cons", "unem", "dep", "log_appinc", "log_loanamt", "netw_signed_log"];
    const fmtMean = (f, v) => (CONT.includes(f) ? num(v, 2) : pct(v, 0));
    table($("#table-single"), ["Variable", "Kind", "AUC alone", "Mean, white", "Mean, Black or Hispanic"],
      P.single.slice(0, 12).map((s) => [s.label, { features: "model input", lender: "lender's judgment", place: "neighborhood" }[s.set], num(s.auc, 3), fmtMean(s.feature, s.mean_white), fmtMean(s.feature, s.mean_nonwhite)]), { textCols: [1] });
  }

  function renderMitigation() {
    const rows = R.mitigation.rows;
    table($("#table-mit"), ["Approach", "Approval, white", "Approval, Black or Hispanic", "Gap", "TPR gap", "FPR gap", "Agreement", "Uses race at decision?"],
      rows.map((r) => [r.label, pct(r.sel_white), pct(r.sel_other), pp(-r.d_selection), pp(-r.d_tpr), pp(-r.d_fpr), pct(r.accuracy), r.key === "parity" || r.key === "equal_opportunity" ? "Yes" : "No"]), { textCols: [7] });
    const F = R.mitigation.frontier;
    xyChart($("#chart-frontier"), [{ name: "Race-blind logistic regression", color: "--ink-2", pts: F.map((f) => ({ x: -100 * f.d_selection, y: f.accuracy, title: `${pct(f.lam, 0)} of the way to parity`, tip: [{ label: "Approval gap", value: pp(-f.d_selection) }, { label: "Agreement with 1990 decisions", value: pct(f.accuracy) }, { label: "TPR gap", value: pp(-f.d_tpr) }] })) }],
      { xLabel: "Remaining approval gap, percentage points", yLabel: "Agreement", yFmt: (v) => pct(v, 1), xFmt: (t) => minus(String(t)), height: 260, label: "Agreement against approval gap" });
    table($("#table-frontier"), ["Step toward parity", "Approval gap", "TPR gap", "Agreement"], F.map((f) => [pct(f.lam, 0), pp(-f.d_selection), pp(-f.d_tpr), pct(f.accuracy)]));
    const b = MIT.baseline, p = MIT.parity, e = MIT.equal_opportunity, w = MIT.reweigh;
    $("#mit-note").innerHTML = `Closing the whole gap costs ${pp(b.accuracy - p.accuracy)} of agreement with the 1990 decisions, and that "cost" is measured against decisions this audit is questioning. Equal opportunity (equal TPRs) costs ${pp(b.accuracy - e.accuracy)} and leaves a ${pp(-e.d_selection)} approval gap. Reweighting (gap ${pp(-w.d_selection)}) barely helps: with race out of the model and a different mix of files by group, reweighting can only shift how much each file counts. Separate cutoffs by race would be disparate treatment under the Equal Credit Opportunity Act and the Fair Housing Act. They are shown to size the trade-off, not as a recommendation. Fixes that don't use race at the decision change the inputs or the training target instead.`;
  }

  function renderLabelBias() {
    const L = LB;
    $("#lb-sub").innerHTML = `A what-if, not an estimate. Suppose the gap the credit-history probit leaves unexplained came from biased decisions. Each denied Black or Hispanic applicant is relabeled "approved" with the probability that closes their predicted gap to a white applicant with the same file: about ${num(L.mean_flips, 0)} of ${int(L.n_nonwhite_denied)} denials per draw, averaged over ${int(L.draws)} random draws. White applicants' labels don't change.`;
    const row = (lab, key, f) => [lab, f(L.recorded[key]), f(L.retrained[key]), f(L.original_vs_relabeled[key])];
    const neg = (v) => pp(-v);
    table($("#table-lb"), ["", "Recorded labels", "Model retrained on relabeled data", "Original model, graded on relabeled data"], [
      row("Black or Hispanic approval rate in the labels", "groups/Black or Hispanic/base_rate", pct),
      row("Model approves: white", "groups/White/selection", pct),
      row("Model approves: Black or Hispanic", "groups/Black or Hispanic/selection", pct),
      row("Approval gap", "gaps/d_selection", neg),
      row("TPR gap (equal opportunity)", "gaps/d_tpr", neg),
      row("FPR gap", "gaps/d_fpr", neg),
      row("Agreement with the labels", "groups/All/accuracy", pct),
    ], { textCols: [] });
    $("#lb-note").innerHTML = `Two lessons. First, the race-blind model's approvals barely move when retrained on the relabeled data (gap ${pp(-L.retrained["gaps/d_selection"])} vs ${pp(-L.recorded["gaps/d_selection"])}): the inputs that predict denial are the same inputs that differ by group, and only a minority of denials are relabeled. Second, the same model's error-rate gaps look smaller against the recorded labels (TPR gap ${pp(-L.recorded["gaps/d_tpr"])}) than against the relabeled ones (${pp(-L.original_vs_relabeled["gaps/d_tpr"])}). If the recorded decisions were biased, metrics computed against them understate unfairness. This data also has no repayment outcomes at all, only decisions, so no version of the label here measures creditworthiness directly.`;
  }

  // ---- method -----------------------------------------------------------------------------------------------
  function renderMethod() {
    const m = R.meta;
    $("#method").innerHTML = `
      <h2>How it was built</h2>
      <h3>The data</h3>
      <p>${m.source}: ${int(m.rows)} applications and ${m.variables} variables. In 1990 the Federal Reserve Bank of Boston
        added loan-file information (debt ratios, credit histories, employment, wealth) to the Home Mortgage Disclosure
        Act records of Boston-area applications to study race and denial (Munnell, Tootell, Browne and McEneaney 1996).
        The study drew every Black and Hispanic applicant's file but only a random sample of white applicants', and
        Wooldridge's textbook distributes a subset of it as LOANAPP, so rates here describe this sample, not all Boston
        applications in 1990.</p>
      <p>The <code>wooldridge</code> Python package ships 59 of the textbook file's 62 variables; the other three
        (<code>race</code>, <code>gender</code> and <code>obwhte</code> = obrat × white) are exact functions of the
        others and are rebuilt. All 62 were compared against the textbook's Stata file and match exactly, and every
        build checks the shape, the non-missing counts and the means against the published variable list. The data
        fingerprint is <code>${m.fingerprint.slice(0, 16)}…</code>. Some fields carry what look like code values rather than
        data (<code>gdlin</code> = 666 for two applicants; 999,999 in <code>lines</code> and <code>term</code>;
        1,000,000 in <code>liq</code>). The analysis treats <code>gdlin</code> = 666 as missing and doesn't use the others.</p>
      <h3>Part A: econometrics</h3>
      <p>Python with statsmodels, following Stata's conventions so the course's models can be checked digit for digit:
        heteroskedasticity-robust (HC1) standard errors for the linear probability model; probit and logit by maximum
        likelihood, with robust sandwich standard errors scaled by N/(N−1) for inference; average marginal effects
        averaged over the estimation sample with delta-method standard errors. The problem-set models were checked
        against the course's Stata output (kept private, as course material) and agree to every printed digit,
        coefficients, standard errors, log likelihoods and marginal effects alike.</p>
      <p>The ladder of controls estimates every specification on one common sample, so the rows differ only in their
        controls. The Oaxaca-Blinder decomposition is linear, two-fold, with pooled coefficients from a regression that
        includes the group indicator; bootstrap standard errors resample within each group.</p>
      <h3>Part B: machine-learning fairness</h3>
      <p>scikit-learn logistic regression (standardized inputs) and gradient boosting, trained on 17 finance and credit
        inputs and nothing about race, sex, marital status, age or neighborhood. Every score is out-of-fold (5-fold
        cross-validation stratified by group and outcome). The cutoff approves the same share the lenders did.
        Fairness metrics are written out by hand (no fairness library) and tested against hand-worked examples.
        Intervals for the gaps resample applicants with the predictions held fixed, so they cover the sampling of
        applicants evaluated, not retraining. Mitigation compares reweighting (Kamiran and Calders 2012) and
        group-specific cutoffs (Hardt, Price and Srebro 2016).</p>
      <h3>Words used carefully</h3>
      <p>"Gap" and "associated with" describe differences in recorded outcomes. "Unexplained" means not accounted for
        by the variables recorded. Nothing here says a lender discriminated or didn't; the Boston Fed study's own
        conclusions were debated, including over data errors and omitted variables (Day and Liebowitz 1998; see Ladd
        1998 for a review).</p>
      <h3>How it's checked</h3>
      <ul>
        <li><code>build.py</code> refuses to write the page's data if the problem-set models stop reproducing, the data
          fail their checks, or a fact the text states stops holding.</li>
        <li>Tests cover the loader, the models (against statsmodels' own marginal effects), the decomposition's
          identity (explained + unexplained = gap), and every fairness metric against hand-worked cases.</li>
        <li>GitHub Actions rebuilds everything on each push and fails if the committed numbers differ from a fresh build.</li>
      </ul>
      <h3>References</h3>
      <ul class="refs">
        <li>Wooldridge, J. M. (2020). <em>Introductory Econometrics: A Modern Approach</em>, 7th ed. Cengage. Data set LOANAPP; Python package <code>wooldridge</code> (T. Haruyama).</li>
        <li>Munnell, A. H., Tootell, G. M. B., Browne, L. E., and McEneaney, J. (1996). Mortgage lending in Boston: Interpreting HMDA data. <em>American Economic Review</em> 86(1), 25–53.</li>
        <li>Day, T. E., and Liebowitz, S. J. (1998). Mortgage lending to minorities: Where's the bias? <em>Economic Inquiry</em> 36(1), 3–28.</li>
        <li>Ladd, H. F. (1998). Evidence on discrimination in mortgage lending. <em>Journal of Economic Perspectives</em> 12(2), 41–62.</li>
        <li>Oaxaca, R. (1973). Male-female wage differentials in urban labor markets. <em>International Economic Review</em> 14(3), 693–709. Blinder, A. S. (1973). Wage discrimination: Reduced form and structural estimates. <em>Journal of Human Resources</em> 8(4), 436–455.</li>
        <li>Jann, B. (2008). The Blinder-Oaxaca decomposition for linear regression models. <em>Stata Journal</em> 8(4), 453–479. Fortin, N. M. (2008). The gender wage gap among young adults in the United States. <em>Journal of Human Resources</em> 43(4), 884–918.</li>
        <li>Kamiran, F., and Calders, T. (2012). Data preprocessing techniques for classification without discrimination. <em>Knowledge and Information Systems</em> 33(1), 1–33.</li>
        <li>Hardt, M., Price, E., and Srebro, N. (2016). Equality of opportunity in supervised learning. <em>NeurIPS</em>.</li>
      </ul>`;
  }

  // ---- tabs & boot ------------------------------------------------------------------------------------------
  const VIEWS = ["overview", "econometrics", "decomposition", "models", "tradeoffs", "method"];
  const ANCHORS = { limits: "overview", models: "models", method: "method" };
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
    if (!$("#view-econometrics").hidden) { renderLadder(); renderInteraction(); }
    if (!$("#view-decomposition").hidden) { renderOaxaca(); renderDetail(); }
    if (!$("#view-models").hidden) renderModels();
    if (!$("#view-tradeoffs").hidden) { renderProxies(); renderMitigation(); }
  }
  function route(h, scroll) {
    const view = VIEWS.includes(h) ? h : ANCHORS[h];
    if (!view) return;
    select(view, false);
    if (scroll) {
      const target = ANCHORS[h] && h !== view ? document.getElementById(h) : document.querySelector(".tabs");
      (target || document.querySelector(".tabs")).scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  window.addEventListener("hashchange", () => route(location.hash.slice(1), true));
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(renderVisible, 120); });
  window.addEventListener("themechange", renderVisible);

  renderHeadline();
  renderFindings();
  renderPS6();
  renderLabelBias();
  renderMethod();
  $("#stamp").textContent = `Built from data fingerprint ${R.meta.fingerprint.slice(0, 12)}.`;
  const start = location.hash.slice(1);
  if (start) route(start, false); else select("overview", false);
})();
