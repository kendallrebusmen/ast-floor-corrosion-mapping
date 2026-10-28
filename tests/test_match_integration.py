"""Integration invariants for the Phase 3 matching outputs."""
from pathlib import Path

import pandas as pd
import pytest

OUT = Path(__file__).resolve().parents[1] / "data" / "processed"


@pytest.fixture(scope="module")
def outputs():
    return {
        "matches": pd.read_csv(OUT / "matched_anomalies.csv"),
        "cluster": pd.read_csv(OUT / "matched_cluster_members.csv"),
        "nf": pd.read_csv(OUT / "exceptions_notfound_2011.csv"),
        "new": pd.read_csv(OUT / "exceptions_new_2026.csv"),
    }


def test_2011_fully_partitioned(outputs):
    assert len(outputs["matches"]) + len(outputs["nf"]) == 336


def test_2026_fully_partitioned(outputs):
    assert (len(outputs["matches"]) + len(outputs["cluster"])
            + len(outputs["new"])) == 5077


def test_no_double_matching(outputs):
    m, c = outputs["matches"], outputs["cluster"]
    assert m["id_2011"].is_unique
    assert m["id_2026"].is_unique
    ids26 = list(m["id_2026"]) + list(c["id_2026"])
    assert len(ids26) == len(set(ids26))


def test_same_plate_and_side(outputs):
    """Matched pairs must come from the same reconciled plate and side."""
    m = outputs["matches"]
    a11 = pd.read_csv(OUT / "anomalies_2011_normalized.csv").set_index("anomaly_id")
    a26 = pd.read_csv(OUT / "anomalies_2026_normalized.csv").set_index("anomaly_id")
    assert (a11.loc[m["id_2011"], "plate_id_norm"].values
            == a26.loc[m["id_2026"], "plate_id_norm"].values).all()
    assert (a11.loc[m["id_2011"], "side"].values
            == a26.loc[m["id_2026"], "side"].values).all()


def test_distances_within_tolerance(outputs):
    assert (outputs["matches"]["distance_in"] <= 12.0 + 1e-6).all()
