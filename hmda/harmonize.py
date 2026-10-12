"""Turn three eras of raw HMDA records into one schema, one Parquet file per year in data/harmonized/.

    python -m hmda.harmonize            # every year with a raw file
    python -m hmda.harmonize 2005 2019  # some years

Every year passes through the same `finish()` step, so the derived fields (applicant group, the core sample flag,
county harmonization, denial reasons) are computed by one piece of code no matter where the record came from. What
each field means in each era, and where the eras differ, is documented in SCHEMA below and published on the page.
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import sources

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "harmonized"

# One row per harmonized field: (name, meaning, 2004-2006 source, 2007-2017 source, 2018+ source, comparability note)
SCHEMA = [
    ("year", "Activity year", "Asof Date", "as_of_year", "activity_year", ""),
    ("lender_id", "Reporting institution", "agency + respondent ID", "agency + respondent ID", "LEI",
     "IDs change form in 2018; lender fixed effects are estimated within a year, so this doesn't matter for them"),
    ("action", "Action taken (1 originated ... 8 preapproval approved)", "action", "action_taken", "action_taken", "Same codes in every era"),
    ("denied", "1 if the application was denied (action 3), 0 if originated or approved (1, 2)", "", "", "", "Defined only for decided applications"),
    ("purpose", "purchase / refinance / improvement / other", "1, 3, 2", "1, 3, 2", "1; 31 and 32; 2; 4 and 5",
     "Cash-out refinances are reported separately from 2018 (cashout = 1); before 2018 they are inside refinance"),
    ("loan_type", "1 conventional, 2 FHA, 3 VA, 4 FSA/RHS", "type", "loan_type", "loan_type", "Same codes"),
    ("lien", "1 first, 2 subordinate, 3 unsecured, 4 n/a", "lien", "lien_status", "lien_status", "Unsecured loans stop being reported in 2018"),
    ("occupancy", "owner / second / investor / not_owner", "1, 2 (not owner), 3", "same", "1, 2, 3",
     "Second homes are split out from 2018; before that they are in not_owner"),
    ("dwelling", "site_1_4 / manufactured / multifamily", "property type 1, 2, 3", "same", "construction method + total units", ""),
    ("closed_end", "1 unless the record is an open-end line, reverse mortgage or business-purpose loan",
     "assumed 1", "assumed 1", "open-end, reverse, business flags",
     "Before 2018 home-equity lines were optional to report and can't be identified; the core sample is first liens, which keeps most of them out"),
    ("loan_k", "Loan amount, $ thousands", "amount", "loan_amount_000s", "loan_amount / 1000",
     "From 2018 amounts are the midpoint of a $10,000 band"),
    ("income_k", "Applicant income, $ thousands", "income", "applicant_income_000s", "income", "Missing when not relied on"),
    ("group", "Applicant group: Hispanic (any race), White, Black, Asian, AIAN, NHPI, Multiracial, Not reported",
     "ethnicity + race 1-5", "same", "ethnicity-1..5 + race-1..5 (subgroups folded in)", "Same rule every year; applicant's own fields"),
    ("sex", "male / female / both / not_reported", "sex", "applicant_sex", "applicant_sex", "'both' exists from 2018"),
    ("co_applicant", "1 if there is a co-applicant", "co-applicant ethnicity/race/sex", "same", "same", ""),
    ("county", "County FIPS, harmonized (Bedford city 51515 folded into Bedford County 51019)", "state + county", "same",
     "county_code", "Bedford city became part of Bedford County in 2013"),
    ("tract", "11-digit census tract", "state + county + tract", "same", "census_tract",
     "Boundaries: 2000 census for 2004-2011, 2010 for 2012-2021, 2020 from 2022 (tract_vintage)"),
    ("tract_minority_pct", "Tract minority population, %", "from the 2007-2011 FFIEC values for the same 2000 tract",
     "minority_population", "tract_minority_population_percent", "FFIEC census values, updated with each census or ACS release"),
    ("tract_income_pct", "Tract median family income as % of its MSA's", "as above", "tract_to_msamd_income",
     "tract_to_msa_income_percentage", "As above"),
    ("rate_spread", "APR minus the benchmark, for loans reported as higher-priced (all loans from 2018)", "rate spread",
     "rate_spread", "rate_spread", "Benchmark and threshold change in October 2009 and again in 2018; not comparable across those breaks"),
    ("reason1..4", "Denial reasons (1 DTI ... 9 other)", "reasons 1-3", "denial_reason_1..3", "denial_reason-1..4",
     "Optional for most lenders before 2018, required from 2018"),
    ("dti, cltv, property_k, score_type, aus, age", "Underwriting fields", "-", "-", "as reported", "Only from 2018"),
]

GROUP_ORDER = ["White", "Black", "Hispanic", "Asian", "AIAN", "NHPI", "Multiracial", "Not reported"]
RACE_MAJOR = {1: "AIAN", 2: "Asian", 3: "Black", 4: "NHPI", 5: "White"}


# ------------------------------------------------------------------------------------------------- raw readers

NARA_COLS = [  # (name, start, end) 1-based inclusive, from the 2004-forward public LAR layout
    ("year", 1, 4), ("respondent", 5, 14), ("agency", 15, 15), ("loan_type", 16, 16), ("purpose", 17, 17),
    ("occupancy", 18, 18), ("loan_k", 19, 23), ("action", 24, 24), ("msa", 25, 29), ("state", 30, 31),
    ("county", 32, 34), ("tract", 35, 41), ("sex", 42, 42), ("co_sex", 43, 43), ("income_k", 44, 47),
    ("purchaser", 48, 48), ("reason1", 49, 49), ("reason2", 50, 50), ("reason3", 51, 51), ("edit", 52, 52),
    ("property", 53, 53), ("preapproval", 54, 54), ("eth", 55, 55), ("co_eth", 56, 56), ("race1", 57, 57),
    ("race2", 58, 58), ("race3", 59, 59), ("race4", 60, 60), ("race5", 61, 61), ("co_race1", 62, 62),
    ("co_race2", 63, 63), ("co_race3", 64, 64), ("co_race4", 65, 65), ("co_race5", 66, 66), ("rate_spread", 67, 71),
    ("hoepa", 72, 72), ("lien", 73, 73), ("seq", 74, 80),
]


def va_lines_nara(year):
    """Virginia's records from the national fixed-width file, cached as their own small file."""
    cache = RAW / f"va_nara_{year}.dat"
    if cache.exists():
        return cache.read_bytes().splitlines()
    zpath = RAW / sources.source(year)[1]
    keep = []
    with zipfile.ZipFile(zpath) as z:
        name = max(z.infolist(), key=lambda i: i.file_size).filename
        with z.open(name) as f:
            for line in f:
                if line[29:31] == b"51":
                    keep.append(line.rstrip(b"\r\n"))
    cache.write_bytes(b"\n".join(keep) + b"\n")
    return keep


