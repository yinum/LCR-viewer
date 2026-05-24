# Ladder species relative abundance (per-ladder AUC) — design

**Date:** 2026-05-23
**Status:** Approved (pending user review of this written spec)
**Scope:** Extend the existing ladder labeler (see
`2026-05-22-ladder-labeling-design.md`) to compute and display, for each
ladder, a per-species relative abundance based on the sum of its rung AUCs
as a fraction of the total rung AUC across all ladders in the spectrum.
Add a per-rung exclude/include control (panel checkbox + plot shortcut)
so the user can omit specific rungs from the abundance calculation. Fold
in a fix for a pre-existing stale assertion in
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

- For each ladder, compute the total AUC across all its **included**
  snapped rungs (`ΣAUC_ladder`), and a relative abundance
  `ΣAUC_ladder / Σ_j ΣAUC_j` where the denominator runs over every ladder
  in the spectrum. Fractions across ladders sum to 100%.
- Allow the user to exclude specific rungs from a ladder's `ΣAUC` via two
  affordances writing to the same state: (a) a checkbox column in the
  panel's rung table, and (b) typing `x` in the existing plot-click prompt
  to toggle a clicked rung. Default: every snapped rung is included.
- Display the abundance in the existing side-panel ladder card header,
  alongside `M` and `σ`. Display `ΣAUC` as a small magnitude line for
  sanity checking.
- Be correct under LCR scaling: integrate the **unscaled** smoothed signal
  so that abundances are not distorted when a ladder straddles the
  threshold or the user toggles `scale_on`.
- Flag ladders with any unsnapped, stale, or excluded rung as `partial`,
  so the user knows their reported `ΣAUC` is a lower bound and the
  comparison is not apples-to-apples.
- Keep the plot annotations unchanged. Per-rung table gains the AUC
  include checkbox but no abundance column.
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
  AUCs are intermediate values — computed and stored on each snapped
  label (including excluded ones, so toggling include is instant), but
  not surfaced in the UI.
- **Exclusion set** `L.excludedZ: Set<number>` — per-ladder ladder-level
  state listing rung charges the user has marked as excluded from the
  AUC. Empty by default. Persists across `refreshLadder` re-snaps (it
  lives on the ladder, not on the labels that get rebuilt).
- **Ladder ΣAUC** `aucSum = Σ_i auc_i` over rungs that are snapped, not
  stale, and not in `excludedZ`. Stale, unsnapped, or excluded rungs
  contribute nothing.
- **Partial flag** `isPartial = true` iff any candidate rung in the ladder
  is unsnapped (`mzObs === null`), stale, or in `excludedZ`. Manual
  overrides at a given z count as snapped for this flag (unless also
  excluded).
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

Three stateful helpers on `LadderLabeler`:

```js
// Mutates L: assigns lb.auc on each snapped label (or null for
// stale/unsnapped), sets L.aucSum (sum over included, snapped rungs)
// and L.isPartial. Reads state.threshold, state.scale, and L.excludedZ.
// Does NOT touch L.abundance.
computeLadderAuc(L, specX, specY)

// Iterates state.ladders and assigns L.abundance = L.aucSum / total.
// Total = 0 → every L.abundance = null.
recomputeAbundances()

// Public toggle used by both the panel checkbox and the plot-click
// shortcut. Flips z's membership in L.excludedZ for the named ladder,
// re-sums L.aucSum from the already-stored lb.auc values (instant — no
// re-integration), updates L.isPartial, and calls recomputeAbundances().
// Returns { id, z, included: boolean } so the caller can update its UI.
toggleAucInclude(id, z)
```

`refreshLadder(id, specX, specY)` is extended to call
`computeLadderAuc(L, …)` after the existing snap loop, then
`recomputeAbundances()` once at the end. `refreshAll` already iterates all
ladders and calls `refreshLadder`; `recomputeAbundances` ends up called
once per ladder refresh, which is fine (it is `O(#ladders)`, cheap).
`removeLadder` calls `recomputeAbundances()` explicitly (it does not path
through `refreshLadder`). `addLadderFromSeed` and `addLadderFromTwoClicks`
already reach `recomputeAbundances` via `refreshLadder`.

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

