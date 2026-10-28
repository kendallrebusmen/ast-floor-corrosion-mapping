"""Smoke tests for the matplotlib floor maps (first tests for this module).

A tiny synthetic layout (two rectangular plates, identity page scale,
tank centre at page origin) exercises both plate-local conventions, the
depth-% banding and the shell-appurtenance markers without the PDFs.
"""
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from tankfloor.viz.bands import bands_from_config  # noqa: E402
from tankfloor.viz.platemap import (  # noqa: E402
    _draw_floor, plot_overlay, plot_platemap, plot_rates_map,
)

BANDS = bands_from_config({"viz": {"depth_bands": {
    "edges_pct": [50, 70, 90, 100],
    "labels": ["<50%", "50-69%", "70-89%", "90-99%", "through-wall"],
    "colors": ["#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#000000"],
}}})

MANWAYS = [
    {"id": "A", "type": "manway", "size_in": 24, "label": 'Manway A 24"',
     "az_deg": 288.8, "x": -664.6, "y": 226.2},
    {"id": "P", "type": "manway", "size_in": 20, "label": 'Manway P 20"',
     "az_deg": 108.8, "x": 664.6, "y": -226.2},
]


def _plate(x0, top, x1, bottom):
    return {
        "rect": (x0, top, x1, bottom),
        "poly": [(x0, top), (x1, top), (x1, bottom), (x0, bottom)],
        "origin": (x0, bottom), "x_sign": -1, "y_sign": 1, "y_horizontal": True,
    }


@pytest.fixture
def layout():
    # page y grows downward; tank centre at page (0, 0); 1 page unit = 1 inch
    return {"center": (0.0, 0.0), "scale_x": 1.0, "scale_y": 1.0,
            "plates": {1: _plate(-250, -80, 0, -5), 2: _plate(0, -80, 250, -5)}}


@pytest.fixture
def df():
    return pd.DataFrame({
        "plate_id_raw": [1, 1, 2], "side": ["topside", "topside", "bottomside"],
        "x": [10.0, 60.0, 30.0], "y": [20.0, 40.0, 30.0],
        "depth": [0.13, 0.20, 0.245], "nominal_thickness": [0.25, 0.25, 0.25],
        "depth_pct": [52, 80, 98], "tank_x": [-240.0, -190.0, 30.0],
        "tank_y": [25.0, 45.0, 35.0],
    })


class TestDrawFloor:
    def test_draws_plates_and_appurtenances(self, layout):
        fig, ax = plt.subplots()
        _draw_floor(ax, layout, appurtenances=MANWAYS)
        polys = [p for p in ax.patches if isinstance(p, Polygon)]
        assert len(polys) == len(layout["plates"]) + len(MANWAYS)
        labels = [t.get_text() for t in ax.texts]
        assert 'Manway A 24"' in labels and 'Manway P 20"' in labels
        plt.close(fig)

    def test_no_appurtenances_by_default(self, layout):
        fig, ax = plt.subplots()
        _draw_floor(ax, layout)
        assert len([p for p in ax.patches if isinstance(p, Polygon)]) == 2
        plt.close(fig)


class TestPlots:
    def test_platemap_banded_both_modes(self, layout, df, tmp_path):
        for mode in ("rosen", "semperfi_2011"):
            out = plot_platemap(df, layout, mode=mode, title="t", subtitle="s",
                                outfile=tmp_path / f"{mode}.png", bands=BANDS,
                                appurtenances=MANWAYS)
            assert out.exists() and out.stat().st_size > 0

    def test_platemap_without_bands_still_works(self, layout, df, tmp_path):
        out = plot_platemap(df, layout, mode="rosen", title="t", subtitle="s",
                            outfile=tmp_path / "plain.png")
        assert out.stat().st_size > 0

    def test_overlay_and_rates(self, layout, df, tmp_path):
        rated = pd.DataFrame({"x_2026": [-240.0], "y_2026": [25.0],
                              "rate_in_per_yr": [0.005], "rate_flag": ["high_growth"]})
        o = plot_overlay(df, df, layout, "t", "s", tmp_path / "ov.png",
                         appurtenances=MANWAYS)
        r = plot_rates_map(rated, df, layout, "t", "s", tmp_path / "r.png",
                           appurtenances=MANWAYS)
        assert o.stat().st_size > 0 and r.stat().st_size > 0
