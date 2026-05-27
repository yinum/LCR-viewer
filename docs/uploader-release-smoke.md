# Uploader release smoke test

Run before tagging an uploader release.

## Build

- [ ] `curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js`
- [ ] `curl -sL https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js -o jszip.min.js`
- [ ] `python3 build_lcr_viewer.py --uploader`
- [ ] `ls -l dist/LCR_viewer.html` — file exists, ≤ ~2 MB

## Open in each browser

For Safari, Firefox, Chrome, Edge:
- [ ] Open `dist/LCR_viewer.html` (double-click)
- [ ] Empty-state landing renders (drop zone + Try-example button visible)
- [ ] Click "Try with example spectrum" → plot renders; sidebar shows
      `✓ example_spectrum.xy`

## Multi-spectrum

- [ ] Drop a folder of 5 `.xy` files → sidebar lists all 5, first auto-activates
- [ ] Click a different row → plot switches
- [ ] Click ✕ → row removed, plot moves to remaining spectrum

## Sidebar toggle (v0.1.1)

- [ ] With ≥1 spectrum loaded, click `‹` in the sidebar header → sidebar
      hides; plot re-flows to full viewport width; `≡` button appears
      top-left
- [ ] Click `≡` → sidebar comes back; plot re-flows to `viewport − 220px`
      with no horizontal overflow

## Ladder persistence

- [ ] Enable Ladder labels; add a ladder on spectrum A
- [ ] Switch to B; add a different ladder
- [ ] Switch back to A → A's ladder is visible (not B's)

## Errors

- [ ] Drop a `.csv` containing only `hello world` → ✗ badge appears,
      hover shows `Couldn't read any numbers from this file.`
- [ ] In devtools console, run `throw new Error('test')` →
      catch-all panel appears bottom-right; Copy button copies payload
      including the build stamp

## CSV parity

- [ ] Drop the same spectrum file that a recent `--serve` build used
- [ ] Click "Download processed CSV"
- [ ] `diff` against the sibling CSV the `--serve` build wrote — must be
      identical (or differ only by trailing newline)

## Bulk export

- [ ] Drop 2+ spectra → "Download all CSVs (zip)" button visible
- [ ] Click it → zip downloads; unzip → each CSV matches the per-spectrum
      "Download processed CSV" output
