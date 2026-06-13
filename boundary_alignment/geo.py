"""Raster + CRS helpers that don't trust the imagery's CRS tag.

The bundled GeoTIFFs are web-mercator (EPSG:3857) but some carry a degenerate
``LOCAL_CS["WGS 84 / Pseudo-Mercator"]`` tag with no EPSG authority, which makes a
generic ``Transformer.from_crs('EPSG:4326', src.crs)`` raise. We therefore treat
imagery as EPSG:3857 explicitly and do all pixel work through the raster's affine
transform (which needs no CRS at all). Geometry stays in 3857 + pixel space during
alignment; results are converted back to lon/lat (EPSG:4326) only at output.

Working in 3857 does not bias positioning: the polygon, the imagery and the estimated
shift are all in the same 3857 frame, so a vertex moved onto a pixel-located field edge
maps back to that edge's true lon/lat. (Web-mercator's scale inflation cancels.)
"""
from __future__ import annotations

import geospatial_environment  # noqa: F401  (pin PROJ data before pyproj/rasterio initialise)

from functools import lru_cache

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

IMAGERY_CRS = "EPSG:3857"


@lru_cache(maxsize=4)
def _tf(src_crs: str, dst_crs: str) -> Transformer:
    return Transformer.from_crs(src_crs, dst_crs, always_xy=True)


def geom_4326_to_3857(geom: BaseGeometry) -> BaseGeometry:
    t = _tf("EPSG:4326", IMAGERY_CRS)
    return shp_transform(lambda xs, ys, z=None: t.transform(xs, ys), geom)


def geom_3857_to_4326(geom: BaseGeometry) -> BaseGeometry:
    t = _tf(IMAGERY_CRS, "EPSG:4326")
    return shp_transform(lambda xs, ys, z=None: t.transform(xs, ys), geom)


def open_raster(path):
    return rasterio.open(path)


def read_patch(src, bounds_3857, bands=(1, 2, 3)):
    """Read a raster window covering ``bounds_3857`` = (left, bottom, right, top).

    Returns (array, window_transform). ``array`` is (H, W, len(bands)) for multi-band
    or (H, W) for a single band. The window is clipped to the raster footprint.
    """
    left, bottom, right, top = bounds_3857
    dl, db, dr, dt = src.bounds
    left, bottom = max(left, dl), max(bottom, db)
    right, top = min(right, dr), min(top, dt)
    if right <= left or top <= bottom:
        raise ValueError("requested bounds do not overlap the raster")
    window = from_bounds(left, bottom, right, top, transform=src.transform)
    arr = src.read(list(bands), window=window)
    tr = src.window_transform(window)
    if arr.shape[0] == 1:
        return arr[0], tr
    return np.transpose(arr, (1, 2, 0)), tr


def xy_to_colrow(transform, x, y):
    """Map 3857 (x, y) -> fractional (col, row) pixel using an affine transform."""
    inv = ~transform
    col, row = inv * (x, y)
    return col, row


def colrow_to_xy(transform, col, row):
    """Map (col, row) pixel centre -> 3857 (x, y)."""
    x, y = transform * (col + 0.5, row + 0.5)
    return x, y


def geom_to_pixels(geom_3857: BaseGeometry, transform):
    """Exterior ring(s) of a 3857 polygon as lists of (col, row) pixel coords."""
    rings = []
    geoms = geom_3857.geoms if geom_3857.geom_type.startswith("Multi") else [geom_3857]
    for g in geoms:
        if g.is_empty:
            continue
        xs, ys = g.exterior.coords.xy
        cols, rows = xy_to_colrow(transform, np.asarray(xs), np.asarray(ys))
        rings.append(np.column_stack([cols, rows]))
    return rings
