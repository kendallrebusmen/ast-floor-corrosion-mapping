"""Depth-% banding for the scan maps (tank-group comment 3, 2026-09-02).

Bands: <50 / 50-69 / 70-89 / 90-99 / through-wall, as % of nominal wall.
"""
import numpy as np
import pytest

from tankfloor.viz.bands import (
    band_index, band_indices, bands_from_config, depth_pct, mpl_cmap_norm,
)

EDGES = [50, 70, 90, 100]
CFG = {"viz": {"depth_bands": {
    "edges_pct": EDGES,
    "labels": ["<50%", "50-69%", "70-89%", "90-99%", "through-wall"],
    "colors": ["#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#000000"],
}}}


class TestDepthPct:
    def test_depth_over_nominal(self):
        assert depth_pct(0.14, 0.25) == pytest.approx(56.0)

    def test_through_wall(self):
        assert depth_pct(0.25, 0.25) == pytest.approx(100.0)


class TestBandIndex:
    @pytest.mark.parametrize("pct,idx", [
        (0, 0), (49, 0), (49.9, 0), (50, 1), (69, 1), (69.9, 1), (70, 2),
        (89.9, 2), (90, 3), (99, 3), (99.9, 3), (100, 4), (130, 4),
    ])
    def test_boundaries_are_lower_inclusive(self, pct, idx):
        assert band_index(pct, EDGES) == idx

    def test_vectorised(self):
        got = band_indices(np.array([49, 50, 70, 90, 100]), EDGES)
        assert got.tolist() == [0, 1, 2, 3, 4]


class TestConfig:
    def test_bands_from_config(self):
        b = bands_from_config(CFG)
        assert b["edges_pct"] == EDGES
        assert len(b["labels"]) == len(b["colors"]) == len(EDGES) + 1

    def test_mismatched_lengths_rejected(self):
        bad = {"viz": {"depth_bands": {"edges_pct": EDGES, "labels": ["a", "b"],
                                       "colors": ["#000"] * 5}}}
        with pytest.raises(ValueError):
            bands_from_config(bad)


class TestMatplotlib:
    def test_cmap_norm_maps_pct_to_band(self):
        cmap, norm = mpl_cmap_norm(bands_from_config(CFG))
        assert cmap.N == 5
        assert [norm(v) for v in (49, 50, 70, 90, 100)] == [0, 1, 2, 3, 4]
        assert cmap(norm(100))[:3] == (0.0, 0.0, 0.0)   # through-wall is black
