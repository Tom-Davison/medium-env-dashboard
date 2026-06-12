"""Colour rendering: index arrays to images, folium maps, colourbars."""

import numpy as np

# colourmap name and display range per index
STYLE = {
    "NDVI": ("RdYlGn", -0.2, 0.8),
    "NDBI": ("RdBu_r", -0.5, 0.5),
    "NDWI": ("RdBu", -0.5, 0.5),
}


def render_index(arr: np.ndarray, index: str):
    """Colourise an index array. Returns an RGBA PIL Image with nodata
    pixels fully transparent."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from PIL import Image

    cmap_name, vmin, vmax = STYLE[index]
    cmap = plt.get_cmap(cmap_name)
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    masked = np.ma.masked_invalid(arr)
    rgba = cmap(norm(masked))
    rgba[..., 3] = np.where(masked.mask, 0.0, 1.0)
    return Image.fromarray((rgba * 255).astype(np.uint8), mode="RGBA")


def make_map(layers: list[tuple], bbox: tuple, index: str):
    """Folium map with one toggleable overlay per (label, PIL image) pair."""
    import base64
    import io

    import folium

    lon_min, lat_min, lon_max, lat_max = bbox
    bounds = [[lat_min, lon_min], [lat_max, lon_max]]

    m = folium.Map(tiles="CartoDB positron")
    m.fit_bounds(bounds)

    for i, (label, img) in enumerate(layers):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        folium.raster_layers.ImageOverlay(
            image=f"data:image/png;base64,{b64}",
            bounds=bounds,
            opacity=0.8,
            name=f"{index} · {label}",
            show=(i == 0),
        ).add_to(m)

    folium.Rectangle(bounds=bounds, color="#333333", weight=1, fill=False).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def make_colorbar(index: str):
    """A thin matplotlib figure containing just the colourbar legend."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    cmap_name, vmin, vmax = STYLE[index]
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    fig, ax = plt.subplots(figsize=(5, 0.4))
    fig.subplots_adjust(bottom=0.5)
    cb = plt.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=plt.get_cmap(cmap_name)),
        cax=ax, orientation="horizontal",
    )
    cb.set_label(index, fontsize=9)
    fig.patch.set_alpha(0)
    return fig
