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
python3 build_lcr_viewer.py INPUT.txt OUTPUT.html
```

INPUT is whitespace/tab-delimited `m/z  intensity`. `plotly-basic.min.js` must
sit next to the script (git-ignored — download once per `README.md`).

## Conventions

- Commit **code only**. Spectra (`*.txt`, `*.csv`), generated viewers (`*.html`),
  and the vendored `plotly-basic.min.js` are git-ignored — keep it that way.
- Remote: `github.com/yinum/polyp-lcr-viewer` (private). Push when the user asks.
- The generated HTML must stay fully self-contained (Plotly inlined) and work
  offline — no data leaves the machine.

## How it works

- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1.
- **Smoothing** — each peak group is resampled onto a uniform m/z grid, then
  smoothed with zero-baseline padding, so a window of N affects every peak and
  the result equals Origin smoothing the full continuous profile.

See code comments in `build_lcr_viewer.py` for detail.
