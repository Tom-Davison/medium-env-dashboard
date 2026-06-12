"""Fetch analysis-ready imagery through the Sentinel Hub Process API.

One POST per scene returns a small multi-band GeoTIFF: the API mosaics
whichever tiles cover the bounding box, resamples to a common grid, crops
server-side and scales to reflectance. A regional scene is a few MB and
arrives in seconds, no .SAFE archives, no 100 MB band files.
"""

import math
from pathlib import Path

import requests

from config import CACHE_DIR, MAX_DIM_PX, PROCESS_URL

# Everything the three indices need, plus a validity mask
BAND_ORDER = ["B03", "B04", "B08", "B11", "dataMask"]

_EVALSCRIPT = """
//VERSION=3
function setup() {
    return {
        input: [{bands: ["B03", "B04", "B08", "B11", "dataMask"],
                 units: "REFLECTANCE"}],
        output: {bands: 5, sampleType: "FLOAT32"}
    };
}
function evaluatePixel(s) {
    return [s.B03, s.B04, s.B08, s.B11, s.dataMask];
}
"""


def fetch_scene(bbox: tuple, day: str, token_mgr, max_cloud_pct: int = 100,
                on_progress=None) -> Path:
    """Download the bands for one acquisition day as a GeoTIFF.

    Files are cached in data/cache/ keyed on bbox and date, so repeat runs
    cost nothing. on_progress, if given, is called with
    (bytes_done, total_bytes_or_None) as the download streams in.
    """
    width, height = output_size(bbox)
    out = CACHE_DIR / f"{_slug(bbox)}_{day}_{width}x{height}.tif"
    if out.exists():
        return out

    payload = {
        "input": {
            "bounds": {"bbox": list(bbox)},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{day}T00:00:00Z",
                        "to": f"{day}T23:59:59Z",
                    },
                    "maxCloudCoverage": max_cloud_pct,
                    "mosaickingOrder": "leastCC",
                },
            }],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [
                {"identifier": "default", "format": {"type": "image/tiff"}}
            ],
        },
        "evalscript": _EVALSCRIPT,
    }

    # The server spends a while mosaicking before the first byte arrives;
    # the generous read timeout covers that. Streaming lets the caller show
    # download progress, and writing to a .part file means an interrupted
    # download never poisons the cache.
    resp = requests.post(
        PROCESS_URL, json=payload, headers=token_mgr.headers,
        stream=True, timeout=(30, 600),
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Process API request failed ({resp.status_code}): {resp.text[:300]}"
        )

    total = int(resp.headers.get("Content-Length", 0)) or None
    done = 0
    part = out.with_suffix(".part")
    with open(part, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)
    part.rename(out)
    return out


def output_size(bbox: tuple) -> tuple[int, int]:
    """Pixel dimensions for a bbox: ~30 m/px, longest side capped at MAX_DIM_PX."""
    lon_min, lat_min, lon_max, lat_max = bbox
    mid_lat = math.radians((lat_min + lat_max) / 2)
    width_m = (lon_max - lon_min) * 111_320 * math.cos(mid_lat)
    height_m = (lat_max - lat_min) * 111_320

    res = 30.0 * max(max(width_m, height_m) / (30.0 * MAX_DIM_PX), 1.0)
    return round(width_m / res), round(height_m / res)


def _slug(bbox: tuple) -> str:
    return "_".join(f"{v:.2f}" for v in bbox)
