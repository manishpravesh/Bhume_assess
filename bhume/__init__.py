"""
BhuMe boundary take-home starter kit.

Removes the geospatial plumbing we are not assessing (CRS juggling, raster windows,
GeoJSON I/O, scoring) so you can spend your time on the judgement that we are.

    from bhume import load, patch_for_plot, write_predictions, score
    from bhume.baseline import global_median_shift

    village = load("data/34855_vadnerbhairav_chandavad_nashik")
    preds = global_median_shift(village)
    write_predictions(village.dir / "predictions.geojson", preds)
    print(score(preds, village))

See `quickstart.py` for the same flow, narrated end to end.
"""

from bhume.geo import Patch, lonlat_to_pixel, patch_for_plot, pixel_to_lonlat
from bhume.io import Village, load, load_vectors, write_predictions
from bhume.score import Scorecard, score

__all__ = [
    "Village",
    "load",
    "load_vectors",
    "write_predictions",
    "Patch",
    "patch_for_plot",
    "lonlat_to_pixel",
    "pixel_to_lonlat",
    "Scorecard",
    "score",
]
