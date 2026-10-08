"""Part A: the econometrics. Linear probability, probit and logit models of approval, average marginal effects,
a ladder of controls, race interactions, and an Oaxaca-Blinder decomposition of the approval gap.

Conventions follow Stata, so the problem-set models can be checked digit for digit:
- LPM standard errors are HC1 (`regress ..., r`).
- Probit and logit report both the information-matrix SEs (Stata's default) and robust sandwich SEs scaled by
  N/(N-1) (`probit ..., vce(robust)`).
- Average marginal effects average over the estimation sample. "Derivative" AMEs treat every regressor as
  continuous, which is what `margins, dydx(*)` does when the variables aren't declared as factors; "discrete"
  AMEs switch a 0/1 regressor from 0 to 1 for everyone (`margins, dydx(i.white)`). The discrete version is the
  right one for a dummy like `white`.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

PS6 = ["white", "hrat", "obrat", "loanprc", "unem", "male", "married", "dep", "pubrec"]
# Wooldridge's richer specification (Computer Exercise C7.8): PS6 plus schooling, a cosigner, the credit-history
# variables and the tract vacancy rate.
CREDIT = ["sch", "cosign", "chist", "mortlat1", "mortlat2", "vr"]
# Judgments and facts from the lender's own file. "Meets credit guidelines" is the lender's judgment, so it may
# itself carry any bias being measured (see the report's "over-controlling" note). Consumer credit history (`cons`,
# 1 best to 6 worst) enters as dummies; `chist` is exactly cons >= 5, so cons5 is left out to avoid collinearity.
FILE = ["gdlin", "cons2", "cons3", "cons4", "cons6", "self", "multi", "unver"]

LADDER = [
    ("raw", "No controls", []),
    ("ps6", "Problem set 6 controls", PS6[1:]),
    ("credit", "+ credit history (Wooldridge C7.8)", PS6[1:] + CREDIT),
    ("file", "+ lender's file (guidelines, consumer credit, self-employed, unverified info)", PS6[1:] + CREDIT + FILE),
]


def prepare(df):
    """Model-ready columns: consumer-credit dummies and gdlin's 666 code treated as missing."""
    d = df.copy()
    d["gdlin"] = d.gdlin.where(d.gdlin.isin([0, 1]))
    for k in range(2, 7):
        d[f"cons{k}"] = (d.cons == k).astype(float)
    d["nonwhite"] = 1.0 - d.white
    return d


@dataclass
class Spec:
    xs: list
    inter: list = field(default_factory=list)  # pairs (a, b) -> a column "a:b" = a*b

    def design(self, df):
        X = pd.DataFrame({"const": 1.0}, index=df.index)
        for x in self.xs:
            X[x] = df[x]
        for a, b in self.inter:
            X[f"{a}:{b}"] = df[a] * df[b]
        return X

    @property
    def columns(self):
        return self.xs + [a for pair in self.inter for a in pair]


LINKS = {
    "lpm": (lambda z: z, lambda z: np.ones_like(z)),
    "probit": (stats.norm.cdf, stats.norm.pdf),
    "logit": (lambda z: 1 / (1 + np.exp(-z)), lambda z: np.exp(-z) / (1 + np.exp(-z)) ** 2),
}


@dataclass
class Fit:
    kind: str
    spec: Spec
    data: pd.DataFrame
    params: pd.Series
    cov: pd.DataFrame  # the covariance used for inference (robust)
    cov_oim: pd.DataFrame | None
    res: object

    @property
    def n(self):
        return len(self.data)

    @property
    def se(self):
        return pd.Series(np.sqrt(np.diag(self.cov)), index=self.params.index)

    def predict(self, df=None):
        X = self.spec.design(self.data if df is None else df)
        return LINKS[self.kind][0](X.values @ self.params.values)


