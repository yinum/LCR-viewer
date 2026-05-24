# Ladder rung relative abundance (per-rung AUC) — design

**Date:** 2026-05-23
**Status:** Approved (pending user review of this written spec)
**Scope:** Extend the existing ladder labeler (see
`2026-05-22-ladder-labeling-design.md`) to compute and display, for each
ladder rung, a relative abundance based on the rung's area under the curve
(AUC) as a fraction of the ladder's total rung AUC. Fold in a fix for a
pre-existing stale assertion in `tests/ladder_labeler_test.html`.

---

## 1. Problem

The labeler currently tells you **which charge** each rung represents and the
back-calculated neutral mass `M`. It does **not** tell you how much of the
ladder's signal sits at each rung. In LCR experiments the distribution of
intensity across rungs is itself informative (charge-reduction efficiency,
collision-energy tuning, comparison across spectra). Users have to eyeball
peak heights today; they should get a number.

## 2. Goals and non-goals

**Goals**

- For every snapped rung in every ladder, compute a per-rung AUC over a
  local-valley window and a per-ladder relative abundance (`auc / Σauc`).
- Display the abundance as a percentage in the existing side-panel ladder
  table, with the ladder's `ΣAUC` magnitude shown as a small footer for
  sanity checking.
- Be correct under LCR scaling: integrate the **unscaled** smoothed signal so
  that abundances are not distorted when a ladder straddles the threshold or
  the user toggles `scale_on`.
- Keep the plot annotations unchanged (per user request — panel only).
- Restore the pure-math test harness to green by updating the one stale
  assertion that has drifted from current behavior.

**Non-goals (v1)**

- No baseline subtraction. There is no universal baseline rule for LCR data;
  added later if needed.
- No cross-ladder normalization. Each ladder's fractions sum to 100% on its
  own.
- No per-rung AUC export to the sibling CSV. The CSV remains the smoothed
  spectrum, not a per-ladder summary.
- No plot annotation changes.
- No Python mirror of the abundance math. Display-only, no offline artifact.

## 3. Physical model and definitions

For a ladder with snapped rungs at observed m/z values `mz₁ < mz₂ < … < mzₙ`
on the viewer's processed trace `(PROC_X, PROC_Y)`:

- **Unscaled intensity** `y'(mz) = (mz ≥ threshold && scale > 0) ? PROC_Y / scale
  : PROC_Y`. Restores pre-LCR-scale signal so AUCs are comparable across the
  threshold.
- **Local-valley window** for rung *i*: indices `[iLo, iHi]` such that
  walking left from the index nearest `mzᵢ`, `y'` is monotonically
  non-increasing — stop at the first index `k` where `y'[k-1] > y'[k]`
  (intensity has started rising again, marking a valley) or when
  `specX[k] ≤ mzLoCap`; mirror to the right. Caps are the midpoints to
  neighboring rungs (`(mzᵢ₋₁ + mzᵢ)/2` and `(mzᵢ + mzᵢ₊₁)/2`); at the
  ladder ends, the cap is `mzᵢ ± state.tolMz` (the snap tolerance,
  default 5.0 m/z).
- **Rung AUC** `auc_i = trapz(PROC_X[iLo..iHi], y'[iLo..iHi])`. Trapezoidal
  on the same uneven grid the labeler already uses.
- **Relative abundance** `abundance_i = auc_i / Σ_j auc_j`. Per-ladder
  denominator. Stale or unsnapped rungs are excluded from both numerator
  and denominator (they contribute to neither sum and render as `—`).
- **Edge cases**
  - `Σauc = 0` → every rung's `abundance = null`, all cells render `—`.
  - Single snapped rung → `abundance = 1.0` (renders `100.0%`). Useful as a
    sanity tell.
  - Manual labels are included in the sum (they are real peaks).
  - Stale labels are excluded.

## 4. API additions (pure math)

Added to `LadderLabelerCore` so they remain testable without DOM or Plotly:

```js
// (mz ≥ threshold && scale > 0) ? y/scale : y
unscaleY(mz, y, threshold, scale)

// Walks left/right from the index nearest mzObs, stops at the first
// local minimum or the cap, returns inclusive index bounds. Returns
// null if specX is empty.
findValleyBounds(mzObs, mzLoCap, mzHiCap, specX, specY)

// Trapezoidal AUC of [iLo, iHi] on (specX, specY) with per-sample
// unscale applied. unscale(mz, y) is a closure.
trapzAuc(iLo, iHi, specX, specY, unscale)
```

And one stateful orchestrator on `LadderLabeler`, called from
`refreshLadder` after the existing snap loop:

