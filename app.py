"""
Sentinel-2 environment dashboard.

Pick a region and date range, choose two acquisition days, and compare
NDVI / NDBI / NDWI between them. Imagery comes from the Copernicus Data
Space Ecosystem via the Sentinel Hub Process API, which mosaics and crops
scenes server-side, each fetch is a few MB, not a full tile archive.

Run with:  streamlit run app.py
"""

import os
from datetime import date, timedelta

import streamlit as st
from dotenv import load_dotenv

from config import (DEFAULT_CLOUD_PCT, DEFAULT_REGION, MIN_COVERAGE_PCT,
                    PRESETS, PROCESSED_DIR)

load_dotenv()

st.set_page_config(
    page_title="Sentinel-2 Dashboard",
    page_icon="🌿",
    layout="wide",
)

INDICES = ["NDVI", "NDBI", "NDWI"]


# ── cached helpers ────────────────────────────────────────────────────────────
# Heavy libraries (rasterio, matplotlib, folium) are imported inside these
# functions so the first paint of the page is instant.

@st.cache_resource
def _token_manager():
    from cdse.auth import get_token_manager
    return get_token_manager()


@st.cache_data(show_spinner=False)
def _scene_days(bbox, start, end, max_cloud):
    from cdse.catalog import search_scenes
    return search_scenes(bbox, start, end, max_cloud,
                         _token_manager().headers, MIN_COVERAGE_PCT)


@st.cache_data(show_spinner=False)
def _scene(tif_path: str):
    """Load a fetched scene GeoTIFF and compute all three indices for it.

    Network fetching happens outside this function: cached functions must
    not touch UI elements, and the download needs a progress bar.
    """
    from pathlib import Path

    from processing.indices import (compute_index, index_stats, load_bands,
                                    save_geotiff)

    tif = Path(tif_path)
    bands = load_bands(tif)

    out = {}
    for name in INDICES:
        arr = compute_index(bands, name)
        out[name] = (arr, index_stats(arr))
        index_tif = PROCESSED_DIR / f"{tif.stem}_{name.lower()}.tif"
        if not index_tif.exists():
            save_geotiff(arr, tif, index_tif)
    return out


@st.cache_data(show_spinner=False)
def _trend(bbox, start, end, max_cloud):
    from cdse.stats import ndvi_timeseries
    return ndvi_timeseries(bbox, start, end, _token_manager(), max_cloud)


# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")

    region = st.selectbox("Region", list(PRESETS),
                          index=list(PRESETS).index(DEFAULT_REGION))

    col_a, col_b = st.columns(2)
    start = col_a.date_input("From", value=date.today() - timedelta(days=365))
    end = col_b.date_input("To", value=date.today())

    max_cloud = st.slider("Max cloud cover %", 0, 50, DEFAULT_CLOUD_PCT)

    search = st.button("Search scenes", type="primary", use_container_width=True)

    st.caption(
        "Needs free CDSE OAuth credentials in `.env`, the README has the "
        "two-minute setup."
    )

# ── header ────────────────────────────────────────────────────────────────────

st.title("Sentinel-2 Environment Dashboard")
st.caption(
    "Powered by the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu) · "
    "Sentinel-2 Level-2A surface reflectance"
)

with st.expander("What do these indices measure?"):
    st.markdown(
        """
| Index | Formula | What it shows |
|---|---|---|
| **NDVI** | (NIR - Red) / (NIR + Red) | Vegetation density and health. Crops and forests score 0.4-0.9; bare soil and water sit near 0 or below. |
| **NDBI** | (SWIR - NIR) / (SWIR + NIR) | Built-up and bare land. Positive values highlight urban areas and quarries. |
| **NDWI** | (Green - NIR) / (Green + NIR) | Open water. Rivers, lakes and flooded fields show values above ~0.3. |
        """
    )

# ── step 1: search ────────────────────────────────────────────────────────────

if search:
    if not (os.getenv("SH_CLIENT_ID") and os.getenv("SH_CLIENT_SECRET")):
        st.error(
            "Credentials not found. Copy `.env.example` to `.env` and add "
            "your OAuth client id and secret, see the README."
        )
        st.stop()
    if end <= start:
        st.error("End date must be after start date.")
        st.stop()

    with st.spinner("Searching the catalogue…"):
        try:
            scenes = _scene_days(PRESETS[region], start, end, max_cloud)
        except Exception as exc:
            st.error(f"Search failed: {exc}")
            st.stop()

    st.session_state.scenes = scenes
    # Freeze the parameters the search used so later steps stay consistent
    # even if the sidebar changes.
    st.session_state.params = (PRESETS[region], start, end, max_cloud)
    st.session_state.pop("pair", None)
    st.session_state.pop("trend", None)

    if not scenes:
        st.warning("No scenes matched. Widen the date range or raise the "
                   "cloud threshold.")

# ── step 2: pick a before/after pair ─────────────────────────────────────────

