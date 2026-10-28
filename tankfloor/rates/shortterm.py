"""Phase 4: short-term corrosion rates from matched anomaly pairs.

Implements only the arithmetic defined in the project brief:

    rate = (depth_2026 - depth_2011) / interval_years        [in/yr]

- Interval in decimal years from the actual inspection dates.
- StPr = topside (product-side) rate, UPr = underside rate (API 653 terms);
  tracked separately via the matched pair's side.
- Negative apparent growth (2026 shallower than 2011) is clamped to 0 and
  flagged, per the configured policy — corrosion doesn't heal; a negative
  delta is sizing noise, a bad match, or a repair.
- Rate uncertainty = sqrt(tol_2011^2 + tol_2026^2) / interval.

MRT projection, next-inspection-interval and repair-strategy math live in
tankfloor/rates/projection.py (API 653 5th Ed §4.4.5.1/§4.4.5.4, Table 4.4,
confirmed against the user's copy 2026-08-06).
"""
import math


def interval_years(d_start, d_end):
    """Decimal years between two dates (365.25-day year)."""
    return (d_end - d_start).days / 365.25


def pair_rates(matches, years, tol11, tol26, high_rate):
    """Per-pair short-term rates.

    matches: DataFrame with depth_2011, depth_2026, growth_in, side.
    Returns a copy with rate_in_per_yr, rate_uncertainty_in_per_yr,
    rate_flag columns. Negative growth -> rate 0 + 'negative_growth_clamped'.
    """
    out = matches.copy()
    unc = math.sqrt(tol11 ** 2 + tol26 ** 2) / years
    rates, flags = [], []
    for _, r in out.iterrows():
        growth = r["growth_in"]
        f = []
        if growth < 0:
            rate = 0.0
            f.append("negative_growth_clamped")
        else:
            rate = growth / years
        if rate > high_rate:
            f.append("high_growth")
        rates.append(round(rate, 6))
        flags.append(";".join(f))
    out["rate_in_per_yr"] = rates
    out["rate_uncertainty_in_per_yr"] = round(unc, 6)
    out["rate_flag"] = flags
    return out


def governing_rates(rated):
    """Per-plate and floor-wide maximum (governing) rates by side.

    Returns (per_plate DataFrame, floor dict). StPr = topside, UPr =
    underside; a side with no matched pairs reports None (cannot be
    measured from matching).
    """
    rows = []
    for plate, g in rated.groupby("plate"):
        top = g[g["side"] == "topside"]["rate_in_per_yr"]
        bot = g[g["side"] == "bottomside"]["rate_in_per_yr"]
        rows.append({
            "plate": plate,
            "n_pairs": len(g),
            "StPr_max": float(top.max()) if len(top) else None,
            "UPr_max": float(bot.max()) if len(bot) else None,
        })
    import pandas as pd

    per_plate = pd.DataFrame(rows)
    top_all = rated[rated["side"] == "topside"]["rate_in_per_yr"]
    bot_all = rated[rated["side"] == "bottomside"]["rate_in_per_yr"]
    floor = {
        "StPr_governing": float(top_all.max()) if len(top_all) else None,
        "UPr_governing": float(bot_all.max()) if len(bot_all) else None,
    }
    return per_plate, floor
