# Ladder species relative abundance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-species relative abundance to the ladder labeler — AUC of each ladder's snapped rungs (on the unscaled smoothed signal, with local-valley integration windows) as a fraction of total ladder AUC — plus a per-rung include/exclude affordance.

**Architecture:** Three new pure functions in `LadderLabelerCore` (`unscaleY`, `findValleyBounds`, `trapzAuc`), three stateful helpers in `LadderLabeler` (`computeLadderAuc`, `recomputeAbundances`, `toggleAucInclude`), called from existing mutation paths. New state: `state.threshold`, `state.scale`, `L.excludedZ`, `L.aucSum`, `L.isPartial`, `L.abundance`, `lb.auc`. UI: ladder card header gets `Abund. = XX.X%` + `(partial)` tag + `ΣAUC` footer + a chip row of per-rung toggles.

**Tech Stack:** Vanilla JS (`ladder_labeler.js`), Python build (`build_lcr_viewer.py`), browser-based test harness (`tests/ladder_labeler_test.html`).

**Spec:** `docs/superpowers/specs/2026-05-23-ladder-rung-abundance-design.md`

**Deviation from spec §5.3:** The spec assumed an existing per-rung table in the panel; there isn't one. Instead, this plan adds a compact chip row per ladder (`[✓3+] [✓4+] [✗5+] [✓6+] [✓7+]`) under the M readout. Same affordance, lower vertical cost, matches the existing panel density. Disabled/grayed for stale or unsnapped rungs.

---

## File Structure

| File | Responsibility | Touch type |
|---|---|---|
| `ladder_labeler.js` | All pure math + state mutations | Modify |
| `build_lcr_viewer.py` | `renderLadderPanel` UI; `recompute()` syncs `state.threshold` + `state.scale` | Modify |
| `tests/ladder_labeler_test.html` | Pure-math + state tests | Modify |
| `docs/superpowers/specs/2026-05-23-ladder-rung-abundance-design.md` | Spec amendment for chip-row UI | Modify (final task) |

---

## Task 0: Fix stale `Ladder A` assertion (baseline green)

**Files:**
- Modify: `tests/ladder_labeler_test.html:364-366`

- [ ] **Step 1: Open the test page in a browser to confirm 61 passed, 1 failed**

```bash
open "/Users/yidu/Library/CloudStorage/OneDrive-UniversityofMassachusetts/UMASS/Projects/PolyP/code/LCR-viewer/tests/ladder_labeler_test.html"
```

Expected: red banner `61 passed, 1 failed.` Failing line: `✗ annotations include a header summary line for ladder A`.

- [ ] **Step 2: Replace the stale assertion**

Edit `tests/ladder_labeler_test.html` lines 364-366:

```js
check('annotations carry ladder identity in hovertext',
      g.annotations.some(a => typeof a.hovertext === 'string'
                              && a.hovertext.indexOf('Ladder A') >= 0));
```

- [ ] **Step 3: Reload the test page**

Expected: green banner `62 passed, 0 failed.` (Old assertion replaced 1-for-1 with a passing one.)

- [ ] **Step 4: Commit**

```bash
cd "/Users/yidu/Library/CloudStorage/OneDrive-UniversityofMassachusetts/UMASS/Projects/PolyP/code/LCR-viewer"
git add tests/ladder_labeler_test.html
git commit -m "test(labeler): fix stale Ladder A header assertion

The M-summary annotation was moved to the side-panel ladder row
(commit 8239e4b, 'fix(labeler): move M readout from plot to
side-panel row'). The test assertion still expected an in-plot
'Ladder A' annotation. Updated to check hovertext, which still
carries ladder identity per rung."
```

---

## Task 1: `LadderLabelerCore.unscaleY`

**Files:**
- Modify: `ladder_labeler.js` (add inside the `LadderLabelerCore` IIFE, after `predictRung`)
- Test: `tests/ladder_labeler_test.html` (new test block at end of try-block, just before the existing `// ---------- Task 13 tests …` block)

- [ ] **Step 1: Write the failing tests**

Add to `tests/ladder_labeler_test.html` just before `// ---------- Task 13 tests` (line ~388):

```js
    // ---------- New: unscaleY ----------
    const UNS = LadderLabelerCore.unscaleY;
    check('unscaleY above threshold with scale=4 returns y/4',
          near(UNS(7000, 100, 6500, 4), 25, 1e-9),
          'got ' + UNS(7000, 100, 6500, 4));
    check('unscaleY below threshold returns y unchanged',
          UNS(3000, 100, 6500, 4) === 100);
    check('unscaleY at threshold uses the scaled branch (>= comparison)',
          near(UNS(6500, 100, 6500, 4), 25, 1e-9));
    check('unscaleY with scale=1 is a no-op everywhere',
          UNS(7000, 100, 6500, 1) === 100 && UNS(3000, 100, 6500, 1) === 100);
    check('unscaleY with scale=0 is a no-op (defensive)',
          UNS(7000, 100, 6500, 0) === 100);
```

- [ ] **Step 2: Reload test page to verify the 5 new tests fail**

Expected: `... LOAD ERROR` or `unscaleY is undefined` — 5 new failures.

- [ ] **Step 3: Implement `unscaleY` inside `LadderLabelerCore`**

Edit `ladder_labeler.js` — add after `predictRung` (before `solveFromTwoClicks`, around line 25):

```js
  // Unscale: divide y by scale when m/z is at or above the LCR scaling
  // threshold; otherwise return y unchanged. scale=1 (or 0, defensive)
  // is a no-op everywhere. Used so AUC integrates the pre-LCR-scale
  // signal regardless of whether the user has scaling toggled on.
  function unscaleY(mz, y, threshold, scale) {
    if (mz >= threshold && scale > 1) return y / scale;
    return y;
  }
```