def fit(df, y, spec, kind):
    d = df.dropna(subset=[y] + spec.columns)
    X = spec.design(d)
    if kind == "lpm":
        res = sm.OLS(d[y], X).fit(cov_type="HC1")
        return Fit(kind, spec, d, res.params, res.cov_params(), None, res)
    model = (sm.Probit if kind == "probit" else sm.Logit)(d[y], X)
    oim = model.fit(disp=0, method="newton", tol=1e-12, maxiter=100)
    rob = model.fit(disp=0, method="newton", tol=1e-12, maxiter=100, cov_type="HC0")
    n = len(d)
    return Fit(kind, spec, d, oim.params, rob.cov_params() * n / (n - 1), oim.cov_params(), oim)


def ame(f, var, how="discrete", cov=None, h=1e-5):
    """Average marginal effect of `var` with a delta-method SE. Works through interactions, since it changes the
    variable in the data and rebuilds the design."""
    cdf, pdf = LINKS[f.kind]
    b = f.params.values
    d0, d1 = f.data.copy(), f.data.copy()
    if how == "discrete":
        d0[var], d1[var], step = 0.0, 1.0, 1.0
    else:
        d0[var], d1[var], step = d0[var] - h, d1[var] + h, 2 * h
    X0, X1 = f.spec.design(d0).values, f.spec.design(d1).values
    z0, z1 = X0 @ b, X1 @ b
    est = np.mean(cdf(z1) - cdf(z0)) / step
    grad = (pdf(z1)[:, None] * X1 - pdf(z0)[:, None] * X0).mean(axis=0) / step
    V = (f.cov if cov is None else cov).values
    return float(est), float(np.sqrt(grad @ V @ grad))


def adjusted_predictions(f, at_var, values, by_var, by_values=(0.0, 1.0), cov=None):
    """Average predicted probability with `at_var` set to each value and `by_var` set to each level, over the
    whole estimation sample (Stata: margins, at(at_var=(...)) over/at by_var). Delta-method SEs."""
    cdf, pdf = LINKS[f.kind]
    b, V = f.params.values, (f.cov if cov is None else cov).values
    out = []
    for v in values:
        row = {"x": float(v)}
        grads = {}
        for g in by_values:
            d = f.data.copy()
            d[at_var], d[by_var] = v, g
            X = f.spec.design(d).values
            z = X @ b
            p = float(np.mean(cdf(z)))
            grad = (pdf(z)[:, None] * X).mean(axis=0)
            grads[g] = grad
            row[f"p{int(g)}"], row[f"se{int(g)}"] = p, float(np.sqrt(grad @ V @ grad))
        gd = grads[by_values[1]] - grads[by_values[0]]
        row["gap"] = row[f"p{int(by_values[1])}"] - row[f"p{int(by_values[0])}"]
        row["gap_se"] = float(np.sqrt(gd @ V @ gd))
        out.append(row)
    return out


def coef_table(f, names=None):
    names = names or [c for c in f.params.index]
    rows = []
    for c in names:
        b, s = float(f.params[c]), float(f.se[c])
        row = {"term": c, "coef": b, "se": s, "z": b / s, "p": float(2 * stats.norm.sf(abs(b / s)))}
        if f.cov_oim is not None:
            row["se_oim"] = float(np.sqrt(f.cov_oim.loc[c, c]))
        rows.append(row)
    return rows


def wald(f, terms):
    """Joint Wald test that the listed coefficients are all zero (robust covariance). Returns chi2, df, p."""
    b = f.params[terms].values
    V = f.cov.loc[terms, terms].values
    chi2 = float(b @ np.linalg.solve(V, b))
    return chi2, len(terms), float(stats.chi2.sf(chi2, len(terms)))


# ---------------------------------------------------------------- problem set 6, reproduced

