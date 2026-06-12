"""Spectral index computation from the multi-band scene GeoTIFFs.

fetch_scene() saves bands in BAND_ORDER (B03, B04, B08, B11, dataMask)
with reflectance values in [0, 1]. Everything here is plain numpy.
"""

from pathlib import Path

import numpy as np

# index name -> (a, b) for (a - b) / (a + b)
FORMULAS = {
    "NDVI": ("B08", "B04"),  # vegetation: NIR vs red
    "NDBI": ("B11", "B08"),  # built-up land: SWIR vs NIR
    "NDWI": ("B03", "B08"),  # open water: green vs NIR
}


def load_bands(tif_path: Path) -> dict[str, np.ndarray]:
    """Read a scene GeoTIFF into a {band: 2-D float32 array} dict."""
    import rasterio  # deferred as rasterio is slow to import

    from cdse.process import BAND_ORDER

    with rasterio.open(tif_path) as src:
        stack = src.read().astype(np.float32)
    return dict(zip(BAND_ORDER, stack))


def compute_index(bands: dict[str, np.ndarray], index: str) -> np.ndarray:
    """Return the named index in [-1, 1], NaN outside the data mask."""
    a, b = (bands[name] for name in FORMULAS[index])
    with np.errstate(invalid="ignore", divide="ignore"):
        result = (a - b) / (a + b)
    result = np.clip(result, -1.0, 1.0).astype(np.float32)
    result[bands["dataMask"] < 0.5] = np.nan
    return result


def index_stats(arr: np.ndarray) -> dict:
    """Basic statistics over the valid pixels of an index array."""
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return {k: float("nan") for k in ("mean", "std", "p10", "p90")}
    return {
        "mean": float(valid.mean()),
        "std": float(valid.std()),
        "p10": float(np.percentile(valid, 10)),
        "p90": float(np.percentile(valid, 90)),
    }


def save_geotiff(arr: np.ndarray, ref_tif: Path, out_path: Path):
    """Write a single-band index raster, georeferenced like the source scene.

    These land in data/processed/ so they can be opened in QGIS or reused
    outside the app.
    """
    import rasterio

    with rasterio.open(ref_tif) as src:
        profile = src.profile.copy()
    profile.update(count=1, dtype="float32", nodata=float("nan"),
                   compress="deflate")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr, 1)
