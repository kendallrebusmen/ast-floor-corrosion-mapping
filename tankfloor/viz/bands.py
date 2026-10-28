"""Discrete depth-% bands for the scan maps (tank-group comment 3, 2026-09-02).

Depth as % of nominal wall is split into API 653-style traffic bands
(config `viz.depth_bands`): edges_pct are the lower bounds of bands 1..n,
everything below the first edge is band 0, and the last band (>= 100%) is
through-wall. Pure helpers shared by the matplotlib maps and the dashboard.
"""
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap


def depth_pct(depth_in, nominal_in):
    """Pit depth as % of nominal wall (0.14" of 0.25" -> 56.0)."""
    return depth_in / nominal_in * 100.0


def band_index(pct, edges_pct):
    """Band number for one depth %; edges are lower-inclusive."""
    return int(np.searchsorted(np.asarray(edges_pct), pct, side="right"))


def band_indices(pct, edges_pct):
    """Vectorised band_index."""
    return np.searchsorted(np.asarray(edges_pct), np.asarray(pct), side="right")


def bands_from_config(cfg):
    """Validated band spec: {edges_pct, labels, colors}."""
    b = cfg["viz"]["depth_bands"]
    edges = list(b["edges_pct"])
    labels, colors = list(b["labels"]), list(b["colors"])
    if not (len(labels) == len(colors) == len(edges) + 1):
        raise ValueError(
            f"viz.depth_bands: need {len(edges) + 1} labels and colors for "
            f"{len(edges)} edges (got {len(labels)} labels, {len(colors)} colors)")
    if edges != sorted(edges):
        raise ValueError("viz.depth_bands.edges_pct must be ascending")
    return {"edges_pct": edges, "labels": labels, "colors": colors}


def mpl_cmap_norm(bands):
    """ListedColormap + BoundaryNorm so scatter(c=depth_pct) colours by band."""
    edges = bands["edges_pct"]
    cmap = ListedColormap(bands["colors"], name="depth_bands")
    boundaries = [0.0, *edges, float(edges[-1]) + 1.0]
    norm = BoundaryNorm(boundaries, ncolors=len(bands["colors"]), clip=True)
    return cmap, norm
