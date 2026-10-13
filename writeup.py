"""The plain-language write-up of the Virginia findings, generated from the built data so no number is typed twice.

    python writeup.py

Writes:
- docs/virginia-in-plain-words.md : a one-page summary for readers who won't open the charts;
- social/virginia/slide-1.png ... slide-8.png and caption.txt : an Instagram explainer carousel (1080 x 1080),
  drafts for the owner to review before anything is posted. Slides are rendered with headless Chrome or Edge
  (set CHROME to its path if it isn't found).
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
SOCIAL = ROOT / "social" / "virginia"
URL = "willmcnulty.github.io/Who-Gets-the-Loan/virginia"


def load():
    t = (ROOT / "site" / "virginia" / "data.js").read_text(encoding="utf-8")
    return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))


def facts(R):
    """Every number the write-up uses, in one place."""
    eras = R["meta"]["eras"]
    F = {"records": sum(r["records"] for r in R["reconcile"]),
         "core": sum(r["core_purchase"] + r["core_refinance"] for r in R["reconcile"]),
         "first": R["meta"]["years"][0], "last": R["meta"]["years"][-1]}
    rates = {}
    for r in R["rates"]:
        if r["purpose"] != "purchase":
            continue
        era = next(k for k, (a, b) in eras.items() if a <= r["year"] <= b)
        n, d = rates.get((era, r["group"]), (0, 0))
        rates[(era, r["group"])] = (n + r["n"], d + r["denied"])
    F["rate"] = {k: d / n for k, (n, d) in rates.items()}
    yearly = {(r["year"], r["group"]): r["rate"] for r in R["rates"] if r["purpose"] == "purchase"}
    ratios = [yearly[(y, "Black")] / yearly[(y, "White")] for y in R["meta"]["years"]]
    F["ratio_lo"], F["ratio_hi"] = min(ratios), max(ratios)
    F["series"] = [(y, yearly[(y, "White")], yearly[(y, "Black")]) for y in R["meta"]["years"]]
    g = {(e["era"], e["purpose"], e["spec"], e["group"]): e for e in R["eras"]}
    F["gap"] = g
    F["sorting"] = {e: v["sorting"] for e, v in R["lenders"].items()}
    return F


def pct(v, d=1):
    return f"{100 * v:.{d}f}%"


def pts(v, d=1):
    return f"{100 * v:.{d}f}"


# ------------------------------------------------------------------------------------------------- summary

def summary(F):
    L, E = "2018-2025", "2004-2011"
    g = F["gap"]
    raw, lend, full = (g[(L, "purchase", s, "Black")] for s in ("raw", "lender", "full"))
    lo, hi = full["est"] - 1.96 * full["se"], full["est"] + 1.96 * full["se"]
    s = F["sorting"][L]
    return f"""# Who gets the loan in Virginia? In plain words

*A summary of [the Virginia report]({"https://" + URL + "/"}). Every number below comes from the report's data.*

**What I looked at.** Every mortgage application Virginia lenders reported under the Home Mortgage Disclosure Act
from {F['first']} through {F['last']}: {F['records']:,} records from three government sources, joined into one dataset
and checked against the official counts. The comparisons use {F['core']:,} home-purchase and refinance applications
that lenders approved or denied.

**What I found.**

- **Black applicants were denied more often in every year.** For home purchases, Black applicants' denial rate was
  between {F['ratio_lo']:.1f} and {F['ratio_hi']:.1f} times white applicants' in each of the 22 years. In {L},
  {pct(F['rate'][(L, 'Black')])} of Black applicants were denied, against {pct(F['rate'][(L, 'White')])} of white
  applicants. Hispanic ({pct(F['rate'][(L, 'Hispanic')])}) and Asian ({pct(F['rate'][(L, 'Asian')])}) applicants were
  also denied more often than white applicants.
- **Part of the gap is where people apply.** Black applicants more often applied to lenders that deny more of
  everyone: in {L}, their lenders turned down {pct(s['Black'])} of all applicants, compared with {pct(s['White'])} at
  white applicants' lenders.
- **Comparing like with like shrinks the gap, but doesn't close it.** Comparing applicants at the same lender, in
  the same county and year, with similar incomes and loans, the Black-white gap falls from {pts(raw['est'])} to
  {pts(lend['est'])} percentage points. Adding what lenders have reported since 2018 (debt-to-income, loan-to-value,
  property value and the type of credit score used) leaves {pts(full['est'])} points (95% confidence interval
  {pts(lo)} to {pts(hi)}).
- **This isn't new.** The same comparison within lenders gave {pts(g[(E, 'purchase', 'lender', 'Black')]['est'])}
  points in {E} and {pts(g[('2012-2017', 'purchase', 'lender', 'Black')]['est'])} in 2012-2017.

**What it can't tell you.** The public data has no credit scores, savings or job histories. A gap that remains
after the controls fits discrimination, and it also fits differences the data don't record. These numbers show
where outcomes differ; they don't prove that any lender discriminated, or that none did.

