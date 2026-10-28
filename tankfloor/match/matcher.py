"""Phase 3: match 2011 anomalies to 2026 features.

Matching runs within (plate_id_norm, side) groups on tank-level coordinates:

1. Candidate generation — 2026 features within `spatial_tolerance_in` of the
   2011 anomaly's extent box (2011 cluster rows span ranges; distance is
   measured to the box, not the midpoint).
2. Scoring — weighted cost of normalized components: spatial distance
   (dominant), size similarity, and depth plausibility (a matched 2026 depth
   should be >= the 2011 depth minus measurement tolerance; corrosion does
   not heal, so apparent healing beyond tolerance is penalized, while any
   amount of growth is free).
3. Assignment — Hungarian algorithm per group so each anomaly matches at
   most one counterpart; assignments costlier than `max_cost` are rejected.
4. Cluster pass — unmatched 2026 features inside a matched 2011 cluster's
   extent box (+margin) join that cluster's match group (coalesced pitting).

Classification reflects the two lists' censoring:
- `matched`
- `new_or_below_2011_threshold` — 2026 only; 2011 recorded topside only at
  remaining <= 0.120" (>=52% loss), so most of these are not literally new
- `not_found_repaired_or_below_2026_threshold` — 2011 only; 91 patches were
  installed after 2011 and the 2026 list is censored at >=49% depth
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


@dataclass
class MatchParams:
    spatial_tolerance_in: float
    depth_tolerance_in: float
    w_distance: float
    w_size: float
    w_depth: float
    max_cost: float
    cluster_margin_in: float


def from_config(cfg):
    m = cfg["matching"]
    return MatchParams(
        spatial_tolerance_in=m["spatial_tolerance_in"],
        depth_tolerance_in=m["depth_tolerance_in"],
        w_distance=m["weights"]["distance"],
        w_size=m["weights"]["size"],
        w_depth=m["weights"]["depth_plausibility"],
        max_cost=m["max_cost"],
        cluster_margin_in=m["cluster_margin_in"],
    )


def box_distance(cx, cy, length, width, px, py):
    """Distance from point (px, py) to the axis-aligned box centered at
    (cx, cy) with full extents length x width (0 inside the box)."""
    dx = max(0.0, abs(px - cx) - length / 2.0)
    dy = max(0.0, abs(py - cy) - width / 2.0)
    return (dx * dx + dy * dy) ** 0.5


def score_pair(r11, r26, params):
    """Match cost for a (2011 anomaly, 2026 feature) pair; inf if out of
    spatial tolerance. Components are normalized to [0, ~1]."""
    d = box_distance(r11["tank_x"], r11["tank_y"],
                     r11.get("length", 0.0) or 0.0,
                     r11.get("width", 0.0) or 0.0,
                     r26["tank_x"], r26["tank_y"])
    if d > params.spatial_tolerance_in:
        return float("inf")
    c_dist = d / params.spatial_tolerance_in

    # size: compare extents when the 2011 record has one (clusters);
    # single pit-gauge points carry no size -> neutral component
    l1, w1 = r11.get("length", 0.0) or 0.0, r11.get("width", 0.0) or 0.0
    l2, w2 = r26.get("length", 0.0) or 0.0, r26.get("width", 0.0) or 0.0
    if l1 > 0 or w1 > 0:
        big = max(l1, w1, l2, w2, 1.0)
        c_size = min(1.0, (abs(l1 - l2) + abs(w1 - w2)) / (2.0 * big))
    else:
        c_size = 0.0

    # depth plausibility: healing beyond measurement tolerance is suspect
    healing = (r11["depth"] - r26["depth"]) - params.depth_tolerance_in
    c_depth = min(1.0, max(0.0, healing) / (2.0 * params.depth_tolerance_in))

    return (params.w_distance * c_dist + params.w_size * c_size
            + params.w_depth * c_depth)


def match_group(d11, d26, params):
    """Hungarian assignment within one (plate, side) group.

    Returns [(idx11, idx26, cost)] using positional indices into the two
    DataFrames; assignments with cost > max_cost are rejected.
    """
    if len(d11) == 0 or len(d26) == 0:
        return []
    BIG = 1e6
    cost = np.full((len(d11), len(d26)), BIG)
    for i, (_, r11) in enumerate(d11.iterrows()):
        for j, (_, r26) in enumerate(d26.iterrows()):
            c = score_pair(r11, r26, params)
            if np.isfinite(c):
                cost[i, j] = c
    rows, cols = linear_sum_assignment(cost)
    return [(int(i), int(j), float(cost[i, j]))
            for i, j in zip(rows, cols)
            if cost[i, j] <= params.max_cost]


def match_inspections(df11, df26, params):
    """Full Phase 3 pipeline over all (plate_id_norm, side) groups.

    Returns (matches, cluster_members):
    - matches: DataFrame, one row per matched 2011<->2026 pair
    - cluster_members: DataFrame of extra 2026 features absorbed into a
      matched 2011 cluster's extent box (one-to-many second pass)
    """
    matches = []
    used26 = set()
    for (plate, side), g11 in df11.groupby(["plate_id_norm", "side"]):
        g26 = df26[(df26["plate_id_norm"] == plate) & (df26["side"] == side)]
        for i, j, c in match_group(g11, g26, params):
            r11, r26 = g11.iloc[i], g26.iloc[j]
            matches.append({
                "plate": plate,
                "side": side,
                "id_2011": r11["anomaly_id"],
                "id_2026": r26["anomaly_id"],
                "cost": round(c, 4),
                "distance_in": round(box_distance(
                    r11["tank_x"], r11["tank_y"],
                    r11.get("length", 0.0) or 0.0,
                    r11.get("width", 0.0) or 0.0,
                    r26["tank_x"], r26["tank_y"]), 2),
                "depth_2011": r11["depth"],
                "depth_2026": r26["depth"],
                "growth_in": round(r26["depth"] - r11["depth"], 4),
                "cluster_count_2011": r11.get("cluster_count", 1),
            })
            used26.add(r26["anomaly_id"])
    matches = pd.DataFrame(matches)

    # second pass: absorb unmatched 2026 features into matched cluster boxes
    cluster_members = []
    if len(matches):
        by_id11 = df11.set_index("anomaly_id")
        for _, m in matches.iterrows():
            r11 = by_id11.loc[m["id_2011"]]
            if (m["cluster_count_2011"] or 1) <= 1:
                continue
            g26 = df26[(df26["plate_id_norm"] == m["plate"])
                       & (df26["side"] == m["side"])
                       & (~df26["anomaly_id"].isin(used26))]
            for _, r26 in g26.iterrows():
                d = box_distance(r11["tank_x"], r11["tank_y"],
                                 r11.get("length", 0.0) or 0.0,
                                 r11.get("width", 0.0) or 0.0,
                                 r26["tank_x"], r26["tank_y"])
                if d <= params.cluster_margin_in:
                    cluster_members.append({
                        "id_2011": m["id_2011"],
                        "id_2026": r26["anomaly_id"],
                        "distance_in": round(d, 2),
                        "depth_2026": r26["depth"],
                    })
                    used26.add(r26["anomaly_id"])
    return matches, pd.DataFrame(cluster_members)
