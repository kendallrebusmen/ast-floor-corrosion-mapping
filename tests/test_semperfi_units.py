"""Unit tests for the 2011 Semper Fi reduction-table parsing helpers.

Sample values are taken verbatim from the Bottom Plate Reduction Table
(2011 report, PDF pages 17-30).
"""
import pytest

from tankfloor.ingest.semperfi_2011 import (
    parse_inch_value,
    parse_inch_range,
    parse_location,
    resolve_plate,
    flags_from_x,
    parse_table_line,
    NOMINAL_IN,
)


class TestParseInchValue:
    def test_dotted_depth(self):
        assert parse_inch_value(".13") == pytest.approx(0.13)

    def test_remaining_with_curly_quote(self):
        assert parse_inch_value("0.120”") == pytest.approx(0.120)

    def test_plain_decimal(self):
        assert parse_inch_value("0.050") == pytest.approx(0.050)


class TestParseInchRange:
    def test_single_value_gives_zero_span(self):
        lo, hi = parse_inch_range(".13")
        assert lo == pytest.approx(0.13)
        assert hi == pytest.approx(0.13)

    def test_range(self):
        lo, hi = parse_inch_range(".13-.14")
        assert lo == pytest.approx(0.13)
        assert hi == pytest.approx(0.14)

    def test_remaining_range_with_quotes(self):
        lo, hi = parse_inch_range("0.110”-0.120”")
        assert lo == pytest.approx(0.110)
        assert hi == pytest.approx(0.120)

    def test_dash_means_missing(self):
        assert parse_inch_range("-") is None


class TestParseLocation:
    def test_single_position(self):
        mid, span = parse_location("58")
        assert mid == pytest.approx(58.0)
        assert span == pytest.approx(0.0)

    def test_leading_zero(self):
        mid, span = parse_location("09")
        assert mid == pytest.approx(9.0)

    def test_range_midpoint_and_span(self):
        mid, span = parse_location("21-34")
        assert mid == pytest.approx(27.5)
        assert span == pytest.approx(13.0)


class TestResolvePlate:
    def test_full_plate_and_letter(self):
        assert resolve_plate("2A", None) == (2, "A")

    def test_letter_only_carries_plate_forward(self):
        assert resolve_plate("B", 2) == (2, "B")

    def test_three_digit_plate(self):
        assert resolve_plate("104C", 96) == (104, "C")

    def test_letter_only_without_context_raises(self):
        with pytest.raises(ValueError):
            resolve_plate("B", None)


class TestFlagsFromX:
    """Flag-column X marks are mapped to columns by their x0 position.

    Header x0 anchors measured from the PDF: Internal=411, Underside=464,
    Critical Zone=522, N/E Corner=575, Mech=614.  Observed marks sit at
    ~419 (Internal), ~480 (Underside), ~578 (N/E Corner).
    """

    def test_internal_mark(self):
        assert flags_from_x([419.3]) == {"internal"}

    def test_underside_mark(self):
        assert flags_from_x([480.0]) == {"underside"}

    def test_ne_corner_mark(self):
        assert flags_from_x([578.2]) == {"ne_corner"}

    def test_internal_plus_ne_corner(self):
        assert flags_from_x([419.3, 578.2]) == {"internal", "ne_corner"}


def _words(*pairs):
    """Build pdfplumber-style word dicts from (text, x0) pairs."""
    return [{"text": t, "x0": x, "x1": x + 8} for t, x in pairs]


class TestParseTableLine:
    def test_single_pit_row(self):
        # "2B .13 0.120" 58 06 X PIT" -> internal/topside single pit
        words = _words(
            ("B", 75), (".13", 127), ("0.120”", 176),
            ("58", 266), ("06", 347), ("X", 419.3), ("PIT", 665),
        )
        rec = parse_table_line(words, prev_plate=2)
        assert rec["plate"] == 2
        assert rec["letter"] == "B"
        assert rec["side"] == "topside"
        assert rec["depth"] == pytest.approx(0.13)
        assert rec["remaining_thickness"] == pytest.approx(0.120)
        assert rec["x"] == pytest.approx(58.0)
        assert rec["y"] == pytest.approx(6.0)
        assert rec["length"] == pytest.approx(0.0)
        assert "PIT" in rec["notes"]

    def test_cluster_row_uses_midpoints(self):
        # "2A .13-.14 0.110"-0.120" 21-34 09-19 X PITTING (3)"
        words = _words(
            ("2A", 73), (".13-.14", 127), ("0.110”-0.120”", 176),
            ("21-34", 266), ("09-19", 347), ("X", 419.3),
            ("PITTING", 665), ("(3)", 700),
        )
        rec = parse_table_line(words, prev_plate=None)
        assert rec["plate"] == 2
        # worst case (max depth / min remaining) is reported
        assert rec["depth"] == pytest.approx(0.14)
        assert rec["remaining_thickness"] == pytest.approx(0.110)
        assert rec["x"] == pytest.approx(27.5)
        assert rec["y"] == pytest.approx(14.0)
        assert rec["length"] == pytest.approx(13.0)
        assert rec["width"] == pytest.approx(10.0)
        assert rec["cluster_count"] == 3

    def test_underside_row(self):
        words = _words(
            ("A", 75), (".16", 127), ("0.090”", 176),
            ("194", 266), ("15", 347), ("X", 480.0), ("PIT", 665),
        )
        rec = parse_table_line(words, prev_plate=15)
        assert rec["side"] == "bottomside"

    def test_missing_depth_derived_from_remaining(self):
        # "17A - 0.190" 158 38 X 1 INDICATION" -> underside row (mark at
        # x~477), depth derived from remaining thickness and flagged
        words = _words(
            ("17A", 73), ("-", 127), ("0.190”", 176),
            ("158", 266), ("38", 347), ("X", 477.0),
            ("1", 665), ("INDICATION", 675),
        )
        rec = parse_table_line(words, prev_plate=None)
        assert rec["side"] == "bottomside"
        assert rec["depth"] == pytest.approx(NOMINAL_IN - 0.190)
        assert rec["depth_derived"] is True
        assert rec["cluster_count"] == 1

    def test_non_table_line_returns_none(self):
        words = _words(("BOTTOM", 100), ("PLATE", 160), ("REDUCTION", 220))
        assert parse_table_line(words, prev_plate=None) is None
