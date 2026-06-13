"""Overlay the FINAL prediction (yellow) vs official (red) and truth (green).

Run after predictions.geojson exists. Saves PNGs to viz_out/final_*.
"""
from __future__ import annotations

import geospatial_environment  # noqa: F401

import sys
from pathlib import Path

from PIL import Image, ImageDraw

from bhume import load
from bhume.io import read_predictions
from boundary_alignment.geo import geom_4326_to_3857, geom_to_pixels, open_raster, read_patch

OUT = Path("viz_out"); UP = 3


def draw_rings(draw, rings, color, width, scale):
    for ring in rings:
        draw.line([(c * scale, r * scale) for c, r in ring], fill=color, width=width)


def render(village_dir, plot_numbers=None, pad_m=35.0):
    v = load(village_dir)
    OUT.mkdir(exist_ok=True)
    src = open_raster(v.imagery_path)
    preds = read_predictions(Path(village_dir) / "predictions.geojson")
    if plot_numbers is None:
        plot_numbers = list(v.example_truths.index) if v.example_truths is not None else list(v.plots.index[:6])

    for pn in plot_numbers:
        og = geom_4326_to_3857(v.plot(pn))
        minx, miny, maxx, maxy = og.bounds
        bounds = (minx - pad_m, miny - pad_m, maxx + pad_m, maxy + pad_m)
        img, tr = read_patch(src, bounds)
        H, W = img.shape[:2]
        base = Image.fromarray(img[:, :, :3]).convert("RGB").resize((W * UP, H * UP), Image.NEAREST)
        draw = ImageDraw.Draw(base)
        draw_rings(draw, geom_to_pixels(og, tr), (255, 40, 40), 1, UP)           # official red
        if v.example_truths is not None and pn in v.example_truths.index:
            tg = geom_4326_to_3857(v.example_truths.loc[pn, "geometry"])
            draw_rings(draw, geom_to_pixels(tg, tr), (40, 255, 40), 2, UP)       # truth green
        if str(pn) in preds.index:
            row = preds.loc[str(pn)]
            pg = geom_4326_to_3857(row.geometry)
            col = (255, 230, 0) if row.get("status") == "corrected" else (255, 140, 0)
            draw_rings(draw, geom_to_pixels(pg, tr), col, 2, UP)                 # predicted yellow
            st = row.get("status"); cf = row.get("confidence")
        else:
            st, cf = "none", None
        out = OUT / f"final_{v.slug[:8]}_{pn}.png"
        base.save(out)
        print(f"  {out}  status={st} conf={cf}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and not args[0].startswith("data"):
        args = ["data/34855_vadnerbhairav_chandavad_nashik"] + args
    if args:
        render(args[0], args[1:] or None)
    else:
        render("data/34855_vadnerbhairav_chandavad_nashik", ["1145", "1710", "2647"])
        render("data/12429_malatavadi_chandgad_kolhapur", ["1177", "1763", "1966"])
