# LCR-viewer Uploader Mode — Design Spec

**Date:** 2026-05-26
**Status:** Draft, pending user review
**Goal:** Let collaborators with zero coding knowledge use the LCR-viewer pipeline on their own spectra, from any browser, on any OS, without installing Python.

---

## 1. Background

Today, `build_lcr_viewer.py` reads a 2-column m/z–intensity spectrum and emits
a self-contained interactive HTML viewer (`LCR_mz<precursor>_<timestamp>.html`)
plus a sibling processed CSV. The viewer is built per-spectrum and shipped with
the spectrum data baked in.

For collaborators to run the tool on their own data they currently need to:
1. Install Python and clone the repo
2. Download `plotly-basic.min.js` next to the script
3. Run a CLI command per spectrum

That bar is too high for non-programmer collaborators. They also can't reuse
the artifact across multiple spectra without re-running the build.

## 2. Goal

Ship one artifact that:
- A zero-coding-knowledge user can open in any browser
- Accepts the user's own spectrum files via drag-and-drop or file picker
- Runs the existing scale + smooth + ladder pipeline entirely client-side
- Keeps all scientific data on the user's machine (privacy invariant)
- Works on macOS, Windows, Linux, iPad, Android — every major browser
- Coexists with the current `--serve` + sibling-CSV workflow without regression

## 3. Decisions made during brainstorming

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Artifact format | Single self-contained HTML | One file, every OS, no install, no code-signing, no SmartScreen/Gatekeeper warnings. JS pipeline already exists. |
| Build flag | New opt-in flag `--uploader` | Zero regression risk to the existing single-spectrum + `--serve` workflows. |
| Multi-spectrum support | Yes, in v1 | User wants colleagues to drop a folder of spectra and switch between them. |
| Sibling CSV in uploader mode | None on disk; in-memory only, downloadable | The "sibling file on disk" concept is replaced by per-spectrum download buttons. |
| Ladder labels | Kept, behind an "Advanced" disclosure | The scientific value of the tool; technical vocabulary hidden until needed. |
| Distribution channels | GitHub Pages link + GitHub Release asset | Same HTML, two pickup routes. |
| Session persistence | None in v1 | Keeps privacy posture clean; v2 may add IndexedDB. |

## 4. Non-goals (v1)

- Desktop binaries (`.exe` / `.app` via PyInstaller, Tauri, Electron). Ruled out
  during brainstorming: code-signing cost, OS-specific warnings, 30–50 MB per
  OS, and no functional gain over the HTML.
- PyScript / Pyodide. JS pipeline already exists and runs faster.
- Server-side anything (uploads, accounts, telemetry, analytics).
- Persistence of user data across sessions.
- Cross-spectrum overlay comparison (defer to v2).
- Localization. English only in v1.
- A "report a bug" button that opens GitHub Issues (skipped to keep the
  artifact contact-info-free for public hosting).

## 5. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  build_lcr_viewer.py --uploader                                  │
│  - Skips spectrum parsing                                        │
│  - Emits dist/LCR_viewer.html (no timestamp, single file)        │
│  - Inlines plotly-basic.min.js + ladder_labeler.js + uploader.js │
│  - Bakes in a build stamp string (date + git short SHA)          │
│  - Bundles a tiny example spectrum as base64 in the HTML         │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────────┐
        │  LCR_viewer.html (single artifact)       │
        │                                          │
        │  Empty landing page → Drop zone          │
        │       │                                  │
        │       ▼                                  │
        │  uploader.js (file ingestion)            │
        │       │                                  │
        │       ▼                                  │
        │  spectra[] in-memory store               │
        │       │                                  │
        │       ▼                                  │
        │  Sidebar (multi-spectrum picker)         │
        │       │                                  │
        │       ▼                                  │
        │  State coordinator (active spectrum)     │
        │       │                                  │
        │       ▼                                  │
        │  Existing viewer pipeline (scale/smooth/ │
        │  plot/ladder/AUC) — unchanged shape      │
        │       │                                  │
        │       ▼                                  │
        │  Download CSV / PNG / zip-of-all-CSVs    │
        └──────────────────────────────────────────┘
