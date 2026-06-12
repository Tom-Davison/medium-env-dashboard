"""Scene search against the Sentinel Hub Catalog API.

Results come back one feature per tile, so we collapse them to one entry
per acquisition day. Each day keeps the cloudiest tile's figure, a
pessimistic but honest summary.

Coverage matters too: different days are imaged from different orbits, and
at swath edges a day's data may only cover a slice of the bounding box.
We union the data footprints per day and drop days that cover too little
of the box, otherwise a before/after pair can show barely-overlapping
imagery.
"""

from datetime import date

import requests
from shapely.geometry import box as bbox_geom, shape
from shapely.ops import unary_union

from config import CATALOG_URL


def search_scenes(
    bbox: tuple,
    start: date,
    end: date,
    max_cloud_pct: int,
    headers: dict,
    min_coverage_pct: int = 90,
) -> list[dict]:
    """Return [{date, cloud_pct, coverage_pct}] for every acquisition day
    whose data covers at least min_coverage_pct of the bbox, oldest first."""
    payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": list(bbox),
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "filter": f"eo:cloud_cover < {max_cloud_pct}",
        "filter-lang": "cql2-text",
        "fields": {
            "include": [
                "geometry",
                "properties.datetime",
                "properties.eo:cloud_cover",
            ],
        },
        "limit": 100,
    }

    days: dict[str, dict] = {}
    while True:
        resp = requests.post(CATALOG_URL, json=payload, headers=headers, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Catalog search failed ({resp.status_code}): {resp.text[:300]}"
            )
        body = resp.json()
        for feat in body.get("features", []):
            day = feat["properties"]["datetime"][:10]
            rec = days.setdefault(day, {"cloud": 0.0, "footprints": []})
            rec["cloud"] = max(rec["cloud"],
                               feat["properties"].get("eo:cloud_cover", 0.0))
            rec["footprints"].append(shape(feat["geometry"]))

        next_token = body.get("context", {}).get("next")
        if not next_token:
            break
        payload["next"] = next_token

    roi = bbox_geom(*bbox)
    scenes = []
    for day, rec in sorted(days.items()):
        footprint = unary_union(rec["footprints"])
        coverage = footprint.intersection(roi).area / roi.area * 100
        if coverage >= min_coverage_pct:
            scenes.append({
                "date": day,
                "cloud_pct": round(rec["cloud"], 1),
                "coverage_pct": round(coverage),
            })
    return scenes
