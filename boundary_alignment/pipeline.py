"""Turn a village bundle into contract-shaped predictions.

Two passes over the plots:

  Pass 1  raw edge registration per plot (no prior) -> a noisy drift estimate + a
          quality score, and a cached cost surface.
  Field   from the *confident* pass-1 plots, estimate a smooth per-plot drift prior
          (boundary_alignment/field.py).
  Pass 2  re-solve each cached surface with a penalty pulling it toward its local
          prior; ambiguous plots snap to the coherent drift, clear plots keep their
          own edge match.

Confidence reflects whether the corrected outline tightly hugs real edges, whether that
match is distinct from other shifts, whether it agrees with the neighbourhood drift, and
whether there were real edges to align to. Plots that fail these are flagged (kept put).
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from shapely.affinity import translate

from boundary_alignment.align import build_surface, solve
from boundary_alignment.field import local_field
from boundary_alignment.geo import geom_3857_to_4326, geom_4326_to_3857, open_raster


@dataclass
class Params:
    search_m: float = 22.0       # max shift considered
    grad_pct: float = 88.0       # imagery-gradient percentile that counts as an edge
    # adaptive prior pull (chamfer-px per shift-px): ~lam_min where the data minimum is
    # sharp (data wins), up to lam_max where it is ambiguous (coherent drift wins)
    lam_min: float = 0.03
    lam_max: float = 0.16
    bandwidth_m: float = 200.0   # spatial scale of drift coherence
    deadzone_m: float = 2.5      # below this shift, keep the official position (restraint)
    flag_conf: float = 0.28      # below this confidence -> flag
    min_edge_density: float = 0.02
    # confidence feature scales, in METRES so they transfer across villages with
    # different pixel sizes (Vadner ~1.2 m/px, Malatavadi ~0.6 m/px)
    cost_hi_m: float = 2.0       # mean outline->edge distance beyond which fit is worthless
    contrast_hi_m: float = 2.5
    consist_hi_m: float = 18.0
    edge_lo: float = 0.02
    edge_hi: float = 0.10
    quality_cost_hi_m: float = 1.8   # for the pass-1 trust used by the drift field / lam
    quality_contrast_hi_m: float = 2.5


def _quality(raw_cost_m, contrast_m, p: Params):
    """Relative trust in a pass-1 estimate (metres), for the drift field and adaptive lam."""
    s_cost = np.clip((p.quality_cost_hi_m - raw_cost_m) / p.quality_cost_hi_m, 0, 1)
    s_contrast = np.clip(contrast_m / p.quality_contrast_hi_m, 0, 1)
    return float(s_cost * s_contrast)


def _confidence(raw_cost_m, contrast_m, field_resid_m, edge_density, sharpness, p: Params):
    """Confidence that the corrected outline is right (all distances in metres).

    Dominated by edge-fit (does the outline actually sit on real edges?), then how
    distinct that match is, then whether it agrees with the coherent neighbourhood
    drift. Gated by whether there were edges to align to at all. Poor-fit corrections
    score low on purpose: an honest low number calibrates better than a flattering one.
    """
    q_fit = np.clip((p.cost_hi_m - raw_cost_m) / p.cost_hi_m, 0, 1)   # outline hugs edges
    q_dist = np.clip(contrast_m / p.contrast_hi_m, 0, 1)              # match is distinct
    q_agree = np.clip(1 - field_resid_m / p.consist_hi_m, 0, 1)       # agrees with drift
    q_edges = np.clip((edge_density - p.edge_lo) / (p.edge_hi - p.edge_lo), 0, 1)
    core = 0.60 * q_fit + 0.25 * q_dist + 0.15 * q_agree
    conf = core * (0.55 + 0.45 * q_edges) * (0.8 + 0.2 * sharpness)
    return float(np.clip(conf, 0.02, 0.99))


def predict(village, params: Params | None = None, verbose: bool = False,
            diag_out: list | None = None) -> gpd.GeoDataFrame:
    p = params or Params()
    src = open_raster(village.imagery_path)
    bnd = open_raster(village.boundaries_path) if village.boundaries_path else None
    res_m = abs(src.res[0])

    plots = village.plots
    pns = list(plots.index)
    geoms3857 = {pn: geom_4326_to_3857(plots.loc[pn, "geometry"]) for pn in pns}

    # --- Pass 1: raw registration, cache surfaces -------------------------------
    surfaces, raw = {}, {}
    cx = np.zeros(len(pns)); cy = np.zeros(len(pns))
    dx = np.zeros(len(pns)); dy = np.zeros(len(pns)); q = np.zeros(len(pns))
    for i, pn in enumerate(pns):
        g = geoms3857[pn]
        c = g.centroid
        cx[i], cy[i] = c.x, c.y
        surf = build_surface(src, bnd, g, res_m, search_m=p.search_m, grad_pct=p.grad_pct)
        surfaces[pn] = surf
        sol = solve(surf, lam=0.0)
        raw[pn] = sol
        dx[i], dy[i] = sol.dx_m, sol.dy_m
        q[i] = _quality(sol.raw_cost * res_m, sol.contrast * res_m, p) if surf.ok else 0.0
    if verbose:
        print(f"  pass1: {int((q>0.3).sum())}/{len(pns)} confident; "
              f"raw drift median dx={np.median(dx[q>0.3]):.1f} dy={np.median(dy[q>0.3]):.1f}")

    # --- Drift field -----------------------------------------------------------
    xy = np.column_stack([cx, cy])
    fdx, fdy, support = local_field(xy, dx, dy, q, bandwidth=p.bandwidth_m)

    # --- Pass 2: re-solve with the local prior; build outputs ------------------
    rows = []
    for i, pn in enumerate(pns):
        surf = surfaces[pn]
        g = geoms3857[pn]
        official_4326 = plots.loc[pn, "geometry"]
        if not surf.ok:
            rows.append(dict(plot_number=str(pn), status="flagged", confidence=None,
                             method_note="no usable imagery/edges", geometry=official_4326))
            continue
        prior_row = -fdy[i] / res_m
        prior_col = fdx[i] / res_m
        lam_i = p.lam_min + (p.lam_max - p.lam_min) * (1.0 - q[i])  # data wins when confident
        sol = solve(surf, prior_row=prior_row, prior_col=prior_col, lam=lam_i)
        field_resid = float(np.hypot(sol.dx_m - fdx[i], sol.dy_m - fdy[i]))
        conf = _confidence(sol.raw_cost * res_m, sol.contrast * res_m, field_resid,
                           surf.edge_density, sol.sharpness, p)

        too_few_edges = surf.edge_density < p.min_edge_density
        if conf < p.flag_conf or too_few_edges:
            rows.append(dict(plot_number=str(pn), status="flagged", confidence=None,
                             method_note=f"low confidence ({conf:.2f}); kept official",
                             geometry=official_4326))
            continue

        if sol.shift_px * res_m < p.deadzone_m:    # already aligned -> don't move it
            geom_out = official_4326
            note = f"already aligned (shift<{p.deadzone_m:.1f}m); kept official"
        else:
            geom_out = geom_3857_to_4326(translate(g, sol.dx_m, sol.dy_m))
            note = (f"edge-registered shift dx={sol.dx_m:.1f} dy={sol.dy_m:.1f} m; "
                    f"cost={sol.raw_cost:.2f}px")
        rows.append(dict(plot_number=str(pn), status="corrected", confidence=round(conf, 3),
                         method_note=note, geometry=geom_out))
        if diag_out is not None:
            diag_out.append(dict(plot_number=str(pn), dx_m=sol.dx_m, dy_m=sol.dy_m,
                                 raw_cost=sol.raw_cost, contrast=sol.contrast,
                                 field_dx=fdx[i], field_dy=fdy[i], field_resid=field_resid,
                                 edge_density=surf.edge_density, sharpness=sol.sharpness,
                                 shift_px=sol.shift_px, conf=conf, status="corrected"))

    if diag_out is not None:
        done = {d["plot_number"] for d in diag_out}
        for i, pn in enumerate(pns):
            if str(pn) not in done:
                surf = surfaces[pn]
                diag_out.append(dict(plot_number=str(pn), dx_m=np.nan, dy_m=np.nan,
                                     raw_cost=getattr(surf, "zero_cost", np.nan), contrast=np.nan,
                                     field_dx=fdx[i], field_dy=fdy[i], field_resid=np.nan,
                                     edge_density=surf.edge_density, sharpness=np.nan,
                                     shift_px=np.nan, conf=np.nan, status="flagged"))

    out = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    if verbose:
        nc = (out.status == "corrected").sum()
        print(f"  corrected={nc} flagged={len(out)-nc} "
              f"median conf={out.loc[out.status=='corrected','confidence'].median():.3f}")
    return out[["plot_number", "status", "confidence", "method_note", "geometry"]]
