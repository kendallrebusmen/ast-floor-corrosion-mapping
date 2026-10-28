"""API 653 MRT projection, next-internal-inspection interval, per-anomaly
years remaining, and the coated/uncoated repair-strategy table.

Equation confirmed against the user's API 653 5th Edition (2014) copy on
2026-08-06 (do not alter without re-confirming):

    MRT = min(RTbc, RTip) − Or × (StPr + UPr)        [§4.4.5.1 / §4.4.5.4]

- RTbc / RTip: minimum remaining thickness after repairs (bottom-side /
  internal), inches
- Or: interval to next internal inspection, years (capped, Table 6.1 basis)
- StPr / UPr: topside / underside corrosion rates, in/yr
- Minimum acceptable MRT at next inspection from Table 4.4
  (0.100" bottom plates for this tank's configuration; 0.125" critical zone)

Repair-strategy table (tank-group request 2026-09-02) reproduces ROSEN's
p.332 "Repair Strategy with Coating — Bottom Plates" worksheet: for each
repair threshold, RT after repair = nominal × (1 − pct); UPr is the
long-term average (nominal − RT) / years_installed; the coated row takes
StPr = 0 (ROSEN's coating credit) and the uncoated row the measured
governing StPr. ROSEN prints Or uncapped; both raw and capped are kept.
"""
import numpy as np
import pandas as pd


def mrt_at(rt_min, or_years, stpr, upr):
    """Projected minimum remaining thickness after or_years."""
    return rt_min - or_years * (stpr + upr)


def next_interval(rt_min, mrt_min, stpr, upr, cap_years):
    """Solve MRT = mrt_min for Or; clamp to [0, cap_years].

    Zero combined rate means the thickness never degrades: the cap governs.
    """
    if rt_min <= mrt_min:
        return 0.0
    total = stpr + upr
    if total <= 0:
        return float(cap_years)
    return float(min(cap_years, (rt_min - mrt_min) / total))


def years_remaining(remaining_in, rate_in_per_yr, mrt_min, upr, cap_years):
    """Vectorised next_interval for per-anomaly remaining life.

    years = (remaining − mrt_min) / (rate + upr), 0 when already at or below
    mrt_min, cap when the combined rate is zero, never above cap. Accepts
    scalars, numpy arrays or pandas Series (a Series keeps its index).
    """
    rem = np.asarray(remaining_in, dtype=float)
    total = np.asarray(rate_in_per_yr, dtype=float) + float(upr)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = (rem - mrt_min) / total
    yrs = np.where(rem <= mrt_min, 0.0,
                   np.where(total <= 0, float(cap_years),
                            np.minimum(float(cap_years), raw)))
    if isinstance(remaining_in, pd.Series):
        return pd.Series(yrs, index=remaining_in.index)
    if np.ndim(yrs) == 0:
        return float(yrs)
    return yrs


def repair_strategy(nominal_in, thresholds_pct, mrt_min, years_installed,
                    stpr_coated, stpr_uncoated, cap_years):
    """ROSEN p.332 repair-strategy table plus an uncoated (measured StPr) row.

    One row per repair threshold (% of nominal). Columns: threshold_pct,
    rt_after_repair_in, upr_in_per_yr, or_coated_raw_yr, or_coated_yr,
    or_uncoated_raw_yr, or_uncoated_yr. *_raw_yr are uncapped (as ROSEN
    prints them); *_yr are clamped to [0, cap_years].
    """
    rows = []
    for pct in thresholds_pct:
        rt = nominal_in * (1.0 - pct / 100.0)
        upr = (nominal_in - rt) / years_installed
        rows.append({
            "threshold_pct": pct,
            "rt_after_repair_in": rt,
            "upr_in_per_yr": upr,
            "or_coated_raw_yr": _or_raw(rt, mrt_min, stpr_coated + upr),
            "or_coated_yr": next_interval(rt, mrt_min, stpr_coated, upr, cap_years),
            "or_uncoated_raw_yr": _or_raw(rt, mrt_min, stpr_uncoated + upr),
            "or_uncoated_yr": next_interval(rt, mrt_min, stpr_uncoated, upr, cap_years),
        })
    return pd.DataFrame(rows)


def _or_raw(rt, mrt_min, total_rate):
    if rt <= mrt_min:
        return 0.0
    if total_rate <= 0:
        return float("inf")
    return (rt - mrt_min) / total_rate


def scenarios(rt_asfound, nominal_in, threshold_pct, mrt_min, stpr, upr, cap_years):
    """The three floor-wide Or scenarios: as-found, all features at/above the
    repair threshold repaired, and a new nominal-thickness bottom."""
    rt_repaired = round(nominal_in * (1.0 - threshold_pct / 100.0), 6)
    spec = [
        ("asfound", "as-found (no repairs)", rt_asfound),
        ("repaired", f"repaired at {threshold_pct}% threshold", rt_repaired),
        ("new", f"new {nominal_in:.3f}\" bottom", nominal_in),
    ]
    return [{"key": k, "name": n, "rt_in": rt,
             "or_yr": next_interval(rt, mrt_min, stpr, upr, cap_years)}
            for k, n, rt in spec]
