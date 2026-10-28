\# AST Floor Corrosion Anomaly Matching \& Rate Analysis



\## Project Overview



This project matches corrosion anomalies between two floor scan inspections of an above-ground storage tank (AST) and calculates short-term corrosion rates per API 653. We have two inspections from the same tank, roughly 15 years apart, to use as the demo dataset.



Inspection data comes from UT (ultrasonic thickness) floor scans performed by inspection companies. Each inspection reports anomalies on both surfaces of the tank floor:

\- \*\*Topside\*\* (inspection side / product side): corrosion on the interior surface of the floor plates

\- \*\*Bottomside\*\* (soil side / external floor): corrosion on the underside of the floor plates, typically inferred from UT remaining-thickness readings



\## Goal



1\. \*\*Ingest\*\* both inspection datasets (formats TBD — likely CSV/Excel exports from the inspection vendor; may differ between vendors/years)

2\. \*\*Normalize\*\* the data into a common schema and coordinate system

3\. \*\*Match\*\* anomalies from Inspection 1 to Inspection 2 using plate number, X/Y location, corrosion side (top/bottom), depth, length, width

4\. \*\*Calculate\*\* corrosion growth and short-term corrosion rates for matched anomalies per API 653

5\. \*\*Report\*\* results: matched pairs with rates, new anomalies (in scan 2 only), disappeared anomalies (in scan 1 only — likely repaired plates or detection differences), and flagged high-growth locations

6\. \*\*Visualize\*\* the tank floor as a plate map with anomaly overlays from both inspections



\## Domain Context (important for correct implementation)



\- Tank floors are made of rectangular \*\*sketch plates and rectangular plates\*\*, plus an \*\*annular ring\*\* (segmented plates around the perimeter) on some tanks. Anomalies are always reported against a plate number.

\- \*\*Plate numbering may differ between inspections.\*\* Different vendors number plates differently (row/column conventions, starting corner, orientation relative to north or to the shell manway). Do not assume plate "A3" in 2010 is plate "A3" in 2025. Part of this project is building a plate-mapping/reconciliation step.

\- \*\*Coordinate conventions may differ.\*\* X/Y may be measured from plate corner, plate center, or tank datum; units may be inches, feet, or mm. Scan direction/orientation can flip axes. Normalize everything to a single tank-level coordinate system (e.g., inches from a fixed datum) before matching.

\- Corrosion may be reported as \*\*remaining thickness\*\* or as \*\*pit depth / % wall loss\*\*. Nominal plate thickness is needed to convert between them. Confirm which convention each dataset uses — mixing them silently is the most dangerous failure mode in this project.

\- UT floor scanners have detection thresholds and sizing tolerances. Two scans of the same unchanged pit can differ by ±10–20% depth and several inches in reported location. Matching tolerances must account for this.

\- Plates may have been \*\*repaired or replaced\*\* between inspections (patch plates, weld build-up). A "disappeared" anomaly cluster on one plate is a strong repair signal — flag it, don't force-match it.



\## Common Data Schema



Normalize each anomaly record to:



| Field | Type | Notes |

|---|---|---|

| `inspection\_id` | str | e.g., "2010", "2025" |

| `anomaly\_id` | str | unique within inspection |

| `plate\_id\_raw` | str | vendor's plate number as reported |

| `plate\_id\_norm` | str | reconciled plate ID in our master plate map |

| `side` | enum | `topside` or `bottomside` |

| `x`, `y` | float | tank-level coordinates, inches, common datum |

| `depth` | float | pit depth, inches (convert from % loss or remaining thickness) |

| `remaining\_thickness` | float | inches |

| `nominal\_thickness` | float | inches, per plate |

| `length`, `width` | float | anomaly extent, inches |

| `notes` | str | vendor comments (through-wall, weld, repair, etc.) |



\## Matching Algorithm



Match within (plate, side) groups after plate reconciliation. Suggested approach:



1\. \*\*Plate reconciliation first.\*\* Build a mapping table between the two inspections' plate numbering schemes. Use plate dimensions, layout order, and anomaly density patterns to assist; require human confirmation of the mapping before trusting downstream results.

2\. \*\*Candidate generation:\*\* for each anomaly in inspection 2, find inspection-1 anomalies on the same plate and side within a spatial tolerance (start with \~6 inches radius; make it configurable). Use `scipy.spatial.cKDTree` per plate/side group.

3\. \*\*Scoring:\*\* score candidate pairs on a weighted combination of:

&#x20;  - spatial distance (dominant weight)

&#x20;  - size similarity (length/width)

&#x20;  - depth plausibility: matched depth in inspection 2 should be \*\*≥ inspection 1 depth minus measurement tolerance\*\* (corrosion doesn't heal; a large negative delta suggests a bad match or a repair)

4\. \*\*Optimal assignment:\*\* use `scipy.optimize.linear\_sum\_assignment` (Hungarian algorithm) per plate/side group so each anomaly matches at most one counterpart. Reject assignments above a max-cost threshold.

5\. \*\*Classification of results:\*\*

&#x20;  - `matched` — compute growth and rate

&#x20;  - `new` — inspection 2 only (new corrosion or previously below detection threshold)

&#x20;  - `not\_found` — inspection 1 only (repaired, replaced plate, or sizing/detection difference)

&#x20;  - Handle \*\*cluster splits/merges\*\*: one large anomaly in scan 2 may correspond to several small pits in scan 1 (coalesced pitting). Support one-to-many matching as a second pass, or at minimum flag near-misses for review.



All tolerances and weights go in a single config file (`config.yaml`) so they can be tuned during the demo.



\## Corrosion Rate Calculations (API 653)



Implement per \*\*API 653, Section 4.4 (Tank Bottom Evaluation)\*\*. The user has the API 653 document — \*\*ask them to provide or verify the exact formulas and paragraph numbers from their edition before finalizing calculations.\*\* Do not guess formula details. The framework:



\- \*\*Short-term corrosion rate per matched anomaly\*\* (per side):

&#x20; - `rate = (depth\_insp2 − depth\_insp1) / interval\_years`

&#x20; - Equivalent remaining-thickness form: `rate = (RT\_insp1 − RT\_insp2) / interval\_years`

&#x20; - Interval in decimal years from actual inspection dates

\- Track \*\*StPr (topside/product-side rate)\*\* and \*\*UPr (underside rate)\*\* separately, matching API 653 terminology

\- Compute per-anomaly rates, plus per-plate and whole-floor maximums (governing rates)

\- \*\*Minimum remaining thickness (MRT) projection and remaining life / next internal inspection interval\*\* per API 653 §4.4.5 — implement using formulas verified from the user's copy of the standard, including any liner/coating and cathodic protection factors the standard applies

\- Handle negative apparent growth (insp2 depth < insp1 depth): report rate as 0 or flag for review rather than reporting a negative rate; make the policy configurable

\- Note measurement uncertainty: with a 15-year interval, rate resolution is good (\~±0.001–0.002 in/yr for typical UT tolerance), but still surface a rate uncertainty estimate alongside each rate



\## Tech Stack



\- Python 3.11+, managed with `uv` or venv

\- `pandas` for data handling, `openpyxl` for Excel ingestion

\- `scipy` for KD-tree matching and Hungarian assignment

\- `matplotlib` (or `plotly` for interactive) for plate-map visualizations

\- `pytest` for tests — matching logic and rate math must have unit tests with hand-checked cases

\- Simple CLI entry points (e.g., `python -m tankfloor match --config config.yaml`) or a small `typer` CLI



\## Project Structure



```

tankfloor/

&#x20; ingest/          # per-vendor parsers -> common schema

&#x20; normalize/       # units, coordinates, plate reconciliation

&#x20; match/           # candidate gen, scoring, assignment

&#x20; rates/           # API 653 calculations

&#x20; report/          # Excel/CSV output tables, summary

&#x20; viz/             # plate map plots, before/after overlays

&#x20; config.yaml

data/

&#x20; raw/             # original inspection files (never modified)

&#x20; processed/

tests/

```



