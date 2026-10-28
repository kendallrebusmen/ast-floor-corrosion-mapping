"""Decode ROSEN's Floor Map (Bottom Layout) pages into plate geometry.

Source: 2026 report, PDF page 22 ("plate coordinate systems definition",
with per-plate x/y axis arrows) and page 23 (same layout, labels only).

Text quirks of these vector pages:
- Plate-number labels extract with every glyph overprinted 9 times
  ('888888888999999999' -> plate 89).
- Axis labels are bare 'x' / 'y' words near each plate's origin corner;
  small plates may show only the 'y' arrow.

The drawn map is to scale; the tank circle's bounding box provides the
page-units -> inches scale (117 ft = 1404 in diameter).
"""
import re

import pdfplumber

TANK_DIAMETER_IN = 117.0 * 12.0

_AXIS_RE = re.compile(r"^[xy]$")


def decode_label(token):
    """'888888888999999999' -> 89. Returns None for non-label tokens.

    Each digit glyph is overprinted 9x; trailing/leading axis letters may be
    glued to the digits. Runs of one digit must be a multiple of 9 long.
    """
    token = token.strip().strip("xy")
    if not token or not token.isdigit():
        return None
    digits = []
    i = 0
    while i < len(token):
        j = i
        while j < len(token) and token[j] == token[i]:
            j += 1
        run = j - i
        if run % 9 != 0:
            return None
        digits.extend(token[i] * (run // 9))
        i = j
    return int("".join(digits))


def _plate_words(page):
    """(plate, center_x, center_y) for every plate label on a layout page."""
    out = []
    for w in page.extract_words():
        plate = decode_label(w["text"])
        if plate is not None:
            out.append((plate, (w["x0"] + w["x1"]) / 2.0,
                        (w["top"] + w["bottom"]) / 2.0))
    return out


def _cluster_rows(labels, tol=12.0):
    """Group plate labels into horizontal rows by vertical position."""
    rows = []
    for plate, cx, cy in sorted(labels, key=lambda t: t[2]):
        if rows and abs(cy - rows[-1]["cy"]) <= tol:
            row = rows[-1]
            row["plates"].append((plate, cx, cy))
            row["cy"] = sum(p[2] for p in row["plates"]) / len(row["plates"])
        else:
            rows.append({"cy": cy, "plates": [(plate, cx, cy)]})
    for row in rows:
        row["plates"].sort(key=lambda t: t[1])
    return rows


def _is_gray(obj):
    """Plate shapes are filled with 75.3% gray on the layout pages."""
    col = obj.get("non_stroking_color")
    return (col is not None and len(col) == 3
            and all(abs(v - 0.753) < 0.002 for v in col))


def _plate_shapes(page):
    """The 110 plate outlines: gray-filled rects (interior plates) plus
    gray-filled polygons (edge/sketch plates clipped by the tank circle).

    Returns a list of dicts: {bbox: (x0, top, x1, bottom), poly: [(x, y), ...]}.
    """
    shapes = []
    for r in page.rects:
        if _is_gray(r) and (r["x1"] - r["x0"]) > 10:
            bbox = (r["x0"], r["top"], r["x1"], r["bottom"])
            poly = [(r["x0"], r["top"]), (r["x1"], r["top"]),
                    (r["x1"], r["bottom"]), (r["x0"], r["bottom"])]
            shapes.append({"bbox": bbox, "poly": poly})
    for c in page.curves:
        if _is_gray(c) and c.get("pts"):
            shapes.append({
                "bbox": (c["x0"], c["top"], c["x1"], c["bottom"]),
                "poly": list(c["pts"]),
            })
    return shapes


def _circle_bbox_from_shapes(shapes):
    """The plate shapes are clipped by (and fill) the tank circle, so their
    union is the circle's bounding box. The vendor map is NOT isotropically
    scaled (the circle prints as an ellipse), hence separate x/y extents.
    """
    xs, ys = [], []
    for s in shapes:
        x0, top, x1, bottom = s["bbox"]
        xs += [x0, x1]
        ys += [top, bottom]
    return min(xs), min(ys), max(xs), max(ys)


def extract_layout(pdf_path, layout_page=23, axes_page=22):
    """Extract plate rectangles, scale, and per-plate axis conventions.

    Returns a dict:
      scale_in_per_pt: inches per page unit
      center: (page_x, page_y) of tank center
      plates: {plate: dict(rect=(x0, top, x1, bottom),  # page units
                           origin=(page_x, page_y),      # plate-local (0,0)
                           x_sign=+1/-1,   # page-y direction of plate-local +x
                           y_sign=+1/-1)}  # page-x direction of plate-local +y

    Plate-local convention (per the feature list): x runs across the plate
    (short dimension, vertical on the map), y along it (horizontal).
    """
    with pdfplumber.open(pdf_path) as pdf:
        lpage = pdf.pages[layout_page - 1]
        apage = pdf.pages[axes_page - 1]

        labels = _plate_words(lpage)
        rows = _cluster_rows(labels)
        shapes = _plate_shapes(lpage)
        bx0, by0, bx1, by1 = _circle_bbox_from_shapes(shapes)
        # The vendor map is anisotropically scaled (the tank circle prints
        # as an ellipse): separate inches-per-page-unit scales per axis.
        scale_x = TANK_DIAMETER_IN / (bx1 - bx0)
        scale_y = TANK_DIAMETER_IN / (by1 - by0)
        center = ((bx0 + bx1) / 2.0, (by0 + by1) / 2.0)

        # assign each plate label to the vendor-drawn shape containing it
        plates = {}
        row_of = {p: ri for ri, row in enumerate(rows) for p, _, _ in row["plates"]}
        for plate, cx, cy in labels:
            candidates = [
                s for s in shapes
                if s["bbox"][0] <= cx <= s["bbox"][2]
                and s["bbox"][1] <= cy <= s["bbox"][3]
            ]
            if not candidates:  # label center just outside its shape: nearest
                candidates = sorted(
                    shapes,
                    key=lambda s: (max(s["bbox"][0] - cx, cx - s["bbox"][2], 0) ** 2
                                   + max(s["bbox"][1] - cy, cy - s["bbox"][3], 0) ** 2),
                )[:1]
            best = min(candidates,
                       key=lambda s: (s["bbox"][2] - s["bbox"][0])
                                     * (s["bbox"][3] - s["bbox"][1]))
            plates[plate] = {
                "rect": best["bbox"],
                "poly": best["poly"],
                "row": row_of[plate],
            }

        # per-plate axis arrows from the axes page
        axis_words = [
            ((w["x0"] + w["x1"]) / 2.0, (w["top"] + w["bottom"]) / 2.0, w["text"])
            for w in apage.extract_words() if _AXIS_RE.match(w["text"])
        ]
        for plate, info in plates.items():
            x0, top, x1, bottom = info["rect"]
            pad = 14.0
            near = [(ax, ay, t) for ax, ay, t in axis_words
                    if x0 - pad <= ax <= x1 + pad and top - pad <= ay <= bottom + pad]
            xs = [(ax, ay) for ax, ay, t in near if t == "x"]
            ys = [(ax, ay) for ax, ay, t in near if t == "y"]
            corners = [(cx_, cy_) for cx_ in (x0, x1) for cy_ in (top, bottom)]

            def _nearest(points, ref):
                return min(points, key=lambda p: (p[0] - ref[0]) ** 2 + (p[1] - ref[1]) ** 2)

            origin = x_sign = y_sign = y_horizontal = None
            if xs and ys:
                xl, yl = xs[0], ys[0]
                if len(xs) > 1 or len(ys) > 1:
                    # keep the x/y pair closest to each other (one bracket)
                    xl, yl = min(
                        ((a, b) for a in xs for b in ys),
                        key=lambda p: (p[0][0] - p[1][0]) ** 2 + (p[0][1] - p[1][1]) ** 2,
                    )
                mid = ((xl[0] + yl[0]) / 2.0, (xl[1] + yl[1]) / 2.0)
                origin = _nearest(corners, mid)
                # Axis orientation comes from the arrow geometry: most plates
                # have local y along the page-x axis (long dimension drawn
                # horizontally), but rotated plates (e.g. 109) swap axes.
                dyx = abs(yl[0] - origin[0])
                dyy = abs(yl[1] - origin[1])
                y_horizontal = dyx >= dyy
                # Plate-local coords are non-negative, so both axes point into
                # the plate: the origin corner determines each direction's sign.
                h_sign = 1 if origin[0] == x0 else -1      # along page-x
                v_sign = 1 if origin[1] == top else -1     # page-y grows downward
                if y_horizontal:
                    x_sign, y_sign = v_sign, h_sign
                else:
                    x_sign, y_sign = h_sign, v_sign
            info.update({"origin": origin, "x_sign": x_sign, "y_sign": y_sign,
                         "y_horizontal": y_horizontal if origin else None})

        # fill plates with missing/partial arrows from their row's majority
        by_row = {}
        for plate, info in plates.items():
            if info["origin"] is not None:
                by_row.setdefault(info["row"], []).append(info)
        for plate, info in plates.items():
            if info["origin"] is None and by_row.get(info["row"]):
                donor = by_row[info["row"]][0]
                x0, top, x1, bottom = info["rect"]
                dx0, dtop, dx1, dbottom = donor["rect"]
                ox = x0 if donor["origin"][0] == dx0 else x1
                oy = top if donor["origin"][1] == dtop else bottom
                info.update({"origin": (ox, oy), "x_sign": donor["x_sign"],
                             "y_sign": donor["y_sign"],
                             "y_horizontal": donor["y_horizontal"],
                             "inferred": True})

    return {"scale_x": scale_x, "scale_y": scale_y, "center": center,
            "plates": plates}


def reconcile_orientation(layout, extents):
    """Fix physically impossible y_horizontal choices.

    The axis-arrow labels are occasionally ambiguous to pair. A plate's
    feature extents settle it: a local-y coordinate larger than the rect's
    vertical size (in inches) cannot be vertical, and vice versa.

    extents: {plate: (max_x_in, max_y_in)} from the feature list.
    Returns the list of plates whose orientation was flipped.
    """
    flipped = []
    for plate, (max_x, max_y) in extents.items():
        info = layout["plates"].get(plate)
        if info is None or info["origin"] is None:
            continue
        x0, top, x1, bottom = info["rect"]
        w_in = (x1 - x0) * layout["scale_x"]
        h_in = (bottom - top) * layout["scale_y"]
        # violation = how far the extents overshoot the rect in each orientation
        # (up to ~6" of overshoot is expected: lap-riveted plates overlap, so
        # the drawn row band is a few inches shorter than the 75" plate width)
        viol_h = max(0.0, max_y - w_in) + max(0.0, max_x - h_in)
        viol_v = max(0.0, max_y - h_in) + max(0.0, max_x - w_in)
        margin = 6.0
        cur, alt = ((viol_h, viol_v) if info["y_horizontal"]
                    else (viol_v, viol_h))
        # flip when the alternative orientation is clearly better; ties and
        # small differences keep the arrow-derived orientation
        flip = alt + margin < cur
        if flip:
            info["y_horizontal"] = not info["y_horizontal"]
            # signs are bound to page directions; swap them with the axes
            info["x_sign"], info["y_sign"] = info["y_sign"], info["x_sign"]
            flipped.append(plate)
    return flipped


def floor_map_marks(pdf_path, page_no=23):
    """Feature marks from the Floor Map (Repair Threshold) page.

    ROSEN draws every reported feature on this page as a tiny rect (to
    feature scale, color-coded by depth class). These are the authoritative
    per-plate positions, used to calibrate each plate's transform.
    Returns an array-like list of (page_x, page_y) mark centers.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_no - 1]
        return [((r["x0"] + r["x1"]) / 2.0, (r["top"] + r["bottom"]) / 2.0)
                for r in page.rects
                if (r["x1"] - r["x0"]) <= 10 and (r["bottom"] - r["top"]) <= 10]


def _candidate_transform(info, X, Y, corner, y_horizontal, scale_x, scale_y):
    x0, top, x1, bottom = info["rect"]
    ox = x0 if corner[0] == "W" else x1
    oy = top if corner[1] == "N" else bottom
    hs = 1 if corner[0] == "W" else -1
    vs = 1 if corner[1] == "N" else -1
    if y_horizontal:
        return ox + hs * Y / scale_x, oy + vs * X / scale_y
    return ox + hs * X / scale_x, oy + vs * Y / scale_y


def calibrate_transforms(layout, features_by_plate, marks, lap_tol_in=8.0):
    """Fit each plate's origin corner + axis orientation to the vendor-drawn
    feature marks (chamfer distance), replacing the arrow-decoded guess.

    features_by_plate: {plate: [(x_in, y_in), ...]} from the feature list.
    marks: [(page_x, page_y), ...] from floor_map_marks().

    Candidates that are physically impossible (feature extents overshooting
    the plate beyond the lap tolerance) are excluded. Plates with fewer than
    3 marks keep their arrow-derived transform. Returns {plate: fit_med_in}.
    """
    import numpy as np
    from scipy.spatial import cKDTree

    sx, sy = layout["scale_x"], layout["scale_y"]
    marks = np.asarray(marks)
    quality = {}
    for plate, feats in features_by_plate.items():
        info = layout["plates"].get(plate)
        if info is None or not feats:
            continue
        x0, top, x1, bottom = info["rect"]
        m = marks[(marks[:, 0] >= x0 - 1) & (marks[:, 0] <= x1 + 1)
                  & (marks[:, 1] >= top - 1) & (marks[:, 1] <= bottom + 1)]
        if len(m) < 3:
            continue
        tree = cKDTree(m)
        w_in = (x1 - x0) * sx
        h_in = (bottom - top) * sy
        max_x = max(f[0] for f in feats)
        max_y = max(f[1] for f in feats)
        feats_a = np.asarray(feats)
        best = None
        for corner in ("WN", "WS", "EN", "ES"):
            for yh in (True, False):
                along, across = (w_in, h_in) if yh else (h_in, w_in)
                if max_y > along + lap_tol_in or max_x > across + lap_tol_in:
                    continue  # physically impossible
                pts = np.array([
                    _candidate_transform(info, X, Y, corner, yh, sx, sy)
                    for X, Y in feats_a
                ])
                score = float(np.median(tree.query(pts)[0]) * sx)
                if best is None or score < best[0]:
                    best = (score, corner, yh)
        if best is None:
            continue
        _, corner, yh = best
        info["origin"] = (x0 if corner[0] == "W" else x1,
                          top if corner[1] == "N" else bottom)
        hs = 1 if corner[0] == "W" else -1
        vs = 1 if corner[1] == "N" else -1
        info["x_sign"], info["y_sign"] = (vs, hs) if yh else (hs, vs)
        info["y_horizontal"] = yh
        info["mark_fit_in"] = best[0]
        quality[plate] = best[0]
    return quality


def to_page(plate_info, x_in, y_in, scale_x, scale_y):
    """Map plate-local inches (x across, y along) to layout-page coordinates."""
    ox, oy = plate_info["origin"]
    if plate_info["y_horizontal"]:
        px = ox + plate_info["y_sign"] * y_in / scale_x
        py = oy + plate_info["x_sign"] * x_in / scale_y
    else:
        px = ox + plate_info["x_sign"] * x_in / scale_x
        py = oy + plate_info["y_sign"] * y_in / scale_y
    return px, py


def page_to_tank(layout, px, py):
    """Layout-page coordinates -> tank-level inches (origin at tank center,
    +X east, +Y north; north is the top of the vendor map)."""
    cx, cy = layout["center"]
    return (px - cx) * layout["scale_x"], (cy - py) * layout["scale_y"]
