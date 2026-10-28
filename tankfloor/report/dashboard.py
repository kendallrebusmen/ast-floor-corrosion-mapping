"""Build the self-contained TK 201 HTML dashboard from processed outputs.

Reads data/processed CSVs + the calibrated layout and emits a single HTML
file (no external resources) suitable for publishing as a Claude artifact.

Contract with dashboard_template.html:
- `__DATA__` -> JSON with positional arrays; FIELDS names each slot and is
  emitted as DATA.fields so the template indexes by name, never by literal.
- `__STATS__` -> JSON of every number the prose quotes; the template fills
  `data-stat="key"` spans from it. STAT_KEYS is the closed set of keys
  (tests check the template only uses these).
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed"

FIELDS = {
    "a11": ["x", "y", "depth", "side", "id", "pct"],
    "a26": ["x", "y", "pct", "side", "yrs", "id"],
    "rates": ["x", "y", "rate", "high", "id11", "id26", "d11", "d26", "dist",
              "clamped", "yrs", "plate", "rem26", "review"],
    "nf": ["x", "y", "id", "flag", "nearest"],
    "high": ["id11", "id26", "plate", "d11", "d26", "rate", "dist", "yrs"],
}

STAT_KEYS = {
    # match / reconciliation counts
    "matched", "cluster", "notfound", "nearmiss", "watchlist", "new", "high",
    "clamped", "n11", "n26", "n11_top", "n11_bot", "n26_top", "n26_bot",
    "matched_pct", "medianDist", "patches",
    # rates
    "stpr", "stpr_unc", "upr", "years", "high_rate", "depth_tol",
    # projection parameters
    "mrt_min", "cap", "nominal", "threshold_pct", "years_installed",
    "coated_stpr",
    # scenarios (measured StPr) and their coated twins (StPr = coated_stpr)
    "rt_asfound", "rt_repaired", "rt_new",
    "or_asfound", "or_repaired", "or_new",
    "or_coated_asfound", "or_coated_repaired", "or_coated_new",
    "or_coated_repaired_raw",
    # deepest 2026 pit
    "deepest_pct", "deepest_rt", "deepest_plates",
    # per-anomaly years remaining
    "yrs_min_matched", "yrs_median_matched", "yrs_min_new",
}


def _round(v, nd=1):
    return round(float(v), nd)


def pack_plates(layout):
    from tankfloor.normalize.rosen_layout import page_to_tank

    plates = []
    for pid, info in sorted(layout["plates"].items()):
        poly = [page_to_tank(layout, px, py) for px, py in info["poly"]]
        x0, top, x1, bottom = info["rect"]
        cx, cy = page_to_tank(layout, (x0 + x1) / 2, (top + bottom) / 2)
        plates.append({
            "id": pid,
            "poly": [[_round(x), _round(y)] for x, y in poly],
            "c": [_round(cx), _round(cy)],
        })
    return plates


def pack_features(a11, a26, rated, nf):
    """Positional arrays for the map layers; slot order per FIELDS.

    Expects the derived columns already present: a11.depth_pct,
    a26.years_remaining, rated.years_remaining.
    """
    d11 = [[_round(r.tank_x), _round(r.tank_y), round(float(r.depth), 3),
            1 if r.side == "bottomside" else 0, r.anomaly_id, int(round(r.depth_pct))]
           for r in a11.itertuples()]
    d26 = [[_round(r.tank_x), _round(r.tank_y), int(r.depth_pct),
            1 if r.side == "bottomside" else 0, _round(r.years_remaining),
            r.anomaly_id]
           for r in a26.itertuples()]
    dr = [[_round(r.x_2026), _round(r.y_2026), round(float(r.rate_in_per_yr), 5),
           1 if "high_growth" in str(r.rate_flag) else 0,
           r.id_2011, r.id_2026, round(float(r.depth_2011), 3),
           round(float(r.depth_2026), 4), _round(r.distance_in),
           1 if "negative" in str(r.rate_flag) else 0,
           round(float(r.years_remaining), 2), int(r.plate),
           round(float(r.remaining_2026), 4),
           "" if pd.isna(r.review_flag) else str(r.review_flag)]
          for r in rated.itertuples()]
    dnf = [[_round(r.tank_x), _round(r.tank_y), r.anomaly_id,
            "" if pd.isna(r.review_flag) else r.review_flag,
            None if pd.isna(r.nearest_2026_in) else _round(r.nearest_2026_in)]
           for r in nf.itertuples()]

    high = rated[rated["rate_flag"].str.contains("high_growth", na=False)] \
        .sort_values("rate_in_per_yr", ascending=False)
    high_rows = [[r.id_2011, r.id_2026, int(r.plate),
                  f"{r.depth_2011:.3f}", f"{r.depth_2026:.4f}",
                  f"{r.rate_in_per_yr:.4f}", f"{r.distance_in:.1f}",
                  f"{r.years_remaining:.1f}"]
                 for r in high.itertuples()]

    growth_mils = ((rated["depth_2026"] - rated["depth_2011"]) * 1000) \
        .round(0).astype(int).tolist()
    return {
        "a11": d11, "a26": d26, "rates": dr, "nf": dnf, "high": high_rows,
        "growth_mils": growth_mils,
        "depthpct26": a26["depth_pct"].astype(int).tolist(),
    }


def pack_appurtenances(items, r_in, depth_in=18.0):
    from tankfloor.normalize.shell import tangent_rect

    out = []
    for a in items:
        pts = tangent_rect(a["az_deg"], r_in, float(a["size_in"]), depth_in)
        out.append({"id": a["id"], "type": a["type"], "label": a["label"],
                    "az": _round(a["az_deg"]), "x": _round(a["x"]),
                    "y": _round(a["y"]),
                    "pts": [[_round(x), _round(y)] for x, y in pts]})
    return out


def build_data(layout, cfg, out_dir=OUT):
    from tankfloor.normalize.shell import appurtenance_positions
    from tankfloor.rates.projection import years_remaining
    from tankfloor.rates.shortterm import governing_rates
    from tankfloor.viz.bands import bands_from_config, depth_pct

    a11 = pd.read_csv(out_dir / "anomalies_2011_normalized.csv")
    a26 = pd.read_csv(out_dir / "anomalies_2026_normalized.csv")
    rated = pd.read_csv(out_dir / "rates_matched.csv")
    nf = pd.read_csv(out_dir / "exceptions_notfound_2011.csv")

    pj = cfg["rates"]["projection"]
    _, floor = governing_rates(rated)
    stpr_g = floor["StPr_governing"] or 0.0
    a11["depth_pct"] = depth_pct(a11["depth"], a11["nominal_thickness"])
    a26["years_remaining"] = years_remaining(
        a26["remaining_thickness"], stpr_g, pj["mrt_min_bottom_in"],
        pj["upr_in_per_yr"], pj["or_cap_years"])
    if "years_remaining" not in rated.columns:
        raise SystemExit("rates_matched.csv lacks years_remaining — rerun "
                         "`python -m tankfloor rates`")

    data = pack_features(a11, a26, rated, nf)
    data["fields"] = FIELDS
    data["plates"] = pack_plates(layout)
    data["bands"] = bands_from_config(cfg)
    r_in = float(cfg["tank"]["diameter_ft"]) * 12.0 / 2.0
    data["app"] = pack_appurtenances(appurtenance_positions(cfg), r_in)
    data["radius"] = r_in
    data["scenarios"] = pd.read_csv(out_dir / "scenarios.csv").to_dict("records")
    data["repair"] = pd.read_csv(out_dir / "repair_strategy.csv").to_dict("records")
    return data


def build_stats(cfg, data, out_dir=OUT):
    from tankfloor.rates.shortterm import governing_rates, interval_years

    rated = pd.read_csv(out_dir / "rates_matched.csv")
    nf = pd.read_csv(out_dir / "exceptions_notfound_2011.csv")
    new26 = pd.read_csv(out_dir / "exceptions_new_2026.csv")
    a11 = pd.read_csv(out_dir / "anomalies_2011_normalized.csv")
    a26 = pd.read_csv(out_dir / "anomalies_2026_normalized.csv")
    _, floor = governing_rates(rated)
    years = interval_years(cfg["inspections"]["2011"]["date_end"],
                           cfg["inspections"]["2026"]["date_start"])
    rc = cfg["rates"]
    pj = rc["projection"]
    tol = rc["measurement_tolerance_in"]
    scen = {s["key"]: s for s in data["scenarios"]}
    deepest = int(a26["depth_pct"].max())
    plates_deep = sorted(a26.loc[a26["depth_pct"] == deepest, "plate_id_norm"]
                         .astype(int).unique().tolist())
    nominal = cfg["nominal_thickness"]["floor_in"]
    stats = {
        "matched": len(rated),
        "cluster": len(pd.read_csv(out_dir / "matched_cluster_members.csv")),
        "notfound": len(nf),
        "nearmiss": int((nf["review_flag"] == "near_miss").sum()),
        "watchlist": int((nf["review_flag"] == "watchlist_plate").sum()),
        "new": len(new26),
        "high": int(rated["rate_flag"].str.contains("high_growth", na=False).sum()),
        "clamped": int(rated["rate_flag"].str.contains("negative", na=False).sum()),
        "n11": len(a11), "n26": len(a26),
        "n11_top": int((a11["side"] == "topside").sum()),
        "n11_bot": int((a11["side"] == "bottomside").sum()),
        "n26_top": int((a26["side"] == "topside").sum()),
        "n26_bot": int((a26["side"] == "bottomside").sum()),
        "matched_pct": int(round(100 * len(rated) / len(a11))),
        "medianDist": _round(rated["distance_in"].median()),
        "patches": cfg["tank"].get("existing_patches_2026"),
        "stpr": round(floor["StPr_governing"] or 0.0, 4),
        "stpr_unc": round(float(rated["rate_uncertainty_in_per_yr"].iloc[0]), 4),
        "upr": pj["upr_in_per_yr"],
        "years": round(years, 2),
        "high_rate": rc["high_growth_rate_in_per_yr"],
        "depth_tol": round(math.hypot(tol["2011"], tol["2026"]), 3),
        "mrt_min": pj["mrt_min_bottom_in"],
        "cap": pj["or_cap_years"],
        "nominal": nominal,
        "threshold_pct": cfg["inspections"]["2026"]["recording_threshold"]["depth_pct_min"],
        "years_installed": pj["years_installed"],
        "coated_stpr": pj["coated_stpr_in_per_yr"],
        "rt_asfound": round(scen["asfound"]["rt_in"], 4),
        "rt_repaired": round(scen["repaired"]["rt_in"], 4),
        "rt_new": round(scen["new"]["rt_in"], 4),
        "or_asfound": _round(scen["asfound"]["or_yr"]),
        "or_repaired": _round(scen["repaired"]["or_yr"]),
        "or_new": _round(scen["new"]["or_yr"]),
        "or_coated_asfound": _round(scen["asfound"]["or_coated_yr"]),
        "or_coated_repaired": _round(scen["repaired"]["or_coated_yr"]),
        "or_coated_new": _round(scen["new"]["or_coated_yr"]),
        "or_coated_repaired_raw": _round(scen["repaired"]["or_coated_raw_yr"]),
        "deepest_pct": deepest,
        "deepest_rt": round(nominal * (1 - deepest / 100.0), 4),
        "deepest_plates": ", ".join(str(p) for p in plates_deep),
        "yrs_min_matched": _round(rated["years_remaining"].min()),
        "yrs_median_matched": _round(rated["years_remaining"].median()),
        "yrs_min_new": _round(new26["years_remaining"].min()),
    }
    missing, extra = STAT_KEYS - set(stats), set(stats) - STAT_KEYS
    if missing or extra:
        raise SystemExit(f"stats contract drift: missing {missing}, extra {extra}")
    return stats


def build(cfg):
    from tankfloor.__main__ import load_calibrated_layout

    a26 = pd.read_csv(OUT / "anomalies_2026.csv")
    a26["plate"] = a26["plate_id_raw"].astype(int)
    layout = load_calibrated_layout(cfg, a26)
    data = build_data(layout, cfg)
    stats = build_stats(cfg, data)

    tpl = (Path(__file__).parent / "dashboard_template.html").read_text(
        encoding="utf-8")
    html = (tpl
            .replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__STATS__", json.dumps(stats)))
    dst = OUT / "dashboard.html"
    dst.write_text(html, encoding="utf-8")
    size = dst.stat().st_size / 1024
    print(f"wrote {dst} ({size:.0f} KB)")
    return dst