\## Outputs / Deliverables



1\. \*\*Matched anomaly table\*\* (Excel/CSV): both inspections' attributes side by side, match score, growth, short-term rate

2\. \*\*Exceptions report\*\*: new anomalies, not-found anomalies, suspected repairs, review-flagged matches

3\. \*\*Governing rates summary\*\*: max StPr and UPr per plate and floor-wide, projected MRT / remaining life inputs

4\. \*\*Floor visualization\*\*: plate layout with anomalies from both inspections overlaid (color by depth, marker by inspection), highlighting matched pairs and high-growth locations



\## First Steps (do these before writing matching code)



1\. Ask the user for the two inspection files and inspect them: file format, columns, units, plate numbering scheme, coordinate convention, whether depth or remaining thickness is reported, nominal plate thicknesses, exact inspection dates, tank diameter and plate layout drawing if available

2\. Build the ingest parsers and get both datasets into the common schema; produce a quick plate map of each inspection so the user can visually confirm orientation and plate reconciliation

3\. Only then implement matching, and tune tolerances against a handful of anomalies the user can manually verify as the same feature



\## Working Rules



\- Never modify files in `data/raw/`

\- Every unit conversion must be explicit and tested; assume nothing about units without confirming from the source file or the user

\- Any API 653 formula implemented must cite the section/paragraph number and be confirmed against the user's copy of the standard

\- Prefer flagging uncertain matches for human review over silently forcing a match — this data drives inspection intervals and repair decisions

---

## Current state (updated 2026-09-02) — read this before the brief above

The brief above was written before implementation. All phases are built; the sections below are what is actually true now.

