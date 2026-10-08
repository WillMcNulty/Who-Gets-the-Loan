"""Run the whole audit and write the report's data: site/data.js (and results/results.json, the same numbers).

    python build.py            # everything (about a minute)
    python build.py --check    # build into memory and compare with the committed site/data.js (used by CI)

The build refuses to write if the problem-set models stop reproducing (see EXPECTED) or the data fail their checks.
"""

import hashlib
import json
import math
import re
import sys
import warnings
from pathlib import Path

import numpy as np

from audit import data, econ, ml

ROOT = Path(__file__).parent
DATA_JS = ROOT / "site" / "data.js"
RESULTS = ROOT / "results" / "results.json"
INDEX = ROOT / "site" / "index.html"

# Problem set 6, reproduced. These are this project's own estimates on the public data; they agree with Stata's
# output for the same commands to every printed digit (checked locally by scripts/check_ps6_private.py).
EXPECTED = {
    "n": 1971,
    "lpm_white": 0.1460959, "lpm_pubrec": -0.2911969, "lpm_white_se": 0.0263961,
    "probit_white": 0.596131, "probit_pubrec": -0.9810615, "probit_ll": -622.73366,
    "logit_white": 1.076127, "logit_pubrec": -1.696559, "logit_ll": -622.82193,
    "ame_white": 0.1026927, "ame_pubrec": -0.1690028, "ame_white_se": 0.0159841,
}


def check_ps6(r):
    got = {
        "n": r["n"],
        "lpm_white": coef(r["lpm"], "white"), "lpm_pubrec": coef(r["lpm"], "pubrec"),
        "lpm_white_se": coef(r["lpm"], "white", "se"),
        "probit_white": coef(r["probit"], "white"), "probit_pubrec": coef(r["probit"], "pubrec"), "probit_ll": r["probit"]["ll"],
        "logit_white": coef(r["logit"], "white"), "logit_pubrec": coef(r["logit"], "pubrec"), "logit_ll": r["logit"]["ll"],
        "ame_white": r["probit"]["ame_derivative"]["white"]["est"], "ame_pubrec": r["probit"]["ame_derivative"]["pubrec"]["est"],
        "ame_white_se": r["probit"]["ame_derivative"]["white"]["se"],
    }
    bad = [f"{k}: got {got[k]:.7g}, expected {v}" for k, v in EXPECTED.items() if not math.isclose(got[k], v, abs_tol=6e-7 if abs(v) < 10 else 6e-5)]
    if bad:
        raise SystemExit("Problem set 6 no longer reproduces:\n  " + "\n  ".join(bad))


def coef(block, term, key="coef"):
    return next(c[key] for c in block["coefs"] if c["term"] == term)


