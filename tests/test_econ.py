import warnings

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from audit import data, econ

warnings.simplefilter("ignore")


@pytest.fixture(scope="module")
def df():
    return econ.prepare(data.load())


@pytest.fixture(scope="module")
def ps6(df):
    return econ.ps6(df)


def coef(block, term, key="coef"):
    return next(c[key] for c in block["coefs"] if c["term"] == term)


# This project's estimates for the problem-set models (they also agree with Stata's printed output for the same
# commands; that comparison runs locally, see scripts/check_ps6_private.py).
@pytest.mark.parametrize("model,term,value,se", [
    ("lpm", "white", 0.1460959, 0.0263961), ("lpm", "pubrec", -0.2911969, 0.0431627),
    ("lpm", "obrat", -0.0062473, 0.0013148), ("lpm", "const", 1.034481, 0.0522301),
    ("probit", "white", 0.596131, 0.0938366), ("probit", "pubrec", -0.9810615, 0.1201642),
    ("logit", "white", 1.076127, 0.1667324), ("logit", "loanprc", -1.903088, 0.4556439),
])
def test_ps6_coefficients(ps6, model, term, value, se):
    assert coef(ps6[model], term) == pytest.approx(value, abs=6e-7)
    key = "se" if model == "lpm" else "se_oim"
    assert coef(ps6[model], term, key) == pytest.approx(se, abs=6e-7)


def test_ps6_fit_statistics(ps6):
    assert ps6["n"] == 1971
    assert ps6["lpm"]["r2"] == pytest.approx(0.1408, abs=5e-5)
    assert ps6["probit"]["ll"] == pytest.approx(-622.73366, abs=1e-5)
    assert ps6["logit"]["ll"] == pytest.approx(-622.82193, abs=1e-5)
    assert ps6["probit"]["lr_chi2"] == pytest.approx(230.49, abs=0.005)
    assert ps6["lpm"]["phat_min"] == pytest.approx(0.1989837, abs=1e-6)
    assert ps6["lpm"]["phat_max"] == pytest.approx(1.17238, abs=1e-5)
    assert ps6["lpm"]["n_out_of_range"] == ps6["lpm"]["n_above_1"] == 151


def test_ame_matches_statsmodels(df, ps6):
    d = df.dropna(subset=["approve"] + econ.PS6)
    X = sm.add_constant(d[econ.PS6])
    res = sm.Probit(d.approve, X).fit(disp=0)
    deriv = res.get_margeff(at="overall", method="dydx").summary_frame()
    disc = res.get_margeff(at="overall", method="dydx", dummy=True).summary_frame()
    for v in econ.PS6:
        got = ps6["probit"]["ame_derivative"][v]
        assert got["est"] == pytest.approx(deriv.loc[v, "dy/dx"], abs=1e-7)
        assert got["se"] == pytest.approx(deriv.loc[v, "Std. Err."], rel=1e-4)
    for v in ("white", "pubrec"):
        assert ps6["probit"]["ame_discrete"][v]["est"] == pytest.approx(disc.loc[v, "dy/dx"], abs=1e-7)
    assert ps6["probit"]["ame_derivative"]["white"]["est"] == pytest.approx(0.1026927, abs=6e-7)


def test_robust_se_uses_stata_scaling(df):
    f = econ.fit(df, "approve", econ.Spec(econ.PS6), "probit")
    d = f.data
    X = econ.Spec(econ.PS6).design(d)
    hc0 = sm.Probit(d.approve, X).fit(disp=0, cov_type="HC0").cov_params()
    assert np.allclose(f.cov.values, hc0.values * len(d) / (len(d) - 1))


def test_ame_with_interaction_equals_lpm_coefficient_when_linear(df):
    # In a linear model the derivative AME of a variable without interactions is just its coefficient.
    f = econ.fit(df, "approve", econ.Spec(econ.PS6, [("white", "obrat")]), "lpm")
    est, se = econ.ame(f, "hrat", "derivative")
    assert est == pytest.approx(f.params["hrat"], abs=1e-9)
    assert se == pytest.approx(f.se["hrat"], rel=1e-5)
    # and the white effect averages the interaction over obrat
    est, _ = econ.ame(f, "white", "discrete")
    assert est == pytest.approx(f.params["white"] + f.params["white:obrat"] * f.data.obrat.mean(), abs=1e-9)


def test_ladder_shrinks_and_stays_positive(df):
    rows = {r["key"]: r for r in econ.ladder(df)["rows"]}
    lpm = [rows[k]["lpm"]["est"] for k in ("raw", "ps6", "credit", "file")]
    assert lpm == sorted(lpm, reverse=True) and lpm[-1] > 0
    # with no controls every model reproduces the raw difference in means
    assert rows["raw"]["probit"]["est"] == pytest.approx(rows["raw"]["lpm"]["est"], abs=1e-6)
    # Wooldridge's C7.8 specification gives about 0.129 on its own sample; here on the common sample
    assert rows["credit"]["lpm"]["est"] == pytest.approx(0.13, abs=0.005)


def test_oaxaca_identity_and_references():
    rng = np.random.default_rng(0)
    n = 400
    g = (rng.random(n) < 0.5).astype(float)
    x = rng.normal(size=n) + g  # group 1 has higher x
    y = 0.3 + 0.2 * x + 0.1 * g + rng.normal(scale=0.1, size=n)
    X = np.column_stack([np.ones(n), x])
    r = econ.oaxaca_point(y, X, g, ["const", "x"])
    for k in ("pooled", "white_coefs", "nonwhite_coefs"):
        assert r[k]["explained"] + r[k]["unexplained"] == pytest.approx(r["gap"])
        assert sum(r[k]["detail"].values()) == pytest.approx(r[k]["explained"])
    # the pooled reference with a group indicator recovers the true slope, so the unexplained part ~ the 0.1 shift
    assert r["pooled"]["unexplained"] == pytest.approx(0.1, abs=0.03)


def test_oaxaca_on_the_data(df):
    o = econ.oaxaca(df, reps=50)
    assert o["n"] == 1971 and o["n_white"] + o["n_nonwhite"] == 1971
    assert o["gap"] == pytest.approx(o["mean_white"] - o["mean_nonwhite"])
    p = o["pooled"]
    assert p["explained"] + p["unexplained"] == pytest.approx(o["gap"])
    assert 0 < p["explained"] < p["unexplained"]
    lo, hi = p["unexplained_ci"]
    assert lo < p["unexplained"] < hi and lo > 0


def test_adjusted_predictions_reduce_to_means_for_lpm(df):
    f = econ.fit(df, "approve", econ.Spec(econ.PS6), "lpm")
    rows = econ.adjusted_predictions(f, "obrat", [30.0], "white")
    assert rows[0]["gap"] == pytest.approx(f.params["white"], abs=1e-9)
