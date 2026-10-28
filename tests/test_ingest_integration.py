"""Integration tests: full parses must reproduce the reports' own stated totals.

Ground truth comes from the reports themselves, independent of parser code:
- 2011 report p.2-5: 336 recordable indications = 333 topside + 3 underside.
- 2026 report p.20 & feature list: 5,077 features, ids 1..5077 contiguous.

These are slow (full-PDF text extraction); run with the full suite.
"""
from pathlib import Path

import pytest

from tankfloor.ingest import rosen_2026, semperfi_2011

DATA = Path(__file__).resolve().parents[1] / "data" / "raw"
PDF_2011 = DATA / "Port Everglades FL (C) - Tank 201- OOS June 2011.pdf"
PDF_2026 = DATA / "Port Everglades, FL - TK 201 - OOS July 2026 - Preliminary Report REV 1.pdf"


@pytest.fixture(scope="module")
def df_2011():
    return semperfi_2011.parse_report(PDF_2011)


@pytest.fixture(scope="module")
def df_2026():
    return rosen_2026.parse_report(PDF_2026)


class Test2011Invariants:
    def test_total_row_count_matches_report(self, df_2011):
        assert len(df_2011) == 336

    def test_side_split_matches_report(self, df_2011):
        counts = df_2011["side"].value_counts()
        assert counts["topside"] == 333
        assert counts["bottomside"] == 3

    def test_ne_corner_flag_count(self, df_2011):
        assert df_2011["notes"].str.contains("ne_corner").sum() == 21

    def test_anomaly_ids_unique(self, df_2011):
        assert df_2011["anomaly_id"].is_unique

    def test_depth_plus_remaining_near_nominal(self, df_2011):
        """Depth + remaining should be ~0.250" except derived/odd rows."""
        measured = df_2011[~df_2011["notes"].str.contains("depth derived")]
        gap = (measured["depth"] + measured["remaining_thickness"] - 0.250).abs()
        # cluster rows pair max-depth with min-remaining, so allow their spread
        assert (gap <= 0.101).all()

    def test_hand_checked_row_2B(self, df_2011):
        r = df_2011.set_index("anomaly_id").loc["2011-002B"]
        assert r["depth"] == pytest.approx(0.13)
        assert r["remaining_thickness"] == pytest.approx(0.120)
        assert (r["x"], r["y"]) == (58.0, 6.0)
        assert r["side"] == "topside"

    def test_hand_checked_topside_row_15A(self, df_2011):
        # "15A .16 0.090” 194 15  [internal mark]  PIT"
        r = df_2011.set_index("anomaly_id").loc["2011-015A"]
        assert r["side"] == "topside"
        assert r["depth"] == pytest.approx(0.16)
        assert r["remaining_thickness"] == pytest.approx(0.090)

    def test_underside_rows_are_the_three_derived_rows(self, df_2011):
        """Underside = 17A, 30A, 41A (remaining-thickness-only calls).

        Max derived underside depth must match the report's stated
        'Maximum Underside Pit Depth 0.090"' (p.2-7).
        """
        under = df_2011[df_2011["side"] == "bottomside"]
        assert sorted(under["anomaly_id"]) == ["2011-017A", "2011-030A", "2011-041A"]
        assert under["depth"].max() == pytest.approx(0.090, abs=0.0011)


class Test2026Invariants:
    def test_total_row_count(self, df_2026):
        assert len(df_2026) == 5077

    def test_feature_numbers_contiguous(self, df_2026):
        nos = sorted(int(a.split("-")[1]) for a in df_2026["anomaly_id"])
        assert nos == list(range(1, 5078))

    def test_side_split(self, df_2026):
        counts = df_2026["side"].value_counts()
        assert counts["topside"] == 4725
        assert counts["bottomside"] == 352

    def test_depth_pct_bounds(self, df_2026):
        assert df_2026["depth_pct"].min() == 49
        assert df_2026["depth_pct"].max() == 98

    def test_plate_universe(self, df_2026):
        plates = set(df_2026["plate_id_raw"].astype(int))
        assert plates <= set(range(1, 111))
        assert len(plates) == 98  # 12 plates have no >=49% features

    def test_hand_checked_row_3376(self, df_2026):
        r = df_2026.set_index("anomaly_id").loc["2026-03376"]
        assert r["plate_id_raw"] == "89"
        assert r["x"] == pytest.approx(3.43)
        assert r["y"] == pytest.approx(97.13)
        assert r["depth_pct"] == 59
        assert r["depth"] == pytest.approx(0.1475)
        assert r["remaining_thickness"] == pytest.approx(0.1025)
        assert r["side"] == "topside"


class TestRepairList:
    def test_repair_counts_match_summary(self):
        """Report p.141: 56 replacement plates + 1 partial + 13 patches = 70."""
        df = rosen_2026.parse_repairs(PDF_2026)
        assert len(df) == 70
        counts = df["repair_type"].value_counts()
        assert counts["Replacement plate"] == 56
        assert counts["Partial replacement plate"] == 1
        assert counts.get("Rounded Rectangle", 0) == 13
