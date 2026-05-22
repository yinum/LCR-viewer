# LCR viewer — preset + batch + auto-threshold

Date: 2026-05-21
Status: approved for planning

## Goal

Make `build_lcr_viewer.py` reusable across many polyP LCR spectra: lock in the
processing parameters the user tuned, auto-place the scaling threshold per
spectrum, and emit one named viewer per spectrum into a shared output folder.

## Background

`build_lcr_viewer.py` currently builds one self-contained interactive HTML
viewer for one LCR spectrum: `python3 build_lcr_viewer.py INPUT.txt OUTPUT.html`.
The HTML exposes live controls — charge-reduced ×factor, "scale applies above
m/z" threshold, smoothing method/window/poly order, overlay and log-Y toggles.
Defaults are hard-coded in the HTML `TEMPLATE`.

The user tuned the viewer to settings they are happy with and now wants to
apply the same processing to additional spectra without re-tuning each time.

## Requirements

1. **Preset.** The user's tuned parameters become the saved, version-controlled
   default for every generated viewer:
   - charge-reduced ×factor = **10**
   - smoothing method = **adjacent averaging**
   - window = **299**
   - pre-smoothing overlay = **hidden** (checkbox unchecked)
   - poly order is retained in the preset (unused by adjacent averaging) so the
     SG control still has a sane default if switched live.
2. **Auto-threshold.** The "scale applies above m/z" value is computed per
   spectrum, not preset — it differs for every spectrum.
3. **Batch input.** The input argument accepts a single file *or* a folder; a
   folder builds one viewer per spectrum file inside it.
4. **Output routing.** Generated viewers go to
   `PolyP/outputs/LCR/individual peaks/`.
5. **Naming.** Each file is named by the precursor ion m/z.
6. **Re-runs.** A timestamp suffix is always appended, so re-running never
   overwrites a prior viewer.
7. **Save the current.** After the change lands, the existing
   `clipboard_spectrum.txt` is processed to produce the first viewer in the
   output folder.
8. **Processed-CSV sync.** The viewer can keep an on-disk CSV synchronized with
   the live parameters: a linked-file auto-rewrite where the browser supports
   it, plus the existing download button as a universal fallback.

## Design

Chosen approach: extend `build_lcr_viewer.py` in place (single ~300-line
script). A separate batch wrapper or JSON preset file was rejected as
unnecessary moving parts given the small size and now-stable parameters.

### Preset

A clearly-marked dict near the top of the script is the single record of the
remembered parameters:

```python
PRESET = {
    "scale": 10,            # charge-reduced ×factor
    "method": "avg",        # adjacent averaging
    "window": 299,          # smoothing window (odd)
    "poly": 3,              # SG poly order, retained for the SG control
    "show_overlay": False,  # pre-smoothing overlay checkbox default
}
```

These values are substituted into the HTML `TEMPLATE` as the live-control
defaults: `scale` input value, `<select id="method">` selected option,
`win` input value, `poly` input value, and the `rawov` checkbox `checked`
attribute. All controls remain live-editable in the browser; the preset only
sets the starting point.

Editing the preset is the supported way to change the saved parameters.

### Auto-threshold

New function `auto_threshold(mz, it) -> float`:

1. Segment the raw data at large m/z gaps, reusing the same gap-detection logic
   the in-HTML `buildGrid` uses (median small gap × ~60, floored at 1.0 m/z).
2. Find the global base peak (max intensity) and the segment containing it —
   this is the parent envelope.
3. Return `right-edge m/z of that segment + margin`, where `margin` is small
   (a couple of m/z) and clamped so the threshold stays within the empty
   valley before the next (charge-reduced) segment — i.e. it never lands inside
   the next cluster.

The result is substituted into `TEMPLATE` as the default `thr` input value,
per spectrum. It stays live-editable.

Assumption: the parent envelope is the most intense cluster in an LCR spectrum
(charge-reduced products are minor — that is why they need ×10). If a spectrum
violates this, the user corrects the threshold live in the browser.

### Input / output / naming

- `main()` argument 1 is a path to a file or a directory.
  - File → build one viewer.
  - Directory → build one viewer per spectrum file in it (non-recursive;
    plain-text two-column files).
- Argument 2 (optional) overrides the output directory.
- Default output directory: `../../outputs/LCR/individual peaks/`, resolved
  relative to the script's own location, then created if absent.
- Precursor m/z = the auto-detected base-peak apex m/z, rounded to the nearest
  integer.
- Output filename: `LCR_mz<precursor>_<YYYYMMDD-HHMM>.html`
  (e.g. `LCR_mz2092_20260521-2345.html`). The timestamp is always present.

### Data flow

```
input path ──> for each spectrum file:
                 parse 2-col m/z,intensity
                 ──> auto_threshold()  ──> thr
                 ──> TEMPLATE + PRESET + thr + data
                 ──> write outputs/LCR/individual peaks/LCR_mz<p>_<ts>.html
```

### Processed-CSV sync

A browser cannot silently write to the filesystem, so a static viewer cannot
keep an arbitrary CSV file updated. Two mechanisms cover the gap:

- **Linked-file auto-rewrite (File System Access API).** A new "Link CSV file"
  button calls `window.showSaveFilePicker()` once; the returned
  `FileSystemFileHandle` is stored. Thereafter every `recompute()` (i.e. every
  parameter change) rewrites that file via `handle.createWritable()` with the
  current processed CSV. A status line shows the linked file name. Writes are
  lightly debounced so rapid edits do not queue many writes.
  - Feature-detected: if `window.showSaveFilePicker` is absent (Firefox,
    Safari), the "Link CSV file" button is disabled with a short note.
- **Download button (fallback).** The existing "Download processed CSV" button
  is retained unchanged — it regenerates the CSV from current parameters on
  each click and works in every browser.

Both paths share one `buildCSV()` helper so the linked file and the downloaded
file are always byte-identical for the same parameters.

### Error handling

- A file with no parseable numeric rows is skipped with a warning; in folder
  mode the run continues to the next file.
- Missing output directory is created.
- `plotly-basic.min.js` missing → hard error (as today).

## Out of scope

- Recursive folder scanning.
- Changing the smoothing / scaling math itself.
- Committing generated viewers (they land in the workspace `outputs/` data
  area and stay un-committed, per repo rules).
- A combined multi-spectrum viewer — each spectrum still gets its own file.

## Verification

- Run on `clipboard_spectrum.txt` (single file) → one viewer in the output
  folder, named by precursor m/z, with preset controls applied and an
  auto-threshold near the existing manual value (~2160).
- Run on a folder containing ≥2 spectra → one correctly named viewer each.
- Open a generated viewer: scale defaults to 10, method to adjacent averaging,
  window 299, overlay hidden, threshold pre-filled and editable.
- In a Chromium browser: "Link CSV file" → pick a file → change a parameter →
  the linked file's contents update. In Firefox/Safari the button is disabled
  and the download button still works.

## Docs to update

- `README.md` — file-or-folder usage, preset, auto-threshold, output location.
- `AGENTS.md` — same, in the agent-facing register.
