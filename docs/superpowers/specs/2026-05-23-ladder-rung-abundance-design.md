# Ladder species relative abundance (per-ladder AUC) — design

**Date:** 2026-05-23
**Status:** Approved (pending user review of this written spec)
**Scope:** Extend the existing ladder labeler (see
`2026-05-22-ladder-labeling-design.md`) to compute and display, for each
ladder, a per-species relative abundance based on the sum of its rung AUCs
as a fraction of the total rung AUC across all ladders in the spectrum.
Fold in a fix for a pre-existing stale assertion in
`tests/ladder_labeler_test.html`.

---

## 1. Problem

Each ladder in an LCR spectrum corresponds to one neutral species (one M),
and its rungs are that species' charge-reduced forms. When more than one
species is present, the user wants to compare **species abundances** —
"polyP-A is 35% of the polyP signal, polyP-B is 22%" — not the
distribution of intensity across charge states within a single species.

The labeler currently tells the user which charge each rung represents and
the back-calculated `M`. It does not tell them how much of the total polyP
signal each species accounts for. They have to eyeball the relative peak
heights, which is noisy and ignores peak shape.

## 2. Goals and non-goals

**Goals**

- For each ladder, compute the total AUC across all its snapped rungs
  (`ΣAUC_ladder`), and a relative abundance `ΣAUC_ladder / Σ_j ΣAUC_j`
  where the denominator runs over every ladder in the spectrum. Fractions
  across ladders sum to 100%.
- Display the abundance in the existing side-panel ladder card header,
  alongside `M` and `σ`. Display `ΣAUC` as a small magnitude line for
  sanity checking.
- Be correct under LCR scaling: integrate the **unscaled** smoothed signal
  so that abundances are not distorted when a ladder straddles the
  threshold or the user toggles `scale_on`.
- Flag ladders with any unsnapped or stale rung as `partial`, so the user
  knows their reported `ΣAUC` is a lower bound and the comparison is not
  apples-to-apples.
- Keep the plot annotations and the per-rung table unchanged. No per-rung
  abundance column.
- Restore the pure-math test harness to green by updating the one stale
  assertion that has drifted from current behavior.

**Non-goals (v1)**

- No per-rung relative abundance. The user does not want the within-ladder
  charge-state distribution.
- No baseline subtraction. There is no universal baseline rule for LCR
  data; added later if needed.
- No per-rung or per-ladder AUC export to the sibling CSV. The CSV remains
  the smoothed spectrum, not a per-ladder summary.
- No plot annotation changes.
- No Python mirror of the abundance math. Display-only, no offline
  artifact.

## 3. Physical model and definitions

For a ladder with snapped rungs at observed m/z values `mz₁ < mz₂ < … < mzₙ`
on the viewer's processed trace `(PROC_X, PROC_Y)`:

- **Unscaled intensity** `y'(mz) = (mz ≥ threshold && scale > 0)
  ? PROC_Y / scale : PROC_Y`. Restores pre-LCR-scale signal so AUCs are
  comparable across the threshold.
- **Local-valley window** for rung *i*: indices `[iLo, iHi]` such that
  walking left from the index nearest `mzᵢ`, `y'` is monotonically
  non-increasing — stop at the first index `k` where `y'[k-1] > y'[k]`
  (intensity has started rising again, marking a valley) or when
  `specX[k] ≤ mzLoCap`; mirror to the right. Caps are the midpoints to
  neighboring rungs (`(mzᵢ₋₁ + mzᵢ)/2` and `(mzᵢ + mzᵢ₊₁)/2`); at the
  ladder ends, the cap is `mzᵢ ± state.tolMz` (the snap tolerance,
  default 5.0 m/z).
- **Rung AUC** `auc_i = trapz(PROC_X[iLo..iHi], y'[iLo..iHi])`.
  Trapezoidal on the same uneven grid the labeler already uses. Per-rung
  AUCs are intermediate values — computed and stored on each label, but
  not surfaced in the UI.
- **Ladder ΣAUC** `aucSum = Σ_i auc_i` over snapped rungs only. Stale or
  unsnapped rungs contribute nothing.
- **Partial flag** `isPartial = true` iff any candidate rung in the ladder
  is unsnapped (`mzObs === null`) or stale. Manual overrides at a given z
  count as snapped for this flag.
- **Species relative abundance** `abundance_k = aucSum_k / Σ_j aucSum_j`.
  Denominator is over every ladder in the spectrum (partial ladders
  included — they still contribute their measurable AUC, just under-
  represented by definition).
- **Edge cases**
  - Total `Σ_j aucSum_j = 0` → every ladder's `abundance = null`, all
    headers render `—`.
  - Single ladder → its abundance is `1.0` (renders `100.0%`). Useful as
    a sanity tell.
  - A ladder where no rung snapped → `aucSum = 0`, `abundance = 0%`,
    `isPartial = true`.

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

Two stateful helpers on `LadderLabeler`:

