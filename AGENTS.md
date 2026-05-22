# polyp-lcr-viewer — agent guide

Interactive HTML viewer for polyP limited-charge-reduction (LCR) mass spectra.
`build_lcr_viewer.py` reads a 2-column m/z–intensity spectrum and emits a
self-contained interactive HTML viewer. User-facing detail is in `README.md`.

## Project layout & boundaries

This repo lives at `PolyP/code/polyp-lcr-viewer/`. The parent `PolyP/` folder and
its sibling directories (`data/`, `results/`, `outputs/`, `meetings/`, …) hold
years of **private scientific data and personal information** — do not read,
move, or commit anything outside this repo folder. All code projects live under
`PolyP/code/<project>/`, each in its own subfolder; never put code loose in the
`PolyP/` root.

## Run

```sh
python3 build_lcr_viewer.py INPUT [OUTPUT_DIR]
```

`INPUT` is a 2-column m/z, intensity file (whitespace- or comma-delimited) or a
folder of them; a folder builds one viewer per `.txt`/`.csv` file. `OUTPUT_DIR`
defaults to `../../outputs/LCR/individual peaks`. Each viewer is named
`LCR_mz<precursor>_<timestamp>.html`. `plotly-basic.min.js` must sit next to the
script (git-ignored — download once per `README.md`). Tests:
`python3 -m unittest discover -s tests -v`.

## Conventions

- Commit **code only**. Spectra (`*.txt`, `*.csv`), generated viewers (`*.html`),
  and the vendored `plotly-basic.min.js` are git-ignored — keep it that way.
- Remote: `github.com/yinum/polyp-lcr-viewer` (private). Push when the user asks.
- The generated HTML must stay fully self-contained (Plotly inlined) and work
  offline — no data leaves the machine.

## How it works

- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1. The threshold is auto-placed per spectrum just past the parent
  envelope (`auto_threshold`): the cluster at the filename precursor m/z
  (`precursor_from_name`, a trailing number in the name) when present, else the
  base-peak cluster. Fixed parameters come from `load_preset()` — the built-in
  `PRESET` dict overlaid with a viewer-saved `preset.json` (git-ignored).
- **Smoothing** — each peak group is resampled onto a uniform m/z grid, then
  smoothed with zero-baseline padding, so a window of N affects every peak and
  the result equals Origin smoothing the full continuous profile.

See code comments in `build_lcr_viewer.py` for detail.