And add `unscaleY` to the return object (around line 104):

```js
  return { M_H, computeM, predictRung, unscaleY, solveFromTwoClicks,
           snapToMaxInWindow, _stdDev, formatMass, formatSigma };
```

- [ ] **Step 4: Reload test page; verify 67 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add LadderLabelerCore.unscaleY

Divides y by scale above the LCR threshold; no-op below or when
scale <= 1. Foundation for AUC integration on the pre-scale
signal so abundances are not distorted by the LCR x-factor."
```

---

## Task 2: `LadderLabelerCore.findValleyBounds`

**Files:**
- Modify: `ladder_labeler.js` (add inside `LadderLabelerCore`)
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing tests**

Append to the same new test block in `tests/ladder_labeler_test.html`:

```js
    // ---------- New: findValleyBounds ----------
    const FVB = LadderLabelerCore.findValleyBounds;
    // Three-peak intensity array with valleys between them.
    // Indices:  0   1   2   3   4   5   6   7   8   9  10
    // y:        1   3   5   3   1   4   6   4   1   3   5
    //         peak1 apex=2, valley=4, peak2 apex=6, valley=8, peak3 apex=10
    const vX = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];
    const vY = [ 1,  3,  5,  3,  1,  4,  6,  4,  1,  3,  5];

    let vb = FVB(12, 10, 20, vX, vY);  // start at peak1 (idx 2)
    check('findValleyBounds at peak1 finds valleys [0, 4]',
          vb && vb.iLo === 0 && vb.iHi === 4,
          JSON.stringify(vb));

    vb = FVB(16, 10, 20, vX, vY);  // start at peak2 (idx 6)
    check('findValleyBounds at peak2 walks until valleys on both sides',
          vb && vb.iLo === 4 && vb.iHi === 8,
          JSON.stringify(vb));

    vb = FVB(16, 14.5, 17.5, vX, vY);  // tight cap
    check('findValleyBounds respects mzLoCap and mzHiCap',
          vb && vX[vb.iLo] >= 14.5 && vX[vb.iHi] <= 17.5,
          JSON.stringify(vb));

    check('findValleyBounds on empty spectrum returns null',
          FVB(100, 0, 200, [], []) === null);

    // mzObs falling between samples — uses nearest index
    vb = FVB(15.6, 10, 20, vX, vY);  // nearest is idx 6 (value 16)
    check('findValleyBounds snaps to nearest sample when mzObs is between',
          vb && vb.iLo === 4 && vb.iHi === 8,
          JSON.stringify(vb));
```

- [ ] **Step 2: Reload — verify 5 new failures (`findValleyBounds is not a function`)**

- [ ] **Step 3: Implement `findValleyBounds`**

Edit `ladder_labeler.js` — add inside `LadderLabelerCore` after `unscaleY`:

```js
  // Walk left and right from the sample nearest mzObs, stopping at the
  // first local minimum (point where intensity starts rising again) or
  // when m/z crosses the supplied cap. Returns inclusive index bounds
  // {iLo, iHi}, or null on an empty spectrum.
  // Assumes specX is ascending.
  function findValleyBounds(mzObs, mzLoCap, mzHiCap, specX, specY) {
    const n = specX.length;
    if (n === 0) return null;
    // Binary search for the sample nearest mzObs.
    let lo = 0, hi = n - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (specX[mid] < mzObs) lo = mid + 1; else hi = mid;
    }
    let i = lo;
    if (i > 0 && Math.abs(specX[i - 1] - mzObs) < Math.abs(specX[i] - mzObs)) {
      i = i - 1;
    }
    // Walk left: stop when next-left value is higher (we are rising again)
    // or m/z dips below mzLoCap.
    let iLo = i;
    while (iLo > 0 && specX[iLo - 1] >= mzLoCap && specY[iLo - 1] <= specY[iLo]) {
      iLo--;
    }
    // Walk right: mirror.
    let iHi = i;
    while (iHi < n - 1 && specX[iHi + 1] <= mzHiCap && specY[iHi + 1] <= specY[iHi]) {
      iHi++;
    }
    return { iLo, iHi };
  }
```

And add to the `LadderLabelerCore` return object:

```js
  return { M_H, computeM, predictRung, unscaleY, solveFromTwoClicks,
           snapToMaxInWindow, findValleyBounds, _stdDev, formatMass, formatSigma };
```

- [ ] **Step 4: Reload — verify 72 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add LadderLabelerCore.findValleyBounds

Walks left and right from the index nearest mzObs, stopping at the
first local minimum or when m/z crosses the supplied cap. Used to
pick AUC integration windows that adapt to peak width and never
overlap neighboring rungs."
```

---

## Task 3: `LadderLabelerCore.trapzAuc`

**Files:**
- Modify: `ladder_labeler.js`
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing tests**

Append to the new test block:

```js
    // ---------- New: trapzAuc ----------
    const TRZ = LadderLabelerCore.trapzAuc;
    const noUnscale = (mz, y) => y;

    // Triangle from (0,0) to (5,10) to (10,0) — closed-form area = 50.
    const trX = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const trY = [0, 2, 4, 6, 8, 10, 8, 6, 4, 2, 0];
    check('trapzAuc of a triangle matches closed-form 50',
          near(TRZ(0, 10, trX, trY, noUnscale), 50, 1e-9),
          'got ' + TRZ(0, 10, trX, trY, noUnscale));

    // Same triangle, with an unscale halving samples above mz=5
    const halfAbove5 = (mz, y) => (mz >= 5 ? y / 2 : y);
    // Left half (mz=0..5, area = 25) unchanged + right half (area = 25) halved → 25 + 12.5 = 37.5
    check('trapzAuc with unscale halving above threshold returns 37.5',
          near(TRZ(0, 10, trX, trY, halfAbove5), 37.5, 1e-9),
          'got ' + TRZ(0, 10, trX, trY, halfAbove5));

    check('trapzAuc with iLo === iHi returns 0',
          TRZ(5, 5, trX, trY, noUnscale) === 0);
```

