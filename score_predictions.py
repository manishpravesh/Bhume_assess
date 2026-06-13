#!/usr/bin/env python3
"""Self-score existing predictions.geojson files against the example truths.

    uv run score_predictions.py            # both bundled villages
    uv run score_predictions.py <dir> ...  # specific village dirs

Reads predictions already written by generate_predictions.py and does not recompute them, so it works even
when the large imagery.tif/boundaries.tif files are not present in your checkout. See
generate_predictions.py --score to compute and score in one step once the raster bundles are downloaded.
"""
from __future__ import annotations

import geospatial_environment  # noqa: F401

import sys
from pathlib import Path

from bhume import load_vectors, score
from bhume.io import read_predictions

VILLAGES = [
    "data/34855_vadnerbhairav_chandavad_nashik",
    "data/12429_malatavadi_chandgad_kolhapur",
]


def main(argv: list[str]) -> None:
    for d in (argv or VILLAGES):
        village = load_vectors(d)
        pred_path = Path(d) / "predictions.geojson"
        if not pred_path.exists():
            print(f"[{village.slug}] no predictions.geojson - run: uv run generate_predictions.py {d}")
            continue
        preds = read_predictions(pred_path)
        if village.example_truths is None:
            print(f"[{village.slug}] no example_truths to score against")
            continue
        print(score(preds, village))
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