```

**Key invariant:** the existing scale + smooth + ladder pipeline never changes
shape. The state coordinator only swaps *which* spectrum's data is in the
globals before each re-render. This keeps the JS-vs-Python parity invariant
from `AGENTS.md` intact for the single-spectrum path.

## 6. Components

### 6.1 `build_lcr_viewer.py` — extended

- Add `--uploader` argparse flag. When set:
  - Skip `INPUT` / `OUTPUT_DIR` parsing entirely (or make `INPUT` optional)
  - Compute a build stamp: `f"{date}-uploader-{git_short_sha or 'nogit'}"`
  - Emit `dist/LCR_viewer.html` (configurable via second positional arg)
  - Use a new HTML template branch that:
    - Omits the embedded spectrum block
    - Includes the new `uploader.js` (inlined)
    - Includes the bundled example spectrum (base64-encoded in a `<script>`)
    - Stamps the build string into a hidden DOM node for the catch-all panel
- `dist/` is git-ignored (mirror `output/` policy).
- No change to default flow or `--serve` flow.

### 6.2 `uploader.js` — new module

- Drag-and-drop handler supporting files *and* folders (`DataTransferItem.webkitGetAsEntry`)
- Click-to-pick fallback using `<input type="file" multiple webkitdirectory>`
- Tolerant per-file parser:
  - Token delimiter: whitespace OR comma OR tab (mixed OK)
  - Skip blank lines
  - Skip leading header lines until the first all-numeric 2-token line
  - On the first un-parseable line *after* numeric data starts, stop with a
    friendly error
- Filename precursor regex (port of existing Python logic)
- In-memory store entry shape:
  ```js
  {
    name,                       // basename
    mz: Float64Array,
    intensity: Float64Array,
    precursor,                  // null if not in filename
    parseStatus: 'ok' | 'error',
    parseMessage,               // friendly one-liner; '' on success
    ladders: [],                // per-spectrum ladder state
    perSpectrumOverrides: {     // optional, see 6.4
      threshold?: number,
      smoothing?: {...},
    }
  }
  ```
- Bundled example: a small (~5 KB) representative polyP spectrum, base64-decoded
  on click of "Try with example spectrum"

### 6.3 Landing + sidebar UI — new HTML chrome

Two states:

**Empty state** (`spectra.length === 0`):
- Large drop zone with copy: *"Drop a spectrum file or folder here, or click to browse"*
- *"Try with example spectrum"* button (loads bundled sample)
- 3-line *"What does this tool do?"* intro

**Loaded state** (`spectra.length > 0`):
- Collapsible left sidebar listing each loaded spectrum
- Per-row: filename, parse status badge (✓ / ✗), click-to-activate, ✕ to remove
- Hover/click on a ✗ row reveals the friendly parseMessage
- *"+ Add more"* button at the bottom of the list
- The existing viewer chrome (plot + controls) fills the right pane

Responsive layout: sidebar collapses into a top dropdown on viewports < 768 px.

### 6.4 State coordinator — new in viewer JS

On *"activate spectrum X"*:
1. Stash the current spectrum's edits (ladders, user windows, per-spectrum
   threshold override) into its `spectra[]` entry
2. Load X's stashed edits into the global state variables the existing viewer
   reads
3. Call the existing re-render path

Global controls (smoothing method, smoothing width, scale on/off, scale factor)
stay global by default with an *"Apply to: this spectrum / all spectra"*
toggle (defaults to *all*). When *this spectrum* is selected, the change is
written to `perSpectrumOverrides` instead of the global state.

### 6.5 Bulk export

- *"Download all processed CSVs (zip)"* button, visible only when
  `spectra.length > 1`
- JSZip inlined (~30 KB)
- Each CSV computed in-browser using the same scale + smooth pipeline as the
  Python mirror

## 7. Data flow

See ASCII diagram in §5. Summary:

1. User drops files / picks folder / clicks "Try example"
2. `uploader.js` parses each file, pushes entries to `spectra[]`
3. Sidebar renders the list; first ✓ spectrum auto-activates
4. User adjusts controls; coordinator routes changes to global or
   per-spectrum state
5. User clicks Download; in-browser pipeline writes CSV / PNG / zip

**Persistence:** none across page reloads. Closes-the-tab loses uploaded files
and ladders. This keeps the privacy posture clean (no IndexedDB cache of
scientific data) and the UX simple (no "restore session?" prompts).

## 8. Error handling

### 8.1 Per-file parse errors

Sidebar row shows ✗ with a one-line plain-English reason on hover/click:
- *"This file doesn't look like a 2-column spectrum (line 7 has 5 numbers)."*
- *"This file is empty."*
- *"Couldn't read any numbers from this file."*
- *"This file is very large (47 MB). Loading anyway… (this may take a moment.)"* — non-blocking warning

Failed files stay listed but are not auto-activated.

### 8.2 Filename precursor missing

Falls back to base-peak cluster (existing behaviour). A small info badge near
the precursor input shows *"Precursor m/z inferred from base peak — click to change."*

### 8.3 Browser-capability gaps

- Folder drop unsupported: silently falls back to file picker
- All other features avoid FSA, so no permission prompts to fail

### 8.4 Plot rendering errors

If Plotly throws, the plot area shows *"Couldn't draw this spectrum — it may
not contain numeric data. Try a different file."* and the rest of the UI stays
usable.

### 8.5 Catch-all panel

A global `window.onerror` + `unhandledrejection` handler shows a dismissible
panel with a copy-able payload:

```
LCR-viewer v<build-stamp>
Browser: <user-agent summary>
Active file: <name or none>
Spectra loaded: <n>
Error: <message>
Stack: <top 5 frames>
```

The panel copy reads: *"Sorry — the viewer hit a problem we didn't plan for.
Copy the box below and paste it into ChatGPT (or any AI assistant), and ask it
to help figure out what went wrong."*

No contact information is included (the artifact is publicly hosted; we don't
embed personal email / handles).

One [Copy] button copies the full payload; visible stack is truncated to 5
frames so a non-coder doesn't panic at the wall of text.

## 9. Testing

### 9.1 Python side

No new functional tests required. Add a regression check:
- `build_lcr_viewer.py --uploader` produces `dist/LCR_viewer.html`
- File contains the uploader marker string and the build stamp

### 9.2 JS side — pure-function tests

New `tests/uploader_test.html` (browser-runnable, same pattern as
`tests/ladder_labeler_test.html`). Cases:
- Parser: whitespace / comma / tab / mixed; with and without headers; empty
  files; single-row files; junk lines
- Filename precursor: `PF4_polyP_3300.xy`, `3300_PF4_polyP.xy`,
  `polyP_no_number.xy`, `polyP_3300.5.xy`
- Coordinator: switch A→B→A round-trip; ladder state survives switch

### 9.3 Manual smoke test before each release

Checklist in `docs/uploader-release-smoke.md`:
1. Open built HTML in Safari, Firefox, Chrome, Edge — empty state renders,
   "Try example" works
2. Drop a folder of 5 spectra — sidebar lists all, switching works
3. Add a ladder on one spectrum, switch away and back — ladder persists
4. Drop a deliberately broken file — friendly error appears
5. Trigger synthetic error (browser devtools) — catch-all panel appears, Copy
   copies the right payload
6. Download CSV and "Download all (zip)" — files match the existing pipeline
   byte-for-byte vs. a `--serve` build of the same spectra (parity guarantee)

## 10. Deployment

### 10.1 GitHub Release asset

Manual release procedure documented in the repo:
```sh
python3 build_lcr_viewer.py --uploader
gh release create v<X.Y.Z> dist/LCR_viewer.html --notes "..."
```

### 10.2 GitHub Pages

`.github/workflows/pages.yml`:
- Trigger: push to `main`
- Steps:
  - Checkout repo
  - Install Python
  - Download `plotly-basic.min.js` (cached)
  - Run `python3 build_lcr_viewer.py --uploader`
  - Copy `dist/LCR_viewer.html` → `index.html`
  - Deploy to `gh-pages` branch via `actions/deploy-pages`

Served at `https://yinum.github.io/LCR-viewer/`. The repo is already public, so
no permissions change is needed.

