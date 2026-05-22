# LCR-viewer — agent guide

Interactive HTML viewer for polyP limited-charge-reduction (LCR) mass spectra.
`build_lcr_viewer.py` reads a 2-column m/z–intensity spectrum and emits a
self-contained interactive HTML viewer. User-facing detail is in `README.md`.

## Project layout & boundaries

This repo lives at `PolyP/code/LCR-viewer/`. The sibling directories under
`PolyP/` (`data/`, `results/`, `outputs/`, `meetings/`, …) hold years of
**private scientific data and personal information**. The tool legitimately
reads input spectra from those areas and writes generated viewers into
`PolyP/outputs/LCR/individual peaks/` — the boundary that matters is **git**:
never commit data, generated viewers, or anything from outside this repo folder,
and never modify the `data/` / `results/` / `meetings/` directories. All code
projects live under `PolyP/code/<project>/`, each in its own subfolder; never
put code loose in the `PolyP/` root.

## Run

```sh
python3 build_lcr_viewer.py INPUT [OUTPUT_DIR]
```

`INPUT` is a 2-column m/z, intensity file (whitespace- or comma-delimited) or a
folder of them; a folder builds one viewer per `.txt`/`.csv`/`.xy` file. `OUTPUT_DIR`
defaults to `../../outputs/LCR/individual peaks`. Each viewer is named
`LCR_mz<precursor>_<timestamp>.html`. `plotly-basic.min.js` must sit next to the
script (git-ignored — download once per `README.md`). Tests:
`python3 -m unittest discover -s tests -v`.

## Conventions

- Commit **code only**. Spectra (`*.txt`, `*.csv`, `*.xy`), generated viewers
  (`*.html`), a viewer-saved `preset.json`, and the vendored
  `plotly-basic.min.js` are git-ignored — keep it that way.
- Remote: `github.com/yinum/LCR-viewer` (private). Push when the user asks.
- The generated HTML must stay fully self-contained (Plotly inlined) and work
  offline — no data leaves the machine.

## How it works

- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1. The threshold is auto-placed per spectrum just past the parent
  envelope (`auto_threshold`): the cluster at the filename precursor m/z
  (`precursor_from_name`, a trailing number in the name) when present, else the
  base-peak cluster. Fixed parameters come from `load_preset()` — the built-in
  `PRESET` dict overlaid with a viewer-saved `preset.json` (git-ignored).
- **Smoothing** — each peak group is linearly interpolated onto a fine uniform
  m/z grid (so sparse, few-point peaks gain enough points to smooth into a
  curve) and padded with zero-baseline cells so a broadened peak decays to zero.
  The smoothing width is set in m/z, so it covers the same span on every peak
  and the result equals Origin smoothing the full continuous profile. Grid
  constants (`GRID_DX`, `MAX_CELLS`, `PAD_MZ`) are in the in-HTML `buildGrid`.

See code comments in `build_lcr_viewer.py` for detail.