### Pipeline and commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q          # 164 tests, ~60 s (two integration modules parse the PDFs)
.\.venv\Scripts\python.exe -m tankfloor ingest         # PDFs -> anomalies_2011/2026.csv, repairs_recommended_2026.csv
.\.venv\Scripts\python.exe -m tankfloor platemap       # platemap_2011/2026.png (depth-% bands, manways)
.\.venv\Scripts\python.exe -m tankfloor normalize      # *_normalized.csv (tank_x/tank_y), platemap_overlay.png
.\.venv\Scripts\python.exe -m tankfloor match          # matched_anomalies.csv, exceptions_*.csv
.\.venv\Scripts\python.exe -m tankfloor rates          # rates_matched.csv (+years_remaining), scenarios.csv, repair_strategy.csv, governing_rates_summary.md, platemap_rates.png
.\.venv\Scripts\python.exe -m tankfloor dashboard      # data/processed/dashboard.html (self-contained artifact body)
powershell -ExecutionPolicy Bypass -File make_standalone.ps1   # wraps it into TK201-Floor-Corrosion-Dashboard-2011-2026.html (run after every dashboard build)
.\.venv\Scripts\python.exe tools\derive_station_zero.py        # reproduces the manway azimuth from the 2011 DWG (read-only)
```

Run order matters: `match` regenerates `exceptions_new_2026.csv` **without** `years_remaining`; `rates` re-adds it and `dashboard` refuses to build if `rates_matched.csv` lacks the column. Always use the venv python.

- Data sources are **PDF reports** (2011 Semper Fi, 2026 ROSEN prelim Rev 1) plus the ROSEN scanner project under `data/raw/Bottom/Tbit/Work/` — `Layout.MAP` is the plate-geometry source of truth (see auto-memory `tbit-raw-data-formats`). No vendor CSV/Excel exists; nothing writes Excel.
- Layering: `ingest/` (pdfplumber parsers) → `normalize/` (`layout_map.py`, `tank_coords.py`, `shell.py` for manways) → `match/matcher.py` → `rates/` (`shortterm.py` pair rates, `projection.py` MRT/Or/years-remaining/repair-strategy) → `viz/` (`platemap.py`, `bands.py`) and `report/dashboard.py`. `__main__.py` is IO glue only; put math in pure functions with tests.

### Config contracts (`tankfloor/config.yaml`)

- `rates.projection`: `mrt_min_bottom_in 0.100`, `upr_in_per_yr 0.00132` (assumed, ROSEN p.332 @49%), `or_cap_years 20`, `years_installed 93` (ROSEN basis, built 1933 — `tank.year_built 1936` is unresolved; **keep 93** or the vendor table cross-check breaks), `coated_stpr_in_per_yr 0.0` (shown alongside, never governing), `repair_thresholds_pct`.
- `shell_appurtenances`: stations (ft, ccw from Manway A) + `station_zero_azimuth_deg 288.8` (derived from DWG 5-1 vectors, ±1.5°). Only `render_types` are drawn (manways); doorsheets/nozzles are listed but off.
- `viz.depth_bands`: edges are lower-inclusive; labels/colors must be edges+1 long (`bands_from_config` raises otherwise).
- `nominal_thickness.floor_in` and `inspections.2026.recording_threshold.depth_pct_min` drive the scenario RTs — no hard-coded 0.250/49 anywhere in `cmd_rates`.

### Dashboard rules

- Every number in `dashboard_template.html` is a `<span data-stat="key" data-fmt="...">` filled from `STATS`; the key set is `STAT_KEYS` in `dashboard.py` and `tests/test_dashboard.py` fails if the template uses a key that isn't emitted. **Never hand-edit numbers in the template.**
- Positional arrays are indexed by name via `DATA.fields` (`FIELDS` in `dashboard.py`); append new slots, never reorder, and update both sides.
- Artifact URL is stable (in home auto-memory `ast-floor-corrosion-project`); republish the same file path / pass that URL. Favicon stays 🛢️.
- The artifact declares the `downloads` runtime capability (the "All matched pairs" table's Download CSV goes through `claude.use("downloads")` in the viewer; the standalone file uses a Blob download). On republish **omit** `capabilities` to keep it — passing `{}` clears it and silently hides the button (Copy CSV still works).
- Design system: steel-paper engineering look, light + dark tokens, dataviz status palette for depth bands (yellow/orange are sub-3:1 on white by design — keep the hairline strokes and % in tooltips). Node is not installed here, so the dataviz palette validator cannot run; rely on the skill's published contrast table.

### Decisions already made (don't re-ask)

- API 653 5th Ed (2014); MRT = min(RTbc, RTip) − Or×(StPr+UPr) confirmed 2026-08-06. Governing StPr is measured 0.0076 in/yr with **no coating credit**; coated figures are comparison only (2026-09-02).
- Years remaining = (RT_2026 − 0.100)/(rate + UPr), cap 20; matched pairs use their own clamped rate, new features the governing StPr.
- Depth bands <50 / 50–69 / 70–89 / 90–99 / through-wall. Manways only, no sumps/nozzles.
- Plate mapping is identity (both vendors use the same serpentine numbering); 2011 within-plate convention is X from west edge, Y from south edge — **except rows flagged "N/E Corner"** in the reduction table (21 rows, all of plates 103/104 whose SW corner is cut by the shell), which are measured from the NORTHEAST corner. Ignoring the flag put two plate-104 pits outside the tank (fixed 2026-09-02; `tests/test_tank_coords.py::TestRealData2011` guards it). Do not "fix" rim-plate positions by measuring from the physical shell cut — that hypothesis was tested and is worse.
- Dashboard map has a depth-band filter (`#bandf`): clicking a band when all are on isolates it; further clicks toggle; "all" resets. Every marker carries `data-b`.

### Environment gotchas

- Multi-line Bash heredocs containing many quotes fail to parse in this tool ("unexpected EOF while looking for matching"); write the script to the scratchpad with the Write tool and run it, or use the Edit tool.
- `pytest` full run reparses both PDFs (~60 s); run a single module while iterating.
- `data/processed/README.md` is rewritten by `ingest` — extend the text in `cmd_ingest`, not the file.

