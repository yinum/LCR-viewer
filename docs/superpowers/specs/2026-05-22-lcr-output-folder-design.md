# LCR-viewer — output folder inside the repo, per dataset

**Date:** 2026-05-22
**Status:** implemented

## Problem

The default `OUTPUT_DIR` was `../../outputs/LCR/individual peaks` — out in the
workspace data area, two levels above the repo, and a single flat folder for
every dataset. The user wants generated viewers kept inside the code repo and
split per dataset, since several datasets (PF4_polyP, polyP, and others) are in
play.

## Decision

When `OUTPUT_DIR` is omitted, the default becomes `<repo>/output/LCR/<dataset>/`
— a subfolder of the script's own directory — where `<dataset>` is the **input
folder's name** (the parent folder's name when the input is a single file):

- `results/LCR/PF4_polyP/` → `output/LCR/PF4_polyP/`
- `results/LCR/polyP/`     → `output/LCR/polyP/`

No new flag: the input folder you point at names the output subfolder, so each
dataset self-organizes. An explicit 2nd CLI argument still overrides the
default. The whole `output/` tree is git-ignored (added to `.gitignore`); the
existing `*.html` / `*.csv` rules already covered the generated files, the
`/output/` rule makes the intent explicit and also keeps any other stray
artifact out of git.

The logic is in `parse_args()`: `folder = src if isdir(src) else dirname(src)`,
`dataset = basename(abspath(folder))`, `out_dir = <here>/output/LCR/<dataset>`.

## Note on the current layout

The spectra in `results/LCR/` are presently flat (`PF4_polyP_3300.xy` …, no
per-dataset subfolder). To get `output/LCR/PF4_polyP/`, group each dataset's
spectra into a folder named for that dataset and point the build at that
folder. Pointing at `results/LCR/` itself would produce `output/LCR/LCR/`.

## Verification

- `python3 -m unittest discover -s tests` — 42 tests pass (added: default
  output derived from an input folder's name, from a single file's parent
  folder, and explicit `OUTPUT_DIR` still overriding).
- Live run: a folder named `PF4_polyP/` built with no `OUTPUT_DIR` wrote its
  viewer + CSV into `output/LCR/PF4_polyP/`; `git status --ignored` confirmed
  `output/` is ignored.
