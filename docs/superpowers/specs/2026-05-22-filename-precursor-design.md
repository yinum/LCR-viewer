# Filename-based precursor detection

Date: 2026-05-22
Status: approved for planning

## Goal

When a spectrum filename ends with the precursor m/z (e.g. `PF4_polyP_3300.xy`),
use that value for the output viewer name and for placing the scaling
threshold — instead of inferring the precursor from the base peak, which is
wrong when a charge-reduced product out-competes the precursor.

## Background

`build_lcr_viewer.py` derives the precursor m/z from the spectrum's base peak
(`precursor_mz`, `_base_peak_index`) and places the scaling threshold just past
the base-peak cluster (`auto_threshold`). This assumes the base peak is the
parent-envelope apex.

Real LCR data in `results/LCR/` breaks that assumption: of five PF4–polyP
spectra named by precursor isolation m/z (3300–3700), `PF4_polyP_3300.xy` has
its base peak at m/z 3595 — a charge-reduced product more intense than the
surviving precursor. Run through the viewer, that file would be mis-named
`LCR_mz3595…` and its ×10 threshold placed ~3640, leaving the real precursor
and most charge-reduced products unscaled.

The filename already carries the true precursor. Using it fixes the case.

## Requirements

1. The viewer reads the precursor m/z from the **trailing number** of the
   spectrum filename (decimals allowed), when present.
2. When a filename precursor is found, it sets both the **output viewer name**
   and the **scaling threshold** anchor.
3. When the filename has no trailing number, behaviour is **unchanged**:
   base-peak detection for both the name and the threshold.
4. The threshold, when anchored to a filename precursor, is placed past the
   peak cluster **containing or nearest** that m/z.

## Design

### `precursor_from_name(path)` — new

- Take `os.path.basename(path)`, strip the extension with `os.path.splitext`.
- Regex-match a trailing number, optional decimal: `(\d+(?:\.\d+)?)$`.
- Return the matched value as a `float`, or `None` when there is no trailing
  number.
- Examples: `PF4_polyP_3300.xy → 3300.0`; `run_3300.5.xy → 3300.5`;
  `clipboard_spectrum.txt → None`; `PF4_polyP.xy → None`.
- Requires `import re`.

### `_segment_nearest(mz, segs, target)` — new helper

Given the gap-segmented spectrum and a target m/z, return the `(start, end)`
segment whose m/z range contains `target`; if none contains it, return the
segment whose nearest edge is closest to `target`.

### `auto_threshold(mz, it, precursor=None)` — gains an optional argument

- `precursor` is `None` (default) → parent segment is the one containing the
  base peak (`_base_peak_index`). Unchanged behaviour; existing two-argument
  calls keep working.
- `precursor` is a number → parent segment is `_segment_nearest(mz, segs,
  precursor)`.
- Either way: threshold = parent segment's right-edge m/z + `THRESHOLD_MARGIN`.

### `output_filename(precursor, when=None)` — rounding

The precursor may now arrive as a `float` (from a filename). The function
rounds it: the label becomes `LCR_mz<int(round(precursor))>_<timestamp>.html`.
Integer inputs are unaffected.

### `main()` — resolve precursor per spectrum

For each spectrum file:

```
named = precursor_from_name(path)          # float or None
thr   = auto_threshold(mz, it, named)
prec  = named if named is not None else precursor_mz(mz, it)
name  = output_filename(prec)
```

The "Wrote …" line states the source: `precursor m/z 3300 (from filename)` or
`precursor m/z 3595 (base peak)`, so a misread is visible.

`precursor_mz` itself is unchanged — it remains the base-peak detector used as
the fallback.

## Data flow

```
spectrum file --> precursor_from_name(path) --> named (float | None)
                       |                              |
                       v                              v
   name = output_filename(named or precursor_mz)   thr = auto_threshold(mz, it, named)
```

## Error handling

- Filename with no trailing number → `precursor_from_name` returns `None` →
  base-peak fallback (no error).
- `_segment_nearest` always returns a segment (`find_segments` returns at least
  one segment for any non-empty spectrum).
- A filename precursor far outside the spectrum's m/z range still resolves to
  the nearest segment; the generated viewer's threshold stays live-editable.

## Out of scope

- Changing base-peak detection or `THRESHOLD_MARGIN`.
- Parsing precursor from file contents/headers (only the filename).
- Charge state or Pn notation in filenames — only a numeric m/z.

## Verification

- `precursor_from_name`: integer name → float; decimal name → float;
  no-digit name → `None`.
- `auto_threshold(mz, it, precursor)` with a fixture whose base peak is far
  from `precursor` → threshold anchors to the precursor's cluster, not the
  base peak's.
- `auto_threshold(mz, it)` (no precursor) → unchanged result (existing test).
- Build the five `results/LCR/` viewers: 3400/3500/3600/3700 named and
  thresholded as before; `PF4_polyP_3300.xy` → `LCR_mz3300…`, threshold
  anchored near 3300.

## Docs to update

- `README.md` — precursor comes from the filename's trailing number, base-peak
  detection is the fallback.
- `AGENTS.md` — same, agent-facing.
