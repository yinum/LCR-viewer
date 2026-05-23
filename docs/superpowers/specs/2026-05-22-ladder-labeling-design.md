# LCR ladder labeling — design

**Date:** 2026-05-22
**Status:** Approved (pending user review of this written spec)
**Scope:** Add a self-contained ladder-labeling module to the existing
`polyP_LCR_viewer.html` so that native-MS limited-charge-reduction (LCR)
spectra can be annotated with charge states and back-calculated neutral mass.
Develop as an opt-in module first ("wired later" = ships disabled, single
checkbox enables it); the existing MS1 workflow is bit-identical when the
module is off.

---

## 1. Problem and physical model

Native-MS LCR spectra of polyP have two relevant features:

1. **Peaks are broad** — isotopes are not resolved at QTOF resolution. Mass
   error per rung is realistically ±50 to several hundred Da. Algorithms that
   assume isotope spacing (Δm/z = 1/z) do not apply.
2. **The precursor m/z window is a mixture** — multiple species and charge
   states collapse to similar m/z because m/z = M/z. LCR removes charges to
   spread that mixture into a ladder of charge-reduced products. Each rung
   corresponds to a single species at a single z, so rungs (but not the
   precursor envelope itself) are cleanly labelable.

Positive-mode math (matches the current viewer, Synapt G2 QTOF):

- `M = z·(m/z) − z·m_H` (neutral mass from one labeled rung)
- `m/z(z) = (M + z·m_H) / z` (predicted m/z for any other rung)
- `m_H = 1.00727646677` Da (CODATA)

A "ladder" is the family of charge-reduced products of a single species: same
M, different z. In native MS a single spectrum can contain **multiple
ladders** from different parent masses (M₁, M₂, …), interleaved.

## 2. Goals and non-goals

**Goals**

- Label each charge-reduced rung with its charge state and observed m/z.
- Back-calculate the neutral mass M for each ladder and display it in the
  header.
- Support multiple ladders per spectrum, each with its own seed and color.
- Provide both auto seeding (type z₀ + precursor m/z) and a two-click solver
  (closed-form recovery of z and M from any two ladder rungs).
- Provide a manual override path: click any peak, type a charge, get a label.
- Ship as an opt-in module inside the existing HTML; default off so the
  current MS1 workflow is unchanged.

**Non-goals (v1)**

- No isotope-resolved labeling (data does not support it).
- No fragment-series identification (no "polyPₙ ladder match" against the PO₃
  repeat). Labels are z + m/z + per-ladder M only.
- No CSV export of labels. The processed CSV pipeline is untouched.
- No Python mirror of the labeling math (display-only, no offline artifact to
  reproduce).
- No labeling of the precursor envelope itself — it is a mixture by
  construction; labeling it as a single z would be a false claim.

## 3. Architecture

A single JS object `LadderLabeler` added to the in-HTML script block.
Self-contained — no dependencies on the existing scaling/smoothing functions
beyond reading the already-processed trace that Plotly is plotting.

### 3.1 Module contract

```js
LadderLabeler = {
  // global state
  enabled: false,
  tolMz: 5.0,                  // snap window half-width, m/z
  sigmaAmberRelative: 0.01,    // amber if σ_M / M exceeds this
  ladders: [],                 // see 3.2
  activeLadderId: null,        // which ladder receives click-create
  pendingMode: null,           // null | 'two-click' (single-shot)
  twoClickBuffer: null,        // first m/z while waiting for second click

  // pure functions (testable headless)
  computeM(z, mz),                          // returns M, positive-mode
  predictRung(M, z),                        // returns predicted m/z
  solveFromTwoClicks(m_a, m_b),             // returns {z, M}; null if ambiguous
  snapToMaxInWindow(mzPred, spectrum, tolMz), // global-max-in-window; null if empty

  // ladder-level operations
  addLadderFromSeed({mz, z}),               // returns new ladder id
  addLadderFromTwoClicks(m_a, m_b),         // wraps solver + addLadderFromSeed
  removeLadder(id),
  setActive(id),
  refreshLadder(id, spectrum),              // re-snap one ladder
  refreshAll(spectrum),                     // re-snap every ladder

  // UI integration
  renderAnnotations(plotDiv),               // Plotly.relayout({annotations})
  renderPanel(panelDiv),                    // re-render the Ladders list
  handlePlotClick(evt, spectrum),           // routes click by pendingMode + nearest-label
};
```

