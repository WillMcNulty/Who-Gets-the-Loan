"""Group fairness metrics, written out by hand so each one is easy to check.

Vocabulary, since the "truth" here is the lender's own decision (see the report's label-bias section):
- selection rate: share of a group the model would approve (demographic parity compares these);
- TPR: of the applicants the lenders approved, the share the model also approves (equal opportunity compares these);
- FPR: of the applicants the lenders denied, the share the model approves (equalized odds compares TPR and FPR);
- calibration: does a predicted 0.8 mean 80% were approved, in each group?
"""

import numpy as np


def rates(y, yhat):
    """Confusion-matrix rates for 0/1 arrays. NaN where a denominator is empty."""
    y, yhat = np.asarray(y, bool), np.asarray(yhat, bool)
    pos, neg = y.sum(), (~y).sum()
    tp, fp = (yhat & y).sum(), (yhat & ~y).sum()
    tn, fn = (~yhat & ~y).sum(), (~yhat & y).sum()
    div = lambda a, b: float(a / b) if b else float("nan")
    return {"n": int(len(y)), "base_rate": div(pos, len(y)), "selection": div(yhat.sum(), len(y)),
            "tpr": div(tp, pos), "fpr": div(fp, neg), "fnr": div(fn, pos), "tnr": div(tn, neg),
            "accuracy": div(tp + tn, len(y)), "precision": div(tp, tp + fp)}


def auc(y, score):
    """Area under the ROC curve via the rank-sum (Mann-Whitney) formula, ties counted as half."""
    y = np.asarray(y, bool)
    score = np.asarray(score, float)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    s = score[order]
    ranks = np.empty(len(s))
    i = 0
    while i < len(s):  # average ranks over ties
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2 + 1
        i = j + 1
    r = np.empty(len(s))
    r[order] = ranks
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def gaps(a, b):
    """Differences between two groups' rate dicts, b minus a (a = reference group)."""
    out = {f"d_{k}": b[k] - a[k] for k in ("selection", "tpr", "fpr", "accuracy")}
    out["selection_ratio"] = b["selection"] / a["selection"] if a["selection"] else float("nan")
    out["equalized_odds"] = max(abs(out["d_tpr"]), abs(out["d_fpr"]))
    return out


def by_group(y, yhat, score, groups, ref="White", other="Black or Hispanic", subgroups=("Black", "Hispanic")):
    """Rates for each group, the reference vs. everyone else, and the gaps."""
    y, yhat, score, groups = map(np.asarray, (y, yhat, score, groups))
    out = {"groups": {}}
    masks = {ref: groups == ref, other: groups != ref}
    for s in subgroups:
        masks[s] = groups == s
    masks["All"] = np.ones(len(y), bool)
    for name, m in masks.items():
        r = rates(y[m], yhat[m])
        r["auc"] = auc(y[m], score[m])
        r["mean_score"] = float(score[m].mean()) if m.any() else float("nan")
        out["groups"][name] = r
    out["gaps"] = gaps(out["groups"][ref], out["groups"][other])
    return out


def bootstrap_gaps(y, yhat, groups, ref="White", reps=1000, seed=7):
    """Percentile intervals for the selection, TPR and FPR gaps (other minus reference), resampling applicants
    within each group. The model's predictions are held fixed, so this covers sampling of the applicants
    evaluated, not retraining."""
    y, yhat, groups = np.asarray(y, bool), np.asarray(yhat, bool), np.asarray(groups)
    a, b = np.flatnonzero(groups == ref), np.flatnonzero(groups != ref)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        ia, ib = rng.choice(a, len(a)), rng.choice(b, len(b))
        ra, rb = rates(y[ia], yhat[ia]), rates(y[ib], yhat[ib])
        draws.append([rb["selection"] - ra["selection"], rb["tpr"] - ra["tpr"], rb["fpr"] - ra["fpr"],
                      (y[ib].mean() - y[ia].mean())])
    D = np.array(draws)
    keys = ["d_selection", "d_tpr", "d_fpr", "d_base_rate"]
    return {k: [float(np.nanpercentile(D[:, j], 2.5)), float(np.nanpercentile(D[:, j], 97.5))] for j, k in enumerate(keys)}


def calibration(y, score, groups, edges=(0, 0.6, 0.75, 0.85, 0.9, 0.95, 1.0001), ref="White"):
    """Observed approval rate against mean predicted probability, in fixed bins, for the reference group and
    everyone else. Bins are fixed (not quantiles) so both groups are compared at the same predicted levels."""
    y, score, groups = np.asarray(y, float), np.asarray(score, float), np.asarray(groups)
    out = []
    for name, m in (("White", groups == ref), ("Black or Hispanic", groups != ref)):
        for lo, hi in zip(edges[:-1], edges[1:]):
            k = m & (score >= lo) & (score < hi)
            n = int(k.sum())
            if n == 0:
                continue
            obs = float(y[k].mean())
            out.append({"group": name, "lo": float(lo), "hi": float(min(hi, 1.0)), "n": n,
                        "predicted": float(score[k].mean()), "observed": obs,
                        "se": float(np.sqrt(max(obs * (1 - obs), 1e-9) / n))})
    return out


def threshold_for_rate(score, rate):
    """The cutoff that approves (about) `rate` of the scores: approve when score >= cutoff."""
    score = np.sort(np.asarray(score, float))[::-1]
    k = int(round(rate * len(score)))
    k = min(max(k, 1), len(score))
    return float(score[k - 1])


def reweighing(y, groups, ref="White"):
    """Kamiran and Calders (2012) weights that make the label independent of group in the training data:
    w(g, y) = P(g) P(y) / P(g, y)."""
    y, g = np.asarray(y), np.where(np.asarray(groups) == ref, 1, 0)
    w = np.empty(len(y), float)
    for gv in (0, 1):
        for yv in (0, 1):
            m = (g == gv) & (y == yv)
            w[m] = (g == gv).mean() * (y == yv).mean() / m.mean()
    return w
