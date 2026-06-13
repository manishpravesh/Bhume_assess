"""Introspect the pipeline: confidence-component distributions + truth-plot detail."""
from __future__ import annotations

import geospatial_environment  # noqa: F401
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.affinity import translate

from bhume import load
from boundary_alignment.pipeline import predict, Params


def utm_for(g):
    return f"EPSG:{32600 + int((g.centroid.x + 180) // 6) + 1}"


def iou(a, b):
    u = a.union(b).area
    return a.intersection(b).area / u if u > 0 else 0.0


def run(village_dir):
    v = load(village_dir)
    diag = []
    preds = predict(v, Params(), verbose=True, diag_out=diag)
    df = pd.DataFrame(diag)
    n = len(df)
    corr = df[df.status == "corrected"]
    print(f"\n[{v.slug}] {n} plots: corrected={len(corr)} ({len(corr)/n:.0%}) flagged={n-len(corr)}")
    print("  conf distribution:", np.round(np.nanpercentile(corr.conf, [10,25,50,75,90]), 3).tolist())
    for col in ["raw_cost", "contrast", "field_resid", "edge_density", "sharpness", "shift_px"]:
        vals = corr[col].to_numpy()
        print(f"  {col:12s} p10/50/90 = "
              f"{np.nanpercentile(vals,10):.2f} / {np.nanpercentile(vals,50):.2f} / {np.nanpercentile(vals,90):.2f}")

    # truth-plot detail
    if v.example_truths is None:
        return
    utm = utm_for(v.example_truths.geometry.iloc[0])
    off_u = v.plots.to_crs(utm); tru_u = v.example_truths.to_crs(utm)
    preds_i = preds.set_index("plot_number")
    print(f"\n  {'plot':>6} {'status':>9} {'conf':>5} {'dx':>6} {'dy':>6} {'fdx':>6} {'fdy':>6} "
          f"{'rcost':>5} {'iou0':>5} {'iouP':>5}")
    for pn in v.example_truths.index:
        d = df[df.plot_number == str(pn)]
        if d.empty:
            continue
        d = d.iloc[0]
        pg = preds_i.loc[str(pn), "geometry"]
        pg_u = gpd.GeoSeries([pg], crs="EPSG:4326").to_crs(utm).iloc[0]
        o = off_u.loc[pn, "geometry"]; t = tru_u.loc[pn, "geometry"]
        print(f"  {pn:>6} {d.status:>9} {d.conf if not np.isnan(d.conf) else 0:5.2f} "
              f"{d.dx_m:6.1f} {d.dy_m:6.1f} {d.field_dx:6.1f} {d.field_dy:6.1f} "
              f"{d.raw_cost:5.2f} {iou(o,t):5.2f} {iou(pg_u,t):5.2f}")


if __name__ == "__main__":
    for d in (sys.argv[1:] or ["data/34855_vadnerbhairav_chandavad_nashik"]):
        run(d)
