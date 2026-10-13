"""Version 2: Virginia, 2004 onward. Builds the page data from the harmonized files.

    python -m hmda.fetch          # download the raw files (about 6.5 GB; not committed)
    python -m hmda.harmonize      # one harmonized Parquet file per year (not committed)
    python build_va.py            # site/virginia/data.js + results/virginia.json (committed)
    python build_va.py --geo      # also rebuild site/virginia/geo.js (map shapes)
    python build_va.py --lenders  # only the lender section (needs data/raw/lenders; see hmda/lenders.py)

The build refuses to write if a year's record count stops matching the publisher's official count.
"""

import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from build import tidy
from hmda import analysis, geo, harmonize, lenders, sources

ROOT = Path(__file__).parent
SITE = ROOT / "site" / "virginia"
RESULTS = ROOT / "results" / "virginia.json"

# Official Virginia record counts (all actions), for reconciliation.
#  2007-2017: the CFPB historic-data page ("Showing records for Virginia, All records"), read 2026-10-12.
#  2018 onward: the HMDA Data Browser aggregations API, summed over action codes 1-8, read 2026-10-12.
#  2004-2006 have no published state count; the check there is that every record parsed and has a valid action.
OFFICIAL = {2007: 784919, 2008: 539572, 2009: 637212, 2010: 517819, 2011: 482943, 2012: 634102, 2013: 563167,
            2014: 365572, 2015: 445447, 2016: 494057, 2017: 411507, 2018: 417107, 2019: 506758, 2020: 828032,
            2021: 828798, 2022: 456043, 2023: 313853, 2024: 351177, 2025: 397846}

BREAKS = [
    {"year": 2009, "what": "Higher-priced loan threshold changes (October 2009): rate spreads are measured against a new benchmark, so the high-priced share before and after isn't comparable."},
    {"year": 2012, "what": "Census tracts switch from 2000 to 2010 boundaries; tract demographics switch to the 2010 census and ACS. The maps put every year on 2020 tracts."},
    {"year": 2018, "what": "The 2015 HMDA rule takes effect: debt-to-income, combined LTV, property value, credit-score model, underwriting system, age, interest rate and loan costs are added; denial reasons become required; cash-out refinances and second homes are reported separately; open-end lines, reverse mortgages and business loans are flagged (and excluded here); race and ethnicity subgroups are added (folded back into the main groups here); loan amounts are rounded to $10,000 bands. Small lenders may be exempt from the new fields."},
    {"year": 2020, "what": "Reporting threshold for closed-end loans rises from 25 to 100 originations a year, so the smallest lenders drop out of the data."},
    {"year": 2022, "what": "Census tracts switch to 2020 boundaries."},
]


def reconcile():
    rows = []
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
    for y in range(sources.FIRST_YEAR, sources.LAST_YEAR + 1):
        p = harmonize.OUT / f"va_{y}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["action", "core", "purpose", "group"])
        row = {"year": y, "era": sources.era(y), "source": manifest[str(y)]["publisher"],
               "sha256": manifest[str(y)]["sha256"][:12], "records": int(len(d)), "official": OFFICIAL.get(y),
               "valid_action": float(d.action.between(1, 8).mean()),
               "core_purchase": int(((d.core == 1) & (d.purpose == "purchase")).sum()),
               "core_refinance": int(((d.core == 1) & (d.purpose == "refinance")).sum()),
               "not_reported": float((d.loc[d.core == 1, "group"] == "Not reported").mean())}
        rows.append(row)
        if row["official"] is not None and row["official"] != row["records"]:
            raise SystemExit(f"{y}: {row['records']:,} records, but the publisher's count is {row['official']:,}")
        if row["valid_action"] < 0.999:
            raise SystemExit(f"{y}: only {row['valid_action']:.3%} of records have a valid action code")
    return rows


def tract_maps(d):
    """Purchase applications by 2020 tract and era: applications, denials, and the same for white and for Black
    applicants, with each year's tracts carried onto 2020 tracts by the crosswalk."""
    s = d[(d.purpose == "purchase") & d.tract.notna()].copy()
    s["is_w"] = (s.group == "White").astype(float)
    s["is_b"] = (s.group == "Black").astype(float)
    s["den_w"] = s.denied * s.is_w
    s["den_b"] = s.denied * s.is_b
    out, coverage = [], {}
    for year, sub in s.groupby("year"):
        c = sub.groupby("tract").agg(n=("denied", "size"), den=("denied", "sum"), n_w=("is_w", "sum"),
                                     den_w=("den_w", "sum"), n_b=("is_b", "sum"), den_b=("den_b", "sum")).reset_index()
        c20, share = geo.to_2020(c, sources.tract_vintage(year))
        coverage[int(year)] = share
        c20["era"] = sources.era(year)
        out.append(c20)
    m = pd.concat(out).groupby(["era", "tract20"], as_index=False).sum(numeric_only=True)
    eras = {}
    for era, g in m.groupby("era"):
        eras[era] = {r.tract20: [round(r.n, 1), round(r.den, 1), round(r.n_w, 1), round(r.den_w, 1), round(r.n_b, 1),
                                 round(r.den_b, 1)] for r in g.itertuples()}
    return {"columns": ["apps", "denied", "apps_white", "denied_white", "apps_black", "denied_black"], "eras": eras,
            "coverage": coverage}


