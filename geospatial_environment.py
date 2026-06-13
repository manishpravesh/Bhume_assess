"""Force PROJ/GDAL to use pyproj's bundled database.

Some machines set a global PROJ_LIB or GDAL_DATA pointing at an unrelated, older PROJ
install, for example one bundled with PostgreSQL/PostGIS. That can shadow the wheel's
own data and break CRS transforms. Import this module before rasterio/pyproj are used to
pin PROJ to the version that ships with pyproj. On a clean machine this is a harmless
no-op.
"""
from __future__ import annotations

import os

import pyproj

_bundled = os.path.join(os.path.dirname(pyproj.__file__), "proj_dir", "share", "proj")
if os.path.isdir(_bundled):
    os.environ["PROJ_DATA"] = _bundled
    os.environ["PROJ_LIB"] = _bundled
    try:
        pyproj.datadir.set_data_dir(_bundled)
    except Exception:
        pass

# A stale GDAL_DATA can break GeoTIFF CRS handling; drop it and let the wheel decide.
os.environ.pop("GDAL_DATA", None)
