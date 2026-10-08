import numpy as np
import pytest

from audit import data


@pytest.fixture(scope="module")
def df():
    return data.load()


def test_matches_the_published_variable_list(df):
    assert df.shape == (1989, 63)  # 62 variables + the derived group label
    assert list(df.columns[:62]) == list(data.LABELS)
    assert df.male.notna().sum() == 1974 and df.min30.notna().sum() == 1806


def test_rebuilt_columns_are_consistent(df):
    assert (df.race.map({3: "Black", 4: "Hispanic", 5: "White"}) == df.group).all()
    assert ((df.gender == 3) == df.male.isna()).all()
    assert np.allclose(df.obwhte, df.obrat * df.white)
    assert df.group.value_counts().to_dict() == {"White": 1681, "Black": 197, "Hispanic": 111}


def test_stata_storage_precision(df):
    # every value survives a round trip through float32, as in the textbook's Stata file
    num = df[list(data.LABELS)]
    assert np.array_equal(num.astype("float32").astype("float64").fillna(-9).values, num.fillna(-9).values)


def test_check_rejects_altered_data(df):
    bad = df[list(data.LABELS)].copy()
    bad.loc[0, "approve"] = 1 - bad.loc[0, "approve"]
    with pytest.raises(ValueError):
        data.check(bad)
    with pytest.raises(ValueError):
        data.check(bad.iloc[:-1])


def test_summary(df):
    s = {r["group"]: r for r in data.summary(df)}
    assert s["All"]["approved"] == 1745
    assert s["White"]["approved"] + s["Black or Hispanic"]["approved"] == 1745
    assert s["White"]["rate"] == pytest.approx(1527 / 1681)
