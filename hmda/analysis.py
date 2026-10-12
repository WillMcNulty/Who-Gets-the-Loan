"""The Virginia analysis: denial rates and adjusted denial gaps by year and by era, on the harmonized files.

Comparison groups are Black, Hispanic and Asian applicants, each against non-Hispanic white applicants. Every model
is a linear probability model of denial (1 = denied) on group indicators, estimated separately for home purchase
and refinance applications in the core sample, with these nested sets of controls:

  raw      no controls
  common   controls every era records: loan type, log income, log loan amount, loan-to-income, a co-applicant,
           applicant sex, tract minority share and tract income ratio (in bands), and county fixed effects
  lender   common + lender fixed effects (compares applicants at the same lender)
  full     lender + the 2018 rule's underwriting fields: debt-to-income band, combined loan-to-value band, log
           property value, credit-score model and the automated underwriting system used (2018 onward only)

Standard errors are clustered by lender.
"""

import numpy as np
import pandas as pd

from . import models, sources
from .harmonize import OUT

COMPARE = ["Black", "Hispanic", "Asian"]
SPECS = ["raw", "common", "lender", "full"]
PURPOSES = ["purchase", "refinance"]
COLS = ["year", "era", "lender_id", "denied", "core", "purpose", "cashout", "loan_type", "loan_k", "income_k",
        "county", "tract", "group", "sex", "co_applicant", "tract_minority_pct", "tract_income_pct", "reason1",
        "reason2", "reason3", "reason4", "reason_any", "dti", "cltv", "property_k", "score_type", "aus"]

REASONS = {1: "Debt-to-income ratio", 2: "Employment history", 3: "Credit history", 4: "Collateral",
           5: "Insufficient cash", 6: "Unverifiable information", 7: "Application incomplete",
           8: "Mortgage insurance denied", 9: "Other"}


def load(years=None):
    years = years or [y for y in range(sources.FIRST_YEAR, sources.LAST_YEAR + 1) if (OUT / f"va_{y}.parquet").exists()]
    frames = [pd.read_parquet(OUT / f"va_{y}.parquet", columns=COLS) for y in years]
    d = pd.concat(frames, ignore_index=True)
    return d[d.core == 1].reset_index(drop=True)


def bands(x, edges, labels):
    return pd.cut(x, edges, labels=labels, right=False).astype(str).replace("nan", "missing")


def design(d, spec):
    """Regressors (as a DataFrame of 0/1 and numeric columns) and the fixed effects for one spec."""
    X = pd.DataFrame(index=d.index)
    for g in COMPARE + ["other_group"]:
        X[g] = (d.group == g).astype(float) if g != "other_group" else (~d.group.isin(COMPARE + ["White"])).astype(float)
    fes = []
    if spec == "raw":
        return X, fes
    inc = d.income_k.where(d.income_k > 0)
    X["log_income"] = np.log(inc).fillna(0)
    X["income_missing"] = inc.isna().astype(float)
    X["log_loan"] = np.log(d.loan_k.clip(lower=1))
    X["loan_to_income"] = (d.loan_k / inc).clip(upper=20).fillna(0)
    X["co_applicant"] = d.co_applicant.astype(float)
    for v in ("female", "not_reported", "both"):
        X[f"sex_{v}"] = (d.sex == v).astype(float)
    for t in (2, 3, 4):
        X[f"loan_type_{t}"] = (d.loan_type == t).astype(float)
    mb = bands(d.tract_minority_pct, [0, 10, 20, 30, 50, 80, 101], ["0-10", "10-20", "20-30", "30-50", "50-80", "80+"])
    ib = bands(d.tract_income_pct, [0, 50, 80, 100, 120, 150, 1e9], ["<50", "50-80", "80-100", "100-120", "120-150", "150+"])
    X = X.join(pd.get_dummies(mb, prefix="tract_minority", drop_first=True, dtype=float))
    X = X.join(pd.get_dummies(ib, prefix="tract_income", drop_first=True, dtype=float))
    fes = [d.county.to_numpy() + "_" + d.year.astype(str).to_numpy()]
    if spec in ("lender", "full"):
        fes.append(d.lender_id.to_numpy() + "_" + d.year.astype(str).to_numpy())
    if spec == "full":
        X = X.join(pd.get_dummies(d.dti.fillna("missing"), prefix="dti", dtype=float).drop(columns="dti_30-36", errors="ignore"))
        cb = bands(d.cltv, [0, 60, 80, 90, 95, 97, 100.01, 1e9], ["<60", "60-80", "80-90", "90-95", "95-97", "97-100", ">100"])
        X = X.join(pd.get_dummies(cb, prefix="cltv", dtype=float).drop(columns="cltv_60-80", errors="ignore"))
        X["log_property"] = np.log(d.property_k.where(d.property_k > 0)).fillna(0)
        X["property_missing"] = d.property_k.isna().astype(float)
        st = d.score_type.astype("Int64").astype(str).replace("<NA>", "missing")
        X = X.join(pd.get_dummies(st, prefix="score", dtype=float).drop(columns="score_1", errors="ignore"))
        au = d.aus.astype("Int64").astype(str).replace("<NA>", "missing")
        X = X.join(pd.get_dummies(au, prefix="aus", dtype=float).drop(columns="aus_1", errors="ignore"))
        if "cashout" in d:
            X["cashout"] = d.cashout.fillna(0).astype(float)
    return X, fes


