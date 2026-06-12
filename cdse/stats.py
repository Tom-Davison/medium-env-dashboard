"""Mean-NDVI time series via the Sentinel Hub Statistical API.

One request covers the whole date range: the API computes per-acquisition
statistics server-side at reduced resolution, so charting a year of NDVI
costs one round trip instead of seventy downloads.
"""

from datetime import date

import requests

from config import STATISTICS_URL

_EVALSCRIPT = """
//VERSION=3
function setup() {
    return {
        input: [{bands: ["B04", "B08", "dataMask"]}],
        output: [
            {id: "ndvi", bands: 1, sampleType: "FLOAT32"},
            {id: "dataMask", bands: 1}
        ]
    };
}
function evaluatePixel(s) {
    return {
        ndvi: [(s.B08 - s.B04) / (s.B08 + s.B04 + 1e-6)],
        dataMask: [s.dataMask]
    };
}
"""


def ndvi_timeseries(
    bbox: tuple,
    start: date,
    end: date,
    token_mgr,
    max_cloud_pct: int = 20,
) -> list[dict]:
    """Return [{date, mean, p10, p90}] for every acquisition in the range."""
    payload = {
        "input": {
            "bounds": {"bbox": list(bbox)},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {"maxCloudCoverage": max_cloud_pct},
            }],
        },
        "aggregation": {
            "timeRange": {
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{end.isoformat()}T23:59:59Z",
            },
            "aggregationInterval": {"of": "P1D"},
            "evalscript": _EVALSCRIPT,
            "width": 256,
            "height": 256,
        },
        "calculations": {
            "default": {
                "statistics": {"default": {"percentiles": {"k": [10, 90]}}}
            }
        },
    }

    resp = requests.post(
        STATISTICS_URL, json=payload, headers=token_mgr.headers, timeout=120
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Statistical API request failed ({resp.status_code}): {resp.text[:300]}"
        )

    rows = []
    for item in resp.json().get("data", []):
        try:
            stats = item["outputs"]["ndvi"]["bands"]["B0"]["stats"]
        except KeyError:
            continue
        if stats.get("sampleCount", 0) == 0 or stats["mean"] is None:
            continue
        rows.append({
            "date": item["interval"]["from"][:10],
            "mean": stats["mean"],
            "p10": stats["percentiles"]["10.0"],
            "p90": stats["percentiles"]["90.0"],
        })
    return rows
