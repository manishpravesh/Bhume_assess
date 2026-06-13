"""Per-plot translation by edge registration (chamfer matching).

The official outline has the right *shape* (verified on the truths: IoU after the
per-plot optimal shift jumps to ~0.8-1.0), it just sits a few metres off. So we slide
the rigid outline over an edge map built from the satellite image (gradient) and the
boundary hints, and pick the translation whose outline best hugs the real field edges.

Chamfer cost(shift) = mean distance, in pixels, from each outline pixel to the nearest
target edge after shifting. The whole cost surface comes from one FFT cross-correlation
of the outline indicator with the edge distance-transform, so it's cheap over thousands
of plots. We keep the windowed cost surface so a second pass can re-solve it with a
*prior penalty* (toward the village's coherent drift) without re-reading imagery — this
is what rescues dense areas where many parallel edges make the raw minimum ambiguous.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve
from skimage.draw import line as skline
from skimage.filters import sobel
from skimage.transform import resize

from boundary_alignment.geo import geom_to_pixels, read_patch


@dataclass
class Surface:
    """Windowed chamfer cost surface for one plot, ready to re-solve with a prior."""
    sub: np.ndarray        # (nr, nc) mean outline->edge distance (px); inf outside circle
    d_rows: np.ndarray     # candidate row shifts (px) for each surface row
    d_cols: np.ndarray     # candidate col shifts (px) for each surface col
    zero_cost: float       # chamfer cost at no shift (px)
    bg_cost: float         # median finite cost over the window (px)
    edge_density: float    # frac of patch pixels that are target edges
    n_outline: int         # outline pixel count
    res_m: float           # imagery pixel size (m)
    ok: bool


@dataclass
class Solution:
    d_row: int
    d_col: int
    dx_m: float
    dy_m: float
    raw_cost: float        # chamfer cost at the chosen shift (px), prior excluded
    shift_px: float
    contrast: float        # (bg_cost - raw_cost): how much better than a typical shift
    sharpness: float       # tightness of the minimum's basin (0..1, higher = sharper)


def _edge_target(img, bnd_resized, grad_pct):
    gray = img[:, :, :3].mean(axis=2).astype(np.float32)
    grad = sobel(gray / (gray.max() + 1e-6))
    if grad.max() > 0:
        grad = grad / grad.max()
    edge = grad > np.percentile(grad, grad_pct)
    if bnd_resized is not None:
        edge = edge | (bnd_resized > 0.5)
    return edge


def _outline_image(rings, shape):
    H, W = shape
    out = np.zeros(shape, dtype=np.float32)
    for ring in rings:
        pts = np.round(ring).astype(int)  # (col, row)
        for i in range(len(pts) - 1):
            c0, r0 = pts[i]
            c1, r1 = pts[i + 1]
            rr, cc = skline(int(r0), int(c0), int(r1), int(c1))
            keep = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W)
            out[rr[keep], cc[keep]] = 1.0
    return out, int(out.sum())


def build_surface(src, bnd_src, geom_3857, res_m, search_m=22.0, pad_extra_m=10.0,
                  grad_pct=88.0) -> Surface:
    minx, miny, maxx, maxy = geom_3857.bounds
    pad = search_m + pad_extra_m
    bounds = (minx - pad, miny - pad, maxx + pad, maxy + pad)
    try:
        img, tr = read_patch(src, bounds)
    except ValueError:
        return Surface(np.array([[np.inf]]), np.array([0]), np.array([0]),
                       9.0, 9.0, 0.0, 0, res_m, False)

    H, W = img.shape[:2]
    bnd_resized = None
    if bnd_src is not None:
        try:
            barr, _ = read_patch(bnd_src, bounds, bands=(1,))
            bnd_resized = resize(barr.astype(np.float32) / 255.0, (H, W), order=0,
                                 preserve_range=True, anti_aliasing=False)
        except ValueError:
            bnd_resized = None

    edge = _edge_target(img, bnd_resized, grad_pct)
    edge_density = float(edge.mean())
    dt = ndimage.distance_transform_edt(~edge).astype(np.float32)

    rings = geom_to_pixels(geom_3857, tr)
    model, n_out = _outline_image(rings, (H, W))
    if n_out < 8:
        return Surface(np.array([[np.inf]]), np.array([0]), np.array([0]),
                       9.0, 9.0, edge_density, n_out, res_m, False)

    corr = fftconvolve(dt, model[::-1, ::-1], mode="same")
    cost = corr / n_out
    cr, cc = H // 2, W // 2

    R = max(1, int(round(search_m / res_m)))
    rows = np.arange(max(0, cr - R), min(H, cr + R + 1))
    cols = np.arange(max(0, cc - R), min(W, cc + R + 1))
    sub = cost[np.ix_(rows, cols)].astype(np.float32)
    d_rows = rows - cr
    d_cols = cols - cc
    rr, cc2 = np.meshgrid(d_rows, d_cols, indexing="ij")
    sub = np.where((rr ** 2 + cc2 ** 2) <= R ** 2, sub, np.inf).astype(np.float32)

    zero_cost = float(cost[cr, cc])
    finite = sub[np.isfinite(sub)]
    bg_cost = float(np.median(finite)) if finite.size else 9.0
    return Surface(sub, d_rows, d_cols, zero_cost, bg_cost, edge_density,
                   n_out, res_m, True)


def solve(surf: Surface, prior_row: float = 0.0, prior_col: float = 0.0,
          lam: float = 0.0) -> Solution:
    """Pick the shift minimising chamfer cost + lam * (px distance from the prior shift).

    ``lam`` in chamfer-px per shift-px: 0 = pure data (pass 1); >0 pulls ambiguous plots
    toward the coherent drift prior (pass 2).
    """
    if not surf.ok:
        return Solution(0, 0, 0.0, 0.0, surf.zero_cost, 0.0, 0.0, 0.0)
    rr, cc = np.meshgrid(surf.d_rows, surf.d_cols, indexing="ij")
    pen = surf.sub.copy()
    if lam > 0:
        dist = np.hypot(rr - prior_row, cc - prior_col)
        pen = pen + lam * dist
    idx = np.unravel_index(np.argmin(pen), pen.shape)
    d_row = int(surf.d_rows[idx[0]])
    d_col = int(surf.d_cols[idx[1]])
    raw_cost = float(surf.sub[idx])

    contrast = surf.bg_cost - raw_cost
    # sharpness: small basin near the raw minimum => sharp, trustworthy peak
    raw_min = float(np.nanmin(np.where(np.isfinite(surf.sub), surf.sub, np.nan)))
    finite = np.isfinite(surf.sub)
    near = (surf.sub <= raw_min + 0.75) & finite
    frac_near = near.sum() / max(1, finite.sum())
    sharpness = float(np.clip(1.0 - frac_near * 4.0, 0.0, 1.0))

    return Solution(
        d_row=d_row, d_col=d_col,
        dx_m=d_col * surf.res_m, dy_m=-d_row * surf.res_m,
        raw_cost=raw_cost, shift_px=float(np.hypot(d_row, d_col)),
        contrast=float(contrast), sharpness=sharpness,
    )