def ps6(df):
    spec = Spec(PS6)
    lpm, probit, logit = (fit(df, "approve", spec, k) for k in ("lpm", "probit", "logit"))
    phat = lpm.predict()
    out = {
        "n": lpm.n,
        "lpm": {"coefs": coef_table(lpm), "r2": float(lpm.res.rsquared), "f": float(lpm.res.fvalue),
                "phat_min": float(phat.min()), "phat_max": float(phat.max()), "phat_mean": float(phat.mean()),
                "n_out_of_range": int(((phat < 0) | (phat > 1)).sum()), "n_above_1": int((phat > 1).sum())},
    }
    for name, f in (("probit", probit), ("logit", logit)):
        llnull = float(f.res.llnull)
        out[name] = {
            "coefs": coef_table(f), "ll": float(f.res.llf), "ll0": llnull, "pseudo_r2": float(1 - f.res.llf / llnull),
            "lr_chi2": float(2 * (f.res.llf - llnull)),
            "ame_derivative": {v: dict(zip(("est", "se"), ame(f, v, "derivative", cov=f.cov_oim))) for v in PS6},
            "ame_derivative_robust": {v: dict(zip(("est", "se"), ame(f, v, "derivative"))) for v in PS6},
            "ame_discrete": {v: dict(zip(("est", "se"), ame(f, v, "discrete")))
                             for v in ("white", "male", "married", "pubrec")},
        }
    return out


# ---------------------------------------------------------------- extensions

def common_sample(df):
    cols = ["approve"] + LADDER[-1][2] + ["white"]
    return df.dropna(subset=cols)


def ladder(df):
    """How the white/non-white gap changes as controls are added, all on one common sample."""
    d = common_sample(df)
    rows = []
    for key, label, xs in LADDER:
        spec = Spec(["white"] + xs)
        lpm, probit, logit = (fit(d, "approve", spec, k) for k in ("lpm", "probit", "logit"))
        row = {"key": key, "label": label, "n": lpm.n, "k": len(xs),
               "lpm": {"est": float(lpm.params["white"]), "se": float(lpm.se["white"])}}
        for name, f in (("probit", probit), ("logit", logit)):
            est, se = ame(f, "white", "discrete")
            row[name] = {"est": est, "se": se, "coef": float(f.params["white"])}
        # Black and Hispanic applicants separately, each against white applicants
        sep = fit(d, "approve", Spec(["black", "hispan"] + xs), "probit")
        row["black"] = dict(zip(("est", "se"), ame(sep, "black", "discrete")))
        row["hispan"] = dict(zip(("est", "se"), ame(sep, "hispan", "discrete")))
        rows.append(row)
    return {"n": len(d), "rows": rows}


def interactions(df):
    """Do debt ratios and loan-to-value 'count' differently by race? LPM with white x (hrat, obrat, loanprc),
    plus a probit curve of approval against obrat for white and non-white applicants."""
    d = common_sample(df)
    xs = ["white"] + PS6[1:] + CREDIT
    terms = [("white", "hrat"), ("white", "obrat"), ("white", "loanprc")]
    lpm = fit(d, "approve", Spec(xs, terms), "lpm")
    names = ["white"] + [f"{a}:{b}" for a, b in terms]
    chi2, k, p = wald(lpm, [f"{a}:{b}" for a, b in terms])
    probit = fit(d, "approve", Spec(xs, [("white", "obrat")]), "probit")
    chi2p, _, pp = wald(probit, ["white:obrat"])
    curve = adjusted_predictions(probit, "obrat", list(range(15, 61, 5)), "white")
    return {"n": lpm.n, "lpm": coef_table(lpm, names), "lpm_wald": {"chi2": chi2, "df": k, "p": p},
            "probit_wald": {"chi2": chi2p, "df": 1, "p": pp}, "probit_coef": coef_table(probit, ["white", "obrat", "white:obrat"]),
            "curve": curve, "obrat_pctiles": {q: float(d.obrat.quantile(q / 100)) for q in (5, 25, 50, 75, 95)}}


# ---------------------------------------------------------------- Oaxaca-Blinder

def _ols(y, X):
    return np.linalg.lstsq(X, y, rcond=None)[0]


def oaxaca_point(y, X, g, names):
    """Two-fold decomposition of mean(y | g=1) - mean(y | g=0), linear model.

    Reference coefficients: the pooled regression *with* a group indicator (Jann 2008; Fortin 2008), which keeps
    the group difference from leaking into the reference slopes. Also reports the two classic single-group
    references, since the split depends on that choice.
    """
    A, B = g == 1, g == 0
    xa, xb = X[A].mean(axis=0), X[B].mean(axis=0)
    gap = y[A].mean() - y[B].mean()
    ba, bb = _ols(y[A], X[A]), _ols(y[B], X[B])
    pooled = _ols(y, np.column_stack([X, g]))[:-1]
    out = {"gap": gap, "mean_a": y[A].mean(), "mean_b": y[B].mean()}
    for key, beta in (("pooled", pooled), ("white_coefs", ba), ("nonwhite_coefs", bb)):
        contrib = (xa - xb) * beta
        explained = contrib.sum()
        out[key] = {"explained": explained, "unexplained": gap - explained,
                    "detail": dict(zip(names, contrib))}
    return out


