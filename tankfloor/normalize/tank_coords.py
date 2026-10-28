"""Phase 2: tank-level coordinate normalization.

Converts plate-local anomaly positions from both inspections into a single
tank-level frame: origin at tank center, +X east, +Y north, inches
(north = top of the ROSEN layout map).

Conventions (established in Phase 2, see plate_mapping.csv notes):
- 2026 ROSEN: per-plate origin corner and axis orientation decoded from the
  layout page's axis arrows (x across plate, y along plate).
- 2011 Semper Fi: X along the plate from its west (left-as-drawn) edge,
  Y across the plate from its SOUTH (bottom-as-drawn) edge (southwest-corner
  origin) — established quantitatively against the red indication letters
  extracted from the vendor's own DWG 5-1: letter-distance metric (16.9" vs
  21.6" median for Y-north) and offset-immune per-plate polarity votes
  (Y: 16 south vs 4 north; X: 20 west vs 8 east).
- Plate numbering: identical serpentine scheme in both inspections
  (identity mapping), verified by density rank-correlation and positional
  nearest-neighbor tests against all 8 layout symmetries.
"""
from tankfloor.normalize.rosen_layout import page_to_tank, to_page


def tank_xy_2026(layout, plate, x_in, y_in):
    """2026 plate-local (x across, y along) -> tank inches."""
    info = layout["plates"][plate]
    px, py = to_page(info, x_in, y_in, layout["scale_x"], layout["scale_y"])
    return page_to_tank(layout, px, py)


def tank_xy_2011(layout, plate, x_in, y_in, ne_corner=False):
    """2011 plate-local (X along from west, Y across from SOUTH) -> tank inches.

    Rows flagged "N/E Corner" in the reduction table are measured from the
    plate's NORTHEAST corner instead (X west from the east edge, Y south from
    the north edge). Established 2026-09-02: the flag is set on every row of
    rim plates 103/104 whose SW corner is cut away by the shell, and applying
    it moves all 21 flagged rows inside their plates and halves their median
    distance to the nearest 2026 feature (15.7" -> 9.3"); the two plate-104
    rows that plotted outside the shell were the visible symptom.
    """
    info = layout["plates"][plate]
    x0, top, x1, bottom = info["rect"]
    if ne_corner:
        px = x1 - x_in / layout["scale_x"]
        py = top + y_in / layout["scale_y"]
    else:
        px = x0 + x_in / layout["scale_x"]
        py = bottom - y_in / layout["scale_y"]
    return page_to_tank(layout, px, py)


def _ne_corner_flag(row):
    for col in ("flags", "notes"):
        v = row.get(col)
        if isinstance(v, str) and "ne_corner" in v:
            return True
    return False


def add_tank_coords(df, layout, inspection_id):
    """Add tank_x / tank_y columns (inches, tank-center origin) to a
    common-schema anomaly DataFrame."""
    xs, ys = [], []
    for _, r in df.iterrows():
        if inspection_id == "2011":
            tx, ty = tank_xy_2011(layout, int(r["plate_id_raw"]), r["x"], r["y"],
                                  ne_corner=_ne_corner_flag(r))
        else:
            tx, ty = tank_xy_2026(layout, int(r["plate_id_raw"]), r["x"], r["y"])
        xs.append(round(tx, 2))
        ys.append(round(ty, 2))
    df = df.copy()
    df["tank_x"] = xs
    df["tank_y"] = ys
    return df
