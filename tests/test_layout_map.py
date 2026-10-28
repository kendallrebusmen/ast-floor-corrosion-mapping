"""Unit + integration tests for the Layout.MAP plate-geometry source.

Layout.MAP is the TBit scanner project's plate layout, exported from the
vendor's Visio drawing: exact plate polygons, per-plate RefPoint (local
origin) and Direction (local +y axis arrow), in millimeters, y already
page-like (most-negative y = north).
"""
from pathlib import Path

import pytest

from tankfloor.normalize.layout_map import (
    MM_PER_IN, build_layout, extent_violations, parse_layout_map,
)
from tankfloor.normalize.rosen_layout import page_to_tank, to_page

ROOT = Path(__file__).resolve().parents[1]
REAL_MAP = ROOT / "data" / "raw" / "Bottom" / "Tbit" / "Work" / "Layout.MAP"

SYNTHETIC = """;VSDtoMAP Converter V2.1  test
PLATE
\tnIndex\t\t=\t5
\tRefPoint\t=\t(1000.00,-3000.00)
\tDirection\t=\t(1100.00,-2900.00)(1500.00,-2900.00)
\tbCheckFlag\t=\t1
\tnCheckSum\t=\t1
\tPolyline\t=\t(1000,-2000)(3000,-2000)\\
\t\t\t\t\t(3000,-3000)(1000,-3000)(1000,-2000)
END_PLATE
PLATE
\tnIndex\t\t=\t7
\tRefPoint\t=\t(5000.00,-2000.00)
\tDirection\t=\t(4900.00,-2100.00)(4900.00,-2600.00)
\tbCheckFlag\t=\t1
\tnCheckSum\t=\t1
\tPolyline\t=\t(4000,-2000)(5000,-2000)(5000,-3000)(4000,-3000)(4000,-2000)
END_PLATE
PLATE
\tnIndex\t\t=\t8
\tbCheckFlag\t=\t1
\tnCheckSum\t=\t1
\tPolyline\t=\t(3000,-2000)(4000,-2000)(4000,-3000)(3000,-3000)(3000,-2000)
END_PLATE
INSTALLATION
\tPolyline\t=\t(0,0)(1,1)
END_INSTALLATION
"""


@pytest.fixture
def synth(tmp_path):
    p = tmp_path / "Layout.MAP"
    p.write_text(SYNTHETIC, encoding="latin-1")
    return p


class TestParse:
    def test_plates_and_installation_blocks(self, synth):
        raw = parse_layout_map(synth)
        assert sorted(raw) == [5, 7, 8]

    def test_polyline_continuation(self, synth):
        raw = parse_layout_map(synth)
        assert len(raw[5]["poly"]) == 5
        assert raw[5]["poly"][2] == (3000.0, -3000.0)

    def test_missing_refpoint(self, synth):
        raw = parse_layout_map(synth)
        assert raw[8]["ref"] is None and raw[8]["direction"] is None


class TestBuildLayout:
    def test_scale_is_isotropic_mm(self, synth):
        lay = build_layout(synth)
        assert lay["scale_x"] == lay["scale_y"] == pytest.approx(1 / MM_PER_IN)

    def test_y_horizontal_plate(self, synth):
        # plate 5: arrow points +x; y is page-like so origin (1000,-3000)
        # is the top-west corner (min x, min y) and +x runs down the page
        info = build_layout(synth)["plates"][5]
        assert info["y_horizontal"] is True
        assert info["y_sign"] == 1
        assert info["x_sign"] == 1
        assert info["origin"] == (1000.0, -3000.0)

    def test_y_vertical_plate(self, synth):
        # plate 7: arrow runs -2100 -> -2600 = decreasing page y (up);
        # origin (5000,-2000) is on the east edge, so +x points west
        info = build_layout(synth)["plates"][7]
        assert info["y_horizontal"] is False
        assert info["y_sign"] == -1
        assert info["x_sign"] == -1

    def test_transform_inferred_from_row_donor(self, synth):
        info = build_layout(synth)["plates"][8]
        assert info.get("inferred") is True
        # donor 5's origin is its west/top corner -> same corner of 8's rect
        assert info["origin"] == (3000.0, -3000.0)
        assert info["y_horizontal"] is True

    def test_to_page_round_trip(self, synth):
        lay = build_layout(synth)
        info = lay["plates"][5]
        # plate 5 is 2000mm (~78.7 in) along y, 1000mm (~39.4 in) across x
        px, py = to_page(info, 0.0, 0.0, lay["scale_x"], lay["scale_y"])
        assert (px, py) == info["origin"]
        px, py = to_page(info, 1000 / MM_PER_IN, 2000 / MM_PER_IN,
                         lay["scale_x"], lay["scale_y"])
        assert px == pytest.approx(3000.0)
        assert py == pytest.approx(-2000.0)

    def test_extent_violations(self, synth):
        lay = build_layout(synth)
        ok = {5: (1000 / MM_PER_IN, 2000 / MM_PER_IN)}
        assert extent_violations(lay, ok) == {}
        bad = {5: (1000 / MM_PER_IN, 2000 / MM_PER_IN + 20.0)}
        assert extent_violations(lay, bad) == {5: pytest.approx(20.0)}


@pytest.fixture(scope="module")
def lay():
    return build_layout(REAL_MAP)


@pytest.mark.skipif(not REAL_MAP.exists(), reason="raw Layout.MAP not present")
class TestRealFile:

    def test_all_110_plates_with_transforms(self, lay):
        assert len(lay["plates"]) == 110
        assert all(i["origin"] is not None for i in lay["plates"].values())
        inferred = [p for p, i in lay["plates"].items() if i.get("inferred")]
        assert inferred == [50]     # the one plate without RefPoint in the file

    def test_tank_extent_close_to_117_ft(self, lay):
        xs = [v for i in lay["plates"].values()
              for v in (i["rect"][0], i["rect"][2])]
        ys = [v for i in lay["plates"].values()
              for v in (i["rect"][1], i["rect"][3])]
        for extent_mm in (max(xs) - min(xs), max(ys) - min(ys)):
            assert extent_mm / MM_PER_IN == pytest.approx(1404.0, abs=12.0)

    def test_interior_plate_drawn_size(self, lay):
        # full plates draw ~246.5 x 70.5 in (lap-riveted overlap eats a few
        # inches off the 251 x 75 nominal)
        x0, top, x1, bottom = lay["plates"][20]["rect"]
        assert (x1 - x0) / MM_PER_IN == pytest.approx(246.5, abs=1.0)
        assert (bottom - top) / MM_PER_IN == pytest.approx(70.5, abs=1.0)

    def test_orientation_matches_vendor_map(self, lay):
        # Layout.MAP's y is already page-like: plate 1's row has the most
        # NEGATIVE y = top of the vendor map ("north" in the pipeline frame),
        # plates 105-110 sit at the bottom. Verified against the PDF floor
        # map (plate centers agree to ~3 in median; negating y mirrors N-S).
        y1 = lay["plates"][1]["rect"][1]
        y108 = lay["plates"][108]["rect"][1]
        assert y1 < y108
        x0, top, x1, bottom = lay["plates"][1]["rect"]
        _, ty = page_to_tank(lay, (x0 + x1) / 2, (top + bottom) / 2)
        assert ty > 0