def read_nara(year):
    lines = va_lines_nara(year)
    cols = {n: [l[a - 1:b].decode("latin-1").strip() for l in lines] for n, a, b in NARA_COLS}
    return pd.DataFrame(cols)


def va_rows_cfpb(year):
    """Virginia's rows from the nationwide CFPB historic CSV, cached."""
    cache = RAW / f"va_cfpb_{year}.csv"
    if not cache.exists():
        zpath = RAW / sources.source(year)[1]
        with zipfile.ZipFile(zpath) as z:
            name = max(z.infolist(), key=lambda i: i.file_size).filename
            with z.open(name) as f, open(cache, "wb") as out:
                header = f.readline()
                out.write(header)
                cols = header.decode().strip().split(",")
                si = cols.index("state_code")
                for line in f:
                    parts = line.split(b",", si + 1)
                    if parts[si].strip(b'"') == b"51":
                        out.write(line)
    return pd.read_csv(cache, dtype=str, keep_default_na=False)


def read_cfpb(year):
    d = va_rows_cfpb(year)
    ren = {"as_of_year": "year", "respondent_id": "respondent", "agency_code": "agency", "loan_type": "loan_type",
           "property_type": "property", "loan_purpose": "purpose", "owner_occupancy": "occupancy",
           "loan_amount_000s": "loan_k", "preapproval": "preapproval", "action_taken": "action", "msamd": "msa",
           "state_code": "state", "county_code": "county", "census_tract_number": "tract",
           "applicant_ethnicity": "eth", "co_applicant_ethnicity": "co_eth", "applicant_sex": "sex",
           "co_applicant_sex": "co_sex", "applicant_income_000s": "income_k", "purchaser_type": "purchaser",
           "denial_reason_1": "reason1", "denial_reason_2": "reason2", "denial_reason_3": "reason3",
           "rate_spread": "rate_spread", "hoepa_status": "hoepa", "lien_status": "lien", "edit_status": "edit",
           "sequence_number": "seq", "population": "tract_pop", "minority_population": "tract_minority_pct",
           "hud_median_family_income": "ffiec_mfi", "tract_to_msamd_income": "tract_income_pct",
           "number_of_owner_occupied_units": "tract_owner_units", "number_of_1_to_4_family_units": "tract_1_4_units"}
    for k in range(1, 6):
        ren[f"applicant_race_{k}"] = f"race{k}"
        ren[f"co_applicant_race_{k}"] = f"co_race{k}"
    missing = [c for c in ren if c not in d.columns]
    if missing:
        raise ValueError(f"{year}: CFPB file lacks {missing}")
    return d.rename(columns=ren)[list(ren.values())]


