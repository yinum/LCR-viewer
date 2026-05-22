# polyP LCR spectrum viewer

Builds self-contained interactive HTML viewers for polyP limited-charge-reduction
(LCR) mass spectra (Waters Synapt, positive mode) — one viewer per spectrum, or a
whole folder of spectra in one run.

The viewer lets you:

1. **Scale** the charge-reduced region (`m/z >= threshold`) by a factor (preset 10x),
   leaving the parent envelope at 1x.
2. **Smooth** the spectrum with an Origin-style method dropdown
   (Savitzky-Golay, adjacent averaging, Gaussian, binomial, median/percentile).
   Each peak group is resampled onto a uniform m/z grid (collapsed baseline
   restored as zeros) and smoothed with zero-baseline padding: past a peak
   group's edge the window is filled with zeros rather than shrunk, so a window
   of N affects every peak identically and the result equals Origin smoothing
   the full continuous zero-baseline profile. The spectrum is drawn as one
   continuous line.

All controls update the plot live; PNG export and processed-CSV export are built in.

## Setup

The Plotly basic bundle is not committed (third-party, ~1 MB). Download it once
next to the script:

```sh
curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js
```

## Usage

Input is a 2-column m/z, intensity file (whitespace-, tab-, or comma-delimited),
or a folder of such files.

```sh
python3 build_lcr_viewer.py INPUT [OUTPUT_DIR]
```

- `INPUT` — a single spectrum file, or a folder; a folder builds one viewer
  per `.txt`/`.csv`/`.xy` file inside it.
- `OUTPUT_DIR` — optional; defaults to `../../outputs/LCR/individual peaks`
  (the workspace `outputs/` data area).

Each viewer is named `LCR_mz<precursor>_<YYYYMMDD-HHMM>.html`. The precursor
m/z is read from the spectrum filename's trailing number when present
(`PF4_polyP_3300.xy` → `3300`, decimals allowed); otherwise it is inferred
from the base peak. A filename precursor also anchors the scaling threshold to
that m/z's peak cluster — correct even when a charge-reduced product is more
intense than the precursor. The timestamp means re-runs never overwrite a
prior viewer.

Processing parameters come from the preset (built-in `PRESET` defaults —
charge-reduced ×10, adjacent-averaging smoothing, window 299, pre-smoothing
overlay hidden — overlaid by a viewer-saved `preset.json` if present; see
[Saving a preset](#saving-a-preset)). The "scale applies above m/z" threshold
is auto-placed per spectrum, just past the parent envelope. All values stay
live-editable in the viewer; the preset only sets the starting point.

The generated HTML is fully self-contained (Plotly inlined) and works offline —
no data leaves the machine.

### Live-synced CSV

The viewer has a **Link CSV file** button: in Chrome or Edge, pick a `.csv`
once and it is rewritten automatically on every parameter change. Other
browsers fall back to the **Download processed CSV** button, which regenerates
the CSV from current parameters on each click.

### Saving a preset

Tune the controls in any viewer, then click **Save preset** to write a
`preset.json`. Keep that file next to `build_lcr_viewer.py`: every later run
loads it and uses its values as the control defaults. The built-in `PRESET`
dict in the script is the fallback when no `preset.json` is present.

In Chrome or Edge, Save preset writes the file directly; other browsers
download `preset.json`, which you then move next to the script. `preset.json`
is git-ignored — it is local tuning state.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Note

Spectral data and generated HTML/CSV are git-ignored: this repository tracks the
code only, never the scientific data.