```js
// Mutates L: assigns lb.auc on each label (or null for stale/unsnapped),
// sets L.aucSum and L.isPartial. Reads state.threshold and state.scale
// for the unscale closure. Does NOT touch L.abundance.
computeLadderAuc(L, specX, specY)

// Iterates state.ladders and assigns L.abundance = L.aucSum / total.
// Total = 0 → every L.abundance = null.
recomputeAbundances()
```

`refreshLadder(id, specX, specY)` is extended to call
`computeLadderAuc(L, …)` after the existing snap loop, then
`recomputeAbundances()` once at the end. `refreshAll` already iterates all
ladders and calls `refreshLadder`; `recomputeAbundances` ends up called
once per ladder refresh, which is fine (it is `O(#ladders)`, cheap).
`removeLadder` and `addLadderFromSeed` already either invoke
`refreshLadder` or change the ladder set — both need a final
`recomputeAbundances()` call to keep the denominator in sync. Single
explicit call site in each.

## 5. UI changes

### 5.1 Ladder card header

`renderLadderPanel()` in `build_lcr_viewer.py` already renders a header
line per ladder card (the line that holds the ladder id, color swatch,
`M`, and `σ`). Append the abundance after `σ`:

```
Ladder A   M = 26.39 kDa ± 0.4%   Abund. = 35.2%
Ladder B   M = 52.78 kDa ± 0.7%   Abund. = 22.1% (partial)
```

Format: `XX.X%` with 1 decimal; `—` when `abundance` is null. When
`isPartial`, append a small dim `(partial)` tag immediately after the
percent.

### 5.2 Per-ladder footer

Below the rung table for each ladder, render a single small dim line:

```
ΣAUC = 1.23e6
```

Scientific notation, 2 significant figures. When `aucSum === 0`, render
`ΣAUC = —`. Purpose: a magnitude sanity check that makes pathological
integration obvious without burdening the rung rows.

### 5.3 Rung table

**Unchanged.** No per-rung `Abund.` column. Per-rung AUCs are computed but
not displayed.

### 5.4 Plot annotations

**Unchanged.** No abundance is added to `buildAnnotations` output.

## 6. State wiring: option (b)

`refreshLadder(id, specX, specY)` keeps its current signature. The labeler
gains two state fields:

```js
state.threshold = +Infinity;   // m/z above which intensity is scaled
state.scale     = 1;            // multiplier above threshold
```

The viewer (in `build_lcr_viewer.py`'s inlined initializer) sets both at
load and re-syncs them whenever the user toggles **Scale charge-reduced
region** or drags the threshold. `unscaleY` correctly degenerates to a
no-op when `scale === 1` or `threshold === +Infinity`, so spectra without
LCR scaling work without ceremony.

Rationale: threshold and scale are global-per-spectrum, not per-call
inputs. Threading them through every `refresh*` call site would touch ~5
places in `build_lcr_viewer.py` for no semantic gain.

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
- `computeLadderAuc` on a synthetic 3-rung ladder with peak amplitudes in
  ratio 1:2:1 yields `aucSum` within 1% of the closed-form sum, and
  `isPartial === false`.
- `computeLadderAuc` with one stale rung sets `isPartial === true` and
  `aucSum` excludes that rung's contribution.
- `recomputeAbundances` on two synthetic ladders with `aucSum` ratio 3:1
  assigns `abundance = 0.75` and `0.25` within 1e-9.
- `recomputeAbundances` with total `aucSum = 0` sets every ladder's
  `abundance = null`.
- Single-ladder spectrum: `abundance === 1.0`.
- Adding a second ladder rebalances the first ladder's abundance below
  1.0 (denominator-update sanity check on the call-site wiring).
- Removing a ladder rebalances the remaining ladders' abundances to sum
  to 1.0.

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
  `LadderLabelerCore`; add `computeLadderAuc` and `recomputeAbundances`
  to `LadderLabeler`; add `state.threshold` and `state.scale`; call
  `computeLadderAuc` then `recomputeAbundances` at the end of
  `refreshLadder`. `removeLadder` calls `recomputeAbundances` explicitly
  (it does not path through `refreshLadder`); `addLadderFromSeed` and
  `addLadderFromTwoClicks` already reach `recomputeAbundances` via
  `refreshLadder`, so no extra call is needed there.
- `build_lcr_viewer.py` — `renderLadderPanel()` appends `Abund. = XX.X%`
  (with optional `(partial)` tag) to the ladder card header and adds the
  `ΣAUC` footer; the inlined initializer sets / re-syncs
  `state.threshold` and `state.scale` on the threshold-drag and scale-
  checkbox handlers.
- `tests/ladder_labeler_test.html` — fix the stale annotation assertion;
  add the new tests in §7.1.

## 9. Out of scope (explicit)

- Per-rung relative abundance (charge-state distribution within a ladder).
- Baseline subtraction.
- Cross-spectrum normalization (no concept of "the same species in two
  spectra" lives in the viewer).
- AUC in the sibling CSV.
- Any plot annotation change.
- Any Python mirror of abundance math.
