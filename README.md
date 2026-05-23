# polyP LCR spectrum viewer

Builds self-contained interactive HTML viewers for polyP limited-charge-reduction
(LCR) mass spectra (Waters Synapt, positive mode) — one viewer per spectrum, or a
whole folder of spectra in one run.

The viewer lets you:

1. **Scale** the charge-reduced region (`m/z >= threshold`) by a factor (preset 10x),
   leaving the parent envelope at 1x. Optional — turn it off with the
   **"Scale charge-reduced region"** checkbox to smooth a plain MS1 spectrum
   with no scaling.
2. **Smooth** the spectrum with an Origin-style method dropdown
   (Savitzky-Golay, adjacent averaging, Gaussian, binomial, median/percentile).
   Each peak group is linearly interpolated onto a fine uniform m/z grid (so
   even sparse, few-point peaks gain enough points to form a smooth curve) and
   padded with zero-baseline cells on each side so a broadened peak decays back
   to zero. The smoothing width is set in **m/z**, so it covers the same span on
   every peak, and the result equals Origin smoothing the full continuous
   zero-baseline profile. The spectrum is drawn as one continuous line.

All controls update the plot live; PNG export and processed-CSV export are built in.
Each build also writes a processed CSV next to the viewer (see
[Sibling CSV file](#sibling-csv-file)).

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
python3 build_lcr_viewer.py [--serve] INPUT [OUTPUT_DIR]
```

- `INPUT` — a single spectrum file, or a folder; a folder builds one viewer
  per `.txt`/`.csv`/`.xy` file inside it.
- `OUTPUT_DIR` — optional; defaults to `output/LCR/<dataset>/` beside the
  script, where `<dataset>` is the input folder's name (the parent folder's
  name for a single input file). Point the build at `results/LCR/PF4_polyP/`
  and its viewers land in `output/LCR/PF4_polyP/`; `results/LCR/polyP/` →
  `output/LCR/polyP/`. The whole `output/` tree is git-ignored.
- `--serve` — after building, also serve the viewer(s) on a localhost address
  and open the browser, so **Save preset** writes `preset.json` directly and
  **Update sibling CSV** overwrites the build-time sibling without a dialog
  (see [Saving a preset](#saving-a-preset) and
  [Updating the sibling CSV in place](#updating-the-sibling-csv-in-place)).

Each run writes two files per spectrum into `OUTPUT_DIR`: the viewer
`LCR_mz<precursor>_<YYYYMMDD-HHMM>.html` and a sibling processed CSV with the
same stem (see [Sibling CSV file](#sibling-csv-file)). The precursor
m/z is read from the spectrum filename's trailing number when present
(`PF4_polyP_3300.xy` → `3300`, decimals allowed); otherwise it is inferred
from the base peak. A filename precursor also anchors the scaling threshold to
that m/z's peak cluster — correct even when a charge-reduced product is more
intense than the precursor. The timestamp means re-runs never overwrite a
prior viewer.

Processing parameters come from the preset (built-in `PRESET` defaults —
charge-reduced scaling on (×10), adjacent-averaging smoothing, width 0.04 m/z,
pre-smoothing overlay hidden — overlaid by a viewer-saved `preset.json` if
present; see [Saving a preset](#saving-a-preset)). The "scale applies above
m/z" threshold is auto-placed per spectrum, just past the parent envelope.
Setting `scale_on: false` in `preset.json` makes plain MS1 smoothing the
default for every later build. All values stay live-editable in the viewer;
the preset only sets the starting point.

The generated HTML is fully self-contained (Plotly inlined) and works offline —
no data leaves the machine.

### Sibling CSV file

Every build writes a processed CSV next to the viewer it belongs to, with the
same stem (`LCR_mz3300_….html` → `LCR_mz3300_….csv`). It holds the
`m/z,intensity_processed` spectrum after the full scale + smooth pipeline, run
with the **preset** parameters — the build computes it directly, no browser
needed, and it matches the viewer's export at its starting settings exactly.
The viewer's header shows a **Sibling CSV file** hyperlink to it. The CSV is a
fixed snapshot: if you edit the controls in the viewer it does not change
automatically — refresh it with the **Update sibling CSV** button (below),
re-run the build, or use the other live options for the current on-screen
settings.

### Updating the sibling CSV in place

The viewer has an **Update sibling CSV** button that overwrites the build-time
sibling with the current on-screen settings:

- **Served** (`build_lcr_viewer.py --serve …`) — one click writes the sibling
  in `OUTPUT_DIR` directly, no dialog. The status line confirms *"updated
  LCR_mz…csv"*.
- **Opened as a file** in Chrome or Edge — first click opens a save dialog
  pre-suggesting the sibling's name (in the sibling CSV's own folder, via
  the shared `lcr-sibling-csv` picker id). The handle is persisted to
  IndexedDB, so subsequent clicks overwrite silently *and reloads re-link the
  same file* — at most a one-click readwrite re-grant after a reload, never
  another save dialog.
- **Other browsers** — disabled (no File System Access API); use **Download
  processed CSV** instead and move the file into place, or run with `--serve`.

### Live-synced CSV

The viewer has a **Link CSV file (live)** button: in Chrome or Edge, click it
once and pick an existing `.csv` (open dialog, opens in the sibling CSV's
folder), grant readwrite permission, and the file is rewritten on every
parameter change. The handle is persisted to IndexedDB; after a page reload
the status shows *"linked … (click Link to re-activate)"* — one click
re-grants permission and live sync resumes without re-picking the file.

The **Download processed CSV** button is the one-shot alternative: in
Chrome/Edge (standalone) it opens a save dialog in the sibling CSV's folder
with the sibling's name pre-filled (rename as needed); in other browsers it
falls back to a classic browser download.

### Saving a preset

Tune the controls in any viewer, then click **Save preset** to write a
`preset.json`. Keep that file next to `build_lcr_viewer.py`: every later run
loads it and uses its values as the control defaults. The built-in `PRESET`
dict in the script is the fallback when no `preset.json` is present.

How **Save preset** delivers the file depends on how the viewer was opened:

- **Served** (`build_lcr_viewer.py --serve …`) — Save preset POSTs to the
  localhost server, which writes `preset.json` next to the script directly:
  one click, no dialog. The status line confirms *"saved to preset.json"*.
- **Opened as a file** in Chrome or Edge — Save preset writes the file via a
  save dialog; point it at the script folder.
- **Other browsers** — Save preset downloads `preset.json`, which you then
  move next to the script.

`preset.json` is git-ignored — it is local tuning state.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Note

Spectral data and generated HTML/CSV are git-ignored: this repository tracks the
code only, never the scientific data.
