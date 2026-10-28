"""Unit tests for the API 653 MRT projection / next-interval math.

Equation confirmed against the user's API 653 5th Edition (2014) copy
(2026-08-06): MRT = min(RTbc, RTip) − Or × (StPr + UPr), §4.4.5.1/§4.4.5.4;
Table 4.4 minimum 0.100" for bottom plates (no lining / leak detection).
"""
import numpy as np
import pandas as pd
import pytest

from tankfloor.rates.projection import (
    mrt_at, next_interval, repair_strategy, scenarios, years_remaining,
)


class TestMrtAt:
    def test_projection(self):
        # RT 0.1275", 10 yr at StPr 0.0076 + UPr 0.00132
        assert mrt_at(0.1275, 10.0, 0.0076, 0.00132) == pytest.approx(
            0.1275 - 10.0 * 0.008920, abs=1e-6)


class TestNextInterval:
    def test_repaired_at_49pct_scenario(self):
        # hand-checked: (0.1275 − 0.100) / (0.0076 + 0.00132) = 3.08 yr
        o = next_interval(rt_min=0.1275, mrt_min=0.100,
                          stpr=0.0076, upr=0.00132, cap_years=20.0)
        assert o == pytest.approx(3.081, abs=0.01)

    def test_as_found_is_zero(self):
        # worst as-found remaining 0.005" is already below the 0.100" floor
        o = next_interval(rt_min=0.005, mrt_min=0.100,
                          stpr=0.0076, upr=0.00132, cap_years=20.0)
        assert o == 0.0

    def test_cap_applies(self):
        # new 0.250" bottom with tiny rates would exceed the 20-yr cap
        o = next_interval(rt_min=0.250, mrt_min=0.100,
                          stpr=0.001, upr=0.001, cap_years=20.0)
        assert o == 20.0

    def test_zero_rates_hit_cap(self):
        o = next_interval(rt_min=0.250, mrt_min=0.100,
                          stpr=0.0, upr=0.0, cap_years=20.0)
        assert o == 20.0


# ---------------------------------------------------------------------------
# Tank-group comments 2026-09-02: per-anomaly years remaining and the
# ROSEN p.332 "Repair Strategy with Coating" reproduction (+ uncoated row).
# ---------------------------------------------------------------------------
MRT, UPR, CAP = 0.100, 0.00132, 20.0


class TestYearsRemaining:
    def test_typical_pair_uses_own_rate_plus_upr(self):
        # (0.1075 − 0.100) / (0.000166 + 0.00132) = 5.05 yr
        assert years_remaining(0.1075, 0.000166, MRT, UPR, CAP) == pytest.approx(5.05, abs=0.01)

    def test_clamped_zero_rate_leaves_upr_alone(self):
        # (0.125 − 0.100) / 0.00132 = 18.94 yr
        assert years_remaining(0.125, 0.0, MRT, UPR, CAP) == pytest.approx(18.94, abs=0.01)

    def test_cap(self):
        assert years_remaining(0.130, 0.0, MRT, UPR, CAP) == 20.0

    def test_below_mrt_is_zero(self):
        assert years_remaining(0.005, 0.007625, MRT, UPR, CAP) == 0.0

    def test_governing_pit_matches_next_interval(self):
        assert years_remaining(0.1275, 0.0076, MRT, UPR, CAP) == pytest.approx(3.081, abs=0.01)

    def test_zero_total_rate_hits_cap(self):
        assert years_remaining(0.2, 0.0, MRT, 0.0, CAP) == 20.0

    def test_vector_equals_scalar(self):
        rem = pd.Series([0.005, 0.1075, 0.125, 0.130, 0.1275, 0.250])
        rate = pd.Series([0.007625, 0.000166, 0.0, 0.0, 0.0076, 0.0])
        got = years_remaining(rem, rate, MRT, UPR, CAP)
        want = [next_interval(r, MRT, s, UPR, CAP) for r, s in zip(rem, rate)]
        assert list(np.round(got, 6)) == list(np.round(want, 6))


class TestRepairStrategy:
    """ROSEN p.332 columns: Or = (RT − 0.100)/UPr with UPr = (0.250 − RT)/93, StPr = 0."""

    @pytest.fixture
    def tbl(self):
        return repair_strategy(
            nominal_in=0.250, thresholds_pct=[35, 40, 45, 49, 51, 54, 56],
            mrt_min=MRT, years_installed=93, stpr_coated=0.0,
            stpr_uncoated=0.007625, cap_years=CAP,
        ).set_index("threshold_pct")

    def test_rt_after_repair(self, tbl):
        assert tbl.loc[49, "rt_after_repair_in"] == pytest.approx(0.1275)
        assert tbl.loc[35, "rt_after_repair_in"] == pytest.approx(0.1625)

    def test_upr_49_matches_config_value(self, tbl):
        assert tbl.loc[49, "upr_in_per_yr"] == pytest.approx(0.001317, abs=1e-6)
        assert abs(tbl.loc[49, "upr_in_per_yr"] - UPR) < 1e-5

    def test_coated_or_reproduces_rosen_uncapped(self, tbl):
        rosen = {35: 66.43, 40: 46.50, 45: 31.00, 49: 20.88, 51: 16.41, 54: 10.33, 56: 6.64}
        for pct, want in rosen.items():
            assert tbl.loc[pct, "or_coated_raw_yr"] == pytest.approx(want, abs=0.01), pct

    def test_coated_or_capped(self, tbl):
        assert list(tbl["or_coated_yr"].round(2)) == [20.0, 20.0, 20.0, 20.0, 16.41, 10.33, 6.64]

    def test_uncoated_or_uses_measured_stpr(self, tbl):
        # 0.0275 / (0.007625 + 0.001317) = 3.08
        assert tbl.loc[49, "or_uncoated_yr"] == pytest.approx(3.08, abs=0.01)
        assert tbl.loc[35, "or_uncoated_yr"] == pytest.approx(7.30, abs=0.01)
        assert tbl.loc[56, "or_uncoated_yr"] == pytest.approx(1.10, abs=0.01)
        assert (tbl["or_uncoated_raw_yr"] == tbl["or_uncoated_yr"]).all()

    def test_columns(self, tbl):
        assert list(tbl.columns) == [
            "rt_after_repair_in", "upr_in_per_yr", "or_coated_raw_yr", "or_coated_yr",
            "or_uncoated_raw_yr", "or_uncoated_yr"]


class TestScenarios:
    def test_three_rows_reproduce_phase4(self):
        rows = scenarios(rt_asfound=0.005, nominal_in=0.250, threshold_pct=49,
                         mrt_min=MRT, stpr=0.0076, upr=UPR, cap_years=CAP)
        assert [r["rt_in"] for r in rows] == pytest.approx([0.005, 0.1275, 0.250])
        assert [round(r["or_yr"], 2) for r in rows] == pytest.approx([0.0, 3.08, 16.82], abs=0.01)
        assert [r["key"] for r in rows] == ["asfound", "repaired", "new"]
        assert all("name" in r for r in rows)
