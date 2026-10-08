# Who Gets the Loan?

An independent audit of the 1990 Boston mortgage-lending data, done two ways: the econometrics of the racial
approval gap, and what a machine-learning model trained **without** race does by race. Not affiliated with or
endorsed by the University of Virginia, the Federal Reserve Bank of Boston, or any lender.

**Live report: https://willmcnulty.github.io/Who-Gets-the-Loan/**

**Status:** version 1 (the 1990 Boston data). Version 2 will use the CFPB's public HMDA data for Virginia over
several years.

## Read this first

Everything here is an **association after controlling for the variables recorded**. A gap that remains after
controls is consistent with discrimination, and also with things the loan files don't record or record with error.
Nothing here proves that any lender discriminated, or that none did. The outcome is the lender's 1990 decision, not
whether a borrower would have repaid, so a model trained on it learns to imitate those lenders. There are 308 Black or
Hispanic applicants, so the intervals are wide and are shown with every estimate.

## What it found

- **The raw gap is large.** Lenders approved 90.8% of white applicants and 70.8% of Black or Hispanic applicants
  (67.5% Black, 76.6% Hispanic): a 20.1-point gap.
- **The recorded finances and credit histories account for part of it, not most of it.** With the problem set's
  controls, being white is associated with a 14.7-point higher approval probability (linear model); with credit
  history added, 13.1 points (probit average marginal effect 10.6). An Oaxaca-Blinder decomposition attributes 7.6
  of the 20.5-point gap to differences in those variables and leaves 12.9 points (63%) unexplained. Depending on the
  reference coefficients, the unexplained part runs from 9.2 to 13.9 points.
- **What counts as a control decides the answer.** Adding the lender's own judgments ("meets credit guidelines",
  "unverifiable information") and finer credit detail cuts the remaining gap to 6.0 points (probit 4.9), still
  above zero. Those judgments were made by the lenders being studied, so this is a lower bound only if they were
  made without bias.
- **Dropping race from a model doesn't remove the gap.** A logistic regression trained without race, sex, marital
  status, age or neighborhood would approve 91.1% of white and 69.7% of Black or Hispanic applicants, a 21.4-point
  gap, about the lenders' own. Its 17 inputs predict race with an AUC of 0.71 (0.76 with neighborhood variables).
- **The same score didn't mean the same outcome.** In every score bin, Black and Hispanic applicants were approved
  less often than the race-blind model predicted, while white applicants were approved as often or more often.
- **Fixes trade agreement for parity, and the race-based ones raise legal problems.** Separate cutoffs by group close the gap at a cost of 1.8 points
  of agreement with the 1990 decisions. But using race at the decision is disparate treatment under U.S.
  fair-lending law, so it's shown only to size the trade-off. Reweighting the training data barely moves the gap.
- **The yardstick is part of the problem.** In a what-if where the unexplained gap came from biased decisions, the
  model's true-positive-rate gap is 16.8 points against the corrected labels but looks like 11.9 against the
  recorded ones. Metrics computed against biased decisions understate unfairness.

## What's in the report

`site/index.html`, a static page in the same design as the
[UVA Capital Plan Tracker](https://willmcnulty.github.io/UVA-Capital-Plan-Tracker/) (UVA Blue and Orange, light and
dark themes through the shared `theme.js`, keyed `wm-theme`):

- **Overview:** the limits, approval rates by group, the findings.
- **Econometrics:** the gap as controls are added (four specifications on one sample, with Black and Hispanic
  applicants also shown separately), a race × obligations-ratio interaction, and problem set 6 reproduced.
- **Decomposition:** Oaxaca-Blinder with three reference choices, a probit check, and each variable's contribution.
- **Race-blind models:** approval-rate, true-positive and false-positive gaps with bootstrap intervals, AUC and
  agreement by group, and calibration by group, for four model variants.
- **Proxies & trade-offs:** how well the inputs predict race, mitigation (reweighting, group cutoffs) and its
  frontier, and the label-bias what-if.
