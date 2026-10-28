"""Parser for the 2026 ROSEN Feature List and repair-patch list.

Source: `Port Everglades, FL - TK 201 - OOS July 2026 - Preliminary Report
REV 1.pdf`. Feature list on PDF pages 25-137; repair patches on 139-140.

Feature-list columns: No. | Plate No. | X Pos [in] | Y Pos [in] | X Size [in]
| Y Size [in] | Depth [%] | Type | Method | Location | Classification.
"Inspection Side" = topside, "Non Inspection Side" = bottomside (underside).
Positions are plate-local inches; Depth is % metal loss.

NOTE (user-confirmed assumption): Depth [%] is taken relative to the 0.250"
nominal plate thickness. The PDF list is censored at >=49% depth.
"""
import re

import pdfplumber

from tankfloor.schema import finalize

DEPTH_BASIS_IN = 0.250  # ASSUMPTION: % of nominal (user-confirmed 2026-08-06)

_KNOWN_METHODS = ("TBit", "Visual")

_FEATURE_RE = re.compile(
    r"^(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(.+)$"
)

# Repair rows come with or without parenthesized "(2.00)" tolerance suffixes;
# tolerances are stripped before matching.
_REPAIR_RE = re.compile(
    r"^(\d+)\s+([A-Za-z][A-Za-z ]*?)\s+(\d+)\s+"       # no, type, plate
    r"(-?[\d.]+)\s+(-?[\d.]+)\s+"                      # x pos, y pos
    r"(-?[\d.]+)\s+(-?[\d.]+)\s+"                      # x dir, y dir
    r"([\d.]+)\s+([\d.]+)\s+"                          # x dim, y dim
    r"(-?\d+)$"                                        # angle to Y
)


def depth_pct_to_inches(pct, basis_in=DEPTH_BASIS_IN):
    """Convert % metal loss to pit depth in inches."""
    return pct / 100.0 * basis_in


def parse_feature_line(line):
    """Parse one feature-list row. Returns a dict or None for non-data lines."""
    m = _FEATURE_RE.match(line.strip())
    if not m:
        return None
    no, plate, x, y, xs, ys, depth_pct, tail = m.groups()

    tail = tail.strip()
    if tail.endswith("Non Inspection Side"):
        side = "bottomside"
        tail = tail[: -len("Non Inspection Side")].strip()
    elif tail.endswith("Inspection Side"):
        side = "topside"
        tail = tail[: -len("Inspection Side")].strip()
    else:
        return None  # not a feature row (e.g. numeric fragment of a chart)

    method = None
    for cand in _KNOWN_METHODS:
        m2 = re.search(rf"\b{cand}\b", tail)
        if m2:
            method = cand
            ftype = tail[: m2.start()].strip()
            zone = tail[m2.end():].strip()
            break
    if method is None:
        ftype, zone = tail, ""

    return {
        "no": int(no),
        "plate": int(plate),
        "x": float(x),
        "y": float(y),
        "length": float(xs),
        "width": float(ys),
        "depth_pct": int(depth_pct),
        "type": ftype,
        "method": method,
        "zone": zone,
        "side": side,
    }


def parse_repair_line(line):
    """Parse one repair-patch/plate row. Returns a dict or None."""
    line = re.sub(r"\s*\([\d.]+\)", "", line)
    m = _REPAIR_RE.match(line.strip())
    if not m:
        return None
    no, rtype, plate, xp, yp, xd, yd, xdim, ydim, angle = m.groups()
    return {
        "no": int(no),
        "repair_type": rtype.strip(),
        "plate": int(plate),
        "x_pos": float(xp),
        "y_pos": float(yp),
        "x_dir": float(xd),
        "y_dir": float(yd),
        "x_dim": float(xdim),
        "y_dim": float(ydim),
        "angle_to_y": int(angle),
    }


def parse_report(pdf_path, pages=(25, 137), depth_basis_in=DEPTH_BASIS_IN):
    """Parse the feature list into the common schema DataFrame."""
    records = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(pages[0] - 1, pages[1]):
            text = pdf.pages[i].extract_text() or ""
            for line in text.splitlines():
                rec = parse_feature_line(line)
                if rec is None:
                    continue
                depth_in = depth_pct_to_inches(rec["depth_pct"], depth_basis_in)
                notes = [rec["type"], rec["method"] or ""]
                if rec["zone"]:
                    notes.append(f"[zone: {rec['zone']}]")
                records.append({
                    "anomaly_id": f"2026-{rec['no']:05d}",
                    "plate_id_raw": str(rec["plate"]),
                    "side": rec["side"],
                    "x": rec["x"],
                    "y": rec["y"],
                    "depth": depth_in,
                    "depth_pct": rec["depth_pct"],
                    "remaining_thickness": depth_basis_in - depth_in,
                    "nominal_thickness": depth_basis_in,
                    "length": rec["length"],
                    "width": rec["width"],
                    "method": rec["method"],
                    "notes": " ".join(n for n in notes if n),
                })
    return finalize(records, "2026")


def parse_repairs(pdf_path, pages=(139, 140)):
    """Parse the recommended repair-patch/plate list into a DataFrame."""
    import pandas as pd

    records = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(pages[0] - 1, pages[1]):
            text = pdf.pages[i].extract_text() or ""
            for line in text.splitlines():
                rec = parse_repair_line(line)
                if rec is not None:
                    records.append(rec)
    return pd.DataFrame(records)