def county_maps(d):
    s = d[d.purpose == "purchase"]
    out = {}
    for era, g in s.groupby("era"):
        t = g.groupby(["county", "group"]).denied.agg(["size", "sum"]).unstack("group").fillna(0)
        rows = {}
        for county in t.index:
            def get(grp):
                return [int(t.loc[county, ("size", grp)]) if ("size", grp) in t.columns else 0,
                        int(t.loc[county, ("sum", grp)]) if ("sum", grp) in t.columns else 0]
            n_all = int(t.loc[county].xs("size").sum())
            d_all = int(t.loc[county].xs("sum").sum())
            rows[county] = {"all": [n_all, d_all], **{grp: get(grp) for grp in ["White"] + analysis.COMPARE}}
        out[era] = rows
    return out


def stamp():
    """Content-hash each local script tag on the Virginia page, as build.py does for the Boston page."""
    import hashlib
    import re

    page = SITE / "index.html"
    html = page.read_text(encoding="utf-8")

    def repl(m):
        name = m.group(1)
        h = hashlib.sha256((SITE / name).resolve().read_bytes()).hexdigest()[:8]
        return f'src="{name}?v={h}"'
    new = re.sub(r'src="((?:\.\./)?[a-z]+\.js)(?:\?v=[0-9a-f]+)?"', repl, html)
    if new != html:
        page.write_text(new, encoding="utf-8")


def build(make_geo=False):
    warnings.simplefilter("ignore")
    t0 = time.time()
    rec = reconcile()
    print(f"reconciled {len(rec)} years", flush=True)
    d = analysis.load()
    print(f"core sample: {len(d):,} decided applications ({time.time() - t0:.0f}s)", flush=True)
    rates = analysis.rates(d)
    yearly = analysis.yearly_gaps(d)
    print(f"yearly gaps done ({time.time() - t0:.0f}s)", flush=True)
    eras = analysis.era_gaps(d)
    print(f"era gaps done ({time.time() - t0:.0f}s)", flush=True)
    robust = analysis.robustness(d)
    reasons = analysis.denial_reasons(d)
    exempt = (d[d.year >= 2018].assign(ex=lambda x: x.dti.isna()).groupby("year").ex.mean()).to_dict()
    out = {
        "meta": {"built": time.strftime("%Y-%m-%d"), "years": [r["year"] for r in rec], "eras": sources.ERAS,
                 "groups": harmonize.GROUP_ORDER, "compare": analysis.COMPARE, "specs": analysis.SPECS,
                 "schema": [dict(zip(["field", "meaning", "src_2004", "src_2007", "src_2018", "note"], s)) for s in harmonize.SCHEMA],
                 "breaks": BREAKS, "reasons": analysis.REASONS, "context_check": harmonize.check_context()},
        "reconcile": rec,
        "rates": rates.to_dict("records"),
        "yearly": yearly.to_dict("records"),
        "eras": eras.to_dict("records"),
        "robustness": robust,
        "reasons": reasons,
        "missing_underwriting": {int(k): float(v) for k, v in exempt.items()},
        "lenders": lenders.tables(d, lenders.names_for(d)),
        "counties": county_maps(d),
        "tracts": tract_maps(d),
    }
    write(tidy(out), make_geo)
    print(f"done in {time.time() - t0:.0f}s")
    return out


def write(out, make_geo=False):
    SITE.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    RESULTS.parent.mkdir(exist_ok=True)
    slim = {k: v for k, v in out.items() if k not in ("tracts", "counties")}
    RESULTS.write_text(json.dumps(slim, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (SITE / "data.js").write_text("// Generated by build_va.py. Do not edit by hand.\nwindow.VA = " + text + ";\n", encoding="utf-8")
    if make_geo or not (SITE / "geo.js").exists():
        g = geo.shapes()
        (SITE / "geo.js").write_text("// Generated by build_va.py --geo from Census cartographic boundary files (2023).\nwindow.VA_GEO = "
                                     + json.dumps(g, separators=(",", ":")) + ";\n", encoding="utf-8")
    stamp()
    print(f"wrote site/virginia/data.js ({len(text) // 1024} KB)")


def committed():
    text = (SITE / "data.js").read_text(encoding="utf-8")
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


def refresh_lenders():
    """Recompute only the lender section (about a minute) and keep everything else as committed."""
    warnings.simplefilter("ignore")
    out = committed()
    d = analysis.load()
    out["lenders"] = tidy(lenders.tables(d, lenders.names_for(d)))
    write(out)


if __name__ == "__main__":
    if "--lenders" in sys.argv:
        refresh_lenders()
    else:
        build(make_geo="--geo" in sys.argv)