- [ ] **Step 2: Reload — verify 3 new failures**

- [ ] **Step 3: Implement `trapzAuc`**

Add inside `LadderLabelerCore` after `findValleyBounds`:

```js
  // Trapezoidal integration of (specX, unscale(specX, specY)) over the
  // inclusive index range [iLo, iHi]. unscale(mz, y) is a closure (use
  // (_, y) => y for no unscale). Returns 0 if iLo === iHi.
  function trapzAuc(iLo, iHi, specX, specY, unscale) {
    let sum = 0;
    for (let i = iLo; i < iHi; i++) {
      const y0 = unscale(specX[i],     specY[i]);
      const y1 = unscale(specX[i + 1], specY[i + 1]);
      sum += 0.5 * (y0 + y1) * (specX[i + 1] - specX[i]);
    }
    return sum;
  }
```

Add to the `LadderLabelerCore` return:

```js
  return { M_H, computeM, predictRung, unscaleY, solveFromTwoClicks,
           snapToMaxInWindow, findValleyBounds, trapzAuc,
           _stdDev, formatMass, formatSigma };
```

- [ ] **Step 4: Reload — verify 75 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add LadderLabelerCore.trapzAuc

Trapezoidal integration over an inclusive index range with a
per-sample unscale closure. Foundation for per-rung AUC."
```

---

## Task 4: State additions — `state.threshold`, `state.scale`, `L.excludedZ`

**Files:**
- Modify: `ladder_labeler.js` (state object + `addLadderFromSeed`)
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing tests**

Append:

```js
    // ---------- New: state.threshold / state.scale defaults; L.excludedZ ----------
    check('state.threshold defaults to +Infinity',
          LadderLabeler.state.threshold === Infinity,
          'got ' + LadderLabeler.state.threshold);
    check('state.scale defaults to 1',
          LadderLabeler.state.scale === 1,
          'got ' + LadderLabeler.state.scale);

    resetLabelerState();
    const specE = makeLadderSpectrum();
    LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, specE.X, specE.Y);
    const Le = LadderLabeler.state.ladders[0];
    check('new ladder has empty L.excludedZ Set',
          Le.excludedZ instanceof Set && Le.excludedZ.size === 0);
```

- [ ] **Step 2: Reload — verify 3 new failures**

- [ ] **Step 3: Add the state defaults and initialize `excludedZ` per ladder**

Edit `ladder_labeler.js` — extend the `state` object (around line 118-126):

```js
  const state = {
    enabled: false,
    tolMz: 5.0,
    sigmaAmberRelative: 0.01,
    threshold: Infinity,      // m/z at/above which intensity is LCR-scaled
    scale: 1,                 // multiplier the viewer applied above threshold
    ladders: [],
    activeLadderId: null,
    pendingMode: null,
    twoClickBuffer: null,
  };
```

Edit `addLadderFromSeed` (around line 146-163) to add `excludedZ: new Set()` and the new ladder fields:

```js
    const ladder = {
      id: _nextId(),
      color: _nextColor(),
      seed: { mz, z },
      M: C.computeM(z, mz),
      sigmaM: 0,
      labels: [],
      excludedZ: new Set(),
      aucSum: 0,
      isPartial: false,
      abundance: null,
    };
```

- [ ] **Step 4: Reload — verify 78 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add threshold/scale state and per-ladder excludedZ

state.threshold / state.scale capture the viewer's LCR scaling so
the labeler can integrate on the unscaled signal. L.excludedZ holds
per-ladder user choices about which rungs participate in AUC."
```

---

## Task 5: `LadderLabeler.computeLadderAuc`

**Files:**
- Modify: `ladder_labeler.js` (add inside the `LadderLabeler` IIFE)
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing tests**

Append:

```js
    // ---------- New: computeLadderAuc ----------
    // 3-rung ladder: peaks of equal Gaussian width at z=7,6,5 of M=26391.94.
    // We construct the spectrum so the integrated AUCs are in ratio 1:2:1
    // by giving the middle peak amplitude 2 and the others amplitude 1.
    function makeRatioSpectrum() {
      const X = [], Y = [];
      // z=7 → m/z=3771.28, z=6 → m/z=4399.66, z=5 → m/z=5279.40
      const peaks = [
        { mz: 3771.28, amp: 1 },
        { mz: 4399.66, amp: 2 },
        { mz: 5279.40, amp: 1 },
      ];
      for (let mz = 3500; mz <= 5800; mz += 0.5) {
        X.push(mz);
        let y = 0;
        for (const p of peaks) y += p.amp * Math.exp(-Math.pow((mz - p.mz) / 2.0, 2));
        Y.push(y);
      }
      return { X, Y };
    }

    resetLabelerState();
    const specR = makeRatioSpectrum();
    LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, specR.X, specR.Y);
    const Lr = LadderLabeler.state.ladders[0];
    LadderLabeler.computeLadderAuc(Lr, specR.X, specR.Y);

    const z7 = Lr.labels.find(lb => lb.z === 7);
    const z6 = Lr.labels.find(lb => lb.z === 6);
    const z5 = Lr.labels.find(lb => lb.z === 5);
    check('computeLadderAuc assigns lb.auc on snapped rungs',
          typeof z7.auc === 'number' && z7.auc > 0
          && typeof z6.auc === 'number' && z6.auc > 0
          && typeof z5.auc === 'number' && z5.auc > 0);
    check('per-rung AUC ratio is approximately 1:2:1',
          near(z6.auc / z7.auc, 2.0, 0.05) && near(z6.auc / z5.auc, 2.0, 0.05),
          'z7=' + z7.auc + ' z6=' + z6.auc + ' z5=' + z5.auc);
    check('L.aucSum sums the included AUCs',
          near(Lr.aucSum, z7.auc + z6.auc + z5.auc
                          + (Lr.labels.filter(lb => lb.auc > 0 && lb.z !== 7 && lb.z !== 6 && lb.z !== 5)
                                       .reduce((s, lb) => s + lb.auc, 0)),
               1e-6));

    // isPartial when a rung is unsnapped (z=1 in the standard ladder spectrum
    // falls outside the 3500..5800 range used by makeRatioSpectrum).
    check('isPartial=true when some candidate rung is unsnapped',
          Lr.isPartial === true);

    // Excluded rung is omitted from aucSum and marks isPartial true.
    const sumWithAll = Lr.aucSum;
    Lr.excludedZ.add(6);
    LadderLabeler.computeLadderAuc(Lr, specR.X, specR.Y);
    check('excluding a rung drops aucSum by exactly that rung auc',
          near(Lr.aucSum, sumWithAll - z6.auc, 1e-6),
          'sumWithAll=' + sumWithAll + ' aucSum=' + Lr.aucSum + ' z6.auc=' + z6.auc);
    check('excluding a rung sets isPartial=true',
          Lr.isPartial === true);

    // Un-exclude → aucSum restored.
    Lr.excludedZ.delete(6);
    LadderLabeler.computeLadderAuc(Lr, specR.X, specR.Y);
    check('un-excluding restores aucSum',
          near(Lr.aucSum, sumWithAll, 1e-6));

    // Unscaling: above threshold the integration uses y/scale.
    LadderLabeler.state.threshold = 4000;
    LadderLabeler.state.scale = 2;
    LadderLabeler.computeLadderAuc(Lr, specR.X, specR.Y);
    // z=7 (m/z≈3771) is below threshold → auc unchanged.
    // z=6 (m/z≈4400) and z=5 (m/z≈5279) are above → auc halved.
    const z7_a = Lr.labels.find(lb => lb.z === 7).auc;
    const z6_a = Lr.labels.find(lb => lb.z === 6).auc;
    check('unscale leaves below-threshold AUC unchanged',
          near(z7_a, z7.auc, 1e-6));
    check('unscale halves above-threshold AUC',
          near(z6_a, z6.auc / 2, 1e-3),
          'z6.auc=' + z6.auc + ' halved=' + (z6.auc / 2) + ' got=' + z6_a);
    // Reset state for later tests.
    LadderLabeler.state.threshold = Infinity;
    LadderLabeler.state.scale = 1;
```

- [ ] **Step 2: Reload — verify ~8 new failures (`computeLadderAuc is not a function`)**

- [ ] **Step 3: Implement `computeLadderAuc`**

Edit `ladder_labeler.js` — add inside the `LadderLabeler` IIFE, between `refreshLadder` and `addLadderFromTwoClicks` (around line 198):

```js
  // Per-rung AUC over local-valley windows, summed (over included,
  // snapped rungs) into L.aucSum. Per-rung values stored on lb.auc
  // (including excluded rungs, so toggleAucInclude is instant).
  // Reads state.threshold / state.scale for the unscale closure.
  // L.isPartial true iff any candidate rung is unsnapped, stale, or in
  // L.excludedZ. Does NOT touch L.abundance — that's recomputeAbundances.
  function computeLadderAuc(L, specX, specY) {
    const thr = state.threshold;
    const sc = state.scale;
    const unscale = (mz, y) => C.unscaleY(mz, y, thr, sc);

    // Sort snapped labels by mzObs for neighbor-midpoint caps.
    const snapped = L.labels
      .filter(lb => lb.mzObs !== null)
      .slice()
      .sort((a, b) => a.mzObs - b.mzObs);

    // Reset auc on every label first (stale/unsnapped stay null).
    for (const lb of L.labels) lb.auc = (lb.mzObs === null) ? null : 0;

    let sum = 0;
    for (let i = 0; i < snapped.length; i++) {
      const lb = snapped[i];
      const prev = snapped[i - 1];
      const next = snapped[i + 1];
      const mzLoCap = prev ? 0.5 * (prev.mzObs + lb.mzObs) : (lb.mzObs - state.tolMz);
      const mzHiCap = next ? 0.5 * (lb.mzObs + next.mzObs) : (lb.mzObs + state.tolMz);
      const vb = C.findValleyBounds(lb.mzObs, mzLoCap, mzHiCap, specX, specY);
      if (vb === null) { lb.auc = 0; continue; }
      const auc = C.trapzAuc(vb.iLo, vb.iHi, specX, specY, unscale);
      lb.auc = auc;
      if (!lb.stale && !L.excludedZ.has(lb.z)) sum += auc;
    }
    L.aucSum = sum;
    L.isPartial = L.labels.some(lb =>
      lb.mzObs === null || lb.stale || L.excludedZ.has(lb.z));
  }
```

Add to the `LadderLabeler` return object (around line 381):

```js
  return {
    state,
    _resetIdCounter,
    _candidateRungs,
    _yAt,
    addLadderFromSeed,
    addLadderFromTwoClicks,
    removeLadder,
    setActive,
    refreshLadder,
    refreshAll,
    computeLadderAuc,
    buildAnnotations,
    handlePlotClick,
  };
```

- [ ] **Step 4: Reload — verify 86 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add computeLadderAuc

