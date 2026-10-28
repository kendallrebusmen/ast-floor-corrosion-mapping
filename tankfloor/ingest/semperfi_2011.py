"""Parser for the 2011 Semper Fi Enterprises "Bottom Plate Reduction Table".

Source: `Port Everglades FL (C) - Tank 201- OOS June 2011.pdf`, PDF pages 17-30.
All values in the table are inches. Rows are one recordable indication each
(cluster rows describe a pitting area with `PITTING (n)` in the comment and
ranges in the depth/remaining/X/Y cells).

Flag columns (Internal / Underside / Critical Zone / N/E Corner / Mech.) carry
an "X" mark whose meaning is recovered from its horizontal position, since
plain text extraction loses column alignment.
"""
import re

import pdfplumber

from tankfloor.schema import finalize

NOMINAL_IN = 0.250

# Header x0 anchors measured from the 2011 PDF (page 17). An X mark is
# assigned to the nearest anchor.
FLAG_ANCHORS = {
    "internal": 411.0,
    "underside": 464.0,
    "critical_zone": 522.0,
    "ne_corner": 575.0,
    "mech": 614.0,
}

# Data-cell column anchors (token *centers*; wide range tokens start left of
# the column, so nearest-anchor-by-center is used instead of x0 bins).
DATA_ANCHORS = {"depth": 137.0, "remaining": 195.0, "x": 273.0, "y": 355.0}
_FLAG_ZONE = (405.0, 640.0)
_COMMENT_X0 = 640.0

_PLATE_RE = re.compile(r"^(\d{1,3})?([A-Z])$")
_NUM_RE = re.compile(r"^\.?\d")


def parse_inch_value(token):
    """'.13' -> 0.13 ; '0.120”' -> 0.120 (strips straight/curly inch marks)."""
    return float(token.strip("”\"″'").strip())


def parse_inch_range(token):
    """A depth/remaining cell: single value, range, or '-' (not measured).

    Returns (lo, hi) in inches, or None for '-'.
    """
    token = token.strip()
    if token == "-":
        return None
    # split on hyphen between two numbers (values look like .13 or 0.120”)
    parts = re.split(r"(?<=[\d”\"])-(?=[.\d])", token)
    values = [parse_inch_value(p) for p in parts]
    return (min(values), max(values))


def parse_location(token):
    """X/Y location cell in inches: '58' or a span '21-34'.

    Returns (midpoint, span).
    """
    parts = token.strip().split("-")
    values = [float(p) for p in parts]
    lo, hi = min(values), max(values)
    return ((lo + hi) / 2.0, hi - lo)


def resolve_plate(token, prev_plate):
    """'2A' -> (2, 'A'); a bare letter continues the previous plate."""
    m = _PLATE_RE.match(token.strip())
    if not m:
        raise ValueError(f"not a plate/indication token: {token!r}")
    num, letter = m.groups()
    if num is None:
        if prev_plate is None:
            raise ValueError(f"letter-only row {token!r} with no previous plate")
        return (prev_plate, letter)
    return (int(num), letter)


def flags_from_x(x_positions):
    """Map X-mark x0 positions to flag-column names (nearest header anchor)."""
    flags = set()
    for x in x_positions:
        name = min(FLAG_ANCHORS, key=lambda k: abs(FLAG_ANCHORS[k] - x))
        flags.add(name)
    return flags


def parse_table_line(words, prev_plate):
    """Parse one text line (pdfplumber word dicts) of the reduction table.

    Returns a record dict, or None if the line is not a data row.
    """
    words = sorted(words, key=lambda w: w["x0"])
    if not words:
        return None
    first = words[0]
    if first["x0"] >= 120 or not _PLATE_RE.match(first["text"].strip()):
        return None
    try:
        plate, letter = resolve_plate(first["text"], prev_plate)
    except ValueError:
        return None

    cells = {}
    flag_xs = []
    comment_parts = []
    for w in words[1:]:
        t, x0 = w["text"].strip(), w["x0"]
        if t == "X" and _FLAG_ZONE[0] <= x0 < _FLAG_ZONE[1]:
            flag_xs.append(x0)
        elif x0 >= _COMMENT_X0:
            comment_parts.append(t)
        else:
            center = (w["x0"] + w.get("x1", w["x0"])) / 2.0
            col = min(DATA_ANCHORS, key=lambda k: abs(DATA_ANCHORS[k] - center))
            cells[col] = t
    depth_tok = cells.get("depth")
    remaining_tok = cells.get("remaining")
    x_tok = cells.get("x")
    y_tok = cells.get("y")

    if remaining_tok is None or x_tok is None or y_tok is None:
        return None

    try:
        remaining = parse_inch_range(remaining_tok)
        depth = parse_inch_range(depth_tok) if depth_tok else None
        x_mid, x_span = parse_location(x_tok)
        y_mid, y_span = parse_location(y_tok)
    except ValueError:
        return None
    if remaining is None:
        return None
    flags = flags_from_x(flag_xs)
    comment = " ".join(comment_parts)

    depth_derived = False
    if depth is None:
        # depth '-' rows report remaining thickness only; derive worst depth
        depth_worst = NOMINAL_IN - remaining[0]
        depth_derived = True
    else:
        depth_worst = depth[1]

    m = re.search(r"\((\d+)\)", comment)
    cluster = int(m.group(1)) if m else None
    if cluster is None:
        m = re.match(r"^(\d+)\s+INDICATION", comment)
        if m:
            cluster = int(m.group(1))

    side = "bottomside" if "underside" in flags else "topside"

    return {
        "plate": plate,
        "letter": letter,
        "side": side,
        "depth": depth_worst,
        "depth_derived": depth_derived,
        "remaining_thickness": remaining[0],  # worst (thinnest)
        "x": x_mid,
        "y": y_mid,
        "length": x_span,
        "width": y_span,
        "cluster_count": cluster if cluster is not None else 1,
        "flags": ",".join(sorted(flags - {"internal", "underside"})),
        "notes": comment,
    }


def _lines(page):
    """Group a page's words into text lines by vertical position."""
    lines = {}
    for w in page.extract_words():
        lines.setdefault(round(w["top"] / 3), []).append(w)
    return [lines[k] for k in sorted(lines)]


def parse_report(pdf_path, pages=(17, 30)):
    """Parse the reduction table into the common schema DataFrame."""
    records = []
    prev_plate = None
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(pages[0] - 1, pages[1]):
            for line in _lines(pdf.pages[i]):
                rec = parse_table_line(line, prev_plate)
                if rec is None:
                    continue
                prev_plate = rec["plate"]
                rec["anomaly_id"] = f"2011-{rec['plate']:03d}{rec['letter']}"
                rec["plate_id_raw"] = str(rec.pop("plate"))
                rec["nominal_thickness"] = NOMINAL_IN
                notes = [rec["notes"]]
                if rec["depth_derived"]:
                    notes.append("[depth derived from remaining thickness]")
                if rec["flags"]:
                    notes.append(f"[flags: {rec['flags']}]")
                rec["notes"] = " ".join(n for n in notes if n)
                records.append(rec)
    return finalize(records, "2011")
