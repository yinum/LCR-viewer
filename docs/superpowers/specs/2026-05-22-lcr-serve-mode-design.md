# LCR-viewer — `--serve` localhost mode

**Date:** 2026-05-22
**Status:** implemented

## Problem

The viewer's **Save preset** button needs to write `preset.json` next to
`build_lcr_viewer.py`. A self-contained `file://` HTML page runs in the browser
sandbox and cannot write to a fixed path — it can only open a save dialog
(File System Access API, Chromium) or download to the Downloads folder. So
saving a preset always required a manual file-placement step.

(Switching the config to YAML was considered and rejected: the format is not
the bottleneck. JSON is written natively by the browser and read natively by
Python; YAML would add a bundled JS library and a `pyyaml` dependency.)

## Decision

Add an optional `--serve` mode. A standalone HTML page cannot reach the
filesystem, but a page served by a local process can POST to it.

- **Invocation:** `python3 build_lcr_viewer.py [--serve] INPUT [OUTPUT_DIR]`.
  `--serve` is parsed by `parse_args()` and stripped; positionals unchanged.
  Without it, behaviour is exactly as before.
- **Server:** stdlib `http.server.ThreadingHTTPServer` (no new dependency),
  bound to `127.0.0.1` on an auto-picked free port. `GET /` serves the built
  viewer (or an index, for folder input); `POST /preset` writes `preset.json`
  via `save_posted_preset()`. Runs until Ctrl-C; opens the browser on start.
- **Viewer (dual-mode Save preset):** the button branches on
  `location.protocol` — served (`http:`) → `fetch('/preset', POST)`, one click,
  no dialog; standalone (`file:`) → the existing File System Access / download
  path. The generated HTML stays fully self-contained; `--serve` is only an
  optional launcher.
- **Scope:** Save preset writes `preset.json` (which `load_preset()` already
  overlays on the built-in `PRESET`), so it sets the defaults for the *next*
  build — it does not retro-change the open viewer. No data leaves the host
  (localhost only).

## Key functions

- `parse_args(argv, here)` → `(serve_mode, src, out_dir)`.
- `save_posted_preset(here, data)` — keeps only `PRESET` keys, writes
  `preset.json`, returns the path.
- `serve(out_dir, written, here)` — builds the server, opens the browser,
  serves until interrupted.

## Verification

- `python3 -m unittest discover -s tests` — 33 tests pass (added: `--serve`
  arg parsing, `save_posted_preset` key-filtering + round-trip, viewer carries
  both the served and standalone Save-preset paths).
- End-to-end: ran `--serve` on `PF4_polyP_3300.xy`; `GET /` returned the viewer
  HTML (200, 1.2 MB), `POST /preset` returned `{"ok": true}` and wrote
  `preset.json` next to the script with only valid keys (an unknown key was
  dropped).