Per-rung AUC over local-valley windows (capped by neighbor
midpoints), integrated on the unscaled signal. Sums included
snapped rungs into L.aucSum; sets L.isPartial when any rung is
unsnapped, stale, or excluded."
```

---

## Task 6: `LadderLabeler.recomputeAbundances`

**Files:**
- Modify: `ladder_labeler.js`
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing tests**

Append:

```js
    // ---------- New: recomputeAbundances ----------
    resetLabelerState();
    // Two synthetic ladders, manually constructed with known aucSum.
    LadderLabeler.state.ladders.push({
      id: 'A', color: '#1f77b4', seed: { mz: 1000, z: 5 }, M: 5000, sigmaM: 0,
      labels: [], excludedZ: new Set(),
      aucSum: 75, isPartial: false, abundance: null,
    });
    LadderLabeler.state.ladders.push({
      id: 'B', color: '#ff7f0e', seed: { mz: 1500, z: 4 }, M: 6000, sigmaM: 0,
      labels: [], excludedZ: new Set(),
      aucSum: 25, isPartial: false, abundance: null,
    });
    LadderLabeler.recomputeAbundances();
    check('recomputeAbundances 3:1 → 0.75/0.25',
          near(LadderLabeler.state.ladders[0].abundance, 0.75, 1e-9)
          && near(LadderLabeler.state.ladders[1].abundance, 0.25, 1e-9),
          'A=' + LadderLabeler.state.ladders[0].abundance
          + ' B=' + LadderLabeler.state.ladders[1].abundance);

    LadderLabeler.state.ladders[0].aucSum = 0;
    LadderLabeler.state.ladders[1].aucSum = 0;
    LadderLabeler.recomputeAbundances();
    check('recomputeAbundances with total=0 → all abundance=null',
          LadderLabeler.state.ladders[0].abundance === null
          && LadderLabeler.state.ladders[1].abundance === null);

    LadderLabeler.state.ladders.length = 1;
    LadderLabeler.state.ladders[0].aucSum = 42;
    LadderLabeler.recomputeAbundances();
    check('recomputeAbundances single ladder → abundance=1.0',
          LadderLabeler.state.ladders[0].abundance === 1.0);
```

- [ ] **Step 2: Reload — verify 3 new failures**

- [ ] **Step 3: Implement `recomputeAbundances`**

Add inside `LadderLabeler` IIFE (next to `computeLadderAuc`):

```js
  // Cross-ladder normalization. Assigns L.abundance = L.aucSum / total
  // for each ladder. total === 0 → all abundance = null. Cheap; runs
  // once after any per-ladder aucSum change.
  function recomputeAbundances() {
    let total = 0;
    for (const L of state.ladders) total += (L.aucSum || 0);
    for (const L of state.ladders) {
      L.abundance = (total > 0) ? ((L.aucSum || 0) / total) : null;
    }
  }
```

Add `recomputeAbundances` to the `LadderLabeler` return:

```js
    computeLadderAuc,
    recomputeAbundances,
    buildAnnotations,
```

- [ ] **Step 4: Reload — verify 89 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add recomputeAbundances

Cross-ladder normalization: each L.abundance = L.aucSum / total.
total=0 → all null. Called after any aucSum change."
```

---

## Task 7: Wire AUC into `refreshLadder` and `removeLadder`

**Files:**
- Modify: `ladder_labeler.js` (extend `refreshLadder`, `removeLadder`)
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing tests**

Append:

```js
    // ---------- New: refreshLadder / removeLadder wiring ----------
    resetLabelerState();
    const specW = makeLadderSpectrum();
    LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, specW.X, specW.Y);
    check('addLadderFromSeed populates aucSum > 0 via refreshLadder',
          LadderLabeler.state.ladders[0].aucSum > 0,
          'aucSum=' + LadderLabeler.state.ladders[0].aucSum);
    check('single ladder gets abundance=1.0 after add',
          LadderLabeler.state.ladders[0].abundance === 1.0);

    // Add a 2nd ladder; first ladder's abundance must drop below 1.0.
    addSecondLadderPeaks(specW.X, specW.Y);
    LadderLabeler.addLadderFromSeed({ mz: 3302.5, z: 16 }, specW.X, specW.Y);
    LadderLabeler.refreshLadder('A', specW.X, specW.Y);  // re-snap A on the updated spectrum
    check('adding a 2nd ladder drops first ladder abundance below 1.0',
          LadderLabeler.state.ladders[0].abundance < 1.0
          && LadderLabeler.state.ladders[0].abundance > 0,
          'A.abundance=' + LadderLabeler.state.ladders[0].abundance);
    check('two ladders abundance sums to 1.0',
          near(LadderLabeler.state.ladders[0].abundance
               + LadderLabeler.state.ladders[1].abundance, 1.0, 1e-9));

    // Remove ladder B → A's abundance returns to 1.0.
    LadderLabeler.removeLadder('B');
    check('removing a ladder rebalances remaining abundance to 1.0',
          LadderLabeler.state.ladders[0].abundance === 1.0);
```

- [ ] **Step 2: Reload — verify 4 new failures (`aucSum` is 0 because refreshLadder doesn't call computeLadderAuc yet)**

- [ ] **Step 3: Wire `computeLadderAuc` and `recomputeAbundances` into `refreshLadder`**

Edit `ladder_labeler.js` — at the end of `refreshLadder` (after the `L.sigmaM = C._stdDev(implied);` line, around line 196):

```js
    L.sigmaM = C._stdDev(implied);
    computeLadderAuc(L, specX, specY);
    recomputeAbundances();
  }
```

Edit `removeLadder` (around line 208-215) to call `recomputeAbundances()`:

```js
  function removeLadder(id) {
    const idx = state.ladders.findIndex(L => L.id === id);
    if (idx < 0) return;
    state.ladders.splice(idx, 1);
    if (state.activeLadderId === id) {
      state.activeLadderId = state.ladders.length ? state.ladders[0].id : null;
    }
    recomputeAbundances();
  }
```

- [ ] **Step 4: Reload — verify 93 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): wire AUC + abundances into refreshLadder/removeLadder

