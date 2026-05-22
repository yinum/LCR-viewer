# polyP LCR spectrum viewer

Builds a self-contained interactive HTML viewer for a polyP limited-charge-reduction
(LCR) mass spectrum (Waters Synapt, positive mode).

The viewer lets you:

1. **Scale** the charge-reduced region (`m/z >= threshold`) by a factor (default 50x),
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

Input is a whitespace/tab-delimited two-column file: `m/z  intensity`.

```sh
python3 build_lcr_viewer.py INPUT.txt OUTPUT.html
```

The generated HTML is fully self-contained (Plotly inlined) and works offline —
no data leaves the machine.

## Note

Spectral data and generated HTML/CSV are git-ignored: this repository tracks the
code only, never the scientific data.
