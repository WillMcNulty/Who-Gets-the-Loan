"""Part B: approval models trained without race, and what they do by race.

Every prediction is out-of-fold (5-fold cross-validation, stratified by group and outcome), so each applicant is
scored by a model that never saw them. The cutoff approves the same share of applicants the lenders approved
(87.7%), so the models are compared at the lenders' own approval volume.
"""

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import econ, fairness as fm

SEED = 20261007
FOLDS = 5

# What an underwriter would see about the applicant and the loan. No race, and none of the other characteristics
# the Equal Credit Opportunity Act protects (sex, marital status, age), and no neighborhood variables.
FEATURES = ["hrat", "obrat", "loanprc", "unem", "dep", "sch", "cosign", "chist", "cons", "pubrec", "mortlat1",
            "mortlat2", "self", "multi", "log_appinc", "log_loanamt", "netw_signed_log"]
# Judgments recorded by the lender: "meets credit guidelines" and "unverifiable information".
LENDER = ["gdlin", "unver"]
# Census-tract and county facts about where the house is.
PLACE = ["suffolk", "vr", "mi", "bd", "min30", "min30_missing"]
PROTECTED = ["male_or_missing", "married", "old"]

LABELS = {
    "hrat": "Housing expense / income", "obrat": "Total obligations / income", "loanprc": "Loan / price",
    "unem": "Unemployment rate in the applicant's industry", "dep": "Dependents", "sch": "More than 12 years of school",
    "cosign": "Cosigner", "chist": "No accounts 60+ days delinquent", "cons": "Consumer credit history (1 best, 6 worst)",
    "pubrec": "Public record of bad credit", "mortlat1": "1-2 late mortgage payments", "mortlat2": "3+ late mortgage payments",
    "self": "Self-employed", "multi": "2+ unit property", "log_appinc": "Applicant income (log)",
    "log_loanamt": "Loan amount (log)", "netw_signed_log": "Net worth (signed log)", "gdlin": "Lender: meets credit guidelines",
    "unver": "Lender: unverifiable information", "suffolk": "In Suffolk County (Boston)", "vr": "Tract vacancy rate above median",
    "mi": "Tract income above median", "bd": "Tract boarded-up rate above median", "min30": "Tract minority share above 30%",
    "min30_missing": "Tract minority share not recorded", "male_or_missing": "Male", "married": "Married", "old": "Age above median",
}


def frame(df):
    """Part B's analysis frame: engineered features, complete cases, and the group labels."""
    d = econ.prepare(df)
    d["log_appinc"] = np.log1p(d.appinc)
    d["log_loanamt"] = np.log(d.loanamt)
    d["netw_signed_log"] = np.sign(d.netw) * np.log1p(np.abs(d.netw))
    d["min30_missing"] = d.min30.isna().astype(float)
    d["min30"] = d.min30.fillna(0.0)
    d["male_or_missing"] = d.male.fillna(0.0)
    d = d.dropna(subset=FEATURES + LENDER + ["married"]).reset_index(drop=True)
    d["two"] = np.where(d.white == 1, "White", "Black or Hispanic")
    return d


def models():
    return {
        "logit": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
        "gbm": GradientBoostingClassifier(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8,
                                          random_state=SEED),
    }


MODEL_NAMES = {"logit": "Logistic regression", "gbm": "Gradient boosting"}


def folds(d, seed=SEED):
    strata = d.group.astype(str) + "_" + d.approve.astype(int).astype(str)
    return list(StratifiedKFold(FOLDS, shuffle=True, random_state=seed).split(d, strata))


def oof(model, X, y, splits, weights=None):
    """Out-of-fold predicted probabilities."""
    p = np.empty(len(y))
    for tr, te in splits:
        m = clone(model)
        if weights is None:
            m.fit(X[tr], y[tr])
        else:
            step = m.steps[-1][0] + "__sample_weight" if hasattr(m, "steps") else "sample_weight"
            m.fit(X[tr], y[tr], **{step: weights[tr]})
        p[te] = m.predict_proba(X[te])[:, 1]
    # Tree models give many applicants the same score; rounding keeps last-bit float differences between platforms
    # from moving a tied group across a cutoff or a calibration-bin edge.
    return np.round(p, 8)


def group_metrics(d, score, yhat, label="approve", boot=True):
    y = d[label].values
    res = fm.by_group(y, yhat, score, d.group.values)
    if boot:
        res["ci"] = fm.bootstrap_gaps(y, yhat, d.group.values)
    return res