### 3.2 Ladder data model

```js
ladder = {
  id: 'A',                          // 'A', 'B', 'C', … by creation order
  color: '#1f77b4',                 // Plotly default palette, cycled by index
  seed: { mz: 3300.0, z: 8 },       // anchor — used for math, NOT plotted as label
  M: 26384.5,                       // computed from seed
  sigmaM: 1.8,                      // Da, sample std over rungs
  labels: [
    { z: 7, mzPred: 3771.3, mzObs: 3771.2, mImplied: 26390.4, manual: false, stale: false },
    { z: 6, mzPred: 4399.7, mzObs: 4399.5, mImplied: 26390.0, manual: false, stale: false },
    { z: 5, mzPred: 5279.4, mzObs: null,   mImplied: null,    manual: false, stale: false }, // missed
    …
  ],
}
```

- `mzObs: null` → predicted rung was not found in the snap window. Recorded
  but not drawn.
- `manual: true` → user-clicked label. Survives ladder re-snapping by
  re-searching near the previous `mzObs`.

### 3.3 Module boundary rationale

- All UI integration funnels through `renderAnnotations`, `renderPanel`, and
  `handlePlotClick`. Pure functions know nothing about Plotly or the DOM —
  they're testable in a headless harness.
- Multi-ladder is a list, not a sharded state — adding/removing ladders is
  array push/splice, no global refactor.
- The processed trace is read on demand from the existing global the viewer
  already maintains; the labeler does not own a copy.

## 4. Algorithm

### 4.1 Ladder generation from a seed

Given `seed = {mz, z}` (with `z` ≥ 2):

1. `M = z·mz − z·m_H`.
2. For each `z' = z−1, z−2, …, 1`:
   1. `mzPred = (M + z'·m_H) / z'`.
   2. If `mzPred` is outside the plot's current x-range, skip silently.
   3. `mzObs = snapToMaxInWindow(mzPred, spectrum, tolMz)`. If null, record
      with `mzObs: null` (not drawn).
   4. `mImplied = z'·mzObs − z'·m_H` if `mzObs` is non-null, else null.
3. `σ_M` = sample std over all non-null `mImplied`. Empty if 0 or 1 rungs.

The seed itself does **not** appear in `labels` — it is the math anchor only.

### 4.2 Snap algorithm — `snapToMaxInWindow`

Native-MS peaks are broad enough that a strict 3-point local-max test is
fragile (sensitive to noise wobble). Use global-max-in-window instead:

```
candidates = { (mz_i, y_i) | mz_i in [mzPred − tolMz, mzPred + tolMz] }
if candidates is empty: return null
return argmax_y(candidates).mz_i
```

This operates on `intensity_processed` (the trace Plotly is currently
plotting). The window is the same `tolMz` for every rung — broad rungs and
narrow rungs both use the global setting.

### 4.3 Two-click solver — `solveFromTwoClicks`

Given two clicks `m₁, m₂` with `m₁ < m₂` (swap if necessary). The higher-
charge rung is at `m₁` (charge `z₁`); the lower-charge rung is at `m₂`
(charge `z₁ − k`, where `k ≥ 1` is the number of charge-reduction steps
between them — `k = 1` for adjacent rungs). Derivation in Appendix B.

```
// Early-return for clicks that are physically the same peak. At native-MS
// resolution, peaks are several m/z wide; any two clicks within 1 m/z
// are the same peak and the math gives garbage z values.
if (m₂ − m₁ < 1.0): return null

candidates = []
for k in [1, 2, 3, 4, 5]:
    z_raw = k · (m₂ − m_H) / (m₂ − m₁)
    z     = round(z_raw)
    if z < 2: continue                          // need z₁ ≥ 2 to have any reduction
    err   = |z − z_raw|
    if err < 0.2:                               // close enough to an integer
        candidates.append({k, z, err})

if candidates is empty:
    return null   // status: "ambiguous two-click — pick farther-apart rungs"

best = argmin_err(candidates)   // smallest |z − z_raw| wins
M    = best.z · m₁  −  best.z · m_H
return { z: best.z, M, k: best.k }
```

