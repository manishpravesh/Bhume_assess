#!/usr/bin/env python3
"""Run the boundary correction on a village bundle and write predictions.geojson.

    uv run generate_predictions.py data/34855_vadnerbhairav_chandavad_nashik
    uv run generate_predictions.py --all          # both bundled villages
    uv run generate_predictions.py <dir> --score  # also self-score against example_truths

The method is in boundary_alignment/; this wires load -> predict -> write (-> score).
"""
from __future__ import annotations

import geospatial_environment  # noqa: F401  (pin PROJ data before geo libs initialise)

import sys
import time
from pathlib import Path

from bhume import load, score, write_predictions
from boundary_alignment.pipeline import predict

VILLAGES = [
    "data/34855_vadnerbhairav_chandavad_nashik",
    "data/12429_malatavadi_chandgad_kolhapur",
]


def run_one(village_dir: str, do_score: bool) -> None:
    t0 = time.time()
    village = load(village_dir)
    print(f"\n=== {village.slug}: {len(village.plots)} plots ===")
    preds = predict(village, verbose=True)
    out = write_predictions(Path(village_dir) / "predictions.geojson", preds)
    print(f"  wrote {len(preds)} predictions -> {out}  ({time.time()-t0:.1f}s)")
    if do_score and village.example_truths is not None:
        print(score(preds, village))


def main(argv: list[str]) -> None:
    do_score = "--score" in argv
    argv = [a for a in argv if a != "--score"]
    if "--all" in argv or not argv:
        targets = VILLAGES
    else:
        targets = argv
    for d in targets:
        run_one(d, do_score)


if __name__ == "__main__":
    main(sys.argv[1:])
