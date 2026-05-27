# LCR spectrum viewer

Builds self-contained interactive HTML viewers for limited-charge-reduction
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

## For collaborators (no coding required)

Use the web version: **https://yinum.github.io/LCR-viewer/**

Or download a single `LCR_viewer.html` file from the
[Releases page](https://github.com/yinum/LCR-viewer/releases) and double-click
it. Either way:

1. Drag one or more spectrum files (`.xy`, `.csv`, or `.txt`, two columns:
   m/z and intensity) onto the page — or drop a whole folder.
2. The viewer shows each spectrum in the sidebar; click any row to view it.
3. Adjust smoothing / scaling / ladder labels live; download processed CSV
   or PNG when you're done.

No files are uploaded anywhere — all processing runs in your browser.

Click "Try with example spectrum" to see what the tool does before you have
your own data.

## Setup

The Plotly basic bundle and JSZip are not committed (third-party; Plotly ~1 MB,
JSZip ~94 KB used by the uploader's Download-all-CSVs button). Download them
once next to the script:

```sh
curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js
curl -sL https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js -o jszip.min.js
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

## Labeling the LCR ladder (opt-in)

The viewer can label charge-reduced (CR) ladder peaks in a native-MS LCR
spectrum with their charge state `z`, observed m/z, and the back-calculated
parent neutral mass `M`. The feature is off by default — turn it on with
the **Ladder labels** checkbox in the toolbar.

A ladder is the family of charge-reduced products of one parent species:
same `M`, different `z`. The precursor envelope at the picked precursor
m/z is itself a mixture of multiple species/charges (that is what LCR
exists to resolve), so it is **not** labeled — only the charge-reduced
rungs are. The precursor m/z and `z₀` you provide are the math anchor,
not a per-peak claim about the precursor envelope.

### Adding a ladder

- **Type seed** — click *+ Type seed*, enter `z₀` (positive integer ≥ 2),
  enter the precursor m/z (auto-filled from the viewer filename). The
  viewer predicts m/z(z) = (M + z·m_H)/z for z = z₀−1, z₀−2, …, 1 and
  snaps each predicted rung to the highest-intensity sample within the
  **Snap tol (m/z)** window.
- **2-click seed** — click *+ 2-click seed*, then click two ladder peaks
  in the plot. A closed-form solver recovers `z` and `M` from the two
  m/z values (it sweeps charge-reduction step `k ∈ {1..5}` automatically,
  so non-adjacent picks work too).

### Manually overriding a label

Click on any labeled peak: a prompt opens, pre-filled with the current
`z`. Enter:
- a **positive integer** to override the label's charge (does *not*
  re-seed `M` — useful when one rung disagrees with the rest);
- a positive integer **suffixed with `s`** (e.g. `8s`) to promote that
  peak as the new seed of its ladder (re-seeds `M`, re-snaps the ladder);
- **empty** (or Cancel) to delete the label.

Clicking an *unlabeled* peak (after a ladder is active) creates a manual
label there with the prompted `z`. Manual labels are shown with an `M`
prefix on the on-plot text.

### Per-ladder controls

Each ladder appears in the panel with editable `z₀` and precursor m/z
inputs, a remove (`✕`) button, and a radio for which ladder is *active*
(takes plot clicks). The header annotation summarises each ladder's
mass: `Ladder A:  M = 26.4 kDa ± 0.4%  (z₀ = 8+, 6 rungs)`. Mass display
precision is picked from σ_M; the line turns amber if σ_M / M exceeds
1% (configurable via preset).

### Persistence

Three keys join `preset.json`:

```json
"ladder_labels": {
  "enabled": false,
  "tol_mz": 5.0,
  "sigma_amber_relative": 0.01
}
```

The ladders themselves are spectrum-specific and not persisted; create
them per spectrum.

### Caveats and limitations

- The labeler is a v1 prototype: manual input uses browser `prompt()`
  dialogs, which work but are visually plain.
- Designed for **native MS positive mode** (Synapt G2 QTOF) — formula:
  `M = z·(m/z) − z·m_H`. Negative mode is not supported in v1.
- Per-rung implied-`M` cross-check is visible only in the hover tooltip
  on each labeled peak. The header `M` is computed from the seed alone.
- No CSV export of labels in v1; processed CSV is unaffected.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Note

Spectral data and generated HTML/CSV are git-ignored: this repository tracks the
code only, never the scientific data.
