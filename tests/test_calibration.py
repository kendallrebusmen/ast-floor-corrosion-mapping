"""Integration test: 2026 per-plate transforms must reproduce ROSEN's own
drawn feature marks on the Floor Map (Repair Threshold) page.

This guards the defect where arrow-decoded plate origins placed anomalies
on the wrong side of ~1/3 of the plates (caught by the user against the
vendor's p.23 floor map).
"""
from pathlib import Path

import pandas as pd
import pytest

from tankfloor.normalize.rosen_layout import (
    calibrate_transforms, extract_layout, floor_map_marks,
    reconcile_orientation,
)

PDF_2026 = (Path(__file__).resolve().parents[1] / "data" / "raw"
            / "Port Everglades, FL - TK 201 - OOS July 2026 - Preliminary Report REV 1.pdf")
CSV_2026 = (Path(__file__).resolve().parents[1] / "data" / "processed"
            / "anomalies_2026.csv")


@pytest.fixture(scope="module")
def quality():
    layout = extract_layout(PDF_2026)
    df = pd.read_csv(CSV_2026)
    df["plate"] = df["plate_id_raw"].astype(int)
    extents = {p: (g["x"].max(), g["y"].max()) for p, g in df.groupby("plate")}
    reconcile_orientation(layout, extents)
    feats = {p: list(zip(g["x"], g["y"])) for p, g in df.groupby("plate")}
    return calibrate_transforms(layout, feats, floor_map_marks(PDF_2026))


def test_most_plates_calibrated(quality):
    # 98 plates have features; a handful have <3 drawn marks
    assert len(quality) >= 80


def test_fit_agrees_with_vendor_marks(quality):
    fits = sorted(quality.values())
    median = fits[len(fits) // 2]
    assert median < 1.5   # inches
    assert max(fits) < 4.0
