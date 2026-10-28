"""Shell-appurtenance geometry (tank-group comment 1, 2026-09-02).

Stations from the 2011 Semper Fi table (pp.40-41) run counterclockwise from
Manway A (2026 report p.11). Manway A azimuth 288.8 deg clockwise from north
was derived from the black Manway P rectangle on DWG 5-1 (2011 PDF p.60).
Tank frame: origin at centre, +X east, +Y north, inches.
"""
import math

import pytest

from tankfloor.normalize.shell import (
    appurtenance_positions, azimuth_to_xy, station_to_azimuth_deg, tangent_rect,
)

CIRC = math.pi * 117.0          # 367.57 ft
R = 117.0 * 12.0 / 2.0          # 702 in
ZERO = 288.8


class TestStationToAzimuth:
    def test_manway_a_is_the_zero(self):
        assert station_to_azimuth_deg(0.0, CIRC, ZERO) == pytest.approx(288.8)

    def test_manway_p_is_diametrically_opposite(self):
        az = station_to_azimuth_deg(183.75, CIRC, ZERO)
        assert az == pytest.approx(108.8, abs=0.05)

    def test_ccw_means_azimuth_decreases_with_station(self):
        assert station_to_azimuth_deg(CIRC / 4, CIRC, ZERO, "ccw") == pytest.approx(198.8, abs=1e-6)

    def test_cw_flips(self):
        assert station_to_azimuth_deg(CIRC / 4, CIRC, ZERO, "cw") == pytest.approx(18.8, abs=1e-6)

    def test_full_circumference_wraps_to_zero(self):
        assert station_to_azimuth_deg(CIRC, CIRC, ZERO) == pytest.approx(288.8, abs=1e-6)

    def test_16in_inlet_matches_dwg_tick(self):
        # X 16" inlet at 274'-0": drawn tick on DWG 5-1 at 21.4 deg
        assert station_to_azimuth_deg(274.0, CIRC, ZERO) == pytest.approx(21.4, abs=1.5)

    def test_unknown_direction_rejected(self):
        with pytest.raises(ValueError):
            station_to_azimuth_deg(0.0, CIRC, ZERO, "widdershins")


class TestAzimuthToXY:
    def test_north_is_plus_y(self):
        assert azimuth_to_xy(0.0, R) == pytest.approx((0.0, R))

    def test_east_is_plus_x(self):
        assert azimuth_to_xy(90.0, R) == pytest.approx((R, 0.0))

    def test_manway_a_is_wnw(self):
        x, y = azimuth_to_xy(288.8, R)
        assert x == pytest.approx(-664.6, abs=0.5)
        assert y == pytest.approx(226.2, abs=0.5)


class TestTangentRect:
    def test_north_marker_straddles_shell(self):
        pts = tangent_rect(0.0, R, width_in=24.0, depth_in=10.0)
        assert len(pts) == 4
        xs = sorted(p[0] for p in pts)
        ys = sorted(p[1] for p in pts)
        assert xs[0] == pytest.approx(-12.0) and xs[-1] == pytest.approx(12.0)
        assert ys[0] == pytest.approx(R - 5.0) and ys[-1] == pytest.approx(R + 5.0)

    def test_rotated_marker_keeps_radial_extent(self):
        pts = tangent_rect(288.8, R, 24.0, 10.0)
        dists = sorted(math.hypot(x, y) for x, y in pts)
        assert dists[0] == pytest.approx(math.hypot(R - 5, 12), abs=0.01)
        assert dists[-1] == pytest.approx(math.hypot(R + 5, 12), abs=0.01)


CFG = {
    "tank": {"diameter_ft": 117.0},
    "shell_appurtenances": {
        "station_direction": "ccw",
        "station_zero_azimuth_deg": 288.8,
        "render_types": ["manway"],
        "items": [
            {"id": "A", "type": "manway", "size_in": 24, "station_ft": 0.0, "label": 'Manway A 24"'},
            {"id": "P", "type": "manway", "size_in": 20, "station_ft": 183.75, "label": 'Manway P 20"'},
            {"id": "X", "type": "nozzle", "size_in": 16, "station_ft": 274.0, "label": '16" inlet'},
        ],
    },
}


class TestAppurtenancePositions:
    def test_only_render_types_returned(self):
        items = appurtenance_positions(CFG)
        assert [i["id"] for i in items] == ["A", "P"]

    def test_positions_in_tank_frame(self):
        a, p = appurtenance_positions(CFG)
        assert a["az_deg"] == pytest.approx(288.8)
        assert a["x"] < 0 and a["y"] > 0          # west-north-west
        assert p["x"] > 0 and p["y"] < 0          # east-south-east
        assert a["x"] == pytest.approx(-p["x"], abs=0.5)   # 183'-9" is 0.03 ft short of half the circumference
        assert math.hypot(a["x"], a["y"]) == pytest.approx(R, abs=1e-6)

    def test_carries_source_fields(self):
        a = appurtenance_positions(CFG)[0]
        assert a["label"] == 'Manway A 24"' and a["size_in"] == 24 and a["type"] == "manway"

    def test_render_types_override(self):
        items = appurtenance_positions(CFG, render_types=["nozzle"])
        assert [i["id"] for i in items] == ["X"]