scenes = st.session_state.get("scenes")
if scenes:
    bbox, t_start, t_end, t_cloud = st.session_state.params

    st.subheader(f"{len(scenes)} clear days found")
    st.caption(f"Days whose data covers less than {MIN_COVERAGE_PCT}% of "
               "the region are hidden; partial swaths make comparisons "
               "meaningless.")
    labels = {s["date"]: f"{s['date']}  ·  {s['cloud_pct']}% cloud  ·  "
                         f"{s['coverage_pct']}% coverage"
              for s in scenes}
    days = list(labels)

    c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    before = c1.selectbox("Before", days, index=0, format_func=labels.get)
    after = c2.selectbox("After", days, index=len(days) - 1,
                         format_func=labels.get)
    fetch = c3.button("Fetch imagery", type="primary",
                      use_container_width=True)

    if fetch:
        if before == after:
            st.warning("Pick two different days.")
            st.stop()

        from cdse.process import fetch_scene

        tifs = st.session_state.setdefault("tifs", {})
        for day in (before, after):
            box = st.status(f"Fetching {day}…", expanded=True)
            bar = box.progress(
                0.0, text="Waiting for the server to mosaic the tiles, "
                          "this is the slow part, allow a minute or two")

            def show(done, total, _bar=bar):
                if total:
                    _bar.progress(min(done / total, 1.0),
                                  text=f"Downloading, {done / 1e6:.0f} of "
                                       f"{total / 1e6:.0f} MB")
                else:
                    _bar.progress(0.0,
                                  text=f"Downloading, {done / 1e6:.0f} MB so far")

            try:
                tifs[day] = str(fetch_scene(bbox, day, _token_manager(),
                                            t_cloud, on_progress=show))
            except Exception as exc:
                box.update(label=f"Fetch failed for {day}", state="error")
                st.error(f"Fetch failed for {day}: {exc}")
                st.stop()
            box.update(label=f"{day} ready", state="complete", expanded=False)
        st.session_state.pair = (before, after)

# ── step 3: compare ───────────────────────────────────────────────────────────

pair = st.session_state.get("pair")
if pair:
    before, after = pair
    bbox, t_start, t_end, t_cloud = st.session_state.params
    scene_b = _scene(st.session_state.tifs[before])
    scene_a = _scene(st.session_state.tifs[after])

    index = st.radio("Index", INDICES, horizontal=True)
    arr_b, _ = scene_b[index]
    arr_a, _ = scene_a[index]

    import numpy as np

    from processing.indices import index_stats
    from viz.maps import make_colorbar, make_map, render_index

    # The two dates may have slightly different data gaps (orbits, cloud
    # masks), so compare numbers only where both have valid pixels.
    overlap = ~np.isnan(arr_b) & ~np.isnan(arr_a)
    arr_b_ov = np.where(overlap, arr_b, np.nan)
    arr_a_ov = np.where(overlap, arr_a, np.nan)
    stats_b = index_stats(arr_b_ov)
    stats_a = index_stats(arr_a_ov)

    img_b = render_index(arr_b, index)
    img_a = render_index(arr_a, index)

    st.pyplot(make_colorbar(index), use_container_width=False)

    tab_swipe, tab_map, tab_hist = st.tabs(
        ["Swipe comparison", "Interactive map", "Distribution"])

    with tab_swipe:
        from streamlit_image_comparison import image_comparison
        # in_memory keeps the component from writing image files to ./temp
        image_comparison(img1=img_b, img2=img_a,
                         label1=before, label2=after, width=900,
                         in_memory=True)

    with tab_map:
        from streamlit_folium import st_folium
        m = make_map([(before, img_b), (after, img_a)], bbox, index)
        st_folium(m, width=900, height=500, returned_objects=[],
                  key="compare_map")
        st.caption("Toggle the two dates with the layer control "
                   "(top right of the map).")

    with tab_hist:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 2.8))
        for arr, label, colour in ((arr_b_ov, before, "#e07b54"),
                                   (arr_a_ov, after, "#4c9a6b")):
            ax.hist(arr[~np.isnan(arr)], bins=80, range=(-1, 1),
                    alpha=0.6, color=colour, label=label)
        ax.set_xlabel(f"{index} value")
        ax.set_ylabel("Pixel count")
        ax.legend(fontsize=8)
        fig.tight_layout()
        st.pyplot(fig)

    delta = stats_a["mean"] - stats_b["mean"]
    st.caption(f"Statistics and histograms use the {overlap.mean() * 100:.0f}% "
               "of pixels valid on both dates, so the comparison is "
               "like-for-like.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Mean · {before}", f"{stats_b['mean']:.3f}")
    m2.metric(f"Mean · {after}", f"{stats_a['mean']:.3f}",
              delta=f"{delta:+.3f}")
    m3.metric(f"p10-p90 · {before}",
              f"{stats_b['p10']:.2f} to {stats_b['p90']:.2f}")
    m4.metric(f"p10-p90 · {after}",
              f"{stats_a['p10']:.2f} to {stats_a['p90']:.2f}")

    # ── NDVI trend over the whole search window ──────────────────────────────

    st.divider()
    st.subheader("NDVI trend")
    st.caption("Mean NDVI for every clear acquisition in the search window, "
               "computed server-side by the Statistical API, one request, "
               "no downloads.")

    if st.button("Compute trend"):
        with st.spinner("Aggregating…"):
            try:
                st.session_state.trend = _trend(bbox, t_start, t_end, t_cloud)
            except Exception as exc:
                st.error(f"Trend request failed: {exc}")

    trend = st.session_state.get("trend")
    if trend:
        import matplotlib.pyplot as plt
        import pandas as pd

        df = pd.DataFrame(trend)
        df["date"] = pd.to_datetime(df["date"])

        fig, ax = plt.subplots(figsize=(8, 3))
        ax.fill_between(df["date"], df["p10"], df["p90"],
                        alpha=0.2, color="#4c9a6b", label="p10-p90")
        ax.plot(df["date"], df["mean"], color="#2d6a4f",
                marker="o", markersize=3, linewidth=1.2, label="mean")
        ax.set_ylabel("NDVI")
        ax.legend(fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        st.pyplot(fig)
    elif trend is not None:
        st.info("No acquisitions found for the trend window.")

else:
    st.info("Search for scenes in the sidebar, then pick a before/after "
            "pair and click **Fetch imagery**.")
