"""Static floor-map plots (matplotlib) on the vendor plate geometry.

All plots share `_draw_floor`: shell circle, vendor plate polygons, plate
numbers, north arrow and (optionally) shell appurtenances such as manways.

Colour encodings:
- plot_platemap: pit depth. With `bands` (viz.depth_bands) the markers use
  discrete API 653-style depth-% bands; without, a continuous inch scale.
- plot_rates_map: short-term rate (sequential blue ramp).
- plot_overlay: inspection (2011 orange / 2026 blue).
"""
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Polygon  # noqa: E402

from tankfloor.normalize.rosen_layout import (  # noqa: E402
    TANK_DIAMETER_IN, page_to_tank,
)
from tankfloor.normalize.shell import tangent_rect  # noqa: E402
from tankfloor.normalize.tank_coords import (  # noqa: E402
    _ne_corner_flag, tank_xy_2011, tank_xy_2026,
)
from tankfloor.viz.bands import depth_pct, mpl_cmap_norm  # noqa: E402

# Sequential blue ramp (dataviz reference palette, steps 100 -> 700).
_BLUES = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
    "#0d366b",
]
RATE_CMAP = LinearSegmentedColormap.from_list("seq_blue", _BLUES)
DEPTH_CMAP = RATE_CMAP   # backwards-compatible alias (continuous depth-in scale)

_INK = "#3a3a37"
_MUTED = "#8a8a85"
_GRID = "#d8d7d3"

# categorical slots (dataviz reference palette, light surface)
_C_2026 = "#2a78d6"   # slot 1 blue
_C_2011 = "#eb6834"   # slot 2 orange
_C_CRIT = "#d03b3b"   # status: critical

_APP_DEPTH_IN = 18.0   # radial thickness of a shell-appurtenance marker


def _row_to_tank(row, layout, mode):
    """Plate-local inches -> tank inches via the shared Phase 2 transforms
    (normalize.tank_coords), so the static maps and the normalized CSVs can
    never disagree on a convention (e.g. the 2011 "N/E Corner" flag)."""
    plate = int(row["plate_id_raw"])
    if mode == "rosen":
        return tank_xy_2026(layout, plate, row["x"], row["y"])
    return tank_xy_2011(layout, plate, row["x"], row["y"],
                        ne_corner=_ne_corner_flag(row))


def _draw_floor(ax, layout, appurtenances=None):
    """Shell circle, vendor plate outlines, plate numbers, north arrow and
    shell appurtenances (dicts from normalize.shell.appurtenance_positions).
    Returns the shell radius in inches."""
    r_in = TANK_DIAMETER_IN / 2.0
    ax.set_aspect("equal")
    ax.add_patch(Circle((0, 0), r_in, fill=False, ec=_INK, lw=1.4, zorder=3))
    for plate, info in layout["plates"].items():
        pts = [page_to_tank(layout, px, py) for px, py in info["poly"]]
        ax.add_patch(Polygon(pts, closed=True, fill=False, ec=_GRID, lw=0.7,
                             zorder=1))
        x0, top, x1, bottom = info["rect"]
        (tx0, ty1) = page_to_tank(layout, x0, top)
        (tx1, ty0) = page_to_tank(layout, x1, bottom)
        ax.text((tx0 + tx1) / 2, (ty0 + ty1) / 2, str(plate), ha="center",
                va="center", color=_MUTED, fontsize=6.5, zorder=2)
    ax.annotate("N", xy=(0, r_in + 46), ha="center", va="bottom", fontsize=11,
                color=_INK)
    ax.annotate("", xy=(0, r_in + 42), xytext=(0, r_in + 6),
                arrowprops=dict(arrowstyle="-|>", color=_INK, lw=1.2))
    for a in appurtenances or []:
        pts = tangent_rect(a["az_deg"], r_in, float(a["size_in"]), _APP_DEPTH_IN)
        ax.add_patch(Polygon(pts, closed=True, fc=_INK, ec="white", lw=0.6,
                             zorder=6))
        # label just outside the shell, on the marker's radial
        k = (r_in + 34.0) / r_in
        lx, ly = a["x"] * k, a["y"] * k
        ax.text(lx, ly, a["label"], fontsize=8, color=_INK, zorder=6,
                ha="right" if lx < 0 else "left", va="center")
    return r_in