def run_models(d):
    """Race-blind models, plus a race-aware logit for contrast. Returns metrics and the out-of-fold scores."""
    y = d.approve.values
    splits = folds(d)
    rate = y.mean()
    out, scores = {}, {}
    sets = {name: (m, FEATURES) for name, m in models().items()}
    sets["logit_race"] = (models()["logit"], FEATURES + ["white"])
    sets["logit_lender"] = (models()["logit"], FEATURES + LENDER)
    for name, (m, feats) in sets.items():
        p = oof(m, d[feats].values, y, splits)
        cut = fm.threshold_for_rate(p, rate)
        yhat = p >= cut
        res = group_metrics(d, p, yhat)
        res["cutoff"] = cut
        res["calibration"] = fm.calibration(y, p, d.group.values)
        out[name] = res
        scores[name] = p
    return out, scores


def proxies(d):
    """How well the race-blind inputs predict race: out-of-fold AUC for predicting Black-or-Hispanic from several
    feature sets, and each single feature's AUC on its own (0.5 = carries no information about race)."""
    target = (d.white == 0).astype(int).values
    splits = list(StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(d, target))
    sets = [
        ("features", "The model's inputs (finances and credit)", FEATURES),
        ("features_lender", "+ the lender's judgments", FEATURES + LENDER),
        ("place", "Neighborhood only", PLACE),
        ("features_place", "Inputs + neighborhood", FEATURES + PLACE),
        ("all", "Inputs + lender's judgments + neighborhood + sex, marriage, age", FEATURES + LENDER + PLACE + PROTECTED),
    ]
    rows = []
    for key, label, feats in sets:
        row = {"key": key, "label": label, "k": len(feats)}
        for name, m in models().items():
            p = oof(m, d[feats].values, target, splits)
            row[name] = fm.auc(target, p)
        rows.append(row)
    single = []
    for f in FEATURES + LENDER + PLACE:
        a = fm.auc(target, d[f].values)
        single.append({"feature": f, "label": LABELS[f], "auc": a, "strength": abs(a - 0.5),
                       "direction": "higher for Black or Hispanic applicants" if a > 0.5 else "higher for white applicants",
                       "mean_white": float(d.loc[d.white == 1, f].mean()), "mean_nonwhite": float(d.loc[d.white == 0, f].mean()),
                       "set": "features" if f in FEATURES else ("lender" if f in LENDER else "place")})
    single.sort(key=lambda r: -r["strength"])
    return {"base_rate": float(target.mean()), "sets": rows, "single": single}


def mitigation(d, base_score):
    """Trade-offs, on the race-blind logistic regression: reweighting the training data, and separate cutoffs by
    group (which uses race at decision time, so it is shown as an illustration, not a recommendation)."""
    y, g = d.approve.values, d.group.values
    white = g == "White"
    rate = y.mean()
    rows = []

    def add(key, label, score, yhat, note):
        r = fm.by_group(y, yhat, score, g)
        rows.append({"key": key, "label": label, "note": note, "selection_overall": float(yhat.mean()),
                     "accuracy": r["groups"]["All"]["accuracy"], "auc": r["groups"]["All"]["auc"],
                     **{k: r["gaps"][k] for k in ("d_selection", "selection_ratio", "d_tpr", "d_fpr", "equalized_odds")},
                     "sel_white": r["groups"]["White"]["selection"], "sel_other": r["groups"]["Black or Hispanic"]["selection"]})

    cut = fm.threshold_for_rate(base_score, rate)
    add("baseline", "Race-blind model, one cutoff", base_score, base_score >= cut, "")

    w = fm.reweighing(y, g)
    p_rw = oof(models()["logit"], d[FEATURES].values, y, folds(d), weights=w)
    add("reweigh", "Reweighted training data", p_rw, p_rw >= fm.threshold_for_rate(p_rw, rate),
        "Weights make approval independent of group in the training data (Kamiran and Calders 2012).")

    # Group cutoffs that equalize selection rates while approving the same total share.
    yhat = np.zeros(len(y), bool)
    for m in (white, ~white):
        yhat[m] = base_score[m] >= fm.threshold_for_rate(base_score[m], rate)
    add("parity", "Separate cutoffs: equal approval rates", base_score, yhat,
        "Uses race at decision time: disparate treatment under U.S. fair-lending law.")

    # Group cutoffs that equalize TPR (equal opportunity) at the same total share, by bisection on the target TPR.
    yhat_eo = _equal_tpr(base_score, y, white, rate)
    add("equal_opportunity", "Separate cutoffs: equal true-positive rates", base_score, yhat_eo,
        "Uses race at decision time; equalizes agreement with the lenders' approvals.")

    # The frontier: move each group's approval rate part of the way from the one-cutoff result to parity.
    frontier = []
    base_sel = {k: (base_score[m] >= cut).mean() for k, m in (("w", white), ("o", ~white))}
    for lam in np.linspace(0, 1, 11):
        yh = np.zeros(len(y), bool)
        for k, m in (("w", white), ("o", ~white)):
            target = base_sel[k] + lam * (rate - base_sel[k])
            yh[m] = base_score[m] >= fm.threshold_for_rate(base_score[m], target)
        r = fm.by_group(y, yh, base_score, g)
        frontier.append({"lam": float(lam), "d_selection": r["gaps"]["d_selection"], "accuracy": r["groups"]["All"]["accuracy"],
                         "d_tpr": r["gaps"]["d_tpr"], "selection_overall": float(yh.mean())})
    return {"rows": rows, "frontier": frontier}