refreshLadder now computes per-rung AUCs and re-normalizes
abundances across all ladders at the end. removeLadder triggers a
recompute so denominators stay consistent."
```

---

## Task 8: `LadderLabeler.toggleAucInclude`

**Files:**
- Modify: `ladder_labeler.js`
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing tests**

Append:

```js
    // ---------- New: toggleAucInclude ----------
    resetLabelerState();
    const specT = makeLadderSpectrum();
    LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, specT.X, specT.Y);
    const Lt = LadderLabeler.state.ladders[0];
    const sumFull = Lt.aucSum;
    const z6lb = Lt.labels.find(lb => lb.z === 6);
    const z6auc = z6lb.auc;

    const r1 = LadderLabeler.toggleAucInclude('A', 6);
    check('toggleAucInclude returns {id, z, included:false} on exclude',
          r1 && r1.id === 'A' && r1.z === 6 && r1.included === false,
          JSON.stringify(r1));
    check('toggleAucInclude exclude drops aucSum by exactly the rung auc',
          near(Lt.aucSum, sumFull - z6auc, 1e-6),
          'sumFull=' + sumFull + ' aucSum=' + Lt.aucSum + ' z6auc=' + z6auc);
    check('toggleAucInclude exclude sets isPartial=true',
          Lt.isPartial === true);

    const r2 = LadderLabeler.toggleAucInclude('A', 6);
    check('toggleAucInclude returns {included:true} on re-include',
          r2 && r2.included === true);
    check('toggleAucInclude re-include restores aucSum',
          near(Lt.aucSum, sumFull, 1e-6));

    // excludedZ survives refreshLadder
    LadderLabeler.toggleAucInclude('A', 6);  // exclude again
    const sumAfterExclude = Lt.aucSum;
    LadderLabeler.refreshLadder('A', specT.X, specT.Y);
    check('excludedZ survives refreshLadder',
          Lt.excludedZ.has(6) && near(Lt.aucSum, sumAfterExclude, 1e-6));

    // Unknown ladder id is a no-op (returns undefined or {error}).
    const r3 = LadderLabeler.toggleAucInclude('ZZZ', 6);
    check('toggleAucInclude on unknown id returns null/error',
          r3 === undefined || r3 === null || (r3 && r3.error),
          JSON.stringify(r3));
```

- [ ] **Step 2: Reload — verify 7 new failures**

- [ ] **Step 3: Implement `toggleAucInclude`**

Add inside `LadderLabeler` IIFE (next to `recomputeAbundances`):

```js
  // Toggle whether the rung at z is included in L.aucSum. Re-sums from
  // stored per-rung lb.auc values — no re-integration. Triggers
  // recomputeAbundances() so cross-ladder fractions stay consistent.
  // Returns { id, z, included } so the caller can update its UI; null
  // if the ladder id is unknown.
  function toggleAucInclude(id, z) {
    const L = state.ladders.find(x => x.id === id);
    if (!L) return null;
    if (L.excludedZ.has(z)) L.excludedZ.delete(z);
    else L.excludedZ.add(z);
    // Re-sum from stored auc values.
    let sum = 0;
    for (const lb of L.labels) {
      if (lb.mzObs === null || lb.stale) continue;
      if (L.excludedZ.has(lb.z)) continue;
      sum += (lb.auc || 0);
    }
    L.aucSum = sum;
    L.isPartial = L.labels.some(lb =>
      lb.mzObs === null || lb.stale || L.excludedZ.has(lb.z));
    recomputeAbundances();
    return { id, z, included: !L.excludedZ.has(z) };
  }
```

Add `toggleAucInclude` to the return object.

- [ ] **Step 4: Reload — verify 100 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add toggleAucInclude(id, z)

Single entry point for both the panel chip and the plot-click 'x'
shortcut. Flips z in L.excludedZ, re-sums from stored per-rung
AUCs (no re-integration), and re-runs recomputeAbundances."
```

---

## Task 9: Extend `handlePlotClick` with `x` shortcut

**Files:**
- Modify: `ladder_labeler.js` (`handlePlotClick` prompt-response parsing)
- Test: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing test**

Append:

```js
    // ---------- New: handlePlotClick 'x' toggles excludedZ ----------
    resetLabelerState();
    LadderLabeler.state.enabled = true;
    const specC = makeLadderSpectrum();
    LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, specC.X, specC.Y);
    LadderLabeler.setActive('A');
    // Stub window.prompt to return 'x' once.
    const _origPrompt = window.prompt;
    let promptCalled = 0;
    window.prompt = () => { promptCalled++; return 'x'; };
    // Click near the z=6 rung (predicted m/z ≈ 4399.66).
    LadderLabeler.handlePlotClick(4400, specC.X, specC.Y);
    window.prompt = _origPrompt;
    check('handlePlotClick x prompt was issued once',
          promptCalled === 1);
    const Lc = LadderLabeler.state.ladders[0];
    check('handlePlotClick x adds z=6 to excludedZ',
          Lc.excludedZ.has(6),
          'excludedZ=' + JSON.stringify([...Lc.excludedZ]));
```

- [ ] **Step 2: Reload — verify 2 new failures (`x` falls through to "unrecognized")**

- [ ] **Step 3: Add the `x` branch to `handlePlotClick`**

Edit `ladder_labeler.js` — in `handlePlotClick`, inside the existing-label branch (around line 325-349). After the `ans === ''` branch and before the integer-parsing branch:

```js
          if (ans === null) return;     // user cancelled
          if (ans === '') {
            L.labels = L.labels.filter(x => x !== lb);
            return;
          }
          if (/^x$/i.test(ans)) {
            toggleAucInclude(L.id, lb.z);
            return;
          }
          const seedFlag = /s$/i.test(ans);
```

Update the prompt text at line ~327 so users know the option exists:

```js
          const ans = prompt(
            'Edit label at m/z=' + lb.mzObs.toFixed(2) + ' (ladder ' + L.id + ').\n'
            + 'Enter integer to override z, integer+s to set as new seed,'
            + ' x to toggle AUC include, empty to delete.', String(lb.z));
```

- [ ] **Step 4: Reload — verify 102 passed, 0 failed**

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add 'x' shortcut to handlePlotClick

Typing 'x' in the edit prompt toggles whether the clicked rung is
counted in the ladder's AUC. Shares toggleAucInclude with the
panel chip-row UI."
```

---

## Task 10: Render abundance + chip row in `renderLadderPanel`

**Files:**
- Modify: `build_lcr_viewer.py` (`renderLadderPanel` around line 1141-1227)
- Manual test: build a viewer, open in browser

- [ ] **Step 1: Inspect current `renderLadderPanel`**

Read `build_lcr_viewer.py:1141-1227`. The ladder card currently has two lines: a header row with seed inputs and a `foundCount/totalCount rungs` indicator, and an M-readout line below.

- [ ] **Step 2: Add the abundance fragment to the M-readout line**

In `build_lcr_viewer.py`, edit the section that builds `mTxt` (around line 1161-1163):

```python
                    "    const mTxt = 'M = ' + LadderLabelerCore.formatMass(L.M, L.sigmaM)\n"
                    "               + '  ' + LadderLabelerCore.formatSigma(L.M, L.sigmaM)\n"
                    "               + (amber ? '  — check assignments' : '');\n"
                    "    const abTxt = (L.abundance === null) ? 'Abund. = —'\n"
                    "                  : ('Abund. = ' + (L.abundance * 100).toFixed(1) + '%'\n"
                    "                     + (L.isPartial ? ' (partial)' : ''));\n"
                    "    const sumTxt = (L.aucSum === 0) ? 'ΣAUC = —'\n"
                    "                   : 'ΣAUC = ' + L.aucSum.toExponential(1);\n"
```

(Adjust the surrounding Python-string concatenation to match the existing style — the JS is embedded in a Python multi-line string.)

- [ ] **Step 3: Render the abundance text alongside the M readout and add a small ΣAUC footer plus the chip row**

Find the JS fragment that emits `+ '<div style="padding:1px 0 2px 22px;font-size:11px;color:'` (around line 1182) and extend it:

```
+ '<div style="padding:1px 0 2px 22px;font-size:11px;color:'
+ mColor + '">' + mTxt
+ '  <span style="color:#444">· </span><span style="color:#444">' + abTxt + '</span>'
+ '</div>'
+ '<div style="padding:0 0 2px 22px;font-size:10px;color:#888">'
+ sumTxt + '</div>'
+ '<div data-ladder="' + L.id + '" '
+ 'style="padding:0 0 4px 22px;display:flex;flex-wrap:wrap;gap:3px">'
+ chipsFor(L)
+ '</div>'
```

Add a `chipsFor` helper just above the `html += '<div …'` loop (around line 1163):

```js
    function chipsFor(L) {
      // sort labels by descending z so chips read 7+, 6+, 5+, …
      const sorted = L.labels.slice().sort((a, b) => b.z - a.z);
      let out = '';
      for (const lb of sorted) {
        const live = lb.mzObs !== null && !lb.stale;
        const included = !L.excludedZ.has(lb.z);
        const mark = !live ? '—' : (included ? '✓' : '✗');
        const bg = !live ? '#eee' : (included ? '#d6e9f8' : '#f8dada');
        const fg = !live ? '#bbb' : (included ? '#1a4a7a' : '#7a1a1a');
        const cur = !live ? 'default' : 'pointer';
        out += '<span class="auc-chip" data-ladder="' + L.id + '" data-z="' + lb.z
            + '" style="font-size:10px;padding:1px 4px;border-radius:3px;'
            + 'background:' + bg + ';color:' + fg + ';cursor:' + cur
            + ';user-select:none">' + mark + lb.z + '+</span>';
      }
      return out;
    }
```

- [ ] **Step 4: Wire chip clicks to `toggleAucInclude`**

Below the existing `querySelectorAll('button[data-action="remove"]')` block (around line 1221), add:

```js
    list.querySelectorAll('span.auc-chip').forEach(el => {
      // Only live chips are clickable.
      if (el.style.cursor !== 'pointer') return;
      el.addEventListener('click', () => {
        LadderLabeler.toggleAucInclude(el.dataset.ladder, parseInt(el.dataset.z, 10));
        renderLadderPanel();
      });
    });
```

- [ ] **Step 5: Rebuild the viewer on the user's test spectrum and open it**

```bash
cd "/Users/yidu/Library/CloudStorage/OneDrive-UniversityofMassachusetts/UMASS/Projects/PolyP/code/LCR-viewer"
python3 build_lcr_viewer.py "/Users/yidu/Library/CloudStorage/OneDrive-UniversityofMassachusetts/UMASS/Projects/PolyP/results/LCR/polyP/polyP_MS1.xy"
open output/LCR/polyP/LCR_mz1_*.html
```

Manual checks:
- Enable the labeler, add a ladder via "+ Type seed".
- Ladder card header shows `M = …  Abund. = 100.0%` and a `ΣAUC = …e…` footer.
- A chip row appears under the M line with `✓` chips for each snapped rung; chips for unsnapped rungs read `—z+` and are grayed.
- Clicking a chip toggles `✓ ↔ ✗`; the abundance number updates.
- Add a second ladder; abundances now split (e.g. `72.3%` / `27.7%`) and sum to 100%.

- [ ] **Step 6: Commit**

```bash
git add build_lcr_viewer.py
git commit -m "feat(viewer): render abundance + AUC chip row in ladder panel