The multi-k sweep handles non-adjacent rungs (e.g., z=8 and z=5, skipping
z=7 and z=6) without forcing the user to know k. When `gcd(z₁, k) = 1`
only one k gives an integer-close result. When `gcd(z₁, k) > 1` (e.g.,
m/z ratios that are exactly rational), multiple k's all give integer-close
zRaw — argmin_err returns the smallest-k (simplest) interpretation; the
user can re-seed to a higher-M reading if context demands.

`addLadderFromTwoClicks` then calls `addLadderFromSeed({ mz: m₁, z })`
using the higher-charge click as the seed anchor.

### 4.4 Manual override

- Click within `tolMz` of an existing label → `prompt()` opens pre-filled
  with the current z as a string. User input is parsed as follows:
  - **Empty string / cancel** → delete this label.
  - **Positive integer** (e.g. `7`) → override this label's z; no re-seed.
  - **Positive integer suffixed with `s`** (e.g. `7s`) → set this label as
    the new seed for its ladder; `refreshLadder` re-runs §4.1 using
    `(mzObs, parsed_z)` as the new anchor.
  - **Any other input** → status: *"unrecognized — expected integer, integer+s, or empty"*; no change.
- Click on unlabeled territory → snap to nearest peak via
  `snapToMaxInWindow(clickedMz, spectrum, tolMz)`. If a peak is found, prompt
  for z and create a manual label in the **active ladder**. `manual: true`.
- Shift-click on a label → delete that one label.

A manual label's `mImplied` is computed from its own (z, mzObs) and shows in
its hover tooltip. If `mImplied` disagrees with the ladder's `M`, that is the
visual flag — no extra warning needed.

### 4.5 Re-snap on parameter change

When the processed trace changes (scaling toggle, smoothing method/width,
threshold), every ladder is re-snapped:

- Auto labels: re-run §4.1 from scratch (seed math is preserved).
- Manual labels: search `[prev_mzObs − tolMz, prev_mzObs + tolMz]` for the
  new global max. If found, update `mzObs`. If not, mark `stale: true` and
  render greyed; click re-affirms or deletes.

## 5. UI surface

### 5.1 Control panel

A new section under the existing Scaling / Smoothing controls, collapsed by
default. Layout:

```
▾ Ladder labels
  [ ] Show ladder labels
  Snap tolerance: [ 5.0 ] m/z       (global, applies to all ladders)

  Ladders:                                       Active
  ┌─────────────────────────────────────────────┐
  │ ●  A   z₀ [ 8 ]   m/z [3300.0]              │  (•)
  │        M = 26.4 kDa ± 0.4%   6/7 rungs   ✕  │
  │ ●  B   z₀ [16 ]   m/z [3302.5]              │  ( )
  │        M = 52.8 kDa ± 0.6%   4/15 rungs  ✕  │
  └─────────────────────────────────────────────┘
  [ + Type seed ]  [ + 2-click seed ]  [ Clear all ]
```

- The colored dot is the on-plot label color for that ladder.
- z₀ and precursor m/z are editable in place; editing triggers
  `refreshLadder` for that ladder only.
- The active-ladder radio determines which ladder receives click-create.
- The denominator in `6/7 rungs` is `z₀ − 1` (the seed is excluded by
  design).

### 5.2 On-plot layer

Two visual elements per ladder:

1. **A dashed vertical line at `precursor m/z`**, colored to the ladder, with
   tooltip *"Ladder A seed (z₀=8, mixture; not labeled)"*. Quiet visual cue
   that the seed is the math anchor, not a peak claim.
2. **Plotly annotations at each found rung**, colored to the ladder, two
   lines:
   ```
       7+
     3771.20
   ```
   Manual labels render the same way with a small "M" prefix on the first
   line (`M 7+ / 3771.20`).