- **Method:** sources, conventions, checks and references.

Charts are hand-built SVG with hover and keyboard tooltips and a table view for each. Blue always means white
applicants and orange always means Black or Hispanic applicants. That pair passes the dataviz colorblind checks for
every pair, in both themes. Charts whose series aren't groups use neutral inks.

## How it works

```
wooldridge package (LOANAPP)  ->  audit/data.py     load, rebuild the 3 missing columns, check against the variable list
                                  audit/econ.py     LPM / probit / logit, AMEs, ladder, interactions, Oaxaca-Blinder
                                  audit/fairness.py hand-written group metrics (rates, AUC, calibration, reweighing)
                                  audit/ml.py       race-blind models, proxies, mitigation, label bias
                              ->  build.py          ->  site/data.js + results/results.json  ->  site/ (static page)
```

## The data

Wooldridge, *Introductory Econometrics: A Modern Approach* (7th ed., 2020), data set LOANAPP: 1,989 applications and
62 variables from the Federal Reserve Bank of Boston's 1990 study of Boston-area mortgage applications (Munnell,
Tootell, Browne and McEneaney, *American Economic Review* 86(1), 1996). It comes from the
[`wooldridge`](https://pypi.org/project/wooldridge/) Python package (T. Haruyama), which ships 59 of the 62 variables.
The other three are exact functions of the rest and are rebuilt: `race` from the race dummies, `gender` from `male`
(3 when missing), and `obwhte` = obrat × white. All 62 were compared once with the textbook's Stata file (as hosted by
Boston College for the textbook) and match exactly. Every build checks the shape, the non-missing counts and the means
against the published variable list, and records a fingerprint of the data. The data isn't redistributed here; it
loads from the package.

## Checking it

- **Problem set 6.** The course's starting models (ECON 3720) reproduce the course's Stata output to every printed
  digit: 81 of 81 coefficients, standard errors, average marginal effects, log likelihoods and the sample size.
  The solutions are private course material, so they're not in this repository. `scripts/check_ps6_private.py` reads
  them from the owner's private archive and prints only whether each number matched. In CI it finds no file and skips.
  One note from the comparison: the linear model's predictions fall outside [0, 1] for 151 of 1,971 applications.
  A Stata `count if phat > 1` reports 169, because Stata counts the 18 missing predictions as larger than any number.
- **`build.py`** refuses to write if the problem-set models stop reproducing, the data fail their checks, or a fact the
  page states stops holding.
- **Tests** (`pytest`): the loader and its checks; the models against statsmodels' own marginal effects and Stata's
  robust-SE scaling; the decomposition's identities on synthetic data; every fairness metric against hand-worked
  cases and scikit-learn's AUC; and the committed results against the story the page tells.
- **GitHub Actions** runs the tests, rebuilds everything and fails if the committed numbers differ from a fresh build
  (to 0.2%; the gradient-boosting results get 1% or 3 applicants, since boosted trees differ slightly between
  Windows and Linux),
  on every push, and only then deploys `site/` to GitHub Pages.

## Run it locally

Python 3.12:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # .venv/bin/python on macOS/Linux
.venv/Scripts/python build.py
.venv/Scripts/python -m pytest
.venv/Scripts/python -m http.server 8000 --directory site
```

Then open http://localhost:8000. `python build.py --check` compares a fresh build with the committed numbers.

## Limits

One metro area, one year, and a textbook subset of a study that drew every Black and Hispanic applicant's file but
only a sample of white applicants' files, so rates describe this sample, not all 1990 Boston applications. The
study's own conclusions were debated, including over data errors and omitted variables (Day and Liebowitz, *Economic
Inquiry* 1998; Ladd, *Journal of Economic Perspectives* 1998, reviews the exchange). There are no repayment outcomes,
only decisions. Group-specific cutoffs are shown to size a trade-off, not as a recommendation. Nothing here describes
any lender today.
