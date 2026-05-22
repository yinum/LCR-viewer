# LCR-viewer — smoothing fix for sparse spectra

**Date:** 2026-05-22
**Status:** implemented

## Problem

New LCR spectra are sparsely sampled — each isotope peak is only ~2 signal
points bracketed by zeros (e.g. `results/LCR/PF4_polyP_3300.xy`, 388 points,
median ~4 raw points per peak group). The viewer's smoothing made these "ugly"
two ways at once:

- **Peaks collapse** — `buildGrid()` set the grid step to the raw point spacing,
  so a 4-point peak got a 4-cell grid; the 299-*grid-point* smoothing window
  then averaged in ~295 zeros and flattened the peak.
- **Jagged triangles** — with smoothing off, 2 points per peak draw as a sharp
  connect-the-dots triangle.

Testing also showed two deeper facts:

1. *Points-per-segment cannot detect sparsity.* One segment had 224 points
   spanning 20 m/z — just as under-sampled per peak (~2–3 points) as the
   4-point segments. The honest signal is the raw **sampling interval**
   (~0.025 m/z here, uniform across the spectrum).
2. *The window-in-grid-points is the root cause.* A grid cell is a different
   m/z width in every segment, so a fixed point count smooths a different
   physical span everywhere.

No dense-profile data exists anywhere in the workspace; all spectra are sparse.

## Decision

Unified pipeline (no dual code path), with the smoothing window expressed in
**m/z**. Changes are localised to the in-HTML JS `buildGrid()` + smoothing, one
control, and the Python `PRESET`/placeholder.

### Grid — fixed fine physical resolution + linear interpolation
- `GRID_DX = 0.002` m/z target resolution; per-segment `dx = min(GRID_DX,
  raw_median_gap)` (never coarser than raw), `ncell` capped at `MAX_CELLS =
  6000`.
- Raw intensities are **linearly interpolated** onto the uniform grid (replaces
  nearest-cell-max). Sparse peaks gain enough points to form a curve.
- Each segment is padded with `PAD_MZ = 0.12` m/z of **zero-baseline cells** on
  both sides, so a smoothed (broadened) peak decays fully back to zero within
  its own segment and the continuous-line connector runs along the baseline.
  Without this, an asymmetric peak's broadened skirt is cut off at the segment
  edge and the connector jumps across the gap at an elevated intensity.

### Smoothing — window in m/z
- Control: **"Smoothing width (m/z)"**, default `0.04` (`PRESET["width_mz"]`).
- `smoothAll()` converts the m/z width to a point window per segment via that
  segment's grid step, so the smoothing covers the same physical span on every
  peak. Smoothing primitives are unchanged (still point-based internally).

### Preset / control
- `PRESET`: `window: 299` → `width_mz: 0.04`. Template `__WIN__` → `__WIDTH__`.
- HTML control `id="win"` → `id="width"` (m/z float, `max="0.2"`).
- No migration: an old `preset.json` `window` key is ignored, default used.

## Verification

- `python3 -m unittest discover -s tests` — 28 tests pass (4 preset tests
  updated for the `width_mz` rename).
- The actual template JS, run in Node on `PF4_polyP_3300.xy` and
  `clipboard_spectrum.txt`: every peak smooths to a monotone up-then-down bump
  (apex preserved, e.g. raw 53.5 → smoothed 32.2), all segment edges return to
  exactly 0, no negative intensities; ~15 k total grid points.
- Full-range plot: `outputs/LCR/lcr_fixed_result.png`.

## Tunable constants

`GRID_DX`, `MAX_CELLS`, `PAD_MZ` live as named constants in the in-HTML
`buildGrid()`.

## Addendum 2026-05-22 — wider smoothing range + CSV cleanup

Follow-up request: the 0.2 m/z width cap was too small; CSV should omit zeros.

- Smoothing-width control `max` raised `0.2` → `10` m/z; `clampWin` cap raised
  `999` → `8001` points so the width is effective across the grid. Smoothing
  stays **per peak group** (peaks do not merge into an envelope).
- `PAD_MZ` `0.12` → `0.5` (the maximum that cannot make padded neighbours
  overlap, since segments split only at gaps > 1.0 m/z). The baseline stays
  clean for widths up to ~1 m/z; beyond that a peak's broadened skirt outruns
  its pad and segment edges lift slightly — accepted, as extreme per-peak
  smoothing of an isolated narrow peak is inherently a broad low smear.
- `movingAvg` reimplemented as an O(n) running sum so the default method stays
  responsive at large widths (verified bit-identical at width 0.04).
- `buildCSV()` now skips rows whose processed intensity is 0 — the exported
  processed-CSV omits the zero-baseline grid/pad cells. The on-screen plot is
  unchanged.

## Addendum 2026-05-22 — zero baseline across large voids

Follow-up: across a wide empty m/z stretch the single continuous line drew a
connector bridging the gap. At wide smoothing widths that connector sat above
zero and looked like a cross-gap average. Breaking the line entirely (a first
attempt) was wrong — it removed the baseline, and a spectrum needs a continuous
zero baseline. Smoothing was always strictly per cluster; this is drawing-only.

- New constant `GROUP_GAP = 30` (m/z). `recompute()` keeps the trace as one
  continuous line but, across any empty stretch wider than `GROUP_GAP`, inserts
  two zero-intensity anchor points so the line runs flat along the zero
  baseline between distant peak groups. Clusters closer than `GROUP_GAP` stay
  connected normally.
- `PROC_X`/`PROC_Y` (CSV source) are unaffected; only the plot trace gets the
  anchors.
- Result on `PF4_polyP_3300.xy`: peak groups (e.g. 3512–3625 and 3887–3964) are
  visually distinct, joined only by a true flat zero baseline — no break, no
  elevated bridge.