Stacked-label collision (two ladders' rungs at near-equal m/z): offset each
ladder's annotations by `−40 px × ladderIndex` in `ay`.

### 5.3 Hover tooltip

Each labeled peak extends Plotly's default tooltip with:
```
Ladder A — z = 7+
M = 26 392.3 Da  (this rung)
```

The per-rung `M` in the tooltip is the cross-check the user gets — disagreement
with the header `M` flags a misassigned z.

### 5.4 Header annotation

Above the plot title, one line per ladder, colored to match:
```
Ladder A:  M = 26.4 kDa ± 0.4%  (z₀ = 8+, 6 rungs)
Ladder B:  M = 52.8 kDa ± 0.6%  (z₀ = 16+, 4 rungs)
```

Mass display precision is auto-picked from σ:

- `precision_Da = 10 ^ floor(log10(σ_M))` (rounded down to the nearest power
  of ten ≤ σ_M; clamped to ≥ 1 Da).
- If `M < 10 000 Da`, display in **Da** rounded to `precision_Da`
  (e.g. `M = 8 432 Da`, `M = 9 800 Da`).
- If `M ≥ 10 000 Da`, display in **kDa** with
  `decimals = max(0, 3 − floor(log10(σ_M)))` (e.g. σ = 1.8 → 3 decimals →
  `26.392 kDa`; σ = 80 → 2 decimals → `26.39 kDa`; σ = 800 → 1 decimal →
  `26.4 kDa`).

The `±` figure in the header is shown in the same units as M (`± 4 Da`,
`± 0.08 kDa`) when σ/M < 0.001, otherwise as a percentage (`± 0.4%`).

If `σ_M / M > sigmaAmberRelative`, the line color turns amber and the suffix
adds *— check assignments*.

If 0 rungs are found for a ladder, the line reads
*Ladder A: no rungs matched — check z₀ or widen tolerance* in amber.

## 6. Edge cases

| Case | Behavior |
|---|---|
| `z₀ = 1` | No ladder possible (z' = 0 doesn't exist). Status: *"z₀ must be ≥ 2"*. |
| `z₀ = 2` | One rung (z=1). Fine, just sparse. |
| Predicted rung outside plot x-range | Skipped silently; not counted in "found / predicted". |
| Snap window empty for a rung | `mzObs = null`; not drawn; counts as "not found". |
| 0 / N rungs found | Header amber, no annotations drawn for that ladder. |
| Two-click order reversed (`m_a > m_b`) | Swap internally. |
| Two-click solver: `\|z − z_raw\| > 0.2` | Reject; status amber: *"ambiguous — pick farther-apart rungs"*. |
| Manual label disagrees with ladder M | No warning; tooltip shows its own M; user sees the disagreement and acts. |
| Smoothing / scaling parameter change | All ladders re-snap (§4.5). |
| Spectrum has zero peaks (degenerate) | Module disables itself; status: *"no data"*. |
| Overlapping rungs from two ladders | Annotations offset by `ay = −40 px × ladderIndex`. |

## 7. Preset persistence

Three new top-level keys join `preset.json`:

```json
"ladder_labels": {
  "enabled": false,
  "tol_mz": 5.0,
  "sigma_amber_relative": 0.01
}
```

`preset.json` is git-ignored (per current convention). The loader merges with
defaults so older presets without `ladder_labels` keep working.

**Ladders themselves are not persisted** — they're spectrum-specific and the
user creates them per file. This avoids cross-contamination between datasets
and keeps the preset semantics ("starting points for processing") clean.

## 8. File touchpoints

| File | Change |
|---|---|
| `build_lcr_viewer.py` | HTML template gains ~300 LOC of new JS (`LadderLabeler`), ~30 LOC of new HTML (control panel), and three new preset keys with default merge. CSV pipeline untouched. |
| `preset.json` (user-saved) | New `ladder_labels` block on next save. Backward-compatible. |
| `tests/ladder_labeler.test.html` | New: headless tests for `computeM`, `predictRung`, `solveFromTwoClicks`, `snapToMaxInWindow`, multi-ladder add/remove. |
| `README.md` | New section *"Labeling the LCR ladder"* with usage, screenshot, and the "z₀ is the math anchor, not a per-peak claim" caveat. |
| `AGENTS.md` | New bullet in "How it works" for the labeler module. |

The Python unittest suite (`tests/test_*.py`) is **not** touched — the JS
labeler has no Python counterpart in v1. If a `labels.csv` sibling is added
later, that's when the Python mirror story begins.

## 9. Testing

**JS pure functions** (`tests/ladder_labeler.test.html`)

A self-contained test page that loads `LadderLabeler` and runs assertions:

- `computeM(8, 3300.0)` → `26 392.4` (within 0.1)
- `predictRung(26 392.4, 7)` → `3771.05` (within 0.1)
- `solveFromTwoClicks(3300.0, 3771.0)` → `{z: 8, M ≈ 26 391.94}` (closed-form sanity; the lower-m/z click is the higher-charge rung)
- `solveFromTwoClicks(3300.0, 3300.5)` → `null` (ambiguous)
- `snapToMaxInWindow` on a synthetic broad peak (Gaussian, σ = 2 m/z)
  returns the apex within `±tolMz`.
- Multi-ladder: add A, add B, remove A → B retains its labels and M; ids do
  not collide.

Pass/fail is printed in the page; manual smoke pass before committing.

**End-to-end smoke** — one real spectrum from `data/`, two ladders seeded
(one via type-z, one via two-click), screenshot included in the README.

## 10. Integration story

The labeler ships as a fully self-contained module inside the existing
`polyP_LCR_viewer.html`. "Wired later" means three things:

1. **Default off** — `ladder_labels.enabled = false` in the built-in
   `PRESET`. New viewers open looking identical to today.
2. **Single-checkbox enable** — turning the module on shows the panel and
   activates click handlers; turning it off restores the unannotated plot.
3. **Zero coupling to the existing pipeline** — scaling, smoothing, threshold,
   sibling CSV all behave bit-identically when the labeler is off.

This means the module can be merged to `main`, used by the author on real
data, and matured (UX, defaults, edge-case handling) without ever blocking
the existing MS1 workflow.

## 11. Open questions deferred to implementation

- Exact default `tol_mz` (starting at 5.0 m/z; will adjust after seeing real
  spectra).
- Exact `sigmaAmberRelative` threshold (starting at 0.01; same).
- `prompt()` vs. a floating inline input for manual z entry — `prompt()` for
  v1; revisit if the UX is too jarring.
- Color palette beyond 8 ladders — irrelevant in practice (typically 2–4
  ladders per spectrum), but the cycle wraps if hit.

---

## Appendix A — worked example

A spectrum with filename `PF4_polyP_3300.xy` shows broad peaks centered near
m/z = 3300, 3771, 4400, 5279, 6599, 8798, 13197. User seeds Ladder A with
z₀ = 8, precursor m/z = 3300 (seed peak is in the spectrum but **not
labeled** — only marked by the dashed vertical line):

- `M = 8·3300 − 8·1.00728 = 26 391.94 Da`
- Predicted rungs (using `m/z(z) = (M + z·m_H) / z`):
  - z=7: `3770.99` → snaps to 3771.2  → `mImplied = 7·3771.2 − 7·m_H = 26 391.35`
  - z=6: `4399.66` → snaps to 4399.8  → `mImplied = 26 392.76`
  - z=5: `5279.40` → snaps to 5279.6  → `mImplied = 26 392.96`
  - z=4: `6598.99` → snaps to 6599.2  → `mImplied = 26 392.77`
  - z=3: `8797.99` → snaps to 8797.8  → `mImplied = 26 390.36`
  - z=2: `13 197.0` → snaps to 13 197.3 → `mImplied = 26 392.58`
  - z=1: `26 392.95` → outside plot x-range → skipped
- 6 rungs found out of 7 candidates → panel shows `6/7 rungs`.
- σ_M (sample std over the six `mImplied`) ≈ `1.0 Da`; σ/M ≈ 0.004% → green.
- Display precision: `floor(log10(1.0)) = 0` → 3 decimals in kDa → header:

  `Ladder A:  M = 26.392 kDa ± 0.004%  (z₀ = 8+, 6 rungs)`

---

## Appendix B — derivation: recovering z from two ladder rungs

### B.1 Setup

Two ladder rungs of the same parent neutral mass `M`, positive mode:

- Rung 1: charge `z₁`, observed m/z `m₁`
- Rung 2: charge `z₂`, observed m/z `m₂`

Convention `m₁ < m₂` (so `z₁ > z₂` — higher charge gives lower m/z because
m/z = M/z + m_H). Adjacent rungs satisfy `z₂ = z₁ − 1`; in general
`z₂ = z₁ − k` for integer `k ≥ 1`.

### B.2 Same-parent constraint

The defining property of a ladder is that every rung gives the same M:

```
M = z₁·m₁ − z₁·m_H            (1)
M = z₂·m₂ − z₂·m_H            (2)
```

Setting (1) = (2) and substituting `z₂ = z₁ − k`:

```
z₁·m₁ − z₁·m_H  =  (z₁ − k)·m₂ − (z₁ − k)·m_H
z₁·m₁ − z₁·m_H  =  z₁·m₂ − k·m₂ − z₁·m_H + k·m_H
z₁·(m₁ − m₂)   =  −k·m₂ + k·m_H
z₁·(m₂ − m₁)   =   k·(m₂ − m_H)        (multiply by −1)
```

### B.3 Closed form

```
                k · (m₂ − m_H)
        z₁  =  ────────────────              (3)
                  m₂ − m₁

        M   =  z₁·m₁ − z₁·m_H               (use (1))
```

### B.4 Sanity checks (m_H = 1.00727646677)

| (m₁, m₂)         | k | z₁_raw                       | round | OK? |
|------------------|---|------------------------------|------:|-----|
| (3300, 3771)     | 1 | (3771 − 1.007)/(3771 − 3300) = 3770.0/471 = 8.0008 | 8 | ✓ |
| (3771, 4400)     | 1 | 4399.0/629 = 6.993                                  | 7 | ✓ |
| (3300, 4400)     | 1 | 4399.0/1100 = 3.999                                 | 4 | ✗ — these are z=8 and z=6, not adjacent |
| (3300, 4400)     | 2 | 2·4399.0/1100 = 8.0                                 | 8 | ✓ — correct k |
| (5279, 13197)    | 1 | 13196.0/7918 = 1.667                                | 2 | ✗ — far from integer |
| (5279, 13197)    | 3 | 3·13196.0/7918 = 5.000                              | 5 | ✓ — z=5 to z=2, k=3 |

The multi-k sweep automatically picks the right k.

### B.5 Why this works at native-MS resolution

The formula above is exact for true rung m/z values. With centroid error `δ`
on each click (independent, ~equal magnitude):

```
   δz₁     δm₂   m₁         δm₁    m₂ − m_H
   ────  ≈ ──── · ──── ·  +   ───· ─────────       (linearize (3))
    z₁      m₂   m₂ − m₁     m₁   (m₂ − m₁)·m₂
```

For native-MS conditions:
- `m₂ − m₁ ≈ 500` m/z (typical adjacent-rung spacing for kDa species)
- `δ ≈ 5` m/z (broad-peak centroid wobble)
- → `δz₁/z₁ ≈ 2%`

For true `z₁ = 8`, observed `z₁_raw ≈ 7.84 to 8.16` — well inside the
`|z − z_raw| < 0.2` tolerance gate. The solver is robust at native-MS
resolution **provided the two clicks are reasonably far apart in m/z**
(if `m₂ − m₁ ≈ 50` instead of 500, the error budget tightens 10×).

### B.6 Why the spec doesn't use isotope spacing instead

Isotope-spacing charge determination (`z = round(1 / Δm/z)` between
adjacent isotope peaks) is the standard method at high resolution. It
**does not apply here** because native polyP at QTOF resolution shows
unresolved isotope envelopes — the peak shape is a Gaussian-like envelope
1–10 m/z wide, not a comb of 1/z-spaced isotopes. The ladder-spacing
method recovers z from spacings between *charge states*, not isotopes,
and those spacings (hundreds of m/z) survive 5-m/z centroid wobble.

---

**Approved sections:** §1–§10 incrementally during brainstorming on
2026-05-22. Appendix B added in response to user request for the explicit
derivation. Pending user review of this written spec before invoking
`superpowers:writing-plans`.
