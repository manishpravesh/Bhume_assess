"""Characterise the boundary error: is it a coherent shift, or rotation/scale/local?

For every public truth: official->truth displacement in true metres, area ratios,
IoU before and IoU after the *per-plot optimal* translation (does pure shift recover
the shape, or is rotation/reshape needed?). Also dumps input.geojson schema and the
boundaries.tif encoding.
"""
from __future__ import annotations

import geospatial_environment  # noqa: F401  (must precede rasterio/pyproj use)

import sys

import numpy as np
import rasterio
from shapely.affinity import translate

from bhume import load


def utm_for(geom):
    lon = geom.centroid.x
    return f"EPSG:{32600 + int((lon + 180) // 6) + 1}"


def iou(a, b):
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    u = a.union(b).area
    return a.intersection(b).area / u if u > 0 else 0.0


def explore(village_dir):
    v = load(village_dir)
    print(f"\n================ {v.slug} ================")
    print(f"plots: {len(v.plots)}  columns: {list(v.plots.columns)}")
    row0 = v.plots.iloc[0]
    for c in v.plots.columns:
        if c == "geometry":
            continue
        val = row0[c]
        s = str(val)
        print(f"   {c!r}: {s[:120]}")

    # area sanity across all plots
    areas = v.plots.to_crs(utm_for(v.plots.geometry.iloc[0]))
    drawn = areas.geometry.area
    print(f"\n drawn polygon area (m^2): min={drawn.min():.0f} median={drawn.median():.0f} max={drawn.max():.0f}")
    if "map_area_sqm" in v.plots.columns:
        ma = v.plots["map_area_sqm"].astype(float)
        ratio = (drawn.values / ma.values)
        ratio = ratio[np.isfinite(ratio) & (ma.values > 0)]
        print(f" drawn/map_area_sqm ratio: median={np.median(ratio):.3f}  (≈1 means map_area_sqm == drawn area)")
    if "recorded_area_sqm" in v.plots.columns:
        rec = v.plots["recorded_area_sqm"].astype(float)
        n_null = rec.isna().sum()
        print(f" recorded_area_sqm: {n_null} null of {len(rec)}")
        m = (ma > 0) & rec.notna() & (rec > 0)
        rr = (ma[m].values / rec[m].values)
        print(f" map_area / recorded_area: median={np.median(rr):.3f} p10={np.percentile(rr,10):.2f} p90={np.percentile(rr,90):.2f}")

    if v.example_truths is None:
        print(" no truths")
        return

    utm = utm_for(v.example_truths.geometry.iloc[0])
    off = v.plots.to_crs(utm)
    tru = v.example_truths.to_crs(utm)
    print(f"\n truths: {len(tru)}   status values: {v.example_truths['status'].unique().tolist()}")
    print(f"\n {'plot':>6} {'dx_m':>7} {'dy_m':>7} {'dist_m':>7} {'iou0':>5} {'iou_shift':>9} {'areaT/areaO':>11}")
    dxs, dys = [], []
    for pn in tru.index:
        if pn not in off.index:
            print(f" {pn:>6}  (not in cadastre)")
            continue
        o = off.loc[pn, "geometry"]
        t = tru.loc[pn, "geometry"]
        dx = t.centroid.x - o.centroid.x
        dy = t.centroid.y - o.centroid.y
        dxs.append(dx)
        dys.append(dy)
        o_shift = translate(o, dx, dy)
        ar = t.area / o.area if o.area else float("nan")
        print(f" {pn:>6} {dx:7.1f} {dy:7.1f} {np.hypot(dx,dy):7.1f} {iou(o,t):5.2f} {iou(o_shift,t):9.2f} {ar:11.3f}")
    dxs, dys = np.array(dxs), np.array(dys)
    print(f"\n displacement dx: median={np.median(dxs):.1f} std={dxs.std():.1f} range=[{dxs.min():.1f},{dxs.max():.1f}]")
    print(f" displacement dy: median={np.median(dys):.1f} std={dys.std():.1f} range=[{dys.min():.1f},{dys.max():.1f}]")
    print(f" => coherent global shift?  spread(std) vs magnitude(|median|): "
          f"dx {dxs.std():.1f}/{abs(np.median(dxs)):.1f}, dy {dys.std():.1f}/{abs(np.median(dys)):.1f}")

    # boundaries.tif encoding
    if v.boundaries_path:
        with rasterio.open(v.boundaries_path) as b:
            arr = b.read(1)
            print(f"\n boundaries.tif: {b.width}x{b.height} bands={b.count} dtype={b.dtypes[0]} "
                  f"min={arr.min()} max={arr.max()} mean={arr.mean():.1f} res={tuple(round(r,2) for r in b.res)}")
            vals, counts = np.unique(arr, return_counts=True)
            if len(vals) <= 12:
                print(f"   unique values: {dict(zip(vals.tolist(), counts.tolist()))}")
            else:
                print(f"   value hist (deciles): {np.percentile(arr,[0,10,50,90,99,100]).tolist()}")


if __name__ == "__main__":
    for d in (sys.argv[1:] or [
        "data/34855_vadnerbhairav_chandavad_nashik",
        "data/12429_malatavadi_chandgad_kolhapur",
    ]):
        explore(d)