Adds 'Abund. = XX.X%' (with optional '(partial)' tag) and a ΣAUC
footer to each ladder card, plus a horizontal chip row for
per-rung include/exclude toggles. Live chips call
LadderLabeler.toggleAucInclude; disabled chips render gray for
unsnapped/stale rungs."
```

---

## Task 11: Sync `state.threshold` and `state.scale` from `recompute()`

**Files:**
- Modify: `build_lcr_viewer.py` (`recompute()` around line 868-929)

- [ ] **Step 1: Read the current `recompute()` body**

Confirm that `scaleOn`, `factor`, and `thr` are computed at the top of `recompute()` and that `LadderLabeler.refreshAll(PROC_X, PROC_Y)` runs near the bottom (line ~918).

- [ ] **Step 2: Set labeler state before `refreshAll`**

Edit `build_lcr_viewer.py` — in `recompute()`, just before the `if (typeof LadderLabeler !== 'undefined')` block (around line 917):

```js
 // Merge ladder-label shapes/annotations from the LadderLabeler module
 // (spec §5.2, §5.4). When disabled, this returns empty arrays so the
 // existing MS1 layout is bit-identical to before.
 if (typeof LadderLabeler !== 'undefined') {
   // Sync the LCR scale/threshold so AUC integrates the unscaled signal.
   LadderLabeler.state.threshold = scaleOn ? thr : Infinity;
   LadderLabeler.state.scale = scaleOn ? factor : 1;
   LadderLabeler.refreshAll(PROC_X, PROC_Y);
```

- [ ] **Step 3: Rebuild and verify in the browser**

```bash
python3 build_lcr_viewer.py "/Users/yidu/Library/CloudStorage/OneDrive-UniversityofMassachusetts/UMASS/Projects/PolyP/results/LCR/polyP/polyP_MS1.xy"
open output/LCR/polyP/LCR_mz1_*.html
```

Manual checks:
- Add a ladder that has at least one rung above the threshold.
- Toggle **Scale charge-reduced region** off → abundance/ΣAUC values change (no unscale applied below; above-threshold rungs no longer divided).
- Toggle back on → values return to the unscaled-based numbers.
- Drag the threshold past a rung and verify aucSum updates on the next recompute.

- [ ] **Step 4: Commit**

```bash
git add build_lcr_viewer.py
git commit -m "feat(viewer): sync LCR scale/threshold into LadderLabeler.state

recompute() now pushes scaleOn/factor/thr to state.scale and
state.threshold before refreshAll, so AUC integration sees the
pre-scale signal whether the user has scaling on or off."
```

---

## Task 12: Amend the spec to record the chip-row deviation

**Files:**
- Modify: `docs/superpowers/specs/2026-05-23-ladder-rung-abundance-design.md` (§5.3)

- [ ] **Step 1: Update §5.3 to match the implementation**

Replace §5.3's current "Rung table — AUC include column" with:

```markdown
### 5.3 Per-rung chip row

The current panel does not have a per-rung table. Instead, each ladder
card carries a compact horizontal chip row under its M readout, one chip
per candidate rung:

`[✓7+] [✓6+] [✗5+] [✓4+] [—3+] [—2+] [—1+]`

- `✓` chip (light blue) — rung is snapped and included in AUC. Clicking
  excludes it.
- `✗` chip (light red) — rung is snapped but excluded. Clicking re-includes.
- `—` chip (gray, disabled) — rung is unsnapped or stale. Not clickable.

Live-chip clicks call `LadderLabeler.toggleAucInclude(id, z)`. The chip
row is rebuilt by `renderLadderPanel` on each labeler state change.
```

- [ ] **Step 2: Commit the spec amendment**

```bash
git add docs/superpowers/specs/2026-05-23-ladder-rung-abundance-design.md
git commit -m "docs(labeler): spec §5.3 amended to chip row

The original spec assumed a per-rung table existed in the panel.
It did not; the panel carried only seed inputs and the M readout.
Implemented as a compact chip row instead — same affordance, much
lower vertical cost, matches the existing panel density."
```

---

## Task 13: Existing Python tests still pass

**Files:**
- Run: `tests/test_build_lcr_viewer.py`, `tests/test_ladder_labeler.py`

- [ ] **Step 1: Run the Python test suite**

```bash
cd "/Users/yidu/Library/CloudStorage/OneDrive-UniversityofMassachusetts/UMASS/Projects/PolyP/code/LCR-viewer"
python3 -m unittest discover -s tests -v
```

Expected: all tests pass. None of the AUC work changes the smoothing pipeline, sibling-CSV writer, or threshold heuristic, so existing tests should be unaffected. If any fail, debug before declaring done.

- [ ] **Step 2: Confirm the JS test harness ends green**

Reload `tests/ladder_labeler_test.html` in the browser. Expected: `102 passed, 0 failed.`

- [ ] **Step 3: No commit needed** (verification only)

---

## Done criteria

- `tests/ladder_labeler_test.html` shows `102 passed, 0 failed.`
- `python3 -m unittest discover -s tests -v` passes.
- A built viewer on `polyP_MS1.xy` shows per-ladder `Abund.`, a `ΣAUC` footer, and a clickable chip row; toggling `Scale charge-reduced region` updates abundances; clicking a chip toggles its include state and rebalances abundances.
- Branch `feat/ladder-labeling` carries: Task 0 (test fix), Tasks 1–9 (JS), Tasks 10–11 (Python wiring), Task 12 (spec amendment).
