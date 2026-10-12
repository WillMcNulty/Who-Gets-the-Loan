"""Tests for version 2 (Virginia HMDA). They run without the raw downloads: the readers and derivations are
checked on small hand-made records, the estimator against statsmodels, the crosswalk on the committed Census
relationship files, and the committed results against the facts the page states."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf

from hmda import geo, harmonize as h, models, sources

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------------------------------------- groups & bands

def test_applicant_group_rule():
    eth = np.array([1, 2, 2, 2, 3, 2, 1, 4])
    races = [np.array(r) for r in zip(
        [5, 0, 0, 0, 0],      # Hispanic white -> Hispanic
        [3, 0, 0, 0, 0],      # Black
        [2, 5, 0, 0, 0],      # Asian + white -> Multiracial
        [6, 0, 0, 0, 0],      # not provided -> Not reported
        [5, 0, 0, 0, 0],      # ethnicity not provided but race white -> White
        [4, 4, 0, 0, 0],      # same race twice -> NHPI
        [6, 0, 0, 0, 0],      # Hispanic, race not provided -> Hispanic
        [7, 0, 0, 0, 0],      # not applicable -> Not reported
    )]
    got = h.applicant_group(eth, races)
    assert list(got) == ["Hispanic", "Black", "Multiracial", "Not reported", "White", "NHPI", "Hispanic", "Not reported"]


@pytest.mark.parametrize("raw,band", [("<20%", "<20"), ("20%-<30%", "20-30"), ("36", "36-40"), ("44", "40-45"),
                                      ("49", "45-50"), ("50%-60%", "50-60"), (">60%", ">60"), ("Exempt", None), ("", None)])
def test_dti_band(raw, band):
    assert h.dti_band(raw) == band


# ------------------------------------------------------------------------------------------------- readers

def nara_line(**kw):
    """One 80-byte record in the 2004-forward public LAR layout."""
    rec = {"year": "2005", "respondent": "0000012345", "agency": "1", "loan_type": "1", "purpose": "1",
           "occupancy": "1", "loan_k": "00200", "action": "3", "msa": "47894", "state": "51", "county": "059",
           "tract": "4501.02", "sex": "2", "co_sex": "5", "income_k": "0085", "purchaser": "0", "reason1": "3",
           "reason2": " ", "reason3": " ", "edit": " ", "property": "1", "preapproval": "2", "eth": "2",
           "co_eth": "5", "race1": "3", "race2": " ", "race3": " ", "race4": " ", "race5": " ", "co_race1": "8",
           "co_race2": " ", "co_race3": " ", "co_race4": " ", "co_race5": " ", "rate_spread": "     ", "hoepa": "2",
           "lien": "1", "seq": "0000001"}
    rec.update(kw)
    line = [" "] * 80
    for name, a, b in h.NARA_COLS:
        v = rec[name].ljust(b - a + 1)[: b - a + 1]
        line[a - 1:b] = list(v)
    return "".join(line).encode()


def parse_nara(lines):
    cols = {n: [l[a - 1:b].decode().strip() for l in lines] for n, a, b in h.NARA_COLS}
    return pd.DataFrame(cols)


def test_nara_layout_round_trip():
    line = nara_line()
    assert len(line) == 80 and line[29:31] == b"51"
    d = parse_nara([line])
    out = h.finish(h.legacy(d.assign(tract_pop="", tract_minority_pct="", ffiec_mfi="", tract_income_pct="",
                                     tract_owner_units=""), 2005, "test"), 2005)
    r = out.iloc[0]
    assert r.tract == "51059450102" and r.county == "51059"
    assert r.group == "Black" and r.sex == "female" and r.co_applicant == 0
    assert r.denied == 1 and r.core == 1 and r.loan_k == 200 and r.income_k == 85 and r.reason1 == 3


def test_bedford_city_is_folded_into_bedford_county():
    d = parse_nara([nara_line(county="515", tract="0501.00")]).assign(
        tract_pop="", tract_minority_pct="", ffiec_mfi="", tract_income_pct="", tract_owner_units="")
    out = h.finish(h.legacy(d, 2006, "test"), 2006)
    assert out.county.iloc[0] == "51019" and out.county_raw.iloc[0] == "51515"


def modern_record(**kw):
    rec = {c: "" for c in ["activity_year", "lei", "derived_msa-md", "state_code", "county_code", "census_tract",
                           "action_taken", "purchaser_type", "preapproval", "loan_type", "loan_purpose", "lien_status",
                           "reverse_mortgage", "open-end_line_of_credit", "business_or_commercial_purpose",
                           "loan_amount", "loan_to_value_ratio", "interest_rate", "rate_spread", "hoepa_status",
                           "property_value", "construction_method", "occupancy_type", "total_units", "income",
                           "debt_to_income_ratio", "applicant_credit_score_type", "applicant_sex", "co-applicant_sex",
                           "applicant_age", "aus-1", "tract_population", "tract_minority_population_percent",
                           "ffiec_msa_md_median_family_income", "tract_to_msa_income_percentage",
                           "tract_owner_occupied_units"]}
    for k in range(1, 6):
        rec[f"applicant_race-{k}"] = ""
        rec[f"applicant_ethnicity-{k}"] = ""
    for k in range(1, 5):
        rec[f"denial_reason-{k}"] = ""
    rec.update({"activity_year": "2022", "lei": "LEI0001", "state_code": "VA", "county_code": "51059",
                "census_tract": "51059450102", "action_taken": "1", "loan_type": "1", "loan_purpose": "32",
                "lien_status": "1", "reverse_mortgage": "2", "open-end_line_of_credit": "2",
                "business_or_commercial_purpose": "2", "loan_amount": "355000", "construction_method": "1",
                "occupancy_type": "1", "total_units": "1", "income": "120", "debt_to_income_ratio": "38",
                "applicant_ethnicity-1": "14", "applicant_race-1": "27", "co-applicant_ethnicity-1": "5",
                "co-applicant_race-1": "8", "applicant_sex": "1", "denial_reason-1": "10", "applicant_credit_score_type": "1"})
    rec.update(kw)
    return rec


def test_modern_mapping():
    d = pd.DataFrame([modern_record(), modern_record(**{"open-end_line_of_credit": "1"}),
                      modern_record(**{"applicant_ethnicity-1": "2", "applicant_race-1": "27"}),
                      modern_record(occupancy_type="2", total_units="5-24")])
    out = h.finish(h.modern(d, 2022), 2022)
    a = out.iloc[0]
    assert a.purpose == "refinance" and a.cashout == 1 and a.loan_k == 355 and a.dti == "36-40"
    assert a.group == "Hispanic" and a.denied == 0 and a.core == 1 and pd.isna(a.reason1)
    assert out.core.iloc[1] == 0  # open-end line excluded
    assert out.group.iloc[2] == "Asian"  # subgroup 27 folded into Asian
    assert out.occupancy.iloc[3] == "second" and out.dwelling.iloc[3] == "multifamily" and out.core.iloc[3] == 0


def test_eras_and_tract_vintages():
    assert [sources.era(y) for y in (2004, 2011, 2012, 2017, 2018, 2025)] == \
        ["2004-2011", "2004-2011", "2012-2017", "2012-2017", "2018-2025", "2018-2025"]
    assert [sources.tract_vintage(y) for y in (2011, 2012, 2021, 2022)] == [2000, 2010, 2010, 2020]


# ------------------------------------------------------------------------------------------------- estimator

def test_fixed_effects_match_dummy_regression():
    rng = np.random.default_rng(0)
    n = 2500
    d = pd.DataFrame({"a": rng.integers(0, 30, n), "b": rng.integers(0, 20, n), "x1": rng.normal(size=n),
                      "x2": (rng.random(n) < 0.3).astype(float)})
    d["y"] = 0.5 * d.x1 - 0.2 * d.x2 + 0.1 * d.a / 30 + 0.05 * (d.b % 3) + rng.normal(size=n)
    r = models.fit(d.y, d[["x1", "x2"]], ["x1", "x2"], fes=[d.a.values, d.b.values], clusters=d.a.values)
    m = smf.ols("y ~ x1 + x2 + C(a) + C(b)", d).fit()
    for v in ("x1", "x2"):
        assert r["coef"][v] == pytest.approx(m.params[v], abs=1e-8)


def test_cluster_se_without_fixed_effects_matches_statsmodels():
    rng = np.random.default_rng(1)
    n = 2000
    g = rng.integers(0, 50, n)
    x = rng.normal(size=n)
    y = 0.3 * x + rng.normal(size=n) + 0.2 * (g % 5)
    r = models.fit(y, x[:, None], ["x"], clusters=g)
    m = smf.ols("y ~ x", pd.DataFrame({"y": y, "x": x})).fit(cov_type="cluster", cov_kwds={"groups": g})
    assert r["se"]["x"] == pytest.approx(m.bse["x"], rel=1e-9)
    assert r["coef"]["const"] == pytest.approx(m.params["Intercept"], abs=1e-10)


def test_singletons_are_dropped_iteratively():
    a = np.array([0, 0, 1, 2, 2, 3])
    b = np.array([0, 1, 1, 2, 2, 2])
    keep = models.drop_singletons([a, b])
    # a=1 and a=3 are singletons; once gone, b=0/b=1 groups become singletons too
    assert keep.tolist() == [False, False, False, True, True, False]


# ------------------------------------------------------------------------------------------------- geography

@pytest.mark.parametrize("vintage", [2000, 2010])
def test_crosswalk_weights_sum_to_one(vintage):
    x = geo.xwalk(vintage)
    s = x.groupby("src").w.sum()
    assert ((s - 1).abs() < 1e-9).mean() > 0.99  # a handful of water-only tracts carry no weight
    assert x.dst.str.len().eq(11).all() and x.dst.str.startswith("51").all()


def test_crosswalk_conserves_counts():
    x = geo.xwalk(2010)
    src = x.src.drop_duplicates().iloc[:200]
    counts = pd.DataFrame({"tract": src, "n": 10.0, "den": 2.0})
    out, share = geo.to_2020(counts, 2010)
    assert share == 1.0
    assert out.n.sum() == pytest.approx(2000.0) and out.den.sum() == pytest.approx(400.0)


def test_rdp_keeps_endpoints_and_drops_collinear_points():
    p = np.array([[0, 0], [1, 0.0001], [2, 0], [2, 2], [0, 0]], float)
    q = geo.rdp(p, 0.01)
    assert (q[0] == p[0]).all() and (q[-1] == p[-1]).all() and len(q) == 4


# ------------------------------------------------------------------------------------------------- committed results

@pytest.fixture(scope="module")
def VA():
    text = (ROOT / "site" / "virginia" / "data.js").read_text(encoding="utf-8")
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


def test_every_year_reconciles(VA):
    years = [r["year"] for r in VA["reconcile"]]
    assert years == list(range(2004, 2026))
    for r in VA["reconcile"]:
        if r["official"] is not None:
            assert r["records"] == r["official"], r["year"]
        assert r["valid_action"] >= 0.999


def test_story_facts(VA):
    """Facts the page's text relies on."""
    raw = [r for r in VA["yearly"] if r["spec"] == "raw" and r["purpose"] == "purchase" and r["group"] == "Black"]
    assert len(raw) == 22 and all(r["est"] > 0 for r in raw)
    eras = {(r["era"], r["spec"], r["group"], r["purpose"]): r for r in VA["eras"]}
    for era in ("2004-2011", "2012-2017", "2018-2025"):
        assert eras[(era, "lender", "Black", "purchase")]["est"] < eras[(era, "raw", "Black", "purchase")]["est"]
    full = eras[("2018-2025", "full", "Black", "purchase")]
    assert full["est"] > 0 and full["est"] - 1.96 * full["se"] > 0
    assert full["est"] < eras[("2018-2025", "lender", "Black", "purchase")]["est"]
    assert eras[("2018-2025", "lender", "Black", "refinance")]["est"] > eras[("2018-2025", "lender", "Black", "purchase")]["est"]
    assert VA["meta"]["context_check"] < 0.05
