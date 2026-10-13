"""Lender names, and what the largest Virginia lenders' own applications show.

Names come from each era's institution files, keyed the same way the application records are:
- 2004-2006: the Federal Reserve's transmittal sheets via the National Archives (fixed width, 240 bytes; agency
  code at byte 5, respondent ID at 6-15, name at 16-45, parent name at 123-152);
- 2007-2017: the CFPB's historic transmittal sheets (CSV);
- 2018 onward: the HMDA Platform's filers API (LEI and name per year).

A lender's gap here compares its own Black (or Hispanic, or Asian) applicants with its own white applicants in the
same county and year, with the controls every year records. That is narrower than the statewide estimate and
noisier; it is not a finding that the lender discriminated.
"""

import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import models, sources
from .analysis import COMPARE, design

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "lenders"
NAMES_CSV = ROOT / "data" / "lender_names_va.csv"
TOP = 15
MIN_GROUP = 100  # applicants in a group before a lender's gap for that group is estimated

URLS = {
    2004: "https://catalog.archives.gov/medialz/electronic-records/rg-082/hmda/FTS04/f2004ts.public.dat",
    2005: "https://catalog.archives.gov/medialz/electronic-records/rg-082/hmda/FTS0506/TS.FINAL.2005.DAT",
    2006: "https://catalog.archives.gov/medialz/electronic-records/rg-082/hmda/FTS0506/TS.Public.2006.DAT",
    "historic": "https://files.consumerfinance.gov/hmda-historic-institution-data/hmda_{year}_transmittal_sheet.zip",
    "filers": "https://ffiec.cfpb.gov/v2/reporting/filers/{year}",
}
NARA_FILES = {2004: "f2004ts.public.dat", 2005: "TS.FINAL.2005.DAT", 2006: "TS.Public.2006.DAT"}

SPECIAL = {"SUNTRUST": "SunTrust", "JPMORGAN": "JPMorgan", "MCLEAN": "McLean", "INC": "Inc.", "INC.": "Inc.",
           "CO": "Co.", "CO.": "Co.", "CORP": "Corp.", "CORP.": "Corp.", "CORPORATION": "Corporation", "LLC": "LLC",
           "L.L.C.": "LLC", "NA": "N.A.", "N.A.": "N.A.", "FSB": "FSB", "F.S.B.": "FSB", "USAA": "USAA", "NFCU": "NFCU",
           "LOANDEPOT.COM": "loanDepot.com", "HOMEBRIDGE": "HomeBridge", "PRIMELENDING": "PrimeLending"}
SMALL = {"OF", "AND", "THE", "FOR", "AT", "IN", "BY", "ON"}