def _finish(fig, ax, r_in, title, subtitle, note, outfile):
    ax.set_title(title, fontsize=13, color=_INK, loc="left", pad=30)
    ax.text(0.0, 1.008, subtitle, transform=ax.transAxes, fontsize=9,
            color=_MUTED)
    if note:
        fig.text(0.06, 0.015, note, fontsize=8, color=_MUTED, wrap=True)
    pad = 110
    ax.set_xlim(-r_in - pad, r_in + pad)
    ax.set_ylim(-r_in - pad, r_in + pad)
    ax.axis("off")
    fig.savefig(outfile, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return outfile


def plot_platemap(df, layout, mode, title, subtitle, outfile,
                  marker_size=14.0, note=None, bands=None, appurtenances=None):
    """One inspection's anomalies on the floor. Colour = depth: discrete
    depth-% bands when `bands` is given, else continuous inches."""
    fig, ax = plt.subplots(figsize=(13.5, 14.2))
    r_in = _draw_floor(ax, layout, appurtenances)

    if bands:
        cmap, norm = mpl_cmap_norm(bands)
        if "depth_pct" in df.columns:
            cvals = df["depth_pct"].astype(float)
        else:
            cvals = depth_pct(df["depth"].astype(float),
                              df["nominal_thickness"].astype(float))
        edge, elw = _MUTED, 0.3
    else:
        cmap, norm = RATE_CMAP, plt.Normalize(0.0, 0.250)
        cvals = df["depth"]
        edge, elw = "white", 0.4

    for side, mk in (("topside", "o"), ("bottomside", "s")):
        mask = df["side"] == side
        sub = df[mask]
        if sub.empty:
            continue
        pts = [_row_to_tank(r, layout, mode) for _, r in sub.iterrows()]
        ax.scatter(
            [p[0] for p in pts], [p[1] for p in pts],
            c=cvals[mask], cmap=cmap, norm=norm,
            marker=mk, s=marker_size * (2.2 if side == "bottomside" else 1.0),
            linewidths=elw, edgecolors=edge, zorder=4,
        )

    n_top = (df["side"] == "topside").sum()
    n_bot = (df["side"] == "bottomside").sum()
    handles = [
        Line2D([], [], marker="o", ls="none", mfc="#5598e7", mec="white",
               ms=7, label=f"topside (product side) — {n_top}"),
        Line2D([], [], marker="s", ls="none", mfc="#5598e7", mec="white",
               ms=7, label=f"bottomside (soil side) — {n_bot}"),
    ]
    if appurtenances:
        handles.append(Line2D([], [], marker="s", ls="none", mfc=_INK,
                              mec="white", ms=7, label="shell manway"))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.01),
              frameon=False, fontsize=9, ncol=3)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.09)
    if bands:
        edges = [0.0, *bands["edges_pct"], bands["edges_pct"][-1] + 1.0]
        mids = [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:])]
        cb.set_ticks(mids)
        cb.set_ticklabels(bands["labels"])
        cb.set_label("pit depth, % of nominal wall (API 653-style bands)",
                     fontsize=9, color=_INK)
    else:
        cb.set_label("pit depth (in)", fontsize=9, color=_INK)
    cb.ax.tick_params(labelsize=8, colors=_INK)
    cb.outline.set_edgecolor(_GRID)
    return _finish(fig, ax, r_in, title, subtitle, note, outfile)


def plot_rates_map(rated, df26, layout, title, subtitle, outfile, note=None,
                   appurtenances=None):
    """Deliverable 4: matched pairs colored by short-term rate, high-growth
    ringed in the critical status color, all 2026 features as context."""
    fig, ax = plt.subplots(figsize=(13.5, 14.2))
    r_in = _draw_floor(ax, layout, appurtenances)

    ax.scatter(df26["tank_x"], df26["tank_y"], s=4, c="#c9c8c4",
               linewidths=0, zorder=3.5)

    high = rated[rated["rate_flag"].str.contains("high_growth", na=False)]
    ax.scatter(high["x_2026"], high["y_2026"], s=210, facecolors="none",
               edgecolors=_C_CRIT, linewidths=1.6, zorder=5)
    sc = ax.scatter(rated["x_2026"], rated["y_2026"],
                    c=rated["rate_in_per_yr"], cmap=RATE_CMAP,
                    vmin=0.0, vmax=max(0.008, rated["rate_in_per_yr"].max()),
                    s=52, linewidths=0.5, edgecolors="white", zorder=4)

    cb = fig.colorbar(sc, ax=ax, fraction=0.035, pad=0.09)
    cb.set_label("short-term corrosion rate (in/yr)", fontsize=9, color=_INK)
    cb.ax.tick_params(labelsize=8, colors=_INK)
    cb.outline.set_edgecolor(_GRID)

    handles = [
        Line2D([], [], marker="o", ls="none", mfc="#5598e7", mec="white",
               ms=8, label=f"matched pair ({len(rated)}) — color = rate"),
        Line2D([], [], marker="o", ls="none", mfc="none", mec=_C_CRIT,
               ms=11, label=f"high growth > 0.004 in/yr ({len(high)})"),
        Line2D([], [], marker="o", ls="none", mfc="#c9c8c4", ms=4,
               label="2026 feature (context)"),
    ]
    if appurtenances:
        handles.append(Line2D([], [], marker="s", ls="none", mfc=_INK,
                              mec="white", ms=7, label="shell manway"))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.01),
              frameon=False, fontsize=9, ncol=4)
    return _finish(fig, ax, r_in, title, subtitle, note, outfile)


def plot_overlay(df11, df26, layout, title, subtitle, outfile, note=None,
                 appurtenances=None):
    """Both inspections in tank coordinates on one floor map.

    Color = inspection (2011 orange, 2026 blue); marker = side
    (circle topside, square bottomside). Expects tank_x/tank_y columns.
    """
    fig, ax = plt.subplots(figsize=(13.5, 14.2))
    r_in = _draw_floor(ax, layout, appurtenances)

    for df, color, size, z in ((df26, _C_2026, 9, 4), (df11, _C_2011, 30, 5)):
        for side, mk in (("topside", "o"), ("bottomside", "s")):
            sub = df[df["side"] == side]
            if sub.empty:
                continue
            ax.scatter(sub["tank_x"], sub["tank_y"], marker=mk,
                       s=size * (2.0 if side == "bottomside" else 1.0),
                       facecolors=color, linewidths=0.4, edgecolors="white",
                       zorder=z)

    handles = [
        Line2D([], [], marker="o", ls="none", mfc=_C_2011, mec="white", ms=8,
               label=f"2011 indications — {len(df11)}"),
        Line2D([], [], marker="o", ls="none", mfc=_C_2026, mec="white", ms=6,
               label=f"2026 features (≥49%) — {len(df26)}"),
        Line2D([], [], marker="s", ls="none", mfc=_MUTED, mec="white", ms=7,
               label="square = bottomside"),
    ]
    if appurtenances:
        handles.append(Line2D([], [], marker="s", ls="none", mfc=_INK,
                              mec="white", ms=7, label="shell manway"))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.01),
              frameon=False, fontsize=9, ncol=4)
    return _finish(fig, ax, r_in, title, subtitle, note, outfile)