def read_browser(year):
    d = pd.read_csv(RAW / sources.source(year)[1], dtype=str, keep_default_na=False)
    return d


# ------------------------------------------------------------------------------------------------- per-era mapping

def num(s):
    return pd.to_numeric(pd.Series(s).replace({"": None, "NA": None, "Exempt": None, "1111": None}), errors="coerce")


def legacy(d, year, source):
    """2004-2017: the pre-2018 code sheet (the same for the NARA and CFPB files)."""
    out = pd.DataFrame({"year": year, "source": source}, index=d.index)
    out["lender_id"] = d.agency.str.strip() + "-" + d.respondent.str.strip()
    out["action"] = num(d.action).astype("Int8")
    out["purpose"] = d.purpose.map({"1": "purchase", "2": "improvement", "3": "refinance"}).fillna("other")
    out["cashout"] = pd.array([pd.NA] * len(d), dtype="Int8")
    out["loan_type"] = num(d.loan_type).astype("Int8")
    out["lien"] = num(d.lien).astype("Int8")
    out["occupancy"] = d.occupancy.map({"1": "owner", "2": "not_owner", "3": "na"}).fillna("na")
    out["dwelling"] = d["property"].map({"1": "site_1_4", "2": "manufactured", "3": "multifamily"}).fillna("na")
    out["closed_end"] = 1
    out["preapproval"] = num(d.preapproval).astype("Int8")
    out["loan_k"] = num(d.loan_k)
    out["income_k"] = num(d.income_k)
    out["county_raw"] = "51" + d.county.str.strip().str.zfill(3)
    t = d.tract.str.strip().str.replace(".", "", regex=False)
    ok = t.str.fullmatch(r"\d{1,6}") & (d.county.str.strip() != "") & ~d.county.str.strip().isin(["NA"])
    out["tract"] = np.where(ok, out.county_raw + t.str.zfill(6), None)
    out["msa"] = d.msa.str.strip()
    out["eth"] = num(d.eth)
    out["co_eth"] = num(d.co_eth)
    for k in range(1, 6):
        out[f"race{k}"] = num(d[f"race{k}"])
    out["co_race1"] = num(d.co_race1)
    out["sex_code"] = num(d.sex)
    out["co_sex_code"] = num(d.co_sex)
    out["rate_spread"] = num(d.rate_spread)
    out["hoepa"] = num(d.hoepa).astype("Int8")
    out["purchaser"] = num(d.purchaser).astype("Int8")
    for k in (1, 2, 3):
        out[f"reason{k}"] = num(d[f"reason{k}"]).astype("Int8")
    out["reason4"] = pd.array([pd.NA] * len(d), dtype="Int8")
    for c in ("tract_pop", "tract_minority_pct", "ffiec_mfi", "tract_income_pct", "tract_owner_units"):
        out[c] = num(d[c]) if c in d.columns else np.nan
    return out


