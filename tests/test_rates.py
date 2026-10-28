"""Unit tests for Phase 4 short-term corrosion rates (hand-checked cases).

Only the short-term rate arithmetic defined in CLAUDE.md is covered here:
rate = (depth_2026 - depth_2011) / interval_years, negative growth clamped
to zero and flagged. MRT projection / next-interval formulas are NOT
implemented until confirmed against the user's API 653 5th Ed copy.
"""
from datetime import date

import pandas as pd
import pytest

from tankfloor.rates.shortterm import (
    interval_years,
    pair_rates,
    governing_rates,
)


class TestInterval:
    def test_known_interval(self):
        # 2011-07-01 -> 2026-07-31 = 5509 days = 15.083 yr
        y = interval_years(date(2011, 7, 1), date(2026, 7, 31))
        assert y == pytest.approx(15.083, abs=0.001)


def _matches():
    return pd.DataFrame([
        # hand-checked: growth 0.115" over 15.083 yr = 0.007625 in/yr
        dict(id_2011="2011-090B", id_2026="2026-03752", plate=90,
             side="topside", depth_2011=0.130, depth_2026=0.245,
             growth_in=0.115),
        # modest grower: 0.025 / 15.083 = 0.001657
        dict(id_2011="2011-053A", id_2026="2026-00617", plate=53,
             side="topside", depth_2011=0.130, depth_2026=0.155,
             growth_in=0.025),
        # apparent healing: clamped to 0 and flagged
        dict(id_2011="2011-060C", id_2026="2026-00921", plate=60,
             side="topside", depth_2011=0.220, depth_2026=0.125,
             growth_in=-0.095),
    ])


class TestPairRates:
    def test_rate_values(self):
        out = pair_rates(_matches(), 15.083, tol11=0.010, tol26=0.025,
                         high_rate=0.004)
        r = out.set_index("id_2011")
        assert r.loc["2011-090B", "rate_in_per_yr"] == pytest.approx(0.007625, abs=1e-5)
        assert r.loc["2011-053A", "rate_in_per_yr"] == pytest.approx(0.001657, abs=1e-5)

    def test_negative_growth_clamped_and_flagged(self):
        out = pair_rates(_matches(), 15.083, 0.010, 0.025, 0.004)
        r = out.set_index("id_2011").loc["2011-060C"]
        assert r["rate_in_per_yr"] == 0.0
        assert "negative_growth_clamped" in r["rate_flag"]

    def test_high_growth_flagged(self):
        out = pair_rates(_matches(), 15.083, 0.010, 0.025, 0.004)
        r = out.set_index("id_2011")
        assert "high_growth" in r.loc["2011-090B", "rate_flag"]
        assert "high_growth" not in r.loc["2011-053A", "rate_flag"]

    def test_uncertainty_combined(self):
        # sqrt(0.010^2 + 0.025^2)/15.083 = 0.001785
        out = pair_rates(_matches(), 15.083, 0.010, 0.025, 0.004)
        assert out["rate_uncertainty_in_per_yr"].iloc[0] == pytest.approx(
            0.001785, abs=1e-5)


class TestGoverning:
    def test_per_plate_and_floor_max(self):
        rated = pair_rates(_matches(), 15.083, 0.010, 0.025, 0.004)
        per_plate, floor = governing_rates(rated)
        assert per_plate.set_index("plate").loc[90, "StPr_max"] == pytest.approx(
            0.007625, abs=1e-5)
        assert floor["StPr_governing"] == pytest.approx(0.007625, abs=1e-5)
        # no bottomside pairs -> underside rate undefined, reported as None
        assert floor["UPr_governing"] is None
