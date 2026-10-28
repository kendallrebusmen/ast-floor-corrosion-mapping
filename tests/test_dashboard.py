"""Dashboard data packing: the template reads positional arrays, so every
packed row must match the FIELDS contract, and every data-stat placeholder
in the template must be a stat the builder emits."""
import re
from pathlib import Path

import pandas as pd

from tankfloor.report.dashboard import FIELDS, STAT_KEYS, pack_features

TEMPLATE = Path(__file__).resolve().parents[1] / "tankfloor" / "report" / "dashboard_template.html"


def _frames():
    a11 = pd.DataFrame({
        "tank_x": [-81.7, 10.0], "tank_y": [646.8, 5.0], "depth": [0.14, 0.13],
        "side": ["topside", "bottomside"], "anomaly_id": ["2011-002A", "2011-017A"],
        "depth_pct": [56.0, 52.0],
    })
    a26 = pd.DataFrame({
        "tank_x": [-99.4, 1.0], "tank_y": [646.3, 2.0], "depth_pct": [52, 98],
        "side": ["topside", "topside"], "anomaly_id": ["2026-00001", "2026-03752"],
        "years_remaining": [2.24, 0.0],
    })
    rated = pd.DataFrame({
        "x_2026": [-80.9], "y_2026": [642.0], "rate_in_per_yr": [0.000166],
        "rate_flag": ["ok"], "id_2011": ["2011-002A"], "id_2026": ["2026-00006"],
        "depth_2011": [0.14], "depth_2026": [0.1425], "distance_in": [0.0],
        "plate": [2], "years_remaining": [5.37],
        "remaining_2026": [0.1075], "review_flag": [None],
    })
    nf = pd.DataFrame({
        "tank_x": [5.0], "tank_y": [6.0], "anomaly_id": ["2011-003A"],
        "review_flag": [None], "nearest_2026_in": [30.2],
    })
    return a11, a26, rated, nf


class TestPackFeatures:
    def test_rows_match_fields_contract(self):
        data = pack_features(*_frames())
        for key, names in FIELDS.items():
            assert key in data, key
            for row in data[key]:
                assert len(row) == len(names), (key, row)

    def test_field_values_land_in_named_slots(self):
        a11, a26, rated, nf = _frames()
        data = pack_features(a11, a26, rated, nf)
        f = {k: {n: i for i, n in enumerate(v)} for k, v in FIELDS.items()}
        assert data["a11"][0][f["a11"]["pct"]] == 56
        assert data["a26"][1][f["a26"]["yrs"]] == 0.0
        assert data["a26"][1][f["a26"]["id"]] == "2026-03752"
        assert data["rates"][0][f["rates"]["yrs"]] == 5.37
        assert data["a11"][1][f["a11"]["side"]] == 1
        # full matched-pairs table needs plate, 2026 remaining thickness, review flag
        assert data["rates"][0][f["rates"]["plate"]] == 2
        assert data["rates"][0][f["rates"]["rem26"]] == 0.1075
        assert data["rates"][0][f["rates"]["review"]] == ""

    def test_high_table_rows_include_years(self):
        a11, a26, rated, nf = _frames()
        rated["rate_flag"] = ["high_growth"]
        data = pack_features(a11, a26, rated, nf)
        assert len(data["high"]) == 1
        assert data["high"][0][FIELDS["high"].index("yrs")] == "5.4"


class TestTemplateContract:
    def test_placeholders_present_once(self):
        tpl = TEMPLATE.read_text(encoding="utf-8")
        assert tpl.count("__DATA__") == 1 and tpl.count("__STATS__") == 1

    def test_every_data_stat_is_emitted(self):
        tpl = TEMPLATE.read_text(encoding="utf-8")
        used = set(re.findall(r'data-stat="([a-zA-Z0-9_]+)"', tpl))
        assert used, "template should use data-stat placeholders"
        assert used <= STAT_KEYS, used - STAT_KEYS

    def test_matched_pairs_table_with_capability_export(self):
        tpl = TEMPLATE.read_text(encoding="utf-8")
        assert 'id="pairstbl"' in tpl
        assert 'claude.use("downloads")' in tpl      # viewer export path
        assert "URL.createObjectURL" in tpl         # standalone export path

    def test_no_stale_hardcoded_scenario_numbers(self):
        tpl = TEMPLATE.read_text(encoding="utf-8")
        for stale in ('class="big">3.1 ', 'class="big">16.8 ', "The 18 locations"):
            assert stale not in tpl