def tidy(x, sig=6):
    """Round floats to `sig` significant digits so the committed file is stable across platforms."""
    if isinstance(x, dict):
        return {str(k): tidy(v, sig) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [tidy(v, sig) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if math.isnan(x) or math.isinf(x):
            return None
        return float(f"{x:.{sig}g}")
    return x


def build():
    warnings.simplefilter("ignore")
    raw = data.load()
    df = econ.prepare(raw)
    out = {"meta": {"source": "Wooldridge LOANAPP (1990 Boston HMDA sample), via the `wooldridge` Python package",
                    "rows": int(len(raw)), "variables": int(data.N_VARS), "fingerprint": data.fingerprint(raw)},
           "summary": data.summary(raw)}

    r = econ.ps6(df)
    check_ps6(r)
    out["ps6"] = r
    out["ladder"] = econ.ladder(df)
    out["interactions"] = econ.interactions(df)
    out["oaxaca"] = econ.oaxaca(df)
    # the decomposition again with the lender's-file variables, to show how much the answer moves
    out["oaxaca_file"] = {k: v for k, v in econ.oaxaca(df, econ.PS6[1:] + econ.CREDIT + econ.FILE, reps=200).items()
                          if k in ("n", "gap", "pooled", "white_coefs", "nonwhite_coefs", "probit_check")}

    d = ml.frame(raw)
    models, scores = ml.run_models(d)
    out["ml"] = {"n": int(len(d)), "groups": d.group.value_counts().to_dict(), "features": ml.FEATURES,
                 "labels": ml.LABELS, "lender": ml.LENDER, "place": ml.PLACE, "folds": ml.FOLDS,
                 "approval_rate": float(d.approve.mean()), "models": models}
    out["proxies"] = ml.proxies(d)
    out["mitigation"] = ml.mitigation(d, scores["logit"])
    out["label_bias"] = ml.label_bias(d, scores["logit"])
    out = tidy(out)
    sanity(out)
    return out


def sanity(o):
    """Facts the report's text states; if any stops holding, the text needs rewriting, so stop."""
    s = {row["group"]: row for row in o["summary"]}
    assert (s["White"]["n"], s["Black"]["n"], s["Hispanic"]["n"]) == (1681, 197, 111)
    gap = s["White"]["rate"] - s["Black or Hispanic"]["rate"]
    assert 0.19 < gap < 0.21, gap
    lad = {row["key"]: row for row in o["ladder"]["rows"]}
    assert lad["raw"]["lpm"]["est"] > lad["ps6"]["lpm"]["est"] > lad["credit"]["lpm"]["est"] > lad["file"]["lpm"]["est"] > 0
    pooled = o["oaxaca"]["pooled"]
    assert 0 < pooled["explained"] < pooled["unexplained"], "text says most of the gap is unexplained"
    blind = o["ml"]["models"]["logit"]["gaps"]
    assert blind["d_selection"] < -0.15, "text says the race-blind model keeps most of the gap"
    assert o["proxies"]["sets"][0]["logit"] > 0.65


def write(out):
    text = json.dumps(out, indent=1, ensure_ascii=False)
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(text + "\n", encoding="utf-8")
    js = "// Generated by build.py from the audit package. Do not edit by hand.\nwindow.RESULTS = " + text + ";\n"
    DATA_JS.write_text(js, encoding="utf-8")
    stamp_scripts()


def stamp_scripts():
    """Add a content hash to each local script tag so a browser never mixes old and new files."""
    if not INDEX.exists():
        return
    html = INDEX.read_text(encoding="utf-8")

    def repl(m):
        name = m.group(1)
        h = hashlib.sha256((ROOT / "site" / name).read_bytes()).hexdigest()[:8]
        return f'src="{name}?v={h}"'
    new = re.sub(r'src="([a-z]+\.js)(?:\?v=[0-9a-f]+)?"', repl, html)
    if new != html:
        INDEX.write_text(new, encoding="utf-8")


def compare(a, b, path="", tol=2e-3):
    """Numbers agree to a relative/absolute tolerance; everything else exactly."""
    diffs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diffs.append(f"{path}/{k}: only in one")
            else:
                diffs += compare(a[k], b[k], f"{path}/{k}", tol)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: length {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diffs += compare(x, y, f"{path}[{i}]", tol)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if "/gbm/" in path or "/gbm" == path[-4:]:
            # Gradient-boosted trees differ slightly between platforms (floating-point ties between candidate
            # splits); on Linux CI a couple of applicants land in a neighboring calibration bin. Allow that much.
            ok = abs(a - b) <= 3 if isinstance(a, int) and isinstance(b, int) else math.isclose(a, b, rel_tol=0.01, abs_tol=0.01)
            if not ok:
                diffs.append(f"{path}: {a} vs {b}")
        elif not math.isclose(a, b, rel_tol=tol, abs_tol=tol):
            diffs.append(f"{path}: {a} vs {b}")
    elif a != b:
        diffs.append(f"{path}: {a!r} vs {b!r}")
    return diffs


def committed():
    text = DATA_JS.read_text(encoding="utf-8")
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


if __name__ == "__main__":
    out = build()
    if "--check" in sys.argv:
        diffs = compare(committed(), json.loads(json.dumps(out)))
        if diffs:
            print(f"site/data.js differs from a fresh build in {len(diffs)} places:")
            print("\n".join(diffs[:40]))
            sys.exit(1)
        print("site/data.js matches a fresh build.")
    else:
        write(out)
        o = out
        s = {row["group"]: row for row in o["summary"]}
        print(f"Approval: white {s['White']['rate']:.1%}, Black {s['Black']['rate']:.1%}, Hispanic {s['Hispanic']['rate']:.1%}")
        print(f"PS6 LPM white {coef(o['ps6']['lpm'], 'white'):.4f}; probit AME (discrete) {o['ps6']['probit']['ame_discrete']['white']['est']:.4f}")
        p = o["oaxaca"]["pooled"]
        print(f"Oaxaca: gap {o['oaxaca']['gap']:.4f} = explained {p['explained']:.4f} + unexplained {p['unexplained']:.4f}")
        g = o["ml"]["models"]["logit"]["gaps"]
        print(f"Race-blind logit: selection gap {g['d_selection']:.4f}, TPR gap {g['d_tpr']:.4f}, FPR gap {g['d_fpr']:.4f}")
        print(f"Wrote {DATA_JS.relative_to(ROOT)} and {RESULTS.relative_to(ROOT)}")
