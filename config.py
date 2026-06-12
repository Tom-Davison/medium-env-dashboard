from pathlib import Path

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / "data" / "cache"
PROCESSED_DIR = ROOT / "data" / "processed"

for _d in (CACHE_DIR, PROCESSED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Study regions as (lon_min, lat_min, lon_max, lat_max).
# Keep boxes under about a degree a side as the Process API caps output at
# 2500 px per dimension, so a bigger box just means coarser pixels.
PRESETS = {
    "London, UK": (-0.45, 51.30, 0.25, 51.65),
    "Po Valley, Italy": (10.50, 44.80, 11.40, 45.30),
    "Nile Delta, Egypt": (30.80, 30.70, 31.60, 31.30),
}

DEFAULT_REGION = "London, UK"
DEFAULT_CLOUD_PCT = 20

# Hide acquisition days whose data covers less of the box than this;
# partial swaths make before/after comparisons meaningless.
MIN_COVERAGE_PCT = 90

# Longest side of fetched rasters, in pixels
MAX_DIM_PX = 1500

# CDSE endpoints
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)
SH_BASE = "https://sh.dataspace.copernicus.eu/api/v1"
CATALOG_URL = f"{SH_BASE}/catalog/1.0.0/search"
PROCESS_URL = f"{SH_BASE}/process"
STATISTICS_URL = f"{SH_BASE}/statistics"
