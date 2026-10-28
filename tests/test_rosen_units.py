"""Unit tests for the 2026 ROSEN feature-list parsing helpers.

Sample lines are verbatim from the Feature List (2026 report, PDF pages 25-137)
and the repair-patch list (pages 139-140).
"""
import pytest

from tankfloor.ingest.rosen_2026 import (
    parse_feature_line,
    parse_repair_line,
    depth_pct_to_inches,
)


class TestParseFeatureLine:
    def test_topside_tbit_line(self):
        rec = parse_feature_line(
            "3376 89 3.43 97.13 0.99 0.44 59 Metal Loss TBit SK Inspection Side"
        )
        assert rec["no"] == 3376
        assert rec["plate"] == 89
        assert rec["x"] == pytest.approx(3.43)
        assert rec["y"] == pytest.approx(97.13)
        assert rec["length"] == pytest.approx(0.99)   # X Size
        assert rec["width"] == pytest.approx(0.44)    # Y Size
        assert rec["depth_pct"] == 59
        assert rec["type"] == "Metal Loss"
        assert rec["method"] == "TBit"
        assert rec["zone"] == "SK"
        assert rec["side"] == "topside"

    def test_bottomside_line(self):
        rec = parse_feature_line(
            "3378 89 31.26 144.45 1.07 0.78 59 Metal Loss TBit SK Non Inspection Side"
        )
        assert rec["side"] == "bottomside"

    def test_zone_codes_with_slashes(self):
        rec = parse_feature_line(
            "10 4 1.0 2.0 0.5 0.5 55 Metal Loss TBit SK / CZ / CA Inspection Side"
        )
        assert rec["zone"] == "SK / CZ / CA"

    def test_visual_method(self):
        rec = parse_feature_line(
            "21 5 10.0 20.0 1.0 1.0 50 Metal Loss Visual SK Inspection Side"
        )
        assert rec["method"] == "Visual"

    def test_header_line_returns_none(self):
        assert parse_feature_line(
            "No. Plate No. X Pos. [in.] Y Pos. [in.] X Size [in.] Y Size [in.] "
            "Depth [%] Type Method Location Classification"
        ) is None

    def test_footer_line_returns_none(self):
        assert parse_feature_line("www.rosen-group.com") is None


class TestDepthConversion:
    def test_percent_of_nominal(self):
        assert depth_pct_to_inches(59, 0.250) == pytest.approx(0.1475)

    def test_49_percent_floor(self):
        assert depth_pct_to_inches(49, 0.250) == pytest.approx(0.1225)


class TestParseRepairLine:
    def test_replacement_plate(self):
        rec = parse_repair_line(
            "1 Replacement plate 5 -1.93 -1.97 -1.93 (2.00) 248.46 (2.00) "
            "75 (2.00) 251 (2.00) 0"
        )
        assert rec["no"] == 1
        assert rec["repair_type"] == "Replacement plate"
        assert rec["plate"] == 5
        assert rec["x_dim"] == pytest.approx(75.0)
        assert rec["y_dim"] == pytest.approx(251.0)

    def test_header_returns_none(self):
        assert parse_repair_line(
            "No. Type Plate No. X Pos.[in.] Y Pos.[in.] X Dir.[in.] Y Dir.[in.] "
            "X Dim.[in.] Y Dim.[in.] Angle to Y[°]"
        ) is None