### 10.3 Privacy posture

- HTML is fully static
- No backend, no analytics, no telemetry, no tracking scripts
- The colleague's browser does all the work; scientific data never leaves
  their machine
- README states this explicitly so the property is verifiable

### 10.4 Lifecycle

- `dist/` is git-ignored
- `gh-pages` branch auto-managed by the workflow; never hand-edited

## 11. Scope summary

### In v1
- `--uploader` build flag
- Drag-and-drop files or folder; click-to-pick fallback
- Tolerant 2-column parser with friendly per-file errors
- Filename precursor extraction
- Multi-spectrum sidebar (switch, remove, add-more)
- Per-spectrum ladder labels + AUC
- "Try with example spectrum"
- Download CSV (active), PNG, all-CSVs-as-zip
- Catch-all "copy & ask AI" error panel with build stamp
- GitHub Release asset + GitHub Pages auto-deploy
- Responsive layout

### Deferred to v2
- "Apply to: this / all spectra" toggle (smoothing/scaling are global in v1
  — the `perSpectrumOverrides` store field is reserved for this)
- "Advanced" disclosure widget around ladder vocabulary + hover tips on
  every control (v1 ships the inline `(opt-in; off by default)` note for
  ladders only)
- IndexedDB session persistence
- Per-spectrum independent smoothing as default
- Cross-spectrum overlays
- Ladder JSON sidecar save/load via picker (FSA)
- Localization (i18n)

### Won't do
- Server-side anything
- Desktop binaries (PyInstaller / Tauri / Electron)
- PyScript / Pyodide
