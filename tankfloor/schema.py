"""Common anomaly schema (see CLAUDE.md)."""
import pandas as pd

COLUMNS = [
    "inspection_id",
    "anomaly_id",
    "plate_id_raw",
    "plate_id_norm",   # filled in Phase 2 (plate reconciliation)
    "side",            # topside | bottomside
    "x", "y",          # Phase 1: plate-local inches (tank-level datum comes in Phase 2)
    "depth",           # pit depth, inches
    "remaining_thickness",  # inches
    "nominal_thickness",    # inches
    "length", "width",      # anomaly extent, inches
    "notes",
]


def finalize(records, inspection_id):
    """Order records into the common schema DataFrame."""
    df = pd.DataFrame(records)
    df["inspection_id"] = inspection_id
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    extras = [c for c in df.columns if c not in COLUMNS]
    return df[COLUMNS + extras]
