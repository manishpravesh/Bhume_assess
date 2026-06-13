#!/usr/bin/env python3
"""Validate predictions.geojson files against the assignment contract.

This is intentionally stricter than the scorer: it checks schema, plot coverage, geometry
validity, and whether flagged plots keep the official geometry. It does not need the large
rasters, so it can run in a lightweight project checkout.
"""
from __future__ import annotations

import geospatial_environment  # noqa: F401

import sys
from pathlib import Path

import geopandas as gpd

from bhume import load_vectors, score
from bhume.io import read_predictions

VILLAGES = [
    "data/34855_vadnerbhairav_chandavad_nashik",
    "data/12429_malatavadi_chandgad_kolhapur",
]

FLAGGED_TOLERANCE_M = 0.05


def _utm_for(gdf: gpd.GeoDataFrame) -> str:
    lon = gdf.geometry.iloc[0].centroid.x
    return f"EPSG:{32600 + int((lon + 180) // 6) + 1}"


def _validate_one(village_dir: str | Path) -> int:
    village = load_vectors(village_dir)
    pred_path = village.dir / "predictions.geojson"
    print(f"\n=== {village.slug} ===")
    if not pred_path.exists():
        print(f"ERROR: missing {pred_path}")
        return 1

    pred = read_predictions(pred_path)
    errors: list[str] = []
    warnings: list[str] = []

    if pred.crs is None:
        warnings.append("predictions has no CRS metadata; GeoJSON is assumed EPSG:4326")
        pred = pred.set_crs("EPSG:4326")
    else:
        pred = pred.to_crs("EPSG:4326")

    if not pred.index.is_unique:
        dupes = pred.index[pred.index.duplicated()].unique().tolist()
        errors.append(f"duplicate plot_number values: {dupes[:10]}")

    unknown = sorted(set(pred.index) - set(village.plots.index))
    if unknown:
        errors.append(f"unknown plot_number values: {unknown[:10]}")

    bad_status = pred.loc[~pred["status"].isin(["corrected", "flagged"]), "status"].unique().tolist()
    if bad_status:
        errors.append(f"bad status values: {bad_status}")

    corrected = pred[pred["status"] == "corrected"]
    flagged = pred[pred["status"] == "flagged"]
    if "confidence" not in pred.columns:
        errors.append("missing confidence column")
    else:
        bad_conf = corrected[
            corrected["confidence"].isna()
            | (corrected["confidence"] < 0)
            | (corrected["confidence"] > 1)
        ]
        if len(bad_conf):
            errors.append(f"{len(bad_conf)} corrected rows have confidence outside [0, 1]")

    invalid_corrected = corrected[
        corrected.geometry.isna() | corrected.geometry.is_empty | ~corrected.geometry.is_valid
    ]
    if len(invalid_corrected):
        errors.append(f"{len(invalid_corrected)} corrected rows have null, empty, or invalid geometry")

    invalid_flagged = flagged[
        flagged.geometry.isna() | flagged.geometry.is_empty | ~flagged.geometry.is_valid
    ]
    if len(invalid_flagged):
        warnings.append(
            f"{len(invalid_flagged)} flagged rows inherit invalid official geometry; "
            "acceptable because flagged plots are kept unchanged"
        )

    if len(flagged):
        utm = _utm_for(village.plots)
        off_u = village.plots.to_crs(utm)
        pred_u = pred.to_crs(utm)
        moved = []
        for pn in flagged.index:
            if pn not in off_u.index:
                continue
            dist = pred_u.loc[pn, "geometry"].hausdorff_distance(off_u.loc[pn, "geometry"])
            if dist > FLAGGED_TOLERANCE_M:
                moved.append((pn, dist))
        if moved:
            sample = ", ".join(f"{pn} ({dist:.2f}m)" for pn, dist in moved[:5])
            errors.append(f"{len(moved)} flagged rows do not match official geometry: {sample}")

    attempted = len(pred)
    omitted = len(village.plots) - len(set(pred.index) & set(village.plots.index))
    print(f"attempted: {attempted} of {len(village.plots)} plots; omitted: {omitted}")
    print(f"corrected: {len(corrected)}; flagged: {len(flagged)}")
    if len(corrected) and "confidence" in corrected:
        print(f"confidence: min={corrected['confidence'].min():.3f}, "
              f"median={corrected['confidence'].median():.3f}, "
              f"max={corrected['confidence'].max():.3f}")

    if village.example_truths is not None:
        print(score(pred, village))

    for msg in warnings:
        print(f"WARNING: {msg}")
    for msg in errors:
        print(f"ERROR: {msg}")
    return 1 if errors else 0


def main(argv: list[str]) -> None:
    failed = 0
    for d in (argv or VILLAGES):
        failed |= _validate_one(d)
    raise SystemExit(failed)


if __name__ == "__main__":
    main(sys.argv[1:])
