"""Estimate the village's drift field from the plots themselves (no truth needed).

The georeferencing error is "mostly a coherent offset, but not entirely": neighbouring
plots drift in nearly the same direction, with slow spatial variation. So we take the
*confident* per-plot registrations and, for every plot, predict a local drift as the
distance-weighted average of its confident neighbours (falling back to a global robust
drift where neighbours are sparse). This prior both denoises noisy plots and anchors
ambiguous ones in dense areas, where the raw edge match alone wanders onto a neighbour.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def weighted_median(values, weights):
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    if cw[-1] <= 0:
        return float(np.median(values))
    cutoff = cw[-1] / 2.0
    return float(v[np.searchsorted(cw, cutoff)])


def global_drift(dx, dy, q):
    m = q > 0
    if m.sum() < 3:
        return float(np.median(dx)), float(np.median(dy))
    return weighted_median(dx[m], q[m]), weighted_median(dy[m], q[m])


def local_field(xy, dx, dy, q, bandwidth=200.0, qmin=0.30, min_weight=0.5):
    """Per-plot smoothed drift from confident neighbours.

    ``xy`` (n,2) plot centroids in metres; ``dx,dy`` raw drift; ``q`` quality in [0,1].
    Returns (field_dx, field_dy, support) where support is the summed neighbour weight
    (low support => we leaned on the global fallback => trust the prior less).
    """
    n = len(xy)
    gdx, gdy = global_drift(dx, dy, q)
    conf = q >= qmin
    fdx = np.full(n, gdx)
    fdy = np.full(n, gdy)
    support = np.zeros(n)
    if conf.sum() >= 3:
        tree = cKDTree(xy[conf])
        cdx, cdy, cq = dx[conf], dy[conf], q[conf]
        r = bandwidth * 3.0
        for i in range(n):
            idx = tree.query_ball_point(xy[i], r)
            if not idx:
                continue
            d = np.linalg.norm(xy[idx] - xy[i], axis=1)
            w = cq[idx] * np.exp(-(d ** 2) / (2 * bandwidth ** 2))
            sw = w.sum()
            support[i] = sw
            if sw >= min_weight:
                fdx[i] = (w * cdx[idx]).sum() / sw
                fdy[i] = (w * cdy[idx]).sum() / sw
    return fdx, fdy, support