def modern(d, year):
    """2018 onward: the 2015 rule's fields."""
    out = pd.DataFrame({"year": year, "source": "CFPB Data Browser"}, index=d.index)
    out["lender_id"] = d.lei
    out["action"] = num(d.action_taken).astype("Int8")
    p = d.loan_purpose
    out["purpose"] = p.map({"1": "purchase", "2": "improvement", "31": "refinance", "32": "refinance"}).fillna("other")
    out["cashout"] = pd.array(np.where(p == "32", 1, np.where(p == "31", 0, -1)), dtype="Int8")
    out.loc[out.cashout == -1, "cashout"] = pd.NA
    out["loan_type"] = num(d.loan_type).astype("Int8")
    out["lien"] = num(d.lien_status).astype("Int8")
    out["occupancy"] = d.occupancy_type.map({"1": "owner", "2": "second", "3": "investor"}).fillna("na")
    units = d.total_units
    small = units.isin(["1", "2", "3", "4"])
    out["dwelling"] = np.where(d.construction_method == "2", "manufactured", np.where(small, "site_1_4", "multifamily"))
    out["closed_end"] = ((d["open-end_line_of_credit"] != "1") & (d.reverse_mortgage != "1")
                         & (d.business_or_commercial_purpose != "1")).astype(int)
    out["preapproval"] = num(d.preapproval).astype("Int8")
    out["loan_k"] = num(d.loan_amount) / 1000
    out["income_k"] = num(d.income)
    out["county_raw"] = d.county_code.where(d.county_code.str.fullmatch(r"\d{5}"), None)
    out["tract"] = d.census_tract.where(d.census_tract.str.fullmatch(r"\d{11}"), None)
    out["msa"] = d["derived_msa-md"]
    out["eth"] = num(d["applicant_ethnicity-1"])
    out["co_eth"] = num(d["co-applicant_ethnicity-1"])
    # 2018 adds Hispanic and Asian/Pacific Islander subgroups (11-14, 21-27, 41-44): fold them into their majors
    for k in range(1, 6):
        r = num(d[f"applicant_race-{k}"])
        out[f"race{k}"] = r.where(r < 10, r // 10)
    co = num(d["co-applicant_race-1"])
    out["co_race1"] = co.where(co < 10, co // 10)
    out["eth"] = out.eth.where(out.eth < 10, 1)  # 11-14 are Hispanic subgroups
    co_e = out.co_eth
    out["co_eth"] = co_e.where(co_e < 10, 1)
    out["sex_code"] = num(d.applicant_sex)
    out["co_sex_code"] = num(d["co-applicant_sex"])
    out["rate_spread"] = num(d.rate_spread)
    out["hoepa"] = num(d.hoepa_status).astype("Int8")
    out["purchaser"] = num(d.purchaser_type).astype("Int8")
    for k in (1, 2, 3, 4):
        r = num(d[f"denial_reason-{k}"])
        out[f"reason{k}"] = r.where(r.between(1, 9)).astype("Int8")
    out["tract_pop"] = num(d.tract_population)
    out["tract_minority_pct"] = num(d.tract_minority_population_percent)
    out["ffiec_mfi"] = num(d.ffiec_msa_md_median_family_income)
    out["tract_income_pct"] = num(d.tract_to_msa_income_percentage)
    out["tract_owner_units"] = num(d.tract_owner_occupied_units)
    # underwriting fields that exist only from 2018
    out["dti"] = d.debt_to_income_ratio.map(dti_band)
    out["cltv"] = num(d.loan_to_value_ratio)
    out["property_k"] = num(d.property_value) / 1000
    out["score_type"] = num(d.applicant_credit_score_type).astype("Int16")
    out["aus"] = num(d["aus-1"]).astype("Int16")
    out["age"] = d.applicant_age.where(~d.applicant_age.isin(["8888", "9999", ""]), None)
    out["interest_rate"] = num(d.interest_rate)
    return out


def dti_band(v):
    """Debt-to-income: 2018+ reports bands below 36 and above 49 and exact values between; harmonize to bands."""
    if v in ("", "NA", "Exempt", "1111"):
        return None
    if v in ("<20%", "20%-<30%", "30%-<36%", "50%-60%", ">60%"):
        return {"<20%": "<20", "20%-<30%": "20-30", "30%-<36%": "30-36", "50%-60%": "50-60", ">60%": ">60"}[v]
    try:
        x = float(v)
    except ValueError:
        return None
    return "36-40" if x < 40 else "40-45" if x < 45 else "45-50" if x < 50 else "50-60"


# ------------------------------------------------------------------------------------------------- shared derivation

def applicant_group(eth, races):
    """One rule for every year. Hispanic ethnicity first (any race); otherwise the set of major races reported:
    one race gives that group, two or more give Multiracial, none gives Not reported."""
    hisp = eth == 1
    R = np.column_stack([np.where(np.isin(r, [1, 2, 3, 4, 5]), r, 0) for r in races])
    present = {k: (R == k).any(axis=1) for k in (1, 2, 3, 4, 5)}
    n = sum(present.values())
    out = np.full(len(eth), "Not reported", dtype=object)
    for k, name in RACE_MAJOR.items():
        out[present[k] & (n == 1)] = name
    out[n >= 2] = "Multiracial"
    out[hisp] = "Hispanic"
    return out


def finish(out, year):
    out = out.reset_index(drop=True)
    out["year"] = out.year.astype(int)
    out["era"] = sources.era(year)
    out["tract_vintage"] = sources.tract_vintage(year)
    out["county"] = out.county_raw.replace({"51515": "51019"})
    out["group"] = applicant_group(out.eth.to_numpy(), [out[f"race{k}"].to_numpy() for k in range(1, 6)])
    sx = out.sex_code
    out["sex"] = np.select([sx == 1, sx == 2, sx == 6], ["male", "female", "both"], "not_reported")
    out["co_applicant"] = (~out.co_race1.isin([7, 8]) & ~out.co_eth.isin([4, 5]) & out.co_race1.notna()).astype(int)
    out["decided"] = out.action.isin([1, 2, 3]).astype(int)
    out["denied"] = np.where(out.decided == 1, (out.action == 3).astype(float), np.nan)
    out["reason_any"] = out[["reason1", "reason2", "reason3", "reason4"]].notna().any(axis=1).astype(int)
    out["core"] = ((out.decided == 1) & (out.lien == 1) & (out.occupancy == "owner") & (out.dwelling == "site_1_4")
                   & (out.closed_end == 1) & out.purpose.isin(["purchase", "refinance"])
                   & out.loan_type.isin([1, 2, 3, 4]) & out.county.notna()).astype(int)
    for c in ("dti", "cltv", "property_k", "score_type", "aus", "age", "interest_rate"):
        if c not in out.columns:
            out[c] = None if c in ("dti", "age") else np.nan
    keep = ["year", "era", "source", "lender_id", "action", "decided", "denied", "core", "purpose", "cashout",
            "loan_type", "lien", "occupancy", "dwelling", "closed_end", "preapproval", "loan_k", "income_k",
            "county", "county_raw", "tract", "tract_vintage", "msa", "group", "sex", "co_applicant", "eth",
            "race1", "race2", "race3", "race4", "race5", "rate_spread", "hoepa", "purchaser",
            "reason1", "reason2", "reason3", "reason4", "reason_any", "tract_pop", "tract_minority_pct",
            "ffiec_mfi", "tract_income_pct", "tract_owner_units",
            "dti", "cltv", "property_k", "score_type", "aus", "age", "interest_rate"]
    return out[keep]


# ------------------------------------------------------------------------------------------------- tract context

def tract_context_2000():
    """FFIEC tract values (population, minority %, income ratio) for 2000-census tracts, from the 2007-2011 CFPB
    records, which carry them. They are census figures, fixed within the vintage; `check_context` confirms that."""
    frames = []
    for y in range(2007, 2012):
        p = OUT / f"va_{y}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p, columns=["year", "tract", "tract_pop", "tract_minority_pct", "tract_income_pct"]))
    if not frames:
        return None
    d = pd.concat(frames).dropna(subset=["tract"])
    return d.groupby("tract")[["tract_pop", "tract_minority_pct", "tract_income_pct"]].median()


def check_context():
    """Share of 2000-vintage tracts whose FFIEC values differ across 2007-2011 (should be ~0)."""
    frames = [pd.read_parquet(OUT / f"va_{y}.parquet", columns=["tract", "tract_minority_pct", "tract_income_pct"])
              for y in range(2007, 2012) if (OUT / f"va_{y}.parquet").exists()]
    d = pd.concat(frames).dropna().drop_duplicates()
    per = d.groupby("tract").agg(n_min=("tract_minority_pct", "nunique"), n_inc=("tract_income_pct", "nunique"))
    return float(((per.n_min > 1) | (per.n_inc > 1)).mean())


# ------------------------------------------------------------------------------------------------- driver

def harmonize(year):
    if year in sources.NARA_FINAL:
        out = legacy(read_nara(year), year, "Federal Reserve via NARA")
        ctx = tract_context_2000()
        if ctx is None:
            raise SystemExit("harmonize 2007-2011 before 2004-2006: their tract context comes from those years")
        out = out.drop(columns=["tract_pop", "tract_minority_pct", "tract_income_pct"]).join(ctx, on="tract")
    elif year <= 2017:
        out = legacy(read_cfpb(year), year, "CFPB historic")
    else:
        out = modern(read_browser(year), year)
    out = finish(out, year)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT / f"va_{year}.parquet", index=False)
    return out


def available_years():
    return [y for y in range(sources.FIRST_YEAR, sources.LAST_YEAR + 1) if (RAW / sources.source(y)[1]).exists()]


if __name__ == "__main__":
    ys = [int(a) for a in sys.argv[1:]] or available_years()
    # 2007-2011 first: 2004-2006 borrow their tract context
    ys = sorted(ys, key=lambda y: (y in sources.NARA_FINAL, y))
    for y in ys:
        o = harmonize(y)
        print(f"{y}: {len(o):>9,} records, core sample {int(o.core.sum()):>8,}, denial rate (core) "
              f"{o.loc[o.core == 1, 'denied'].mean():.3f}", flush=True)