def oaxaca(df, xs=None, reps=500, seed=20261007):
    """Decompose the white / Black-or-Hispanic approval gap, with bootstrap SEs (resampling within each group)."""
    xs = xs or PS6[1:] + CREDIT
    d = df.dropna(subset=["approve", "white"] + xs)
    y, g = d.approve.values, d.white.values
    X = np.column_stack([np.ones(len(d)), d[xs].values])
    names = ["const"] + xs
    point = oaxaca_point(y, X, g, names)
    rng = np.random.default_rng(seed)
    ia, ib = np.flatnonzero(g == 1), np.flatnonzero(g == 0)
    draws = {k: [] for k in ("gap", "pooled", "white_coefs", "nonwhite_coefs")}
    detail = []
    for _ in range(reps):
        idx = np.concatenate([rng.choice(ia, len(ia)), rng.choice(ib, len(ib))])
        r = oaxaca_point(y[idx], X[idx], g[idx], names)
        draws["gap"].append(r["gap"])
        for k in ("pooled", "white_coefs", "nonwhite_coefs"):
            draws[k].append(r[k]["explained"])
        detail.append([r["pooled"]["detail"][n] for n in names])
    se = lambda a: float(np.std(a, ddof=1))
    out = {"n": len(d), "n_white": int(len(ia)), "n_nonwhite": int(len(ib)), "reps": reps, "variables": xs,
           "gap": float(point["gap"]), "gap_se": se(draws["gap"]),
           "mean_white": float(point["mean_a"]), "mean_nonwhite": float(point["mean_b"])}
    for k in ("pooled", "white_coefs", "nonwhite_coefs"):
        expl = np.array(draws[k])
        unexp = np.array(draws["gap"]) - expl
        out[k] = {"explained": float(point[k]["explained"]), "explained_se": se(expl),
                  "unexplained": float(point[k]["unexplained"]), "unexplained_se": se(unexp),
                  "explained_ci": [float(np.percentile(expl, 2.5)), float(np.percentile(expl, 97.5))],
                  "unexplained_ci": [float(np.percentile(unexp, 2.5)), float(np.percentile(unexp, 97.5))]}
    D = np.array(detail)
    out["detail"] = [{"var": n, "contrib": float(point["pooled"]["detail"][n]), "se": float(D[:, j].std(ddof=1)),
                      "mean_white": float(d.loc[d.white == 1, n].mean()) if n != "const" else 1.0,
                      "mean_nonwhite": float(d.loc[d.white == 0, n].mean()) if n != "const" else 1.0}
                     for j, n in enumerate(names) if n != "const"]
    out["probit_check"] = oaxaca_probit(d, xs)
    return out


def oaxaca_probit(d, xs):
    """A nonlinear check: the same pooled-reference split using a probit, explained = mean P(X_white b*) -
    mean P(X_nonwhite b*), with b* from the pooled probit that includes the group indicator."""
    spec = Spec(xs + ["white"])
    f = fit(d, "approve", spec, "probit")
    A, B = d[d.white == 1].copy(), d[d.white == 0].copy()
    # Evaluate both groups at the same group indicator, so only the X distribution differs.
    explained = []
    for w in (0.0, 1.0):
        A["white"], B["white"] = w, w
        explained.append(float(f.predict(A).mean() - f.predict(B).mean()))
    gap = float(d.loc[d.white == 1, "approve"].mean() - d.loc[d.white == 0, "approve"].mean())
    e = float(np.mean(explained))
    return {"gap": gap, "explained": e, "unexplained": gap - e, "explained_range": explained}
