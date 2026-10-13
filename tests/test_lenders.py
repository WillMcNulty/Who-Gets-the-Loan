"""Lender names and the lender section of the Virginia results."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from hmda import lenders

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("raw,shown", [
    ("C&F MORTGAGE CORP", "C&F Mortgage Corp."),
    ("JPMORGAN CHASE BANK NA", "JPMorgan Chase Bank N.A."),
    ("BRANCH BANKING AND TRUST CO", "Branch Banking and Trust Co."),
    ("WELLS   FARGO BANK, N.A.", "Wells Fargo Bank, N.A."),
    ("Movement Mortgage, LLC", "Movement Mortgage, LLC"),  # mixed case is left as reported
    ("", ""),
])
def test_tidy_name(raw, shown):
    assert lenders.tidy_name(raw) == shown


def test_historic_ts_rejoins_names_split_by_commas(tmp_path, monkeypatch):
    header = "Activity Year, Respondent ID, Agency Code, Federal Tax ID, Respondent Name, Respondent City, Parent Name, Parent City\n"
    rows = ["2012,0000000047,1,35-0704860,FIRST FINANCIAL BANK NA,TERRE HAUTE,FIRST FINANCIAL CORP,TERRE HAUTE\n",
            "2012,0000012345,9,11-1111111,ACME MORTGAGE, INC,RICHMOND,ACME HOLDINGS,RICHMOND\n"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hmda_2012_transmittal_sheet.csv", header + "".join(rows))
    (tmp_path / "ts_2012.zip").write_bytes(buf.getvalue())
    monkeypatch.setattr(lenders, "RAW", tmp_path)
    got = lenders.read_historic_ts(2012)
    assert got[0] == (2012, "1-0000000047", "FIRST FINANCIAL BANK NA", "FIRST FINANCIAL CORP")
    assert got[1] == (2012, "9-0000012345", "ACME MORTGAGE, INC", "ACME HOLDINGS")


@pytest.fixture(scope="module")
def L():
    t = (ROOT / "site" / "virginia" / "data.js").read_text(encoding="utf-8")
    return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))["lenders"]


def test_lender_tables(L):
    assert set(L) == {"2004-2011", "2012-2017", "2018-2025"}
    for era, v in L.items():
        apps = [r["apps"] for r in v["rows"]]
        assert apps == sorted(apps, reverse=True) and len(apps) == lenders.TOP
        assert 0 < v["top_share"] < 1 and abs(sum(r["share"] for r in v["rows"]) - v["top_share"]) < 1e-3
        for r in v["rows"]:
            assert r["name"] and not r["name"].startswith(("1-", "2-", "3-", "5-", "7-", "9-"))  # every top lender is named
            for g, gap in (r.get("gap_common") or {}).items():
                if gap is not None:
                    assert r["groups"][g]["n"] >= lenders.MIN_GROUP
        # the "where people apply" fact the page and the write-up state
        assert v["sorting"]["Black"] > v["sorting"]["White"]


def test_writeup_numbers_come_from_the_data():
    import writeup

    F = writeup.facts(writeup.load())
    text = writeup.summary(F)
    assert f"{F['records']:,}" in text
    assert writeup.pct(F["rate"][("2018-2025", "Black")]) in text
    assert len(writeup.slides(F)) == 8
