"""Linear probability models with high-dimensional fixed effects, written out with numpy.

`fit(y, X, fes, clusters)` absorbs any number of fixed effects by alternating projections (the method reghdfe and
fixest use), drops singleton groups first, and returns coefficients with cluster-robust (CR1) standard errors. The
fixed effects are nested in the clusters when clustering by lender with lender effects, so the small-sample factor
counts only the slope coefficients, as reghdfe does.
"""

import numpy as np


def codes(a):
    """Integer codes 0..G-1 for any array of labels."""
    _, inv = np.unique(np.asarray(a, dtype=str), return_inverse=True)
    return inv


def drop_singletons(fes):
    """Boolean mask keeping observations whose group has 2+ members in every fixed effect, iterated to a fixed point."""
    keep = np.ones(len(fes[0]), bool)
    while True:
        changed = False
        for f in fes:
            cnt = np.bincount(f[keep], minlength=f.max() + 1)
            bad = keep & (cnt[f] < 2)
            if bad.any():
                keep &= ~bad
                changed = True
        if not changed:
            return keep


def demean(M, fes, tol=1e-9, maxiter=500):
    """Residualize every column of M on all the fixed effects (alternating projections)."""
    M = M.astype(float).copy()
    sizes = [np.bincount(f).astype(float) for f in fes]
    for _ in range(maxiter):
        delta = 0.0
        for f, n in zip(fes, sizes):
            for j in range(M.shape[1]):
                means = np.bincount(f, weights=M[:, j], minlength=len(n)) / np.where(n > 0, n, 1)
                step = means[f]
                M[:, j] -= step
                delta = max(delta, float(np.abs(step).max()))
        if delta < tol or len(fes) == 1:
            break
    return M


def fit(y, X, names, fes=(), clusters=None):
    """OLS of y on X after absorbing `fes` (list of label arrays). Returns a dict with coefficients, CR1 SEs and N."""
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    fe_codes = [codes(np.asarray(f)[ok]) for f in fes]
    y, X = y[ok], X[ok]
    cl = codes(np.asarray(clusters)[ok]) if clusters is not None else np.arange(len(y))
    if fe_codes:
        keep = drop_singletons(fe_codes)
        y, X, cl = y[keep], X[keep], cl[keep]
        fe_codes = [codes(f[keep]) for f in fe_codes]
        R = demean(np.column_stack([y, X]), fe_codes)
        y_r, X_r = R[:, 0], R[:, 1:]
    else:
        X = np.column_stack([np.ones(len(y)), X])
        names = ["const"] + list(names)
        y_r, X_r = y, X
    # drop columns that the fixed effects absorbed entirely (constant within groups)
    live = X_r.std(axis=0) > 1e-10
    if not fe_codes:
        live[0] = True  # the constant
    X_r = X_r[:, live]
    nm = [n for n, l in zip(names, live) if l]
    XtX = X_r.T @ X_r
    beta = np.linalg.solve(XtX, X_r.T @ y_r)
    e = y_r - X_r @ beta
    G = cl.max() + 1
    S = np.zeros((G, X_r.shape[1]))
    np.add.at(S, cl, X_r * e[:, None])
    inv = np.linalg.inv(XtX)
    n, k = X_r.shape
    adj = G / (G - 1) * (n - 1) / (n - k)
    V = adj * inv @ (S.T @ S) @ inv
    se = np.sqrt(np.diag(V))
    return {"n": int(n), "clusters": int(G), "coef": dict(zip(nm, beta.tolist())), "se": dict(zip(nm, se.tolist())),
            "mean_y": float(y.mean())}
