# LCR-viewer — agent guide

Interactive HTML viewer for polyP limited-charge-reduction (LCR) mass spectra.
`build_lcr_viewer.py` reads a 2-column m/z–intensity spectrum and emits a
self-contained interactive HTML viewer. User-facing detail is in `README.md`.

## Project layout & boundaries

This repo lives at `PolyP/code/LCR-viewer/`. The sibling directories under
`PolyP/` (`data/`, `results/`, `outputs/`, `meetings/`, …) hold years of
**private scientific data and personal information**. The tool legitimately
reads input spectra from those areas and writes generated viewers into its own
`output/LCR/<dataset>/` subfolder (git-ignored — see `.gitignore`) — the
boundary that matters is **git**: never commit data, generated viewers, or
anything from outside this repo folder, and never modify the `data/` /
`results/` / `meetings/` directories. All code projects live under
`PolyP/code/<project>/`, each in its own subfolder; never put code loose in the
`PolyP/` root.

## Run

```sh
python3 build_lcr_viewer.py [--serve] INPUT [OUTPUT_DIR]
```

`INPUT` is a 2-column m/z, intensity file (whitespace- or comma-delimited) or a
folder of them; a folder builds one viewer per `.txt`/`.csv`/`.xy` file. `OUTPUT_DIR`
defaults to `output/LCR/<dataset>/` inside this repo, where `<dataset>` is the
input folder's name (logic in `parse_args()`); pass a 2nd arg to override. Each
run writes two files per spectrum:
`LCR_mz<precursor>_<timestamp>.html` and a sibling processed CSV with the same
stem (a preset-parameter snapshot the viewer's header hyperlink points at).
`--serve` additionally serves the built viewers and their CSVs on `127.0.0.1`
(stdlib `http.server`, auto port) so the viewer's **Save preset** POSTs
`preset.json` next to the script directly; plain runs and standalone `file://`
viewers are unaffected. `plotly-basic.min.js` must sit next to the script
(git-ignored — download once per `README.md`). Tests:
`python3 -m unittest discover -s tests -v`.

## Conventions

- Commit **code only**. Spectra (`*.txt`, `*.csv`, `*.xy`), generated viewers
  (`*.html`), a viewer-saved `preset.json`, and the vendored
  `plotly-basic.min.js` are git-ignored — keep it that way.
- Remote: `github.com/yinum/LCR-viewer` (public). Push when the user asks.
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
- **Sibling CSV** — the build runs the same scale + smooth pipeline in Python
  (`process_spectrum` / `build_csv`, a faithful mirror of the in-HTML JS) to
  write the preset-snapshot CSV without a browser. The Python mirror and the
  JS pipeline must stay in lockstep — change one, change the other.

See code comments in `build_lcr_viewer.py` for detail.