def gap_model(d, spec):
    X, fes = design(d, spec)
    r = models.fit(d.denied.to_numpy(), X.to_numpy(), list(X.columns), fes=fes, clusters=d.lender_id.to_numpy())
    out = {"n": r["n"], "clusters": r["clusters"], "mean": r["mean_y"]}
    for g in COMPARE:
        out[g] = {"est": r["coef"].get(g), "se": r["se"].get(g)}
    return out


def rates(d):
    """Applications, denials and denial rates by year, purpose and group."""
    g = d.groupby(["year", "purpose", "group"]).denied.agg(n="size", denied="sum").reset_index()
    g["rate"] = g.denied / g.n
    return g


def yearly_gaps(d):
    rows = []
    for (year, purpose), sub in d.groupby(["year", "purpose"]):
        for spec in SPECS:
            if spec == "full" and year < 2018:
                continue
            m = gap_model(sub, spec)
            for g in COMPARE:
                rows.append({"year": int(year), "purpose": purpose, "spec": spec, "group": g, "est": m[g]["est"],
                             "se": m[g]["se"], "n": m["n"], "clusters": m["clusters"], "mean": m["mean"]})
    return pd.DataFrame(rows)


def era_gaps(d):
    rows = []
    for (era, purpose), sub in d.groupby(["era", "purpose"]):
        for spec in SPECS:
            if spec == "full" and era != "2018-2025":
                continue
            m = gap_model(sub, spec)
            for g in COMPARE:
                rows.append({"era": era, "purpose": purpose, "spec": spec, "group": g, "est": m[g]["est"],
                             "se": m[g]["se"], "n": m["n"], "clusters": m["clusters"], "mean": m["mean"]})
    return pd.DataFrame(rows)


def robustness(d):
    """Pooled 2018-2025 purchase gaps under alternative choices, all with the lender spec unless named."""
    sub = d[(d.era == "2018-2025") & (d.purpose == "purchase")]
    variants = [
        ("Main (lender spec)", sub, "lender"),
        ("Full underwriting controls", sub, "full"),
        ("Single applicants only", sub[sub.co_applicant == 0], "lender"),
        ("Conventional loans only", sub[sub.loan_type == 1], "lender"),
        ("FHA/VA/RHS loans only", sub[sub.loan_type != 1], "lender"),
        ("Only applications with a DTI value", sub[sub.dti.notna()], "full"),
    ]
    rows = []
    for label, s, spec in variants:
        m = gap_model(s, spec)
        rows.append({"label": label, "spec": spec, "n": m["n"], **{g: m[g] for g in COMPARE}})
    return rows


def denial_reasons(d):
    """Share of denials citing each reason, by era and group, among denials that report any reason."""
    den = d[(d.denied == 1)]
    rows = []
    for (era, group), s in den.groupby(["era", "group"]):
        if group not in ["White"] + COMPARE:
            continue
        with_r = s[s.reason_any == 1]
        row = {"era": era, "group": group, "denials": int(len(s)), "with_reason": int(len(with_r))}
        R = with_r[["reason1", "reason2", "reason3", "reason4"]]
        for code, name in REASONS.items():
            row[name] = float((R == code).any(axis=1).mean()) if len(with_r) else None
        rows.append(row)
    return rows


def county_panel(d):
    """County x era x group counts for the map (purchase applications)."""
    s = d[d.purpose == "purchase"]
    g = s.groupby(["era", "county", "group"]).denied.agg(n="size", denied="sum").reset_index()
    return g
