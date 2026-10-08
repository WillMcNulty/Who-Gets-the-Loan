"""Compare this project's problem-set-6 estimates with the course's Stata output, which is private course material.

Run locally only:
    python scripts/check_ps6_private.py [path-to-problem-set-6-solutions.md]

The default path is the owner's private course archive. The file is read in place and never copied: this script
prints only which numbers matched, never the solution text. Without the file it exits quietly (CI never has it).
"""

import os
import re
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import data, econ  # noqa: E402

DEFAULT = Path(os.environ.get("PS6_SOLUTIONS", Path(__file__).resolve().parents[2] / "uva-knowledge" / "courses" /
               "econ-3720-2026sp" / "material" / "problem-sets-and-solutions" / "problem-set-6-solutions.md"))
TERMS = ["white", "hrat", "obrat", "loanprc", "unem", "male", "married", "dep", "pubrec", "_cons"]
NUM = r"-?\d*\.\d+|-?\d+"
OFFSET = float(os.environ.get("PS6_SELFTEST_OFFSET", 0))  # set nonzero to confirm the check can fail


def blocks(text):
    """The Stata output that follows each command in problem 4, as {command: text}."""
    start, end = text.index("### 4)"), text.index("### 5)")
    part = text[start:end]
    out = {}
    for cmd in ("regress approve", "probit approve", "logit approve", "margins, dydx(*)"):
        i = part.index(". " + cmd)
        nxt = [part.find(". " + c, i + 5) for c in ("regress", "probit", "logit", "margins", "predict", "summarize")]
        j = min([k for k in nxt if k > i] + [len(part)])
        out[cmd] = part[i:j]
    return out


def table(block):
    """Rows of a Stata coefficient table: term -> (coef, se)."""
    rows = {}
    for t in TERMS:
        m = re.search(r"`" + re.escape(t) + r"`<br>\*\*`(" + NUM + r")`?\*\*\|?\*\*`?\s*(" + NUM + r")", block)
        if not m:
            m = re.search(r"`" + re.escape(t) + r"`<br>\*\*`(" + NUM + r")\s+(" + NUM + r")", block)
        if m:
            rows[t] = (m.group(1), m.group(2))
    return rows


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not path.exists():
        print(f"Private solutions not found at {path}; nothing to check.")
        return 0
    warnings.simplefilter("ignore")
    text = path.read_text(encoding="utf-8")
    B = blocks(text)
    r = econ.ps6(econ.prepare(data.load()))
    ours = {
        "regress approve": {c["term"].replace("const", "_cons"): (c["coef"], c["se"]) for c in r["lpm"]["coefs"]},
        "probit approve": {c["term"].replace("const", "_cons"): (c["coef"], c["se_oim"]) for c in r["probit"]["coefs"]},
        "logit approve": {c["term"].replace("const", "_cons"): (c["coef"], c["se_oim"]) for c in r["logit"]["coefs"]},
        "margins, dydx(*)": {v: (e["est"], e["se"]) for v, e in r["probit"]["ame_derivative"].items()},
    }
    checked = failed = 0
    for cmd, block in B.items():
        theirs = table(block)
        for term, (b, se) in theirs.items():
            mb, mse = ours[cmd][term]
            for label, a, printed in (("coef", mb, b), ("se", mse, se)):
                checked += 1
                # agree to within one unit in the last place Stata printed
                decimals = len(printed.split(".")[1]) if "." in printed else 0
                if abs(a + OFFSET - float(printed)) > 10 ** -decimals:
                    failed += 1
                    print(f"MISMATCH {cmd} {term} {label}: ours {a:.7g}")
        missing = set(TERMS if cmd != "margins, dydx(*)" else TERMS[:-1]) - set(theirs)
        if missing:
            print(f"(could not parse {sorted(missing)} in the {cmd!r} output)")
    for name, want in (("probit", r["probit"]["ll"]), ("logit", r["logit"]["ll"])):
        m = re.search(r"Log likelihood = (-?\d+\.\d+)\s+Pseudo", B[f"{name} approve"])
        checked += 1
        if not m or abs(float(m.group(1)) - want) > 1e-5:
            failed += 1
            print(f"MISMATCH {name} log likelihood: ours {want:.5f}")
    n = re.search(r"Number of obs\s*=\s*\D*([\d,]+)", B["regress approve"])
    checked += 1
    if not n or int(n.group(1).replace(",", "")) != r["n"]:
        failed += 1
        print("MISMATCH number of observations")
    print(f"{checked - failed} of {checked} printed numbers match (coefficients, SEs, AMEs, log likelihoods, N).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
