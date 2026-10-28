"""Unit tests for decoding ROSEN's floor-map (bottom layout) pages.

Plate-number labels on the layout pages extract with each glyph overprinted
9x ('888888888999999999' -> '89'). Axis labels are bare 'x'/'y' words.
"""
import pytest

from tankfloor.normalize.rosen_layout import decode_label


class TestDecodeLabel:
    def test_single_digit(self):
        assert decode_label("111111111") == 1

    def test_two_digits(self):
        assert decode_label("888888888999999999") == 89

    def test_three_digits(self):
        assert decode_label("111111111000000000333333333") == 103

    def test_repeated_same_digit(self):
        # plate 11: '1' glyph overprinted 18 times
        assert decode_label("1" * 18) == 11

    def test_trailing_axis_letter_stripped(self):
        assert decode_label("444444444222222222x") == 42

    def test_non_label_returns_none(self):
        assert decode_label("Classification") is None
        assert decode_label("x") is None

    def test_wrong_multiple_returns_none(self):
        assert decode_label("11111") is None