```js
// Mutates L.labels: assigns lb.auc and lb.abundance.
// Sets L.aucSum = Σ auc over non-null contributors.
computeLadderAbundances(L, specX, specY)
```

`computeLadderAbundances` reads `state.threshold` and `state.scale` (see §6
for how those are wired) and builds the `unscale` closure once.

## 5. UI changes

### 5.1 Side-panel column

`renderLadderPanel()` in `build_lcr_viewer.py` already emits a rung table
per ladder. Add one column:

| Header | Cell format | Alignment |
|--------|-------------|-----------|
| `Abund.` | `XX.X%` (1 decimal); `—` when `abundance` is null | right |

No other columns change. Existing manual/stale visual markers stay as-is on
the same row.

### 5.2 Per-ladder footer

Below the rung table for each ladder, render a single small dim line:

```
ΣAUC = 1.23e6
```

Scientific notation, 2 significant figures. When `aucSum === 0`, render
`ΣAUC = —`. Purpose: a magnitude sanity check that makes pathological
integration obvious without burdening the rung rows.

### 5.3 Plot annotations

**Unchanged.** No abundance is added to `buildAnnotations` output. The plot
stays at z + m/z per rung, matching the user's "panel only" choice.

## 6. State wiring: option (b)

`refreshLadder(id, specX, specY)` keeps its current signature. The labeler
gains two state fields:

```js
state.threshold = +Infinity;   // m/z above which intensity is scaled
state.scale     = 1;            // multiplier above threshold
```

The viewer (in `build_lcr_viewer.py`'s inlined initializer) sets both at
load and re-syncs them whenever the user toggles **Scale charge-reduced
region** or drags the threshold. `unscale` correctly degenerates to a no-op
when `scale === 1` or `threshold === +Infinity`, so spectra without LCR
scaling work without ceremony.

Rationale: threshold and scale are global-per-spectrum, not per-call inputs.
Threading them through every `refresh*` call site would touch ~5 places in
`build_lcr_viewer.py` for no semantic gain.

## 7. Tests

All in `tests/ladder_labeler_test.html` (pure-math harness, no browser
automation needed — opens with `file://`).

### 7.1 New tests

- `unscaleY` above threshold with `scale=4` returns `y/4`; below threshold
  returns `y`; `scale=1` is a no-op everywhere; `scale=0` is a no-op
  everywhere.
- `findValleyBounds` on a hand-rolled three-peak intensity array stops at
  the local minima between peaks and not before.
- `findValleyBounds` respects `mzLoCap` / `mzHiCap` — when the cap is
  tighter than the natural valley, the cap wins.
- `findValleyBounds` on empty `specX` returns `null`.
- `trapzAuc` on a triangle of known area matches closed-form to 1e-9.
- `trapzAuc` with `unscale` halving samples above a threshold returns half
  the AUC of the same triangle without `unscale`.
- `computeLadderAbundances` end-to-end: a synthetic 3-rung ladder with peak
  amplitudes in ratio 1:2:1 yields abundances within 1 pp of 25/50/25%.
- Stale label excluded from the sum (4-rung ladder, mark one stale, sum is
  over the remaining three).
- Single snapped rung yields `abundance = 1.0`.
- All rungs zero-intensity → every `abundance` is `null`, `aucSum === 0`.

### 7.2 Stale-test fix

`tests/ladder_labeler_test.html:364–366` currently asserts that
`buildAnnotations` emits an annotation whose `text` contains "Ladder A".
That summary annotation was deliberately moved to the side panel in the
parent ladder-labeling work; only `hovertext` still carries ladder
identity. Replace the assertion with:

```js
check('annotations carry ladder identity in hovertext',
      g.annotations.some(a => typeof a.hovertext === 'string'
                              && a.hovertext.indexOf('Ladder A') >= 0));
```

One-line semantic change; restores the harness to green.

## 8. Files touched

- `ladder_labeler.js` — add `unscaleY`, `findValleyBounds`, `trapzAuc` to
  `LadderLabelerCore`; add `computeLadderAbundances` to `LadderLabeler`;
  add `state.threshold` and `state.scale`; call
  `computeLadderAbundances` at the end of `refreshLadder`.
- `build_lcr_viewer.py` — `renderLadderPanel()` adds the `Abund.` column
  and `ΣAUC` footer; the inlined initializer sets / re-syncs
  `state.threshold` and `state.scale` on the threshold-drag and scale-
  checkbox handlers.
- `tests/ladder_labeler_test.html` — fix the stale annotation assertion;
  add the new tests in §7.1.

## 9. Out of scope (explicit)

- Baseline subtraction.
- Cross-ladder normalization.
- AUC in the sibling CSV.
- Any plot annotation change.
- Any Python mirror of abundance math.