def _equal_tpr(score, y, white, rate):
    best = None
    for t in np.linspace(0.80, 1.0, 401):
        yh = np.zeros(len(y), bool)
        for m in (white, ~white):
            pos = np.sort(score[m & (y == 1)])[::-1]
            k = max(int(np.ceil(t * len(pos))), 1)
            yh[m] = score[m] >= pos[k - 1]
        gap = abs(yh.mean() - rate)
        if best is None or gap < best[0]:
            best = (gap, yh)
    return best[1]


def label_bias(d, base_score, draws=50):
    """What if the recorded decisions were biased? A what-if, not an estimate.

    Scenario: the part of the gap the credit-history probit leaves unexplained came from biased decisions. Each
    denied Black or Hispanic applicant is relabeled "approved" with probability (p1 - p0) / (1 - p0), where p0 is
    their predicted approval as recorded and p1 their prediction with white = 1. That raises each group's expected
    approval rate to the model's "same file, white applicant" rate and leaves white applicants unchanged. Then:
    (1) retrain the race-blind model on the relabeled data; (2) re-measure the original model against the new labels.
    """
    spec = econ.Spec(["white"] + econ.PS6[1:] + econ.CREDIT)
    dd = d.copy()
    dd["male"] = dd["male"].fillna(dd["male_or_missing"])  # same sample as Part B; male missing for a few
    f = econ.fit(dd, "approve", spec, "probit")
    d1 = dd.copy()
    d1["white"] = 1.0
    p0, p1 = f.predict(dd), f.predict(d1)
    flip_p = np.where((dd.white.values == 0) & (dd.approve.values == 0), np.clip((p1 - p0) / (1 - p0), 0, 1), 0.0)
    rng = np.random.default_rng(SEED)
    y = dd.approve.values
    rate_rec = y.mean()
    splits = folds(dd)
    g = dd.group.values
    acc = {"relabeled_train": [], "orig_vs_new": []}
    flips = []
    cut0 = fm.threshold_for_rate(base_score, rate_rec)
    yhat0 = base_score >= cut0
    rec = fm.by_group(y, yhat0, base_score, g)
    for i in range(draws):
        y_new = np.where(rng.random(len(y)) < flip_p, 1, y)
        flips.append(int((y_new != y).sum()))
        p = oof(models()["logit"], dd[FEATURES].values, y_new, splits)
        # same approval volume as the recorded decisions, so only the labels differ
        yh = p >= fm.threshold_for_rate(p, rate_rec)
        acc["relabeled_train"].append(fm.by_group(y_new, yh, p, g))
        # the original model, same approvals, judged against the relabeled outcomes
        acc["orig_vs_new"].append(fm.by_group(y_new, yhat0, base_score, g))
    avg = lambda rs, path: float(np.mean([_get(r, path) for r in rs]))
    keys = [("gaps", "d_selection"), ("gaps", "d_tpr"), ("gaps", "d_fpr"), ("groups", "All", "accuracy"),
            ("groups", "Black or Hispanic", "base_rate"), ("groups", "White", "base_rate"),
            ("groups", "Black or Hispanic", "tpr"), ("groups", "White", "tpr"), ("groups", "Black or Hispanic", "selection"),
            ("groups", "White", "selection")]
    summarize = lambda rs: {"/".join(k): avg(rs, k) for k in keys}
    return {
        "draws": draws, "mean_flips": float(np.mean(flips)), "flip_expected": float(flip_p.sum()),
        "n_nonwhite_denied": int(((dd.white == 0) & (dd.approve == 0)).sum()),
        "recorded": {"/".join(k): _get(rec, k) for k in keys},
        "retrained": summarize(acc["relabeled_train"]),
        "original_vs_relabeled": summarize(acc["orig_vs_new"]),
    }


def _get(d, path):
    for k in path:
        d = d[k]
    return d
