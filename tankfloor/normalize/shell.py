"""Shell appurtenances (manways, doorsheets, nozzles) in the tank frame.

Source: 2011 Semper Fi report pp.40-41 "Shell Nozzle and Appurtenances
Table" gives each opening as a circumferential station (ft) from Manway A;
the 2026 ROSEN report (p.11) states stations run counterclockwise (viewed
from above). Config `shell_appurtenances.station_zero_azimuth_deg` pins
Manway A's compass azimuth (derived from the DWG 5-1 vector drawing, see
tools/derive_station_zero.py).

Tank frame: origin at tank centre, +X east, +Y north, inches; azimuth is
degrees clockwise from north, so x = r·sin(az), y = r·cos(az).
"""
import math


def station_to_azimuth_deg(station_ft, circumference_ft, zero_az_deg,
                           direction="ccw"):
    """Circumferential station -> compass azimuth (deg, clockwise from north).

    Counterclockwise stations (viewed from above) sweep toward decreasing
    azimuth; clockwise stations toward increasing azimuth.
    """
    if direction not in ("ccw", "cw"):
        raise ValueError(f"station_direction must be 'ccw' or 'cw', got {direction!r}")
    sweep = station_ft / circumference_ft * 360.0
    az = zero_az_deg - sweep if direction == "ccw" else zero_az_deg + sweep
    return az % 360.0


def azimuth_to_xy(az_deg, radius_in):
    """Point on a circle of radius_in at compass azimuth az_deg."""
    a = math.radians(az_deg)
    return radius_in * math.sin(a), radius_in * math.cos(a)


def tangent_rect(az_deg, radius_in, width_in, depth_in):
    """Four corners of a rectangle centred on the shell at az_deg: width_in
    along the shell (tangent), depth_in across it (radial), so the marker
    straddles the shell line. Returned in polygon order."""
    a = math.radians(az_deg)
    ux, uy = math.sin(a), math.cos(a)        # radial unit vector
    tx, ty = math.cos(a), -math.sin(a)       # tangent unit vector
    cx, cy = radius_in * ux, radius_in * uy
    hw, hd = width_in / 2.0, depth_in / 2.0
    return [
        (cx - tx * hw - ux * hd, cy - ty * hw - uy * hd),
        (cx + tx * hw - ux * hd, cy + ty * hw - uy * hd),
        (cx + tx * hw + ux * hd, cy + ty * hw + uy * hd),
        (cx - tx * hw + ux * hd, cy - ty * hw + uy * hd),
    ]


def appurtenance_positions(cfg, render_types=None):
    """Config items -> tank-frame positions, filtered to the rendered types.

    Each result carries the config fields plus az_deg, x, y (inches).
    render_types=None uses config `shell_appurtenances.render_types`; an
    empty list renders every type.
    """
    sa = cfg["shell_appurtenances"]
    d_ft = float(cfg["tank"]["diameter_ft"])
    circ_ft = math.pi * d_ft
    r_in = d_ft * 12.0 / 2.0
    types = sa.get("render_types") if render_types is None else render_types
    out = []
    for item in sa["items"]:
        if types and item["type"] not in types:
            continue
        az = station_to_azimuth_deg(float(item["station_ft"]), circ_ft,
                                    float(sa["station_zero_azimuth_deg"]),
                                    sa.get("station_direction", "ccw"))
        x, y = azimuth_to_xy(az, r_in)
        out.append({**item, "az_deg": az, "x": x, "y": y})
    return out
