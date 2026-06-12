# Sentinel-2 Environment Dashboard

A Streamlit dashboard that compares land-surface change between any two
dates using real Sentinel-2 imagery from the Copernicus Data Space
Ecosystem (CDSE).

## What it shows

| Index | What it measures |
|---|---|
| **NDVI** | Vegetation density. Crops and forests score 0.4-0.9; bare soil and water near 0. |
| **NDBI** | Built-up land. Positive values highlight urban areas and quarries. |
| **NDWI** | Open water. Rivers, reservoirs and flooded fields show values above ~0.3. |

Pick a region and two acquisition dates and you get a swipe slider to
compare them, an interactive map, value histograms, and a mean-NDVI trend
line covering the whole search window.

## How it works

The app never downloads raw satellite products. It uses three Sentinel Hub
APIs that ship with every free CDSE account:

- **Catalog API** lists acquisition days matching your bounding box,
  date range and cloud threshold.
- **Process API** mosaics the tiles covering your box, crops and
  resamples them server-side, and returns one multi-band GeoTIFF per
  scene. Building the mosaic takes the server a minute or two for a
  regional box; after that the scene is cached on disk and loads
  instantly. The three indices are computed locally with numpy.
- **Statistical API** computes mean NDVI per acquisition across the whole
  date range in a single request, which powers the trend chart.

Fetched scenes are cached in `data/cache/` and the computed index rasters
are written to `data/processed/` as georeferenced GeoTIFFs you can open in
QGIS.

## Setup

You need Python 3.9 or later and a free CDSE account. Register at
<https://dataspace.copernicus.eu> (takes two minutes, no credit card).

```bash
# 1. Clone the repo
git clone https://github.com/Tom-Davison/medium-env-dashboard.git
cd medium-env-dashboard

# 2. Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

Next, create API credentials. The Sentinel Hub APIs authenticate with an
OAuth client rather than your account password:

4. Log in at <https://shapps.dataspace.copernicus.eu/dashboard/>
5. Go to **User settings → OAuth clients → Create**
6. Give it a name and click create. Copy the **client id** and **client
   secret** straight away; the secret is shown only once.

Finally, put the credentials where the app can find them:

```bash
# 7. Copy the template and paste in the id and secret from step 6
cp .env.example .env
```

Your `.env` should end up looking like:

```
SH_CLIENT_ID=sh-12345678-abcd-...
SH_CLIENT_SECRET=...
```

## Running the dashboard

```bash
streamlit run app.py
```

Open <http://localhost:8501>, then:

1. Pick a region, date range and cloud threshold in the sidebar and click
   **Search scenes**. You get one entry per clear acquisition day. Days
   whose data covers less than 90% of the region (orbit swath edges) are
   filtered out so before/after pairs always overlap.
2. Choose a *Before* and *After* day and click **Fetch imagery**. The
   first fetch of each scene takes a minute or two (the server builds the
   mosaic, then ~30 MB downloads with a progress bar); from then on it
   loads straight from the disk cache.
3. Switch between NDVI / NDBI / NDWI instantly (all bands are fetched up
   front), and click **Compute trend** for the NDVI time series.

## Project structure

```
medium-env-dashboard/
├── app.py                 # Streamlit entry point
├── config.py              # Regions, endpoints, paths
├── cdse/
│   ├── auth.py            # OAuth2 token management
│   ├── catalog.py         # Acquisition-day search
│   ├── process.py         # Scene fetching (Process API)
│   └── stats.py           # NDVI time series (Statistical API)
├── processing/
│   └── indices.py         # NDVI, NDBI, NDWI with numpy
├── viz/
│   └── maps.py            # Colour rendering, folium maps, colourbars
├── data/
│   ├── cache/             # Fetched scene GeoTIFFs (gitignored)
│   └── processed/         # Index rasters (gitignored)
├── requirements.txt
└── .env.example
```

## Adding your own region

Edit `PRESETS` in `config.py`:

```python
PRESETS["My Region"] = (lon_min, lat_min, lon_max, lat_max)
```

Keep the box under about a degree a side as output resolution is capped at
1500 px on the longest edge, so bigger boxes just mean coarser pixels.

## Data source

Copernicus Sentinel-2 Level-2A (surface reflectance), distributed by the
European Space Agency via the
[Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu).
Contains modified Copernicus Service information (2026).
