"""Load the 1990 Boston HMDA sample (Wooldridge's LOANAPP) and check it against the published variable list.

The source is the `wooldridge` Python package (Wooldridge, *Introductory Econometrics: A Modern Approach*, 7th
ed., data set LOANAPP). The package ships 59 of the 62 variables in the textbook's Stata file; the other three
(`race`, `gender`, `obwhte`) are exact functions of variables it does ship, so they are rebuilt here. All 62 were
compared once against the Stata file Boston College hosts for the textbook (fmwww.bc.edu/ec-p/data/wooldridge/)
and matched exactly.

Stata stores every LOANAPP column as a 4-byte float. The package widens some of them to 8-byte floats, which
moves values like `hrat` in the 7th digit, so every column is rounded through float32 first. That is what makes
the regressions here agree with Stata to the last printed digit.
"""

import hashlib

import numpy as np
import pandas as pd

N_ROWS = 1989
N_VARS = 62

# Wooldridge's variable list (loanapp.des), in the Stata file's column order.
LABELS = {
    "occ": "occupancy", "loanamt": "loan amount, $1000s", "action": "type of action taken",
    "msa": "MSA number of property", "suffolk": "=1 if property in Suffolk County",
    "race": "race of applicant (3 Black, 4 Hispanic, 5 white)", "gender": "gender of applicant (1 male, 2 female, 3 not recorded)",
    "appinc": "applicant income, $1000s", "typur": "type of purchaser of loan", "unit": "number of units in property",
    "married": "=1 if applicant married", "dep": "number of dependents", "emp": "years employed in line of work",
    "yjob": "years at this job", "self": "=1 if self-employed", "atotinc": "total monthly income",
    "cototinc": "co-applicant total monthly income", "hexp": "proposed housing expense", "price": "purchase price",
    "other": "other financing, $1000s", "liq": "liquid assets", "rep": "number of credit reports",
    "gdlin": "credit history meets guidelines", "lines": "number of credit lines on reports",
    "mortg": "credit history on mortgage payments", "cons": "credit history on consumer debts",
    "pubrec": "=1 if public record of bad credit (filed bankruptcy)", "hrat": "housing expense, % of total income",
    "obrat": "other obligations, % of total income", "fixadj": "fixed or adjustable rate", "term": "term of loan in months",
    "apr": "appraised value", "prop": "type of property", "inss": "PMI sought", "inson": "PMI approved",
    "gift": "gift as down payment", "cosign": "=1 if there is a cosigner", "unver": "unverifiable information",
    "review": "number of times reviewed", "netw": "net worth", "unem": "unemployment rate by industry",
    "min30": "=1 if minority population > 30% (census tract)", "bd": "=1 if boarded-up value > MSA median",
    "mi": "=1 if tract income > MSA median", "old": "=1 if applicant age > MSA median",
    "vr": "=1 if tract vacancy rate > MSA median", "sch": "=1 if > 12 years of schooling", "black": "=1 if applicant Black",
    "hispan": "=1 if applicant Hispanic", "male": "=1 if applicant male", "reject": "=1 if action == 3",
    "approve": "=1 if action == 1 or 2", "mortno": "no mortgage history", "mortperf": "no late mortgage payments",
    "mortlat1": "one or two late mortgage payments", "mortlat2": "more than two late mortgage payments",
    "chist": "=0 if accounts delinquent >= 60 days", "multi": "=1 if two or more units", "loanprc": "loan amount / price",
    "thick": "=1 if rep > 2", "white": "=1 if applicant white", "obwhte": "obrat x white",
}

# Non-missing counts from the course's variable list (and Wooldridge's Stata file).
NON_MISSING = {"unit": 1985, "married": 1986, "dep": 1986, "rep": 1980, "min30": 1806, "male": 1974,
               "multi": 1985, "thick": 1980}

# Means of the Stata file, to 4 significant digits; the loader must reproduce them.
MEANS = {"approve": 0.877325, "white": 0.845148, "black": 0.0990447, "hispan": 0.0558069, "hrat": 24.7909,
         "obrat": 32.389, "loanprc": 0.77064, "unem": 3.8823, "male": 0.81307, "married": 0.65861, "dep": 0.770896,
         "pubrec": 0.0688788, "chist": 0.837607, "loanamt": 143.245, "appinc": 84.6777, "race": 4.7461,
         "gender": 1.2006}

GROUPS = {"white": "White", "black": "Black", "hispan": "Hispanic"}


def load_raw():
    """The package's LOANAPP, untouched (59 columns)."""
    import wooldridge

    return wooldridge.data("loanapp")


def rebuild(raw):
    """Rebuild the textbook's 62-column file from the package's 59 columns."""
    df = raw.copy()
    df["race"] = np.select([df.black == 1, df.hispan == 1, df.white == 1], [3.0, 4.0, 5.0], np.nan)
    df["gender"] = np.where(df.male.isna(), 3.0, np.where(df.male == 1, 1.0, 2.0))
    df["obwhte"] = df.obrat * df.white
    order = list(LABELS)
    df = df[order]
    # Stata's storage type, then double for the arithmetic, exactly as Stata computes.
    return df.astype("float32").astype("float64")


def load():
    """The checked 62-variable LOANAPP, with a `group` column (White / Black / Hispanic)."""
    df = rebuild(load_raw())
    check(df)
    df["group"] = np.select([df.white == 1, df.black == 1], ["White", "Black"], "Hispanic")
    return df


def check(df):
    """Fail loudly if the data differ from the published variable list."""
    problems = []
    if df.shape != (N_ROWS, N_VARS):
        problems.append(f"shape {df.shape}, expected ({N_ROWS}, {N_VARS})")
    if list(df.columns[:N_VARS]) != list(LABELS):
        problems.append("column names or order differ from the variable list")
    for col in LABELS:
        want = NON_MISSING.get(col, N_ROWS)
        got = int(df[col].notna().sum())
        if got != want:
            problems.append(f"{col}: {got} non-missing, expected {want}")
    for col, mean in MEANS.items():
        if not np.isclose(df[col].mean(), mean, rtol=1e-4):
            problems.append(f"{col}: mean {df[col].mean():.6g}, expected {mean}")
    groups = df.white + df.black + df.hispan
    if not (groups == 1).all():
        problems.append("every applicant should be exactly one of white, Black, Hispanic")
    if not ((df.approve == 1) == df.action.isin([1, 2])).all():
        problems.append("approve should be action 1 or 2")
    if not (df.approve + df.reject == 1).all():
        problems.append("approve and reject should be complements")
    if problems:
        raise ValueError("LOANAPP failed its checks:\n  " + "\n  ".join(problems))


def fingerprint(df):
    """A SHA-256 of the 62 columns' values, stable across platforms (rounded to float32 text)."""
    text = df[list(LABELS)].to_csv(index=False, float_format="%.7g", lineterminator="\n")
    return hashlib.sha256(text.encode()).hexdigest()


def summary(df):
    """Counts and approval rates by group, plus the sample's basic shape."""
    rows = []
    for name in ["White", "Black", "Hispanic"]:
        g = df[df.group == name]
        rows.append({"group": name, "n": int(len(g)), "approved": int(g.approve.sum()),
                     "rate": float(g.approve.mean())})
    nonwhite = df[df.white == 0]
    rows.append({"group": "Black or Hispanic", "n": int(len(nonwhite)), "approved": int(nonwhite.approve.sum()),
                 "rate": float(nonwhite.approve.mean())})
    rows.append({"group": "All", "n": int(len(df)), "approved": int(df.approve.sum()), "rate": float(df.approve.mean())})
    return rows
