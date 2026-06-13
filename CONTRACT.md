# Data And Prediction Contract

This file summarizes the technical input/output rules used by the boundary-correction
pipeline.

## Input

Each village folder contains:

```text
data/<village_slug>/
  input.geojson
  imagery.tif
  boundaries.tif
  example_truths.geojson
```

`input.geojson` is a GeoJSON FeatureCollection in EPSG:4326. Each feature is one official
plot boundary and includes a unique `plot_number`.

`imagery.tif` is the satellite raster used as the primary signal.

`boundaries.tif` is an optional rough field-boundary hint. It is useful evidence, but not
treated as truth.

`example_truths.geojson` is a small public sample used only for local self-scoring.

## Output

For every attempted plot, write a feature to:

```text
data/<village_slug>/predictions.geojson
```

Required properties:

```text
plot_number  exact plot id from input.geojson
status       corrected or flagged
confidence   number from 0 to 1 for corrected plots
method_note  optional explanation
geometry     predicted boundary, or original boundary for flagged plots
```

Rules:

- `corrected` means the geometry is the predicted better boundary.
- `flagged` means the method is not confident; geometry should remain the official input
  geometry.
- Omitted plots are treated as not attempted.
- Output coordinates must remain EPSG:4326 lon/lat.

## Local Checks

Regenerate predictions:

```bash
uv run generate_predictions.py --all --score
```

Score existing predictions:

```bash
uv run score_predictions.py
```

Validate schema and geometry:

```bash
uv run validate_predictions.py
```