### 5.3 Per-rung chip row

The current side panel does not have a per-rung table to extend (the
original spec assumed one existed). Each ladder card instead carries a
compact horizontal chip row under its M readout, one chip per candidate
rung:

`[✓7+] [✓6+] [✗5+] [✓4+] [—3+] [—2+] [—1+]`

- `✓` chip (light blue) — rung is snapped and included in AUC. Clicking
  excludes it.
- `✗` chip (light red) — rung is snapped but excluded. Clicking re-includes.
- `—` chip (gray, disabled) — rung is unsnapped or stale. Not clickable.

Live-chip clicks call `LadderLabeler.toggleAucInclude(id, z)`. The chip
row is rebuilt by `renderLadderPanel()` on each labeler state change.
Chips are rendered inline (no separate CSS rule) inside `chipsFor(L)`,
which sorts labels by descending z so chips read 7+, 6+, 5+, ….

### 5.4 Plot click shortcut

Extend the existing click prompt in `handlePlotClick`. Current convention:

> Enter integer to override z, integer+s to set as new seed, empty to delete.

New convention:

> Enter integer to override z, integer+s to set as new seed, `x` to
> toggle AUC include, empty to delete.

Typing `x` (case-insensitive, no integer) calls
`toggleAucInclude(L.id, lb.z)`. All other prompt paths unchanged.

### 5.5 Plot annotations

**Unchanged.** No abundance or exclusion mark is added to
`buildAnnotations` output. Exclusion state is visible only in the panel
checkbox and (indirectly) via the ladder's `Abund.` and `(partial)` tag.

## 6. State wiring: option (b)

`refreshLadder(id, specX, specY)` keeps its current signature. The labeler
gains two state fields:

```js
state.threshold = +Infinity;   // m/z above which intensity is scaled
state.scale     = 1;            // multiplier above threshold
```

The viewer (in `build_lcr_viewer.py`'s inlined initializer) sets both at
load and re-syncs them whenever the user toggles **Scale charge-reduced
region** or drags the threshold; immediately after the re-sync it calls
`refreshAll(PROC_X, PROC_Y)` so per-rung AUCs are recomputed against the
new unscale rule (re-summing alone is not enough — the integration
itself depends on `unscaleY`). `unscaleY` correctly degenerates to a
no-op when `scale === 1` or `threshold === +Infinity`, so spectra
without LCR scaling work without ceremony.

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
- `toggleAucInclude` adds z to `excludedZ` on first call, removes it on
  second call (idempotent toggle).
- After `toggleAucInclude` excludes a rung, `aucSum` drops by exactly the
  excluded rung's `auc` and `isPartial === true`.
- After `toggleAucInclude` re-includes the rung, `aucSum` and `isPartial`
  return to their original values.
- `excludedZ` survives `refreshLadder` (re-snap on the same spectrum
  preserves the exclusion).
- `computeLadderAuc` with one stale rung AND one excluded rung sets
  `aucSum` excluding both, and `isPartial === true`.

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
  `LadderLabelerCore`; add `computeLadderAuc`, `recomputeAbundances`, and
  `toggleAucInclude` to `LadderLabeler`; add `state.threshold` and
  `state.scale`; initialize `L.excludedZ = new Set()` in
  `addLadderFromSeed`; call `computeLadderAuc` then `recomputeAbundances`
  at the end of `refreshLadder`. `removeLadder` calls
  `recomputeAbundances` explicitly; `addLadderFromSeed` and
  `addLadderFromTwoClicks` reach it via `refreshLadder`. Extend
  `handlePlotClick` to recognize `x` in the edit prompt.
- `build_lcr_viewer.py` — `renderLadderPanel()` appends `Abund. = XX.X%`
  (with optional `(partial)` tag) to the ladder card header, adds the
  `ΣAUC` footer, and adds the `AUC?` checkbox column to each rung row
  (wired to `toggleAucInclude`); the inlined initializer sets / re-syncs
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
