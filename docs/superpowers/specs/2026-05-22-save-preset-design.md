# Save preset — viewer-tuned parameters persist to future builds

Date: 2026-05-22
Status: approved for planning

## Goal

Let the user adjust processing parameters (mainly smoothing) live in a generated
viewer, save them once, and have every future `build_lcr_viewer.py` run use
those values as the control defaults — without editing the script.

## Background

`build_lcr_viewer.py` builds self-contained HTML viewers for polyP LCR spectra.
A built-in `PRESET` dict (`scale`, `method`, `window`, `poly`, `show_overlay`)
supplies the live-control defaults baked into every viewer; `build_html` reads
it. The viewer's controls are editable in the browser, but browser edits do not
persist — to change the defaults today you must edit the `PRESET` dict in the
script.

The user tunes smoothing in the browser and wants those tuned values to become
the default for future spectra, saved from the viewer itself.

## Requirements

1. The viewer can **save the current control values** to a `preset.json` file.
2. `build_lcr_viewer.py` **auto-loads `preset.json`** (next to the script) on
   every run; its values become the control defaults of generated viewers.
3. The built-in `PRESET` dict **stays as the fallback** — used when no
   `preset.json` exists or it cannot be read.
4. `preset.json` is **git-ignored** (local-only state).
5. The saved preset covers the five viewer-control fields: `scale`, `method`,
   `window`, `poly`, `show_overlay`. (The per-spectrum auto-threshold is not a
   preset value and is unaffected.)

## Design

### preset.json

A flat JSON object next to `build_lcr_viewer.py`, e.g.:

```json
{
  "scale": 10,
  "method": "avg",
  "window": 301,
  "poly": 3,
  "show_overlay": false
}
```

Keys match the built-in `PRESET` dict exactly. Git-ignored.

### `load_preset(here)`

New function in `build_lcr_viewer.py`:

- Start from a copy of the built-in `PRESET` dict.
- If `os.path.join(here, "preset.json")` exists, read it as JSON and overlay
  every key that is also present in `PRESET` (unknown keys ignored; missing
  keys keep their default).
- On malformed JSON or read error: print a one-line warning and return the
  built-in defaults unchanged.
- Return the effective preset dict.

`main()` calls `load_preset(here)` once. `build_html` gains a `preset` parameter
(the effective dict) and uses it instead of the module-global `PRESET`. The
global `PRESET` remains as the documented fallback baseline.

### Viewer "Save preset" button

A new button in the controls row, alongside the CSV buttons, plus a small
status span. On click:

1. Read the current control values: `#scale` (number), `#method` (string),
   `#win` (int), `#poly` (int), `#rawov` (checkbox → `show_overlay` bool).
2. Build a JSON object with exactly the five preset keys.
3. Write `preset.json`, pretty-printed (`JSON.stringify(obj, null, 2)`):
   - If `window.showSaveFilePicker` exists (Chrome/Edge): open it with
     `suggestedName: "preset.json"`, write the file.
   - Otherwise: trigger a download of `preset.json`.
4. Update the status span to confirm, noting the file must sit next to
   `build_lcr_viewer.py` for future builds to pick it up.

The JSON shape written by the viewer is exactly what `load_preset()` reads, so
a saved file round-trips: save from viewer → place next to script → next build
uses it.

### .gitignore + docs

- Add `preset.json` to `.gitignore`.
- README and AGENTS.md: short note on the workflow — adjust in the viewer, click
  Save preset, future builds auto-load it; built-in `PRESET` is the fallback.

## Data flow

```
viewer controls --(Save preset click)--> preset.json next to script
build_lcr_viewer.py run:
  load_preset(here): PRESET defaults <- overlay preset.json
  --> build_html(..., effective preset) --> generated viewer control defaults
```

## Error handling

- `preset.json` malformed / unreadable → warn to stdout, use built-in defaults.
- `preset.json` absent → use built-in defaults silently.
- Unknown keys in `preset.json` → ignored. Missing keys → default retained.
- Non-Chromium browsers → download fallback (cannot write in place).

## Out of scope

- Auto-writing `preset.json` on every control change (it is a deliberate click).
- Editing the per-spectrum auto-threshold or `THRESHOLD_MARGIN` via the preset.
- Type/range validation of manually hand-edited `preset.json` values beyond
  key filtering — the viewer always writes well-typed values.
- Multiple named presets / preset switching.

## Verification

- `load_preset` with no file → returns built-in defaults.
- `load_preset` with a valid `preset.json` → overlaid values returned.
- `load_preset` with partial keys → those overlaid, rest default.
- `load_preset` with malformed JSON → built-in defaults, warning printed.
- Generated viewer contains the "Save preset" button and its JSON-building JS.
- Round-trip: save a preset.json with `window` changed, place it next to the
  script, rebuild a viewer, confirm the window control default changed.

## Docs to update

- `README.md` — Save preset workflow.
- `AGENTS.md` — same, agent-facing.
