# LCR-viewer — sibling processed CSV per build

**Date:** 2026-05-22
**Status:** implemented

## Problem

The viewer exports a processed CSV three ways — the **Download** button, the
**Link CSV file** live sync, and (Chromium) the File System Access picker — but
all of them need a human to open the viewer and click. There was no CSV on disk
straight from a build. The user wants every build to drop a CSV next to the
viewer and have the HTML link to it.

## Decision

Each build writes two files per spectrum into `OUTPUT_DIR`: the viewer
`LCR_mz<precursor>_<timestamp>.html` and a sibling `…<timestamp>.csv` with the
same stem. The viewer's control bar gains a **Sibling CSV file** hyperlink
(`href` is the bare filename, so it resolves in the same folder both as
`file://` and when `--serve`d). The existing Download / Link buttons stay.

The sibling CSV is a **preset-parameter snapshot**: it reflects the built-in
`PRESET` overlaid with `preset.json`, the viewer's starting settings. It does
not track live control edits — re-run the build to refresh it, or use the
buttons for current on-screen settings. The viewer header and the link's
tooltip say so.

## How the CSV is computed

The processing pipeline lived only in the viewer's JavaScript (`buildGrid` +
`smoothAll` + `buildCSV`). To write the CSV at build time without a browser,
that pipeline is mirrored in Python in `build_lcr_viewer.py`:

- `build_grid(mz, it)` — segment, fine-grid resample, zero-baseline pad.
- `smooth_all(...)` with `_moving_avg` / `_gauss_kernel` / `_convolve` /
  `_median_filt` / `_binomial` / `_savgol` (+ `_invert`) — all five methods.
- `process_spectrum(mz, it, thr, preset)` → `(proc_x, proc_y)`; `build_csv`
  emits `m/z,intensity_processed`, dropping zero-baseline rows.
- `_jround` reproduces JavaScript `Math.round` (round half up) so grid-cell and
  window counts match the JS exactly; Python's banker's rounding would drift.

The Python mirror and the in-HTML JS must stay in lockstep — a duplication
accepted so a plain (non-`--serve`) build needs no Node/browser. `--serve` also
serves the sibling CSVs (`text/csv`) so the in-viewer hyperlink works there too.

## Verification

- `python3 -m unittest discover -s tests` — 39 tests pass (added: `build_grid`
  finer-than-raw + segment count, `process_spectrum` scaling and smoothing,
  `build_csv` header + zero-row drop, integration now expects HTML + CSV).
- Cross-check against the viewer's own JS pipeline (extracted from `TEMPLATE`,
  run in Node) on `PF4_polyP_3300.xy`: 128,433 CSV rows on each side, maximum
  absolute m/z and intensity difference 0.0 — the Python mirror is bit-exact.
- End-to-end on `results/LCR/` (5 spectra): each produced a paired `.html` and
  `.csv`; the HTML carries `href="<same-stem>.csv"`.
