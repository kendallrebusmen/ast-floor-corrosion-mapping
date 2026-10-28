"""Derive config `shell_appurtenances.station_zero_azimuth_deg` (Manway A) from
the 2011 Semper Fi floor-plate drawing DWG 5-1 (PDF page 60, vector).

Read-only on data/raw. The drawing has exactly one black-filled shape on the
shell: the Manway P symbol (the Manway "A" symbol is drawn as an outline over
the shell). Its azimuth + 180 deg is Manway A (the two are 183'-9" apart on a
367.6 ft circumference). The ten green nozzle ticks cross-check direction and
zero against the pp.40-41 station table.

Run:  .venv\\Scripts\\python.exe tools\\derive_station_zero.py
"""
import math
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data" / "raw" / "Port Everglades FL (C) - Tank 201- OOS June 2011.pdf"
PAGE_INDEX = 59                   # DWG 5-1 (1-based page 60)
CENTER = (294.0, 317.9)           # tank circle on the page, pt (Phase 2 calibration)
RADIUS = 216.25
CIRC_FT = math.pi * 117.0
# id, station_ft from the pp.40-41 table (subset drawn as ticks on DWG 5-1)
STATIONS = [("P manway", 183.75), ("X 16in inlet", 274.0), ("Q 8in", 221.67),
            ("J 10in inlet", 121.58), ("H 10in suction", 101.25), ("AA 2in W/D", 317.0)]


def _az(x, y):
    """Page point -> compass azimuth (deg cw from north); page y grows down."""
    return math.degrees(math.atan2(x - CENTER[0], CENTER[1] - y)) % 360.0


def _is_black(obj):
    c = obj.get("non_stroking_color")
    return obj.get("fill") and c is not None and all(abs(float(v)) < 0.05 for v in _flat(c))


def _is_green(obj):
    c = obj.get("stroking_color") or obj.get("non_stroking_color")
    if c is None:
        return False
    v = _flat(c)
    return len(v) == 3 and v[1] > 0.5 and v[0] < 0.4 and v[2] < 0.4


def _flat(c):
    return [float(x) for x in (c if isinstance(c, (list, tuple)) else [c])]


def main():
    if not PDF.exists():
        sys.exit(f"missing {PDF}")
    with pdfplumber.open(PDF) as pdf:
        page = pdf.pages[PAGE_INDEX]
        shapes = list(page.rects) + list(page.curves)
    on_shell = []
    for s in shapes:
        cx, cy = (s["x0"] + s["x1"]) / 2, (s["top"] + s["bottom"]) / 2
        r = math.hypot(cx - CENTER[0], cy - CENTER[1])
        if abs(r - RADIUS) < 12:
            on_shell.append((s, cx, cy, r))
    black = [(cx, cy) for s, cx, cy, r in on_shell if _is_black(s)]
    if len(black) != 1:
        sys.exit(f"expected exactly 1 black shell shape, found {len(black)}: {black}")
    az_p = _az(*black[0])
    az_a = (az_p + 180.0) % 360.0
    print(f"Manway P (black shell symbol): azimuth {az_p:.1f} deg")
    print(f"Manway A = P + 180            : azimuth {az_a:.1f} deg  <- station_zero_azimuth_deg")

    ticks = sorted(_az(cx, cy) for s, cx, cy, r in on_shell if _is_green(s))
    print(f"\n{len(ticks)} green nozzle ticks on the shell at: "
          + ", ".join(f"{t:.1f}" for t in ticks))
    print("\nstation -> predicted azimuth (ccw = decreasing) vs nearest drawn tick")
    for name, st in STATIONS:
        pred = (az_a - st / CIRC_FT * 360.0) % 360.0
        near = min(ticks + [az_p], key=lambda t: abs((t - pred + 180) % 360 - 180)) if ticks else float("nan")
        print(f"  {name:16} {st:7.2f} ft -> {pred:6.1f}   drawn {near:6.1f}   "
              f"residual {((near - pred + 180) % 360 - 180):+5.1f}")


if __name__ == "__main__":
    main()
