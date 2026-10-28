"""Unit tests for tank-level coordinate normalization (Phase 2)."""
import pytest

from tankfloor.normalize.tank_coords import tank_xy_2011, tank_xy_2026

# Synthetic layout: one 100pt x 30pt plate, scales 3.0 in/pt both axes,
# tank center at page (100, 100). Plate rect x 40..140, top 55..85.
LAYOUT = {
    "scale_x": 3.0,
    "scale_y": 3.0,
    "center": (100.0, 100.0),
    "plates": {
        7: {
            "rect": (40.0, 55.0, 140.0, 85.0),
            "origin": (40.0, 55.0),   # NW corner
            "x_sign": 1, "y_sign": 1,
            "y_horizontal": True,
        },
    },
}


class TestTank2011:
    def test_origin_is_southwest_corner(self):
        # X=0 (west edge), Y=0 (SOUTH edge) -> page (40, 85)
        tx, ty = tank_xy_2011(LAYOUT, 7, 0.0, 0.0)
        assert tx == pytest.approx((40 - 100) * 3.0)   # -180 (west of center)
        assert ty == pytest.approx((100 - 85) * 3.0)   # +45 (north of center)

    def test_x_increases_east_y_increases_north(self):
        tx, ty = tank_xy_2011(LAYOUT, 7, 30.0, 15.0)
        assert tx == pytest.approx(-180 + 30)
        assert ty == pytest.approx(45 + 15)

    def test_ne_corner_flag_measures_from_northeast_corner(self):
        # Report column "N/E Corner": X runs WEST from the east edge, Y SOUTH
        # from the north edge. X=0, Y=0 -> page (140, 55) -> tank (120, 135).
        tx, ty = tank_xy_2011(LAYOUT, 7, 0.0, 0.0, ne_corner=True)
        assert tx == pytest.approx((140 - 100) * 3.0)
        assert ty == pytest.approx((100 - 55) * 3.0)
        tx, ty = tank_xy_2011(LAYOUT, 7, 30.0, 15.0, ne_corner=True)
        assert tx == pytest.approx(120 - 30)
        assert ty == pytest.approx(135 - 15)


class TestAddTankCoords2011:
    def test_flag_in_notes_switches_origin(self):
        import pandas as pd

        from tankfloor.normalize.tank_coords import add_tank_coords

        df = pd.DataFrame({
            "plate_id_raw": [7, 7], "x": [0.0, 0.0], "y": [0.0, 0.0],
            "notes": ["PIT", "PIT [flags: ne_corner]"],
        })
        out = add_tank_coords(df, LAYOUT, "2011")
        assert list(out["tank_x"]) == pytest.approx([-180.0, 120.0])
        assert list(out["tank_y"]) == pytest.approx([45.0, 135.0])


class TestRealData2011:
    """Regression for 2026-09-02: two plate-104 indications plotted outside the
    shell because the N/E Corner flag was ignored. Skipped without the raw
    files."""

    def test_all_2011_indications_inside_shell_and_plate(self):
        from pathlib import Path

        import numpy as np
        from matplotlib.path import Path as MPath

        from tankfloor.ingest import semperfi_2011
        from tankfloor.normalize.layout_map import build_layout
        from tankfloor.normalize.rosen_layout import page_to_tank
        from tankfloor.normalize.tank_coords import add_tank_coords

        root = Path(__file__).resolve().parents[1]
        pdf = root / "data/raw/Port Everglades FL (C) - Tank 201- OOS June 2011.pdf"
        lmap = root / "data/raw/Bottom/Tbit/Work/Layout.MAP"
        if not (pdf.exists() and lmap.exists()):
            pytest.skip("raw files not present")
        layout = build_layout(lmap)
        df = add_tank_coords(semperfi_2011.parse_report(pdf), layout, "2011")
        r = np.hypot(df["tank_x"], df["tank_y"])
        assert int((r > 702.0).sum()) == 0
        outside_plate = 0
        for _, row in df.iterrows():
            poly = MPath([page_to_tank(layout, px, py)
                          for px, py in layout["plates"][int(row["plate_id_raw"])]["poly"]])
            outside_plate += not poly.contains_point((row["tank_x"], row["tank_y"]), radius=-1.0)
        assert outside_plate == 0


class TestTank2026:
    def test_rosen_axes_from_decoded_origin(self):
        # origin NW, y along page-x (east), x across page-y (south):
        # plate-local (x=9, y=30) -> page (40 + 30/3, 55 + 9/3) = (50, 58)
        tx, ty = tank_xy_2026(LAYOUT, 7, 9.0, 30.0)
        assert tx == pytest.approx((50 - 100) * 3.0)
        assert ty == pytest.approx((100 - 58) * 3.0)
