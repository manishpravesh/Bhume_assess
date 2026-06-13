"""Does the registration recover the truth? Per truth plot: estimated shift, resulting IoU."""
from __future__ import annotations

import geospatial_environment  # noqa: F401
import sys

import numpy as np
from shapely.affinity import translate

from bhume import load
from boundary_alignment.align import build_surface, solve
from boundary_alignment.geo import geom_3857_to_4326, geom_4326_to_3857, open_raster


def utm_for(geom):
    return f"EPSG:{32600 + int((geom.centroid.x + 180) // 6) + 1}"


def iou(a, b):
    u = a.union(b).area
    return a.intersection(b).area / u if u > 0 else 0.0


def run(village_dir):
    v = load(village_dir)
    res_m = abs(open_raster(v.imagery_path).res[0])
    src = open_raster(v.imagery_path)
    bnd = open_raster(v.boundaries_path) if v.boundaries_path else None
    utm = utm_for(v.example_truths.geometry.iloc[0])
    off_u = v.plots.to_crs(utm)
    tru_u = v.example_truths.to_crs(utm)

    print(f"\n=== {v.slug}  (res {res_m:.3f} m/px) ===")
    print(f"{'plot':>6} {'dx_m':>6} {'dy_m':>6} {'shiftpx':>7} {'iou0':>5} {'iouP':>5} "
          f"{'best':>5} {'zero':>5} {'bg':>5} {'supp':>5} {'edens':>6}")
    ious0, iousP = [], []
    for pn in v.example_truths.index:
        g3857 = geom_4326_to_3857(v.plot(pn))
        surf = build_surface(src, bnd, g3857, res_m)
        reg = solve(surf)
        moved3857 = translate(g3857, reg.dx_m, reg.dy_m)
        moved4326 = geom_3857_to_4326(moved3857)
        import geopandas as gpd
        moved_u = gpd.GeoSeries([moved4326], crs="EPSG:4326").to_crs(utm).iloc[0]
        o = off_u.loc[pn, "geometry"]
        t = tru_u.loc[pn, "geometry"]
        i0, iP = iou(o, t), iou(moved_u, t)
        ious0.append(i0); iousP.append(iP)
        print(f"{pn:>6} {reg.dx_m:6.1f} {reg.dy_m:6.1f} {reg.shift_px:7.1f} {i0:5.2f} {iP:5.2f} "
              f"{reg.raw_cost:5.2f} {surf.zero_cost:5.2f} {surf.bg_cost:5.2f} {reg.contrast:5.2f} {surf.edge_density:6.3f}")
    print(f"  median IoU: official={np.median(ious0):.3f} -> predicted={np.median(iousP):.3f}")


if __name__ == "__main__":
    for d in (sys.argv[1:] or [
        "data/34855_vadnerbhairav_chandavad_nashik",
        "data/12429_malatavadi_chandgad_kolhapur",
    ]):
        run(d)
