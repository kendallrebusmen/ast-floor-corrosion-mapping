"""Unit tests for Phase 3 anomaly matching (hand-checked synthetic cases)."""
import pandas as pd
import pytest

from tankfloor.match.matcher import (
    box_distance,
    score_pair,
    match_group,
    MatchParams,
)

PARAMS = MatchParams(
    spatial_tolerance_in=12.0,
    depth_tolerance_in=0.050,
    w_distance=0.6,
    w_size=0.2,
    w_depth=0.2,
    max_cost=0.75,
    cluster_margin_in=6.0,
)


class TestBoxDistance:
    def test_point_anomaly_is_euclidean(self):
        # 2011 single pit (no extent): plain distance
        assert box_distance(10.0, 0.0, 0.0, 0.0, 13.0, 4.0) == pytest.approx(5.0)

    def test_inside_extent_box_is_zero(self):
        # cluster spanning 20x10 centered at (0,0): point inside -> 0
        assert box_distance(0.0, 0.0, 20.0, 10.0, 8.0, 3.0) == 0.0

    def test_outside_box_measures_from_edge(self):
        # box half-width 10 in x; point at x=13 -> 3 beyond edge
        assert box_distance(0.0, 0.0, 20.0, 10.0, 13.0, 0.0) == pytest.approx(3.0)


class TestScorePair:
    def _row11(self, **kw):
        base = dict(tank_x=0.0, tank_y=0.0, length=0.0, width=0.0, depth=0.130)
        base.update(kw)
        return pd.Series(base)

    def _row26(self, **kw):
        base = dict(tank_x=0.0, tank_y=0.0, length=1.0, width=0.5, depth=0.150)
        base.update(kw)
        return pd.Series(base)

    def test_perfect_pair_scores_low(self):
        cost = score_pair(self._row11(), self._row26(), PARAMS)
        assert cost < 0.1

    def test_distance_dominates(self):
        near = score_pair(self._row11(), self._row26(tank_x=2.0), PARAMS)
        far = score_pair(self._row11(), self._row26(tank_x=11.0), PARAMS)
        assert far > near

    def test_beyond_tolerance_is_infinite(self):
        cost = score_pair(self._row11(), self._row26(tank_x=13.0), PARAMS)
        assert cost == float("inf")

    def test_healed_corrosion_penalized(self):
        # 2026 depth much shallower than 2011: implausible (corrosion
        # doesn't heal); worse cost than a plausible grower
        heal = score_pair(self._row11(depth=0.20), self._row26(depth=0.13),
                          PARAMS)
        grow = score_pair(self._row11(depth=0.13), self._row26(depth=0.16),
                          PARAMS)
        assert heal > grow

    def test_growth_not_penalized(self):
        a = score_pair(self._row11(depth=0.13), self._row26(depth=0.13), PARAMS)
        b = score_pair(self._row11(depth=0.13), self._row26(depth=0.20), PARAMS)
        assert b == pytest.approx(a)


def _df(rows, insp):
    df = pd.DataFrame(rows)
    df["anomaly_id"] = [f"{insp}-{i}" for i in range(len(rows))]
    return df


class TestMatchGroup:
    def test_one_to_one_assignment(self):
        d11 = _df([dict(tank_x=0, tank_y=0, length=0, width=0, depth=0.13),
                   dict(tank_x=50, tank_y=0, length=0, width=0, depth=0.15)], "a")
        d26 = _df([dict(tank_x=1, tank_y=1, length=1, width=1, depth=0.15),
                   dict(tank_x=51, tank_y=0, length=1, width=1, depth=0.16),
                   dict(tank_x=200, tank_y=0, length=1, width=1, depth=0.13)], "b")
        pairs = match_group(d11, d26, PARAMS)
        assert {(i, j) for i, j, _ in pairs} == {(0, 0), (1, 1)}

    def test_each_anomaly_matches_at_most_once(self):
        # two 2011 pits close to ONE 2026 feature: only one gets it
        d11 = _df([dict(tank_x=0, tank_y=0, length=0, width=0, depth=0.13),
                   dict(tank_x=3, tank_y=0, length=0, width=0, depth=0.13)], "a")
        d26 = _df([dict(tank_x=1, tank_y=0, length=1, width=1, depth=0.15)], "b")
        pairs = match_group(d11, d26, PARAMS)
        assert len(pairs) == 1

    def test_far_apart_rejected(self):
        d11 = _df([dict(tank_x=0, tank_y=0, length=0, width=0, depth=0.13)], "a")
        d26 = _df([dict(tank_x=40, tank_y=40, length=1, width=1, depth=0.15)], "b")
        assert match_group(d11, d26, PARAMS) == []
