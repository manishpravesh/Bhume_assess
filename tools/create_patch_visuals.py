"""Visual sanity check: do truths land on real field edges? Is boundaries.tif usable?

Renders, per plot, the imagery patch with the official outline (red), the hand-aligned
truth outline (green, if available) and the boundary-hint edges (cyan). Saves PNGs to
viz_out/ so they can be eyeballed.
"""
from __future__ import annotations

import geospatial_environment  # noqa: F401

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from bhume import load
from boundary_alignment.geo import (
    geom_4326_to_3857,
    geom_to_pixels,
    open_raster,
    read_patch,
)

OUT = Path("viz_out")
UP = 3  # upscale factor for visibility


def draw_rings(draw, rings, color, width=1, scale=1.0):
    for ring in rings:
        pts = [(c * scale, r * scale) for c, r in ring]
        draw.line(pts, fill=color, width=width)


def render(village_dir, plot_numbers=None, pad_m=35.0):
    v = load(village_dir)
    OUT.mkdir(exist_ok=True)
    src = open_raster(v.imagery_path)
    bnd = open_raster(v.boundaries_path) if v.boundaries_path else None
    if plot_numbers is None:
        plot_numbers = list(v.example_truths.index) if v.example_truths is not None else list(v.plots.index[:4])

    for pn in plot_numbers:
        og = geom_4326_to_3857(v.plot(pn))
        minx, miny, maxx, maxy = og.bounds
        bounds = (minx - pad_m, miny - pad_m, maxx + pad_m, maxy + pad_m)
        img, tr = read_patch(src, bounds)
        H, W = img.shape[:2]
        base = Image.fromarray(img[:, :, :3]).convert("RGB").resize((W * UP, H * UP), Image.NEAREST)

        # boundary hints as a cyan overlay, resampled onto the patch grid
        if bnd is not None:
            try:
                barr, btr = read_patch(bnd, bounds, bands=(1,))
                bimg = Image.fromarray(barr).resize((W * UP, H * UP), Image.NEAREST)
                bmask = np.asarray(bimg) > 127
                ov = np.asarray(base).copy()
                ov[bmask] = (0, 255, 255)
                base = Image.blend(base, Image.fromarray(ov), 0.45)
            except ValueError:
                pass

        draw = ImageDraw.Draw(base)
        draw_rings(draw, geom_to_pixels(og, tr), (255, 40, 40), width=2, scale=UP)  # official red
        if v.example_truths is not None and pn in v.example_truths.index:
            tg = geom_4326_to_3857(v.example_truths.loc[pn, "geometry"])
            draw_rings(draw, geom_to_pixels(tg, tr), (40, 255, 40), width=2, scale=UP)  # truth green

        out = OUT / f"{v.slug[:8]}_{pn}.png"
        base.save(out)
        print(f"  saved {out}  patch={W}x{H}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        render(args[0], args[1:] or None)
    else:
        render("data/34855_vadnerbhairav_chandavad_nashik", ["1145", "1710", "2647"])
        render("data/12429_malatavadi_chandgad_kolhapur", ["1177", "1763", "1966"])