**Where it comes from.** HMDA loan/application registers: 2004-2006 from the Federal Reserve via the National
Archives, 2007-2017 from the CFPB's historic files, 2018-2025 from the CFPB's HMDA Data Browser. Code and method:
[github.com/WillMcNulty/Who-Gets-the-Loan](https://github.com/WillMcNulty/Who-Gets-the-Loan).

*An independent student project; not affiliated with the University of Virginia, the CFPB, the Federal Reserve or
any lender.*
"""


# ------------------------------------------------------------------------------------------------- carousel

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1080px;height:1080px;background:#232d4b;color:#fff;font-family:"Segoe UI",system-ui,Arial,sans-serif;
  display:flex;flex-direction:column;padding:96px 96px 72px;position:relative;overflow:hidden}
body::after{content:"";position:absolute;left:0;right:0;bottom:0;height:16px;background:#e57200}
.k{font:700 26px "Cascadia Mono",Consolas,monospace;letter-spacing:.08em;text-transform:uppercase;color:#ff8f2e;margin-bottom:36px}
h1{font:600 76px/1.08 "Iowan Old Style","Palatino Linotype",Georgia,serif;letter-spacing:-.01em}
h1 .o{color:#ff8f2e}
h2{font:600 60px/1.12 "Iowan Old Style","Palatino Linotype",Georgia,serif}
p{font-size:34px;line-height:1.4;color:#c6cfe8;margin-top:28px}
.big{display:flex;gap:56px;margin-top:56px}
.big div{flex:1}
.big b{display:block;font:700 112px/1 "Cascadia Mono",Consolas,monospace;color:#fff}
.big b.o{color:#ff8f2e}
.big span{display:block;font-size:30px;color:#c6cfe8;margin-top:14px;line-height:1.3}
.foot{margin-top:auto;font-size:24px;color:#9aa6c8;display:flex;justify-content:space-between}
.n{font:700 24px "Cascadia Mono",Consolas,monospace;color:#9aa6c8}
ul{margin-top:36px;padding-left:36px}
li{font-size:34px;line-height:1.4;color:#c6cfe8;margin-bottom:18px}
li b{color:#fff}
svg text{font-family:"Segoe UI",Arial,sans-serif}
"""


def chart_svg(series):
    """Denial rates by year, white (blue) and Black (orange) applicants, home purchase."""
    W, H, l, r, t, b = 888, 420, 70, 20, 20, 50
    ys = [v for _, w, k in series for v in (w, k)]
    top = 0.40 if max(ys) <= 0.40 else 0.5
    x = lambda i: l + i * (W - l - r) / (len(series) - 1)
    y = lambda v: t + (1 - v / top) * (H - t - b)
    grid = "".join(f'<line x1="{l}" x2="{W - r}" y1="{y(v)}" y2="{y(v)}" stroke="#3a4570" stroke-width="2"/>'
                   f'<text x="{l - 12}" y="{y(v) + 9}" fill="#9aa6c8" font-size="24" text-anchor="end">{int(v * 100)}%</text>'
                   for v in [0, 0.1, 0.2, 0.3, 0.4][: int(top * 10) + 1])
    anchor = lambda yr: "start" if yr == series[0][0] else "end" if yr == series[-1][0] else "middle"
    years = "".join(f'<text x="{x(i)}" y="{H - 10}" fill="#9aa6c8" font-size="24" text-anchor="{anchor(yr)}">{yr}</text>'
                    for i, (yr, _, _) in enumerate(series) if yr in (2004, 2010, 2016, 2025))
    line = lambda k, c: '<path fill="none" stroke="%s" stroke-width="7" stroke-linejoin="round" d="M%s"/>' % (
        c, " L".join(f"{x(i):.1f},{y(s[k]):.1f}" for i, s in enumerate(series)))
    last = series[-1]
    labels = (f'<text x="{x(len(series) - 1) - 6}" y="{y(last[2]) - 22}" fill="#ff8f2e" font-size="28" font-weight="700" text-anchor="end">Black applicants</text>'
              f'<text x="{x(len(series) - 1) - 6}" y="{y(last[1]) + 44}" fill="#8ea3ea" font-size="28" font-weight="700" text-anchor="end">White applicants</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="margin-top:40px">{grid}{years}{line(1, "#8ea3ea")}{line(2, "#ff8f2e")}{labels}</svg>'


def slides(F):
    L = "2018-2025"
    g = F["gap"]
    raw, lend, full = (g[(L, "purchase", s, "Black")] for s in ("raw", "lender", "full"))
    s = F["sorting"][L]
    foot = lambda i: f'<div class="foot"><span>Source: HMDA, CFPB and Federal Reserve</span><span class="n">{i}/8</span></div>'
    return [
        f"""<div class="k">Virginia mortgages · {F['first']}–{F['last']}</div>
<h1>Who gets the loan <span class="o">in Virginia?</span></h1>
<p>{F['records'] / 1e6:.0f} million mortgage records from 22 years, joined into one dataset. Here's what they show,
and what they can't.</p>{foot(1)}""",
        f"""<div class="k">Every year</div><h2>Black applicants were denied more often than white applicants in all 22 years.</h2>
{chart_svg(F['series'])}{foot(2)}""",
        f"""<div class="k">{L.replace('-', '–')} · home purchase</div><h2>Denied:</h2>
<div class="big"><div><b class="o">{pct(F['rate'][(L, 'Black')])}</b><span>of Black applicants</span></div>
<div><b>{pct(F['rate'][(L, 'White')])}</b><span>of white applicants</span></div></div>
<p>Hispanic applicants: {pct(F['rate'][(L, 'Hispanic')])}. Asian applicants: {pct(F['rate'][(L, 'Asian')])}.</p>{foot(3)}""",
        f"""<div class="k">Where people apply</div><h2>Black applicants more often applied to lenders that deny more of everyone.</h2>
<div class="big"><div><b class="o">{pct(s['Black'])}</b><span>denied overall at Black applicants' lenders</span></div>
<div><b>{pct(s['White'])}</b><span>at white applicants' lenders</span></div></div>{foot(4)}""",
        f"""<div class="k">Like with like</div><h2>Same lender, same county, same year, similar income and loan:</h2>
<div class="big"><div><b>{pts(raw['est'])}</b><span>point gap before comparing like with like</span></div>
<div><b class="o">{pts(lend['est'])}</b><span>point gap after</span></div></div>{foot(5)}""",
        f"""<div class="k">Adding the 2018 data</div><h2>Add debt-to-income, loan-to-value and property value, and</h2>
<div class="big"><div><b class="o">{pts(full['est'])}</b><span>points remain (95% interval {pts(full['est'] - 1.96 * full['se'])}–{pts(full['est'] + 1.96 * full['se'])})</span></div></div>
<p>Smaller, but not zero, in every specification tried.</p>{foot(6)}""",
        f"""<div class="k">What this can't show</div><h2>The public data has no credit scores, savings or job histories.</h2>
<ul><li>A gap that remains <b>fits discrimination</b>, and it also <b>fits differences the data don't record</b>.</li>
<li>It shows where outcomes differ. <b>It doesn't prove</b> that any lender discriminated, or that none did.</li></ul>{foot(7)}""",
        f"""<div class="k">See it yourself</div><h2>Every chart, the map, the lenders and the method:</h2>
<p style="color:#fff;font-size:38px;margin-top:40px">{URL}</p>
<p>Data: HMDA loan/application registers (Federal Reserve via the National Archives, CFPB). Independent student
project; not affiliated with UVA, the CFPB or any lender. Link in bio.</p>{foot(8)}""",
    ]


def caption(F):
    L = "2018-2025"
    full = F["gap"][(L, "purchase", "full", "Black")]
    return (f"Who gets the loan in Virginia? I joined 22 years of public mortgage records ({F['records'] / 1e6:.0f} million) into "
            f"one dataset. Black applicants were denied more often than white applicants in every year from {F['first']} to "
            f"{F['last']}. Comparing similar applicants at the same lender, with the extra data lenders report since 2018, "
            f"a {pts(full['est'])}-point gap remains. The data have no credit scores, so this shows where outcomes differ, "
            f"not proof of discrimination.\n\nFull report and method: link in bio ({URL})\n"
            "Source: HMDA data from the CFPB and the Federal Reserve via the National Archives.\n\n"
            "#Virginia #Housing #Mortgages #FairLending #HMDA #DataAnalysis #RVA #NoVA #HamptonRoads")


def chrome():
    for c in [os.environ.get("CHROME"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", shutil.which("google-chrome"),
              shutil.which("chromium"), shutil.which("chrome")]:
        if c and Path(c).exists():
            return c
    return None


def render(pages):
    exe = chrome()
    SOCIAL.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for i, body in enumerate(pages, 1):
            html = Path(tmp) / f"s{i}.html"
            html.write_text(f"<!doctype html><meta charset='utf-8'><style>{CSS}</style><body>{body}</body>", encoding="utf-8")
            (SOCIAL / f"slide-{i}.html").write_text(html.read_text(encoding="utf-8"), encoding="utf-8")
            if exe:
                subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1080,1080",
                                "--force-device-scale-factor=1", f"--screenshot={SOCIAL / f'slide-{i}.png'}", html.as_uri()],
                               check=True, capture_output=True)
    return exe


if __name__ == "__main__":
    F = facts(load())
    DOCS.mkdir(exist_ok=True)
    (DOCS / "virginia-in-plain-words.md").write_text(summary(F), encoding="utf-8")
    exe = render(slides(F))
    (SOCIAL / "caption.txt").write_text(caption(F) + "\n", encoding="utf-8")
    print("wrote docs/virginia-in-plain-words.md, social/virginia/caption.txt and "
          + ("8 slides" if exe else "8 slide HTML files (no Chrome found for PNGs)"))