def tidy_name(s):
    """Display form of a lender name. All-caps names (most pre-2018 files) are title-cased, keeping short
    abbreviations (PHH, NVR, C&F) and known forms (N.A., LLC, JPMorgan); mixed-case names are left as reported."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if not s or s != s.upper():
        return s
    out = []
    for i, w in enumerate(s.split(" ")):
        core = w.rstrip(",")
        tail = w[len(core):]
        if core in SPECIAL:
            core = SPECIAL[core]
        elif "&" in core or (len(core) <= 3 and core.isalpha() and core not in SMALL):
            pass
        elif core in SMALL and i > 0:
            core = core.lower()
        else:
            core = "-".join(p.capitalize() for p in core.split("-"))
        out.append(core + tail)
    return " ".join(out)


def read_names():
    rows = []
    for y, f in NARA_FILES.items():
        for line in (RAW / f).read_bytes().splitlines():
            t = line.decode("latin-1")
            if len(t) < 152:
                continue
            rows.append((y, f"{t[4]}-{t[5:15].strip().zfill(10)}", t[15:45].strip(), t[122:152].strip()))
    for y in range(2007, 2018):
        rows += read_historic_ts(y)
    for y in range(2018, sources.LAST_YEAR + 1):
        p = RAW / f"filers_{y}.json"
        if p.exists():
            for inst in json.loads(p.read_text(encoding="utf-8"))["institutions"]:
                rows.append((y, inst["lei"], inst["name"], ""))
    n = pd.DataFrame(rows, columns=["year", "lender_id", "name", "parent"])
    n["name"] = n.name.map(tidy_name)
    n["parent"] = n.parent.map(tidy_name)
    return n.drop_duplicates(["year", "lender_id"])


SUFFIX = re.compile(r"^\s*(inc\.?|llc|l\.l\.c\.|n\.?a\.?|fsb|lp|ltd\.?|co\.?|corp\.?|ssb|a federal savings bank|national association)\s*$", re.I)


def read_historic_ts(y):
    """The 2007-2017 transmittal sheets have some unquoted commas inside names, so parse line by line: the first
    four fields (year, respondent ID, agency, tax ID) are always clean; a name split by a comma is rejoined when
    the piece after the comma is a corporate suffix."""
    import csv

    z = zipfile.ZipFile(RAW / f"ts_{y}.zip")
    text = io.TextIOWrapper(z.open(z.namelist()[0]), encoding="latin-1")
    reader = csv.reader(text)
    header = [h.strip().lower() for h in next(reader)]
    width = len(header)
    pi = header.index("parent name")
    out = []
    for parts in reader:
        if len(parts) < 5:
            continue
        extra = len(parts) - width
        name = parts[4]
        k = 5
        while extra > 0 and k < len(parts) and SUFFIX.match(parts[k]):
            name += "," + parts[k]
            k += 1
            extra -= 1
        parent = parts[pi + (len(parts) - width)] if len(parts) - width == k - 5 and pi + (k - 5) < len(parts) else ""
        out.append((y, f"{parts[2].strip()}-{parts[1].strip().zfill(10)}", name.strip(), parent.strip()))
    return out


def names_for(d):
    """Names for the lenders that appear in the Virginia data (committed as a small CSV)."""
    n = read_names()
    used = d[["year", "lender_id"]].drop_duplicates()
    out = used.merge(n, on=["year", "lender_id"], how="left")
    NAMES_CSV.write_text(out.sort_values(["year", "lender_id"]).to_csv(index=False), encoding="utf-8")
    return out


def lender_gap(sub, spec):
    """One lender's gaps: its own applicants, county-by-year fixed effects, SEs clustered by county."""
    X, fes = design(sub, spec)
    fes = fes[:1]  # county x year only; the lender is fixed by construction
    r = models.fit(sub.denied.to_numpy(), X.to_numpy(), list(X.columns), fes=fes, clusters=sub.county.to_numpy())
    return {g: {"est": r["coef"].get(g), "se": r["se"].get(g)} for g in COMPARE}, r["n"]


def tables(d, names):
    """Per era: the TOP largest lenders for home purchase, with rates by group and within-lender gaps; plus how
    unevenly groups are spread across lenders."""
    s = d[d.purpose == "purchase"]
    out = {}
    for era, e in s.groupby("era"):
        counts = e.groupby("lender_id").size().sort_values(ascending=False)
        total = int(len(e))
        nm = names[names.year.between(*sources.ERAS[era])].sort_values("year").groupby("lender_id").last()
        rows = []
        for lid, n in counts.head(TOP).items():
            sub = e[e.lender_id == lid]
            by = sub.groupby("group").denied.agg(["size", "mean"])
            row = {"lender_id": lid, "name": nm.name.get(lid) or lid, "parent": nm.parent.get(lid) or "",
                   "apps": int(n), "share": n / total, "denial": float(sub.denied.mean()),
                   "groups": {g: {"n": int(by.loc[g, "size"]) if g in by.index else 0,
                                  "rate": float(by.loc[g, "mean"]) if g in by.index else None}
                              for g in ["White"] + COMPARE}}
            enough = [g for g in COMPARE if row["groups"][g]["n"] >= MIN_GROUP] and row["groups"]["White"]["n"] >= MIN_GROUP
            if enough:
                gaps, nfit = lender_gap(sub, "common")
                row["gap_common"] = {g: (gaps[g] if row["groups"][g]["n"] >= MIN_GROUP else None) for g in COMPARE}
                if era == "2018-2025":
                    gf, _ = lender_gap(sub, "full")
                    row["gap_full"] = {g: (gf[g] if row["groups"][g]["n"] >= MIN_GROUP else None) for g in COMPARE}
            rows.append(row)
        # sorting across lenders: the average overall denial rate of the lender each group's applicants used
        lender_rate = e.groupby("lender_id").denied.mean()
        e = e.assign(lender_rate=e.lender_id.map(lender_rate))
        sorting = {g: float(e.loc[e.group == g, "lender_rate"].mean()) for g in ["White"] + COMPARE}
        top_share = float(counts.head(TOP).sum() / total)
        out[era] = {"apps": total, "lenders": int(len(counts)), "top_share": top_share, "rows": rows,
                    "sorting": sorting, "min_group": MIN_GROUP}
    return out
