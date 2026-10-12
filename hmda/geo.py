"""One geography for every year: a crosswalk from each year's census tracts to 2020 tracts, and simplified map
shapes for Virginia's 2020 tracts and its counties and independent cities.

Crosswalk weights (the share of an old tract's applications assigned to each 2020 tract):
- 2000 -> 2010 tracts: the Census Bureau's 2010 tract relationship file, weighted by 2010 housing units in each
  piece (mortgages follow housing), falling back to land area where a piece has no housing.
- 2010 -> 2020 tracts: the 2020 tract relationship file, weighted by land area (the only measure it carries).
- 2000 -> 2020: the product of the two.
County boundaries come from the 2023 cartographic boundary file; the county field is already harmonized (Bedford
city is part of Bedford County throughout).
"""

import io
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data" / "geo"          # relationship files (committed, public domain)
SHAPES = ROOT / "data" / "raw" / "geo"  # boundary shapefiles (downloaded, not committed)
TRF_COLS = ["STATE00", "COUNTY00", "TRACT00", "GEOID00", "POP00", "HU00", "PART00", "AREA00", "AREALAND00",
            "STATE10", "COUNTY10", "TRACT10", "GEOID10", "POP10", "HU10", "PART10", "AREA10", "AREALAND10", "AREAPT",
            "AREALANDPT", "AREAPCT00PT", "AREALANDPCT00PT", "AREAPCT10PT", "AREALANDPCT10PT", "POP10PT", "POPPCT00",
            "POPPCT10", "HU10PT", "HUPCT00", "HUPCT10"]


def _shares(df, src, weight, fallback):
    w = df[weight].astype(float)
    tot = w.groupby(df[src]).transform("sum")
    fb = df[fallback].astype(float)
    fbtot = fb.groupby(df[src]).transform("sum")
    return np.where(tot > 0, w / tot.where(tot > 0, 1), fb / fbtot.where(fbtot > 0, 1))


@lru_cache
def xwalk_00_10():
    d = pd.read_csv(GEO / "va51trf.txt", header=None, names=TRF_COLS, dtype=str)
    d = d[d.STATE00 == "51"].copy()
    d["w"] = _shares(d, "GEOID00", "HU10PT", "AREALANDPT")
    return d[["GEOID00", "GEOID10", "w"]].rename(columns={"GEOID00": "src", "GEOID10": "dst"})


@lru_cache
def xwalk_10_20():
    d = pd.read_csv(GEO / "tab20_tract20_tract10_st51.txt", sep="|", dtype=str, encoding="utf-8-sig")
    d = d[d.GEOID_TRACT_10.str.startswith("51") & d.GEOID_TRACT_20.str.startswith("51")].copy()
    d["land"] = d.AREALAND_PART.astype(float)
    d["all"] = d.land + d.AREAWATER_PART.astype(float)
    d["w"] = _shares(d, "GEOID_TRACT_10", "land", "all")
    return d[["GEOID_TRACT_10", "GEOID_TRACT_20", "w"]].rename(columns={"GEOID_TRACT_10": "src", "GEOID_TRACT_20": "dst"})


@lru_cache
def xwalk(vintage):
    """DataFrame src (tract of that vintage) -> dst (2020 tract), weights summing to 1 per src."""
    if vintage == 2020:
        return None
    b = xwalk_10_20()
    if vintage == 2010:
        return b
    a = xwalk_00_10()
    m = a.merge(b, left_on="dst", right_on="src", suffixes=("_a", "_b"))
    m["w"] = m.w_a * m.w_b
    out = m.groupby(["src_a", "dst_b"], as_index=False).w.sum().rename(columns={"src_a": "src", "dst_b": "dst"})
    return out


def to_2020(counts, vintage):
    """Re-express tract-level counts (columns tract + numeric columns) on 2020 tracts."""
    if vintage == 2020:
        return counts.rename(columns={"tract": "tract20"}), 1.0
    x = xwalk(vintage)
    m = counts.merge(x, left_on="tract", right_on="src", how="left")
    matched = m.dst.notna()
    share = float(m.loc[matched, counts.columns.drop("tract")[0]].sum() / max(m[counts.columns.drop("tract")[0]].sum(), 1))
    num = [c for c in counts.columns if c != "tract"]
    m = m[matched]
    for c in num:
        m[c] = m[c] * m.w
    out = m.groupby("dst", as_index=False)[num].sum().rename(columns={"dst": "tract20"})
    return out, share


# ------------------------------------------------------------------------------------------------- shapes

def _read_shapes(zip_name, keep):
    import shapefile

    with zipfile.ZipFile(SHAPES / zip_name) as z:
        stem = [n[:-4] for n in z.namelist() if n.endswith(".shp")][0]
        r = shapefile.Reader(shp=io.BytesIO(z.read(stem + ".shp")), dbf=io.BytesIO(z.read(stem + ".dbf")),
                             shx=io.BytesIO(z.read(stem + ".shx")))
        fields = [f[0] for f in r.fields[1:]]
        for sr in r.iterShapeRecords():
            rec = dict(zip(fields, sr.record))
            if keep(rec):
                yield rec, sr.shape


LON0, LAT0 = -79.4, 37.9
KX = np.cos(np.radians(LAT0))


def project(pts):
    p = np.asarray(pts, float)
    return np.column_stack([(p[:, 0] - LON0) * KX, -(p[:, 1] - LAT0)])


def rdp(p, eps):
    """Ramer-Douglas-Peucker simplification of one ring (iterative)."""
    if len(p) < 4:
        return p
    keep = np.zeros(len(p), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(p) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        seg = p[b] - p[a]
        L = np.hypot(*seg)
        rel = p[a + 1:b] - p[a]
        d = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / L if L > 0 else np.hypot(rel[:, 0], rel[:, 1])
        i = int(np.argmax(d))
        if d[i] > eps:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return p[keep]


def path(shape, eps, scale=1000):
    """SVG path string (integer units of 1/scale degree, projected) for a polygon shape."""
    parts = list(shape.parts) + [len(shape.points)]
    out = []
    for i in range(len(parts) - 1):
        ring = project(shape.points[parts[i]:parts[i + 1]])
        ring = rdp(ring, eps)
        if len(ring) < 4:
            continue
        q = np.round(ring * scale).astype(int)
        out.append("M" + "L".join(f"{x},{y}" for x, y in q) + "Z")
    return "".join(out)


def shapes():
    """Simplified 2020-tract and county paths for the page, plus each tract's county."""
    tracts = {rec["GEOID"]: path(shp, 0.0012) for rec, shp in _read_shapes("cb_2023_51_tract_500k.zip", lambda r: True)}
    counties = {rec["GEOID"]: {"name": rec["NAMELSAD"], "d": path(shp, 0.004)}
                for rec, shp in _read_shapes("cb_2023_us_county_500k.zip", lambda r: r["STATEFP"] == "51")}
    return {"tracts": {k: v for k, v in tracts.items() if v}, "counties": counties}
