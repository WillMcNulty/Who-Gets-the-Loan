import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from audit import fairness as fm

ROOT = Path(__file__).resolve().parents[1]


def test_rates_hand_worked():
    #        y: 1 1 1 1 0 0 0 0 0 0
    #     yhat: 1 1 1 0 1 0 0 0 0 0   -> tp 3, fn 1, fp 1, tn 5
    y = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
    yhat = [1, 1, 1, 0, 1, 0, 0, 0, 0, 0]
    r = fm.rates(y, yhat)
    assert r["tpr"] == 0.75 and r["fnr"] == 0.25
    assert r["fpr"] == pytest.approx(1 / 6) and r["tnr"] == pytest.approx(5 / 6)
    assert r["selection"] == 0.4 and r["base_rate"] == 0.4
    assert r["accuracy"] == 0.8 and r["precision"] == 0.75


def test_rates_empty_denominators_are_nan():
    r = fm.rates([1, 1], [1, 0])
    assert np.isnan(r["fpr"]) and r["tpr"] == 0.5


def test_auc_matches_sklearn_with_ties():
    rng = np.random.default_rng(1)
    y = rng.random(300) < 0.4
    s = np.round(rng.random(300) + 0.3 * y, 1)  # rounding makes many ties
    assert fm.auc(y, s) == pytest.approx(roc_auc_score(y, s))
    assert fm.auc([0, 0, 1, 1], [0.1, 0.2, 0.3, 0.4]) == 1.0
    assert fm.auc([0, 1], [0.5, 0.5]) == 0.5


def test_gaps_and_by_group():
    y = np.array([1, 1, 0, 0, 1, 1, 0, 0])
    yhat = np.array([1, 1, 1, 0, 1, 0, 0, 0])
    groups = np.array(["White"] * 4 + ["Black"] * 4)
    out = fm.by_group(y, yhat, yhat.astype(float), groups)
    g = out["gaps"]
    assert g["d_selection"] == pytest.approx(0.25 - 0.75)
    assert g["d_tpr"] == pytest.approx(0.5 - 1.0)
    assert g["d_fpr"] == pytest.approx(0.0 - 0.5)
    assert g["equalized_odds"] == pytest.approx(0.5)
    assert g["selection_ratio"] == pytest.approx(1 / 3)
    assert out["groups"]["Black or Hispanic"]["n"] == 4


def test_threshold_for_rate():
    s = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
    assert fm.threshold_for_rate(s, 0.4) == 0.8
    assert (s >= fm.threshold_for_rate(s, 0.6)).mean() == 0.6


def test_reweighing_makes_label_independent_of_group():
    y = np.array([1, 1, 1, 0, 1, 0, 0, 0, 1, 1])
    groups = np.array(["White"] * 5 + ["Black"] * 5)
    w = fm.reweighing(y, groups)
    for g in ("White", "Black"):
        m = groups == g
        assert np.average(y[m], weights=w[m]) == pytest.approx(y.mean())
    assert w.sum() == pytest.approx(len(y))


def test_calibration_bins_cover_every_score():
    rng = np.random.default_rng(2)
    s = rng.random(500)
    y = (rng.random(500) < s).astype(int)
    groups = np.where(rng.random(500) < 0.7, "White", "Black")
    bins = fm.calibration(y, s, groups)
    assert sum(b["n"] for b in bins) == 500


def test_bootstrap_interval_contains_point_estimate():
    rng = np.random.default_rng(3)
    groups = np.where(rng.random(600) < 0.8, "White", "Black")
    y = rng.random(600) < np.where(groups == "White", 0.9, 0.7)
    yhat = rng.random(600) < np.where(groups == "White", 0.9, 0.7)
    ci = fm.bootstrap_gaps(y, yhat, groups, reps=300)
    point = fm.by_group(y, yhat, yhat.astype(float), groups)["gaps"]["d_selection"]
    assert ci["d_selection"][0] < point < ci["d_selection"][1]


def test_committed_results_tell_the_story():
    """The facts the page's text relies on, read from the committed data file."""
    text = (ROOT / "site" / "data.js").read_text(encoding="utf-8")
    R = json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))
    blind = R["ml"]["models"]["logit"]
    assert "white" not in R["ml"]["features"] and "male_or_missing" not in R["ml"]["features"]
    assert blind["gaps"]["d_selection"] < -0.15  # the race-blind model keeps most of the gap
    assert blind["ci"]["d_selection"][1] < 0
    nb = [c for c in blind["calibration"] if c["group"] == "Black or Hispanic"]
    assert sum(c["observed"] < c["predicted"] for c in nb) >= len(nb) - 1
    assert R["proxies"]["sets"][0]["logit"] > 0.65
    mit = {r["key"]: r for r in R["mitigation"]["rows"]}
    assert abs(mit["parity"]["d_selection"]) < 0.01 and abs(mit["equal_opportunity"]["d_tpr"]) < 0.01
    lb = R["label_bias"]
    assert lb["original_vs_relabeled"]["gaps/d_tpr"] < lb["recorded"]["gaps/d_tpr"]
