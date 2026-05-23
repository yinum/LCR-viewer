# LCR ladder labeling — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained, opt-in ladder-labeling module to the existing
`polyP_LCR_viewer.html` so native-MS LCR spectra can be annotated with
charge state, observed m/z, and back-calculated neutral mass per ladder.
Supports multiple interleaved ladders, typed-z₀ seeding, two-click
closed-form solving, and per-peak manual override.

**Architecture:** Pure-JS module (`ladder_labeler.js`) inlined into the
viewer HTML at build time (same pattern as `plotly-basic.min.js`).
Math-only functions are testable in a standalone browser page.
The Python builder adds one new preset block (`ladder_labels`) and one
new template placeholder (`__LADDER_LABELER__`). MS1 workflow is
bit-identical when the labeler is disabled (default).

**Tech Stack:** Python 3 stdlib (unittest); vanilla JS (no Node); Plotly
(already vendored); browser `prompt()` for manual z input in v1.

**Reference spec:** `docs/superpowers/specs/2026-05-22-ladder-labeling-design.md`

---

## File map

| Path | Action | Responsibility |
|---|---|---|
| `ladder_labeler.js` | **create** | Pure-JS labeler: math + state + Plotly integration. ~300 LOC. |
| `tests/ladder_labeler_test.html` | **create** | Browser-run test page for the pure math (`computeM`, `predictRung`, `solveFromTwoClicks`, `snapToMaxInWindow`, ladder management). |
| `tests/test_ladder_labeler.py` | **create** | Python unittests for preset wiring + build-time substitution of `__LADDER_LABELER__`. |
| `build_lcr_viewer.py` | modify | `PRESET` gets `ladder_labels` block; `load_preset` does nested merge; `TEMPLATE` gets control panel + new `__LADDER_LABELER__` placeholder; `build_html` substitutes labeler JS; `main` reads `ladder_labeler.js` next to the script. |
| `.gitignore` | modify | Add `!tests/*.html` exception so the test page can be checked in despite the project-wide `*.html` ignore. |
| `README.md` | modify | New "Labeling the LCR ladder" section + caveat that z₀ is a math anchor, not a peak claim. |
| `AGENTS.md` | modify | New "How it works" bullet for the labeler module. |

---

## Task 1: Preset wiring — Python side

**Files:**
- Modify: `build_lcr_viewer.py:38-66` (`PRESET` dict and `load_preset`)
- Create: `tests/test_ladder_labeler.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add `.gitignore` exception for tests HTML**

Append to `.gitignore`:

```
# Test pages (allow the labeler test page; *.html is otherwise ignored)
!tests/*.html
```

- [ ] **Step 2: Write the failing Python test**

Create `tests/test_ladder_labeler.py`:

```python
"""Tests for the LCR ladder-labeling Python wiring (preset block,
load_preset nested merge, build-time substitution of __LADDER_LABELER__).
The labeler JS itself is tested by tests/ladder_labeler_test.html in a
browser; this suite covers only the Python build surface."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import build_lcr_viewer as B


class PresetBlockTests(unittest.TestCase):
    def test_preset_has_ladder_labels_block(self):
        self.assertIn("ladder_labels", B.PRESET)
        block = B.PRESET["ladder_labels"]
        self.assertEqual(block["enabled"], False)
        self.assertEqual(block["tol_mz"], 5.0)
        self.assertEqual(block["sigma_amber_relative"], 0.01)

    def test_load_preset_no_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            eff = B.load_preset(td)
            self.assertEqual(eff["ladder_labels"], B.PRESET["ladder_labels"])

    def test_load_preset_partial_merge_keeps_unspecified_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "preset.json"), "w") as fh:
                json.dump({"ladder_labels": {"enabled": True}}, fh)
            eff = B.load_preset(td)
            # 'enabled' came from saved; tol_mz and sigma_amber_relative stay default
            self.assertEqual(eff["ladder_labels"]["enabled"], True)
            self.assertEqual(eff["ladder_labels"]["tol_mz"], 5.0)
            self.assertEqual(eff["ladder_labels"]["sigma_amber_relative"], 0.01)

    def test_load_preset_full_override(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "preset.json"), "w") as fh:
                json.dump({"ladder_labels": {
                    "enabled": True, "tol_mz": 8.0, "sigma_amber_relative": 0.02
                }}, fh)
            eff = B.load_preset(td)
            self.assertEqual(eff["ladder_labels"]["enabled"], True)
            self.assertEqual(eff["ladder_labels"]["tol_mz"], 8.0)
            self.assertEqual(eff["ladder_labels"]["sigma_amber_relative"], 0.02)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run from `code/LCR-viewer/`:

```bash
python3 -m unittest tests.test_ladder_labeler -v
```

Expected: FAIL — `KeyError: 'ladder_labels'` or `AssertionError`.

- [ ] **Step 4: Add `ladder_labels` to `PRESET` and update `load_preset`**

In `build_lcr_viewer.py`, replace the `PRESET = { … }` block (lines 38–47) with:

```python
PRESET = {
    "scale_on": True,       # apply the charge-reduced x factor at all; turn off
                            # for plain MS1 smoothing (everything stays x1, and
                            # the threshold line/annotation are hidden)
    "scale": 10,            # charge-reduced x factor (used only when scale_on)
    "method": "avg",        # smoothing method (adjacent averaging)
    "width_mz": 0.04,       # smoothing width in m/z
    "poly": 3,              # SG poly order, retained for the SG control
    "show_overlay": False,  # pre-smoothing overlay checkbox default
    # Ladder-labeling block — opt-in module documented in
    # docs/superpowers/specs/2026-05-22-ladder-labeling-design.md
    "ladder_labels": {
        "enabled": False,           # module default off; turn on via panel checkbox
        "tol_mz": 5.0,              # snap window half-width (m/z); native-MS broad peaks
        "sigma_amber_relative": 0.01,  # amber if sigma_M / M > this
    },
}
```

Then replace the `load_preset` function body (lines 49–66) with:

```python
def load_preset(here):
    """Effective preset: the built-in PRESET overlaid with preset.json, if a
    readable one sits next to the script. preset.json is written by the
    viewer's Save preset button; only keys also present in PRESET are taken.
    The 'ladder_labels' value is a nested dict; we merge it key-by-key so a
    partial saved block does not drop the other defaults."""
    eff = dict(PRESET)
    path = os.path.join(here, "preset.json")
    if not os.path.exists(path):
        return eff
    try:
        with open(path) as fh:
            saved = json.load(fh)
    except (ValueError, OSError) as e:
        print("preset.json ignored (%s); using built-in defaults" % e)
        return eff
    for k in PRESET:
        if k not in saved:
            continue
        if isinstance(PRESET[k], dict) and isinstance(saved[k], dict):
            merged = dict(PRESET[k])
            for ik in PRESET[k]:
                if ik in saved[k]:
                    merged[ik] = saved[k][ik]
            eff[k] = merged
        else:
            eff[k] = saved[k]
    return eff
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m unittest tests.test_ladder_labeler -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Confirm the existing test suite still passes**

```bash
python3 -m unittest discover -s tests -v
```

Expected: every existing test still passes (PRESET shape changed but old keys still present).

- [ ] **Step 7: Commit**

```bash
git add .gitignore build_lcr_viewer.py tests/test_ladder_labeler.py
git commit -m "feat(labeler): add ladder_labels preset block + nested merge

Adds the 'ladder_labels' block to PRESET with default-off, 5.0 m/z snap
tolerance, and 1% sigma amber threshold. load_preset() now merges nested
dict values key-by-key so a partial saved preset.json does not drop
the unspecified defaults.

Also: .gitignore exception for tests/*.html so the upcoming browser
test page can be checked in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `ladder_labeler.js` skeleton + core constants and `computeM` / `predictRung`

**Files:**
- Create: `ladder_labeler.js`
- Create: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Write the failing browser test**

Create `tests/ladder_labeler_test.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LadderLabeler tests</title>
<style>
 body{font-family:-apple-system,Segoe UI,Arial,sans-serif;margin:20px;color:#222}
 #summary{font-size:18px;font-weight:600;padding:8px;border-radius:4px;margin-bottom:14px}
 .pass{background:#d4f8d4;color:#1a6f1a}
 .fail{background:#f8d4d4;color:#8a1a1a}
 pre{background:#f4f4f4;padding:6px 10px;border-left:3px solid #888;margin:4px 0;white-space:pre-wrap;font-size:12px}
 .pass-line{color:#1a6f1a}
 .fail-line{color:#8a1a1a;font-weight:600}
</style>
</head>
<body>
<h2>LadderLabeler — pure-function tests</h2>
<p>Open this file directly in a browser (file:// works). The page loads
<code>../ladder_labeler.js</code> and runs the test cases below.</p>
<div id="summary">running…</div>
<div id="log"></div>

<script src="../ladder_labeler.js"></script>
<script>
const log = document.getElementById('log');
const summary = document.getElementById('summary');
let passed = 0, failed = 0;

function near(a, b, tol) { return Math.abs(a - b) <= tol; }

function check(name, condition, detail) {
  const div = document.createElement('pre');
  if (condition) {
    div.className = 'pass-line';
    div.textContent = '✓ ' + name;
    passed++;
  } else {
    div.className = 'fail-line';
    div.textContent = '✗ ' + name + (detail ? '  — ' + detail : '');
    failed++;
  }
  log.appendChild(div);
}

// ---------- Task 2 tests: M_H, computeM, predictRung ----------
check('M_H is the proton mass to 9 sig figs',
      near(LadderLabelerCore.M_H, 1.00727646677, 1e-10),
      'got ' + LadderLabelerCore.M_H);

check('computeM(8, 3300) ≈ 26391.94 Da',
      near(LadderLabelerCore.computeM(8, 3300), 26391.94, 0.1),
      'got ' + LadderLabelerCore.computeM(8, 3300));

check('predictRung(26391.94, 7) ≈ 3771.28',
      near(LadderLabelerCore.predictRung(26391.94, 7), 3771.28, 0.05),
      'got ' + LadderLabelerCore.predictRung(26391.94, 7));

check('round-trip: predictRung(computeM(z, mz), z) === mz',
      near(LadderLabelerCore.predictRung(LadderLabelerCore.computeM(8, 3300), 8), 3300, 1e-9));

// ---------- summary ----------
summary.className = failed === 0 ? 'pass' : 'fail';
summary.textContent = passed + ' passed, ' + failed + ' failed.';
</script>
</body>
</html>
```

- [ ] **Step 2: Run test to verify it fails**

Open `tests/ladder_labeler_test.html` in a browser (Chrome, Safari, or
Firefox — file:// works). Expected: the page reports `Failed to load
resource: ladder_labeler.js` in the console, and the summary stays
"running…" because `LadderLabelerCore` is undefined.

- [ ] **Step 3: Create `ladder_labeler.js` with core constants and functions**

Create `ladder_labeler.js` at the repo root (next to `build_lcr_viewer.py`):

```javascript
// ladder_labeler.js — opt-in ladder-labeling module for polyP_LCR_viewer.
// Spec: docs/superpowers/specs/2026-05-22-ladder-labeling-design.md
//
// This file is loaded two ways:
//   1. Inlined into the viewer HTML at build time by build_lcr_viewer.py
//      (via the __LADDER_LABELER__ placeholder).
//   2. Loaded directly by tests/ladder_labeler_test.html for pure-math tests.
//
// All pure functions live on LadderLabelerCore (testable without DOM/Plotly).
// The higher-level LadderLabeler object (state + UI integration) is added
// in later tasks.

const LadderLabelerCore = (function () {
  const M_H = 1.00727646677;  // proton mass, CODATA (Da)

  // Neutral mass from a single labeled rung (positive-mode ESI).
  function computeM(z, mz) {
    return z * mz - z * M_H;
  }

  // Predicted m/z of a same-parent rung at charge z, given the parent's M.
  function predictRung(M, z) {
    return (M + z * M_H) / z;
  }

  return { M_H, computeM, predictRung };
})();
```

- [ ] **Step 4: Run test to verify it passes**

Refresh `tests/ladder_labeler_test.html` in the browser. Expected: green
summary "4 passed, 0 failed" with four ✓ lines.

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add ladder_labeler.js core (M_H, computeM, predictRung)

First pure-math piece of the labeler module. Loaded by a standalone
browser test page (tests/ladder_labeler_test.html) for verification;
to be inlined into the viewer HTML at build time in a later task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `solveFromTwoClicks` with multi-k sweep

**Files:**
- Modify: `ladder_labeler.js`
- Modify: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Add failing tests for the solver**

In `tests/ladder_labeler_test.html`, after the `// ---------- Task 2 tests` block
and **before** the `// ---------- summary` block, append:

```javascript
// ---------- Task 3 tests: solveFromTwoClicks ----------
function sol(m1, m2) { return LadderLabelerCore.solveFromTwoClicks(m1, m2); }

check('adjacent rungs (3300, 3771) → z=8, k=1',
      sol(3300, 3771) && sol(3300, 3771).z === 8 && sol(3300, 3771).k === 1,
      JSON.stringify(sol(3300, 3771)));

check('adjacent rungs swapped order (3771, 3300) → same result',
      sol(3771, 3300) && sol(3771, 3300).z === 8 && sol(3771, 3300).k === 1);

check('non-adjacent (3300, 4400) — z=8 and z=6 — solver finds k=2',
      sol(3300, 4400) && sol(3300, 4400).z === 8 && sol(3300, 4400).k === 2);

check('non-adjacent (5279, 13197) — z=5 and z=2 — solver finds k=3',
      sol(5279, 13197) && sol(5279, 13197).z === 5 && sol(5279, 13197).k === 3);

check('M is computed from the higher-charge click',
      near(sol(3300, 3771).M, 8 * 3300 - 8 * LadderLabelerCore.M_H, 1e-6),
      'got ' + sol(3300, 3771).M);

check('ambiguous: clicks too close in m/z → null',
      sol(3300, 3300.5) === null,
      JSON.stringify(sol(3300, 3300.5)));

check('identical clicks → null',
      sol(3300, 3300) === null);

check('would-be z₀ = 1 (no reduction product) → null',
      sol(3300, 6600) === null, // would give z=1, rejected (need z>=2)
      JSON.stringify(sol(3300, 6600)));
```

- [ ] **Step 2: Refresh the browser; verify the new tests fail**

Reload `tests/ladder_labeler_test.html`. Expected: summary becomes red with
"4 passed, N failed" (the new tests fail because `solveFromTwoClicks` is
not yet defined — they all throw or return undefined).

- [ ] **Step 3: Add `solveFromTwoClicks` to the core**

In `ladder_labeler.js`, replace the `return { M_H, computeM, predictRung };`
line in the IIFE with the following expanded body:

```javascript
  // Closed-form charge recovery from any two ladder rungs (positive mode).
  // Multi-k sweep handles non-adjacent picks: only the correct k yields an
  // integer-close result. See spec §4.3 and Appendix B.
  function solveFromTwoClicks(m1, m2) {
    if (m1 > m2) { const t = m1; m1 = m2; m2 = t; }
    if (m2 - m1 < 1e-6) return null;          // identical clicks
    let best = null;
    for (let k = 1; k <= 5; k++) {
      const zRaw = (k * (m2 - M_H)) / (m2 - m1);
      const z = Math.round(zRaw);
      if (z < 2) continue;                     // need z₀ ≥ 2
      const err = Math.abs(z - zRaw);
      if (err >= 0.2) continue;                // not integer-close enough
      if (best === null || err < best.err) {
        best = { k, z, err };
      }
    }
    if (best === null) return null;
    const M = best.z * m1 - best.z * M_H;
    return { z: best.z, M, k: best.k };
  }

  return { M_H, computeM, predictRung, solveFromTwoClicks };
```

- [ ] **Step 4: Refresh and verify all 12 tests pass**

Reload `tests/ladder_labeler_test.html`. Expected: green "12 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add solveFromTwoClicks with multi-k sweep

Closed-form z recovery from two ladder rungs, with k ∈ {1..5} sweep so
non-adjacent clicks (e.g. z=8 and z=6, skipping z=7) are handled
without forcing the user to specify k. Rejects ambiguous picks
(|z − z_raw| ≥ 0.2) and z < 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `snapToMaxInWindow`

**Files:**
- Modify: `ladder_labeler.js`
- Modify: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Add failing tests**

Append to the test page's test script (before the summary block):

```javascript
// ---------- Task 4 tests: snapToMaxInWindow ----------
const SNAP = LadderLabelerCore.snapToMaxInWindow;

// Synthetic spectrum: Gaussian-shaped peak around m/z = 3771, width σ ≈ 2 m/z.
const sX = [], sY = [];
for (let mz = 3700; mz <= 3850; mz += 0.5) {
  sX.push(mz);
  sY.push(Math.exp(-Math.pow((mz - 3771) / 2, 2)));
}

check('snap to apex of broad Gaussian within ±5 m/z tolerance',
      near(SNAP(3770, sX, sY, 5), 3771, 0.5),
      'got ' + SNAP(3770, sX, sY, 5));

check('window with no points returns null',
      SNAP(2000, sX, sY, 5) === null);

check('window at right edge still returns the apex if it falls in range',
      near(SNAP(3775, sX, sY, 5), 3771, 0.5));

check('empty spectrum returns null',
      SNAP(3771, [], [], 5) === null);

// Two-peak spectrum, snap should pick the higher one in the window
const tX = [3760, 3765, 3771, 3777, 3782];
const tY = [0.3,   0.5,  0.8,  0.4,  0.2];

check('snap picks global max in window (not just nearest)',
      SNAP(3768, tX, tY, 10) === 3771);
```

- [ ] **Step 2: Verify the tests fail in the browser**

Reload: expected 5 new failures (function undefined).

- [ ] **Step 3: Add `snapToMaxInWindow` to the core**

In `ladder_labeler.js`, immediately before the `return { M_H, computeM, …`
line, add:

```javascript
  // Global-max-in-window snap. Returns the m/z of the highest-intensity
  // sample within ±tolMz of mzPred, or null if the window is empty.
  // Spec §4.2: native-MS peaks are broad, so global-max is more robust
  // than a 3-point local-max test against centroid noise.
  // Assumes specX is ascending (true for the viewer's PROC_X).
  function snapToMaxInWindow(mzPred, specX, specY, tolMz) {
    const lo = mzPred - tolMz, hi = mzPred + tolMz;
    let bestI = -1, bestY = -Infinity;
    for (let i = 0; i < specX.length; i++) {
      if (specX[i] < lo) continue;
      if (specX[i] > hi) break;
      if (specY[i] > bestY) { bestY = specY[i]; bestI = i; }
    }
    return bestI < 0 ? null : specX[bestI];
  }
```

And update the return statement to:

```javascript
  return { M_H, computeM, predictRung, solveFromTwoClicks, snapToMaxInWindow };
```

- [ ] **Step 4: Verify all 17 tests pass**

Reload `tests/ladder_labeler_test.html`. Expected: green "17 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add snapToMaxInWindow (global-max in tolerance window)

Snap a predicted rung m/z to the highest-intensity sample within ±tolMz.
Uses global max in window rather than 3-point local-max because native-MS
peaks are broad and centroid noise makes the local-max test fragile
(spec §4.2). Assumes ascending m/z (matches the viewer's PROC_X).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Mass formatting (`formatMass`, `formatSigma`) + `_stdDev` helper

**Files:**
- Modify: `ladder_labeler.js`
- Modify: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Add failing tests**

Append to the test page's script (before summary):

```javascript
// ---------- Task 5 tests: formatMass + formatSigma + _stdDev ----------
const FM = LadderLabelerCore.formatMass;
const FS = LadderLabelerCore.formatSigma;
const STD = LadderLabelerCore._stdDev;

// stdDev sanity
check('_stdDev([26390, 26391, 26392, 26393, 26394]) ≈ 1.58',
      near(STD([26390, 26391, 26392, 26393, 26394]), 1.58, 0.01),
      'got ' + STD([26390, 26391, 26392, 26393, 26394]));

check('_stdDev of one element → 0',
      STD([42]) === 0);

check('_stdDev of empty array → 0',
      STD([]) === 0);

// formatMass: small M, σ ≈ 1 → 1-Da precision, displayed in Da
check('formatMass(8432, 1.0) ≈ "8,432 Da"',
      FM(8432, 1.0) === '8,432 Da',
      'got ' + FM(8432, 1.0));

// formatMass: large M, σ ≈ 1 → 3 decimals in kDa
check('formatMass(26391.94, 1.0) === "26.392 kDa"',
      FM(26391.94, 1.0) === '26.392 kDa',
      'got ' + FM(26391.94, 1.0));

// formatMass: large M, σ ≈ 80 → 2 decimals in kDa, rounds to 10 Da precision
check('formatMass(26391.94, 80) === "26.39 kDa"',
      FM(26391.94, 80) === '26.39 kDa',
      'got ' + FM(26391.94, 80));

// formatMass: large M, σ ≈ 800 → 1 decimal in kDa
check('formatMass(26391.94, 800) === "26.4 kDa"',
      FM(26391.94, 800) === '26.4 kDa',
      'got ' + FM(26391.94, 800));

// formatSigma: relative form by default
check('formatSigma(26000, 100) === "± 0.4%"',
      FS(26000, 100) === '± 0.4%',
      'got ' + FS(26000, 100));

check('formatSigma at very small rel uses absolute units',
      FS(26000, 5).indexOf('Da') >= 0 || FS(26000, 5).indexOf('kDa') >= 0,
      'got ' + FS(26000, 5));
```

- [ ] **Step 2: Verify failure**

Reload: expected 9 new failures.

- [ ] **Step 3: Add formatters and the stdDev helper to the core**

In `ladder_labeler.js`, add these functions inside the IIFE, after
`snapToMaxInWindow` and before the `return`:

```javascript
  // Sample standard deviation. Returns 0 for length < 2.
  function _stdDev(arr) {
    const n = arr.length;
    if (n < 2) return 0;
    const mean = arr.reduce((s, v) => s + v, 0) / n;
    const v = arr.reduce((s, x) => s + (x - mean) * (x - mean), 0) / (n - 1);
    return Math.sqrt(v);
  }

  // Format M according to the precision rule in spec §5.4.
  // precDa = 10 ^ floor(log10(sigma)); clamped at 1 Da.
  // If M < 10000, render in Da rounded to precDa.
  // Else render in kDa with decimals = max(0, 3 - floor(log10(sigma))).
  function formatMass(M, sigmaM) {
    const sig = Math.max(sigmaM, 1.0);
    const lg = Math.floor(Math.log10(sig));
    const precDa = Math.pow(10, lg);
    if (M < 10000) {
      const rounded = Math.round(M / precDa) * precDa;
      return rounded.toLocaleString('en-US') + ' Da';
    }
    const decimals = Math.max(0, 3 - lg);
    return (M / 1000).toFixed(decimals) + ' kDa';
  }

  // Format ± dispersion. Below sigma/M < 0.001 use absolute units;
  // otherwise use percentage.
  function formatSigma(M, sigmaM) {
    if (M === 0 || sigmaM === 0) return '';
    const rel = sigmaM / M;
    if (rel < 0.001) {
      return '± ' + formatMass(sigmaM, sigmaM);
    }
    return '± ' + (rel * 100).toFixed(rel < 0.01 ? 2 : 1) + '%';
  }
```

Update the return to expose the new functions (the helper `_stdDev` is
prefixed-underscore but still exported for testing):

```javascript
  return { M_H, computeM, predictRung, solveFromTwoClicks,
           snapToMaxInWindow, _stdDev, formatMass, formatSigma };
```

- [ ] **Step 4: Verify all 26 tests pass**

Reload. Expected: green "26 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add formatMass / formatSigma per spec §5.4

Mass display precision follows the σ-driven rule: precDa = 10^floor(log10(σ))
(clamped ≥ 1 Da). Da for M<10kDa, kDa with decimals=max(0, 3-log10σ) above.
Sigma uses percentage for σ/M ≥ 0.001, absolute Da/kDa below that.
Also adds _stdDev helper for the per-ladder dispersion summary.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Ladder management — `LadderLabeler` skeleton + `addLadderFromSeed` + `refreshLadder`

**Files:**
- Modify: `ladder_labeler.js`
- Modify: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Add failing tests**

Append to the test page's script (before summary):

```javascript
// ---------- Task 6 tests: state + addLadderFromSeed + refreshLadder ----------
// Synthetic ladder: parent M = 26391.94, z₀=8, m/z=3300. Predicted rungs:
//   z=7: 3771.28, z=6: 4399.66, z=5: 5279.40, z=4: 6598.99, z=3: 8797.99,
//   z=2: 13197.0, z=1: 26392.95 (outside our 3000–14000 range below)
// Build a spectrum with broad gaussian "peaks" at those m/z's.
function makeLadderSpectrum() {
  const X = [], Y = [];
  const peaks = [3300, 3771.2, 4399.5, 5279.6, 6599.2, 8797.8, 13197.3];
  for (let mz = 3000; mz <= 14000; mz += 0.5) {
    X.push(mz);
    let y = 0;
    for (const p of peaks) y += Math.exp(-Math.pow((mz - p) / 2.0, 2));
    Y.push(y);
  }
  return { X, Y };
}

// Reset module state before each test (rebuilt fresh by reloading the page;
// but the test page only loads once, so call resetLabelerState() between
// sub-tests).
function resetLabelerState() {
  LadderLabeler.state.ladders = [];
  LadderLabeler.state.activeLadderId = null;
  LadderLabeler.state.enabled = false;
  LadderLabeler._resetIdCounter();
}

resetLabelerState();
const spec = makeLadderSpectrum();

const r1 = LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, spec.X, spec.Y);
check('addLadderFromSeed assigns id A to first ladder',
      r1.id === 'A',
      JSON.stringify(r1));

const L = LadderLabeler.state.ladders[0];
check('ladder.color is a hex string',
      typeof L.color === 'string' && L.color.startsWith('#'),
      L.color);

check('ladder.M ≈ 26391.94',
      near(L.M, 26391.94, 0.1),
      'M = ' + L.M);

check('ladder has 7 candidate labels (z = 7..1)',
      L.labels.length === 7,
      'got ' + L.labels.length);

const found = L.labels.filter(lb => lb.mzObs !== null);
check('at least 6 of 7 candidates were snapped to peaks',
      found.length >= 6,
      'got ' + found.length);

check('z=1 rung at predicted ≈26393 is null (outside synthetic spectrum range)',
      L.labels.find(lb => lb.z === 1).mzObs === null);

check('every found rung\'s mImplied is within ±20 Da of L.M',
      found.every(lb => Math.abs(lb.mImplied - L.M) < 20),
      JSON.stringify(found.map(lb => ({z: lb.z, mImplied: Math.round(lb.mImplied*10)/10}))));

check('addLadderFromSeed rejects z₀ = 1 with an error',
      LadderLabeler.addLadderFromSeed({ mz: 3300, z: 1 }, spec.X, spec.Y).error !== undefined);

check('addLadderFromSeed rejects non-integer z₀',
      LadderLabeler.addLadderFromSeed({ mz: 3300, z: 7.5 }, spec.X, spec.Y).error !== undefined);

// active ladder is the most recently added valid one
check('first valid ladder becomes the active ladder',
      LadderLabeler.state.activeLadderId === 'A');
```

- [ ] **Step 2: Verify failure**

Reload: expected ~10 new failures.

- [ ] **Step 3: Add LadderLabeler to `ladder_labeler.js`**

Append to `ladder_labeler.js` (after the `const LadderLabelerCore = …` IIFE):

```javascript
// ============================================================================
// LadderLabeler — stateful, multi-ladder manager that consumes LadderLabelerCore.
// Spec §3.1, §3.2, §4.1, §4.5.
// ============================================================================

const LadderLabeler = (function () {
  const C = LadderLabelerCore;
  const COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
                  '#9467bd', '#8c564b', '#e377c2', '#7f7f7f'];

  const state = {
    enabled: false,
    tolMz: 5.0,
    sigmaAmberRelative: 0.01,
    ladders: [],
    activeLadderId: null,
    pendingMode: null,        // null | 'two-click'
    twoClickBuffer: null,
  };

  let _nextIdIndex = 0;
  function _nextId() {
    const letter = String.fromCharCode(65 + (_nextIdIndex % 26));
    _nextIdIndex++;
    return letter;
  }
  function _nextColor() {
    return COLORS[(_nextIdIndex - 1) % COLORS.length];
  }
  function _resetIdCounter() { _nextIdIndex = 0; }

  // z' = z₀-1, z₀-2, …, 1. Seed itself is NOT in this list (spec §3.2).
  function _candidateRungs(z0) {
    const out = [];
    for (let z = z0 - 1; z >= 1; z--) out.push(z);
    return out;
  }

  function addLadderFromSeed(opts, specX, specY) {
    const { mz, z } = opts;
    if (!Number.isInteger(z) || z < 2) {
      return { error: 'z₀ must be an integer ≥ 2' };
    }
    const ladder = {
      id: _nextId(),
      color: _nextColor(),
      seed: { mz, z },
      M: C.computeM(z, mz),
      sigmaM: 0,
      labels: [],
    };
    state.ladders.push(ladder);
    state.activeLadderId = ladder.id;
    refreshLadder(ladder.id, specX, specY);
    return { id: ladder.id };
  }

  function refreshLadder(id, specX, specY) {
    const L = state.ladders.find(x => x.id === id);
    if (!L) return;
    L.M = C.computeM(L.seed.z, L.seed.mz);
    // Preserve manual overrides across re-snapping. Auto labels are rebuilt.
    const manualPreserved = L.labels.filter(lb => lb.manual);
    L.labels = [];
    for (const z of _candidateRungs(L.seed.z)) {
      const mzPred = C.predictRung(L.M, z);
      const mzObs = C.snapToMaxInWindow(mzPred, specX, specY, state.tolMz);
      const mImplied = (mzObs === null) ? null : C.computeM(z, mzObs);
      L.labels.push({ z, mzPred, mzObs, mImplied, manual: false, stale: false });
    }
    // Re-snap each manual label near its previous mzObs; mark stale if not found.
    for (const m of manualPreserved) {
      const newMz = C.snapToMaxInWindow(m.mzObs, specX, specY, state.tolMz);
      if (newMz !== null) {
        m.mzObs = newMz;
        m.mImplied = C.computeM(m.z, newMz);
        m.stale = false;
      } else {
        m.stale = true;
      }
      L.labels.push(m);
    }
    const implied = L.labels
      .filter(lb => lb.mImplied !== null && !lb.manual)
      .map(lb => lb.mImplied);
    L.sigmaM = C._stdDev(implied);
  }

  return {
    state,
    _resetIdCounter,
    _candidateRungs,
    addLadderFromSeed,
    refreshLadder,
  };
})();
```

- [ ] **Step 4: Verify all 36 tests pass**

Reload `tests/ladder_labeler_test.html`. Expected: green "36 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): add LadderLabeler skeleton + addLadderFromSeed + refreshLadder

Stateful per-ladder manager built on LadderLabelerCore. addLadderFromSeed
creates a ladder anchored at (precursor m/z, z₀≥2), assigns id A,B,C…
and a color from the Plotly palette, and immediately runs refreshLadder.
refreshLadder iterates z' = z₀-1 → 1 (seed excluded by design, spec §3.2),
snaps each predicted rung to the global max in ±tolMz, computes per-rung
mImplied, and stores σ_M over the auto rungs.

Manual labels are preserved across re-snapping (re-searched near their
previous mzObs and flagged stale if not found) — that supports the live
re-snap when smoothing/scaling parameters change (spec §4.5).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Multi-ladder ops — `addLadderFromTwoClicks`, `removeLadder`, `setActive`, `refreshAll`

**Files:**
- Modify: `ladder_labeler.js`
- Modify: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Add failing tests**

Append to the test page's script (before summary):

```javascript
// ---------- Task 7 tests: multi-ladder ops ----------
resetLabelerState();
const spec2 = makeLadderSpectrum();

// add a second synthetic ladder at higher M
function addSecondLadderPeaks(X, Y) {
  // M₂ ≈ 52784 Da, z₀=16, parent at m/z = (52784 + 16*m_H)/16 ≈ 3300
  // To keep this test distinguishable, place ladder B parent at m/z = 3302.5
  // and add peaks at predicted rungs.
  const M2 = 16 * 3302.5 - 16 * LadderLabelerCore.M_H;
  const peaks = [];
  for (let z = 15; z >= 1; z--) {
    const p = LadderLabelerCore.predictRung(M2, z);
    if (p >= 3000 && p <= 14000) peaks.push(p);
  }
  for (let i = 0; i < X.length; i++) {
    for (const p of peaks) {
      Y[i] += Math.exp(-Math.pow((X[i] - p) / 2.0, 2));
    }
  }
}
addSecondLadderPeaks(spec2.X, spec2.Y);

const rA = LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, spec2.X, spec2.Y);
const rB = LadderLabeler.addLadderFromSeed({ mz: 3302.5, z: 16 }, spec2.X, spec2.Y);

check('second ladder gets id B', rB.id === 'B');

check('two ladders both present in state',
      LadderLabeler.state.ladders.length === 2);

check('ladders have distinct colors',
      LadderLabeler.state.ladders[0].color !== LadderLabeler.state.ladders[1].color);

check('new ladder becomes active',
      LadderLabeler.state.activeLadderId === 'B');

LadderLabeler.setActive('A');
check('setActive switches the active ladder',
      LadderLabeler.state.activeLadderId === 'A');

LadderLabeler.setActive('Z');  // nonexistent
check('setActive with unknown id is a no-op',
      LadderLabeler.state.activeLadderId === 'A');

LadderLabeler.removeLadder('A');
check('removeLadder removes A',
      LadderLabeler.state.ladders.length === 1
      && LadderLabeler.state.ladders[0].id === 'B');

check('removing the active ladder shifts active to the remaining ladder',
      LadderLabeler.state.activeLadderId === 'B');

LadderLabeler.removeLadder('B');
check('removing the last ladder leaves activeLadderId null',
      LadderLabeler.state.activeLadderId === null
      && LadderLabeler.state.ladders.length === 0);

// addLadderFromTwoClicks
resetLabelerState();
const rTC = LadderLabeler.addLadderFromTwoClicks(3300, 3771, spec2.X, spec2.Y);
check('addLadderFromTwoClicks succeeds with adjacent clicks',
      rTC.id !== undefined,
      JSON.stringify(rTC));

check('two-click-seeded ladder has z₀ = 8',
      LadderLabeler.state.ladders[0].seed.z === 8);

check('two-click ambiguous returns error, no ladder created',
      LadderLabeler.addLadderFromTwoClicks(3300, 3300.5, spec2.X, spec2.Y).error !== undefined
      && LadderLabeler.state.ladders.length === 1);

// refreshAll re-snaps every ladder
resetLabelerState();
LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, spec2.X, spec2.Y);
LadderLabeler.addLadderFromSeed({ mz: 3302.5, z: 16 }, spec2.X, spec2.Y);
const sigBefore = LadderLabeler.state.ladders[0].sigmaM;
LadderLabeler.refreshAll(spec2.X, spec2.Y);
const sigAfter = LadderLabeler.state.ladders[0].sigmaM;
check('refreshAll preserves sigmaM (idempotent on unchanged spectrum)',
      near(sigBefore, sigAfter, 1e-9),
      'before=' + sigBefore + ' after=' + sigAfter);
```

- [ ] **Step 2: Verify failure**

Reload: expected 12 new failures.

- [ ] **Step 3: Add the multi-ladder operations**

In `ladder_labeler.js`, inside the `LadderLabeler` IIFE, add these functions
**after** `refreshLadder` and **before** the `return` block:

```javascript
  function addLadderFromTwoClicks(m1, m2, specX, specY) {
    const sol = C.solveFromTwoClicks(m1, m2);
    if (sol === null) {
      return { error: 'ambiguous two-click — pick farther-apart rungs' };
    }
    const mLo = Math.min(m1, m2);  // higher-charge click is the seed anchor
    return addLadderFromSeed({ mz: mLo, z: sol.z }, specX, specY);
  }

  function removeLadder(id) {
    const idx = state.ladders.findIndex(L => L.id === id);
    if (idx < 0) return;
    state.ladders.splice(idx, 1);
    if (state.activeLadderId === id) {
      state.activeLadderId = state.ladders.length ? state.ladders[0].id : null;
    }
  }

  function setActive(id) {
    if (state.ladders.some(L => L.id === id)) {
      state.activeLadderId = id;
    }
  }

  function refreshAll(specX, specY) {
    for (const L of state.ladders) refreshLadder(L.id, specX, specY);
  }
```

Update the return statement to include them:

```javascript
  return {
    state,
    _resetIdCounter,
    _candidateRungs,
    addLadderFromSeed,
    addLadderFromTwoClicks,
    removeLadder,
    setActive,
    refreshLadder,
    refreshAll,
  };
```

- [ ] **Step 4: Verify all 48 tests pass**

Reload. Expected: green "48 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): multi-ladder ops (twoClicks/remove/setActive/refreshAll)

Adds addLadderFromTwoClicks (wraps the core solver), removeLadder
(maintains active-id invariant), setActive, and refreshAll. The
labeler now supports multiple interleaved ladders per spectrum
with distinct ids and colors.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Inline `ladder_labeler.js` into the viewer HTML at build time

**Files:**
- Modify: `build_lcr_viewer.py` (`build_html` function; `main`)
- Modify: `tests/test_ladder_labeler.py`

- [ ] **Step 1: Write the failing Python test**

In `tests/test_ladder_labeler.py`, add a new test class **after** the
existing `PresetBlockTests` class and before the `if __name__` block:

```python
class TemplateSubstitutionTests(unittest.TestCase):
    """The build inlines ladder_labeler.js into the HTML via the
    __LADDER_LABELER__ placeholder, mirroring the __PLOTLY__ pattern."""

    def _build_minimal_html(self):
        mz = [3000.0, 3100.0, 3200.0, 3300.0, 3400.0]
        it = [0.0, 1.0, 5.0, 10.0, 5.0]
        thr = 3250.0
        plotly_stub = "/* plotly stub */"
        labeler_stub_path = os.path.join(ROOT, "ladder_labeler.js")
        with open(labeler_stub_path) as fh:
            labeler_js = fh.read()
        # Build HTML through the same path main() uses.
        html = B.build_html(mz, it, thr, plotly_stub,
                            "LCR_mz3300_20260522-1200.html",
                            B.PRESET, labeler_js)
        return html, labeler_js

    def test_built_html_inlines_ladder_labeler(self):
        html, labeler_js = self._build_minimal_html()
        # A signature line that is unique to ladder_labeler.js
        self.assertIn("const LadderLabelerCore", html)
        self.assertIn("const LadderLabeler", html)

    def test_built_html_no_unsubstituted_placeholder(self):
        html, _ = self._build_minimal_html()
        self.assertNotIn("__LADDER_LABELER__", html)
```

- [ ] **Step 2: Run; verify failure**

```bash
python3 -m unittest tests.test_ladder_labeler -v
```

Expected: the two new tests fail — `build_html` has the wrong arity (no
`labeler_js` parameter) and the template has no `__LADDER_LABELER__`
placeholder.

- [ ] **Step 3: Add the placeholder to TEMPLATE**

In `build_lcr_viewer.py`, find the line:

```
<script>__PLOTLY__</script>
```

(approximately line 649; inside the `TEMPLATE` string). Add a new line
**immediately after** it:

```
<script>__LADDER_LABELER__</script>
```

So that the two consecutive lines become:

```
<script>__PLOTLY__</script>
<script>__LADDER_LABELER__</script>
```

- [ ] **Step 4: Extend `build_html` to accept and substitute labeler JS**

In `build_lcr_viewer.py`, modify the `build_html` function signature
(line 400) and body:

```python
def build_html(mz, it, thr, plotly, html_name, preset, labeler_js):
    """Assemble a self-contained viewer HTML from spectrum data, the
    per-spectrum threshold, the inlined Plotly bundle, and the inlined
    ladder-labeler JS. Control defaults come from the effective preset
    (see load_preset). The processed-CSV download/link/sibling-file
    reuses html_name's stem so the CSV matches its viewer
    (LCR_mz<precursor>_<timestamp>.csv); the header hyperlink points at
    that sibling file written next to the viewer (see main)."""
    csv_name = os.path.splitext(os.path.basename(html_name))[0] + ".csv"
    html = TEMPLATE
    html = html.replace("__SCALEON__",
                        "checked" if preset.get("scale_on", True) else "")
    html = html.replace("__SCALE__", str(preset["scale"]))
    html = html.replace("__THR__", "%g" % thr)
    html = html.replace("__WIDTH__", str(preset["width_mz"]))
    html = html.replace("__POLY__", str(preset["poly"]))
    html = html.replace("__RAWOV__", "checked" if preset["show_overlay"] else "")
    html = html.replace('value="%s"' % preset["method"],
                        'value="%s" selected' % preset["method"])
    html = html.replace("__CSVNAME__", json.dumps(csv_name))
    html = html.replace("__CSVHREF__", csv_name)
    html = html.replace("__MZ__", json.dumps(mz))
    html = html.replace("__IT__", json.dumps(it))
    html = html.replace("__PLOTLY__", plotly)
    html = html.replace("__LADDER_LABELER__", labeler_js)
    return html
```

- [ ] **Step 5: Update `main()` to read `ladder_labeler.js` and pass it through**

In `build_lcr_viewer.py`, locate `main()` (around line 531) and the line:

```python
    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()
```

Add **immediately after** it:

```python
    with open(os.path.join(here, "ladder_labeler.js")) as fh:
        labeler_js = fh.read()
```

Then find the `build_html(...)` call in the same function (around line 558):

```python
        html = build_html(mz, it, thr, plotly, name, preset)
```

Replace with:

```python
        html = build_html(mz, it, thr, plotly, name, preset, labeler_js)
```

- [ ] **Step 6: Run all tests**

```bash
python3 -m unittest discover -s tests -v
```

Expected: every test, including the two new ones, PASS. The existing
`tests/test_build_lcr_viewer.py` suite may also exercise `build_html`
directly — if it calls the old signature without `labeler_js`, fix
those calls by passing an empty string `""` as the new argument (no
labeler in those test calls).

- [ ] **Step 7: Check existing test suite for build_html arity**

```bash
grep -n "build_html(" tests/test_build_lcr_viewer.py
```

For each call site, if it does not already pass `labeler_js`, add `, ""`
as the last argument. (The `""` is fine because those tests don't
assert on labeler content.)

- [ ] **Step 8: Re-run full test suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add build_lcr_viewer.py tests/test_ladder_labeler.py tests/test_build_lcr_viewer.py
git commit -m "feat(labeler): inline ladder_labeler.js into viewer HTML at build time

Adds __LADDER_LABELER__ placeholder to TEMPLATE, mirroring the __PLOTLY__
pattern: build_html() now takes labeler_js as an argument and main()
reads ladder_labeler.js from next to the script. The built HTML stays
fully self-contained (Plotly + labeler both inlined).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Control-panel HTML — static markup with preset defaults

**Files:**
- Modify: `build_lcr_viewer.py` (`TEMPLATE` and `build_html`)
- Modify: `tests/test_ladder_labeler.py`

- [ ] **Step 1: Add failing tests**

In `tests/test_ladder_labeler.py`, add a new test class after
`TemplateSubstitutionTests` (and before the `if __name__` block):

```python
class PanelMarkupTests(unittest.TestCase):
    """The viewer HTML carries the ladder-labels control panel markup
    (always rendered; visible when the labeler is enabled)."""

    def _build(self, ladder_labels=None):
        preset = dict(B.PRESET)
        if ladder_labels is not None:
            preset["ladder_labels"] = ladder_labels
        html = B.build_html([3000.0, 3100.0], [0.0, 1.0], 3050.0,
                            "/* plotly */", "LCR_mz3000_20260522-1200.html",
                            preset, "/* labeler */")
        return html

    def test_panel_has_enabled_checkbox(self):
        html = self._build()
        self.assertIn('id="ladder-enabled"', html)

    def test_panel_has_tol_input(self):
        html = self._build()
        self.assertIn('id="ladder-tol"', html)

    def test_tol_input_default_from_preset(self):
        html = self._build()
        self.assertIn('value="5.0"', html)  # the default tol_mz

    def test_enabled_checked_when_preset_enabled(self):
        html = self._build({"enabled": True, "tol_mz": 5.0,
                            "sigma_amber_relative": 0.01})
        self.assertIn('id="ladder-enabled" checked', html)

    def test_panel_has_ladders_list_container(self):
        html = self._build()
        self.assertIn('id="ladder-list"', html)

    def test_panel_has_add_buttons(self):
        html = self._build()
        self.assertIn('id="ladder-add-type"', html)
        self.assertIn('id="ladder-add-twoclick"', html)
        self.assertIn('id="ladder-clear"', html)
```

- [ ] **Step 2: Verify failure**

```bash
python3 -m unittest tests.test_ladder_labeler.PanelMarkupTests -v
```

Expected: 6 FAIL (markup missing).

- [ ] **Step 3: Insert the panel markup into TEMPLATE**

In `build_lcr_viewer.py`, find the `<div id="controls">` block (around
line 604) and the closing `</div>` of that block (around line 639,
immediately before `<div class="hint">`). Just **before** that closing
`</div>`, insert:

```
 <div class="ctl chk" style="border-left:1px solid #ddd;padding-left:14px">
   <label><input type="checkbox" id="ladder-enabled" __LADDER_ENABLED__>
     Ladder labels
     <span style="font-size:11px;color:#888">(opt-in; off by default)</span></label>
   <label style="display:flex;align-items:center;gap:6px;margin-top:4px">
     Snap tol (m/z):
     <input type="number" id="ladder-tol" value="__LADDER_TOL__" step="0.5"
            min="0.1" max="50" style="width:70px;padding:3px 5px"></label>
 </div>
 <div class="ctl" style="min-width:280px">
   <label>Ladders</label>
   <div id="ladder-list"
        style="font-size:11px;border:1px solid #ddd;border-radius:4px;
               padding:4px 6px;min-height:28px;max-height:88px;overflow:auto;
               background:#fafafa">
     <span style="color:#888">(none — use Add buttons)</span>
   </div>
   <div style="display:flex;gap:4px;margin-top:4px">
     <button id="ladder-add-type" style="font-size:11px;padding:3px 8px">
       + Type seed</button>
     <button id="ladder-add-twoclick" style="font-size:11px;padding:3px 8px">
       + 2-click seed</button>
     <button id="ladder-clear" style="font-size:11px;padding:3px 8px">
       Clear all</button>
   </div>
   <span id="ladder-status"
         style="font-size:11px;color:#888;margin-top:3px"></span>
 </div>
```

- [ ] **Step 4: Substitute the new placeholders in `build_html`**

In `build_lcr_viewer.py`, in `build_html`, add **before** the
`return html` line:

```python
    ll = preset.get("ladder_labels", {})
    html = html.replace("__LADDER_ENABLED__",
                        "checked" if ll.get("enabled", False) else "")
    html = html.replace("__LADDER_TOL__", str(ll.get("tol_mz", 5.0)))
```

- [ ] **Step 5: Re-run tests**

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests PASS (including the 6 new panel-markup tests).

- [ ] **Step 6: Smoke build**

```bash
python3 build_lcr_viewer.py tests/test_data/example.xy /tmp/lcr_smoke/ 2>&1 | head -3
```

(If `tests/test_data/example.xy` does not exist, use any 2-column file
you have under `data/`.) Then open the resulting HTML in a browser and
visually confirm the new control group appears in the toolbar (the
checkbox + tol input + ladder list + three buttons). The list shows
`(none — use Add buttons)` and the buttons do nothing yet.

- [ ] **Step 7: Commit**

```bash
git add build_lcr_viewer.py tests/test_ladder_labeler.py
git commit -m "feat(labeler): add ladder-labels control panel markup to TEMPLATE

Static HTML for the panel: enable checkbox, snap tolerance, ladders list
container, add/clear buttons, status line. Substitutes __LADDER_ENABLED__
and __LADDER_TOL__ from the preset. No behavior yet — wiring lands in
the next tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: `buildAnnotations()` — Plotly annotations + shapes from labeler state

**Files:**
- Modify: `ladder_labeler.js`
- Modify: `tests/ladder_labeler_test.html`

- [ ] **Step 1: Add failing tests**

Append to the test page's script (before summary):

```javascript
// ---------- Task 10 tests: buildAnnotations ----------
resetLabelerState();
const spec3 = makeLadderSpectrum();
LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, spec3.X, spec3.Y);

// Disabled: should return empty arrays
LadderLabeler.state.enabled = false;
let g = LadderLabeler.buildAnnotations();
check('buildAnnotations returns empty arrays when disabled',
      g.annotations.length === 0 && g.shapes.length === 0);

LadderLabeler.state.enabled = true;
g = LadderLabeler.buildAnnotations(spec3.X, spec3.Y);

check('buildAnnotations returns dashed seed line',
      g.shapes.length >= 1 && g.shapes[0].line.dash === 'dash',
      JSON.stringify(g.shapes[0]));

check('seed line is at the seed m/z',
      Math.abs(g.shapes[0].x0 - 3300) < 1e-9);

check('annotations include a header summary line for ladder A',
      g.annotations.some(a => typeof a.text === 'string'
                              && a.text.indexOf('Ladder A') >= 0));

const rungAnnots = g.annotations.filter(a => a.xref === 'x' && a.x !== undefined);
check('annotations include per-rung labels with charge tag',
      rungAnnots.length >= 6 && rungAnnots[0].text.match(/\d+\+/));

check('annotation color matches ladder color',
      rungAnnots.every(a => a.font && a.font.color === LadderLabeler.state.ladders[0].color));

// Two ladders → ay offset differs by ladderIndex
LadderLabeler.addLadderFromSeed({ mz: 3302.5, z: 16 }, spec3.X, spec3.Y);
g = LadderLabeler.buildAnnotations(spec3.X, spec3.Y);
const aRungs = g.annotations.filter(a => a.xref === 'x'
                                          && a.font.color === LadderLabeler.state.ladders[0].color);
const bRungs = g.annotations.filter(a => a.xref === 'x'
                                          && a.font.color === LadderLabeler.state.ladders[1].color);
check('two ladders → both produce rung annotations',
      aRungs.length >= 1 && bRungs.length >= 1);

check('ladder B annotations use a different ay offset than ladder A',
      bRungs[0].ay !== aRungs[0].ay);
```

- [ ] **Step 2: Verify failure**

Reload: expected ~7 new failures.

- [ ] **Step 3: Implement `buildAnnotations` and the y-lookup helper**

In `ladder_labeler.js`, inside the `LadderLabeler` IIFE, add **after** the
multi-ladder operations and **before** the `return` block:

```javascript
  // Linear interpolation of the currently plotted intensity at any m/z.
  // specX/specY are passed explicitly to keep this testable.
  function _yAt(mz, specX, specY) {
    if (!specX || specX.length === 0) return 0;
    // Binary search for the first index with specX[i] >= mz.
    let lo = 0, hi = specX.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (specX[mid] < mz) lo = mid + 1; else hi = mid;
    }
    if (lo === 0) return specY[0] || 0;
    const x0 = specX[lo - 1], x1 = specX[lo];
    const y0 = specY[lo - 1] || 0, y1 = specY[lo] || 0;
    if (x1 === x0) return y1;
    const t = (mz - x0) / (x1 - x0);
    return y0 + t * (y1 - y0);
  }

  // Returns { annotations, shapes } ready to merge into Plotly's layout.
  function buildAnnotations(specX, specY) {
    if (!state.enabled) return { annotations: [], shapes: [] };
    const annots = [];
    const shapes = [];
    let ladderIdx = 0;
    for (const L of state.ladders) {
      // 1. Dashed seed vertical line (spec §5.2).
      shapes.push({
        type: 'line',
        x0: L.seed.mz, x1: L.seed.mz,
        yref: 'paper', y0: 0, y1: 1,
        line: { color: L.color, width: 1, dash: 'dash' },
      });

      // 2. Header summary line (spec §5.4) — stacked above the plot.
      const foundCount = L.labels.filter(lb => lb.mzObs !== null).length;
      const amber = L.M > 0 && (L.sigmaM / L.M) > state.sigmaAmberRelative;
      const hdrColor = amber ? '#cc4400' : L.color;
      const hdrText = 'Ladder ' + L.id + ':  M = ' + C.formatMass(L.M, L.sigmaM)
                    + '  ' + C.formatSigma(L.M, L.sigmaM)
                    + '  (z₀ = ' + L.seed.z + '+, ' + foundCount + ' rungs)'
                    + (amber ? '  — check assignments' : '');
      annots.push({
        text: hdrText,
        xref: 'paper', yref: 'paper',
        x: 0.0, y: 1.10 + 0.04 * ladderIdx,
        xanchor: 'left', showarrow: false,
        font: { size: 11, color: hdrColor },
      });

      // 3. Per-rung annotations (spec §5.2, §5.3 hover).
      const yshift = -40 * ladderIdx;
      for (const lb of L.labels) {
        if (lb.mzObs === null) continue;
        const prefix = lb.manual ? 'M ' : '';
        const txt = prefix + lb.z + '+<br>' + lb.mzObs.toFixed(2);
        const hoverM = (lb.mImplied !== null)
                        ? C.formatMass(lb.mImplied, Math.max(L.sigmaM, 1))
                        : '?';
        annots.push({
          x: lb.mzObs,
          y: _yAt(lb.mzObs, specX, specY),
          xref: 'x', yref: 'y',
          text: txt,
          showarrow: true, arrowhead: 2, arrowsize: 0.6, arrowwidth: 1,
          ax: 0, ay: yshift - 22,
          font: { size: 10, color: L.color },
          bgcolor: 'rgba(255,255,255,0.78)',
          // Plotly annotation hover: hovertext via 'captureevents' / 'hovertext'
          hovertext: 'Ladder ' + L.id + ' — z = ' + lb.z + '+\nM = '
                   + hoverM + ' (this rung)' + (lb.stale ? ' [stale]' : ''),
          opacity: lb.stale ? 0.4 : 1.0,
        });
      }
      ladderIdx++;
    }
    return { annotations: annots, shapes };
  }
```

Update the return statement to expose `buildAnnotations`:

```javascript
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
    buildAnnotations,
  };
```

- [ ] **Step 4: Verify all 55 tests pass**

Reload `tests/ladder_labeler_test.html`. Expected: green "55 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html
git commit -m "feat(labeler): buildAnnotations renders Plotly shapes + annotations

Per ladder: one dashed vertical seed line (spec §5.2), one header
summary text annotation with mass + sigma in the chosen color (amber
if σ/M > threshold), and per-rung annotations with z+ / m/z text and
the implied-M in hovertext (spec §5.3). Stacked label collision
mitigated by ay = -40px * ladderIdx.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Hook `buildAnnotations()` into `recompute()` so the plot shows labels

**Files:**
- Modify: `build_lcr_viewer.py` (`TEMPLATE`, inside the existing `recompute()` JS)

- [ ] **Step 1: Locate the Plotly.react call in the existing viewer JS**

In `build_lcr_viewer.py`, find the `Plotly.react('plot', traces, layout, …)`
line inside the `recompute()` function (currently the last expressive
line of `recompute`).

- [ ] **Step 2: Merge labeler shapes + annotations into the layout before plotting**

In `build_lcr_viewer.py`, locate the `recompute()` function in `TEMPLATE`.
The function currently ends roughly like this (annotations array varies by
scale_on state):

```
   shapes:scaleOn?[{type:'line',x0:thr,x1:thr,yref:'paper',y0:0,y1:1,
            line:{color:'#cc4400',width:1,dash:'dot'}}]:[],
   annotations:scaleOn?[{x:thr,yref:'paper',y:1.04,text:'x'+factor+' above',
                 showarrow:false,font:{size:10,color:'#cc4400'}}]:[]
 };
 Plotly.react('plot',traces,layout,{responsive:true,
   toImageButtonOptions:{format:'png',scale:3,filename:'polyP_LCR_spectrum'}});
```

Just **before** the `Plotly.react(...)` call, insert the labeler merge:

```javascript
 // Merge ladder-label shapes/annotations from the LadderLabeler module
 // (spec §5.2, §5.4). When disabled, this returns empty arrays so the
 // existing MS1 layout is bit-identical to before.
 if (typeof LadderLabeler !== 'undefined') {
   LadderLabeler.refreshAll(PROC_X, PROC_Y);
   const g = LadderLabeler.buildAnnotations(PROC_X, PROC_Y);
   layout.shapes = (layout.shapes || []).concat(g.shapes);
   layout.annotations = (layout.annotations || []).concat(g.annotations);
   if (typeof renderLadderPanel === 'function') renderLadderPanel();
 }
```

- [ ] **Step 3: Smoke test — open a built viewer**

```bash
python3 build_lcr_viewer.py path/to/any/spectrum.xy /tmp/lcr_labeler_smoke/ 2>&1 | tail -3
```

Open the generated HTML in a browser. The labeler is disabled by default,
so the plot must look identical to before this task. **Open the browser
console** and confirm no errors. Then run, in the console:

```javascript
LadderLabeler.state.enabled = true;
LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, PROC_X, PROC_Y);
recompute();
```

Expected: a dashed vertical seed line appears at m/z=3300, and rungs at
predicted m/z values get charge-tag annotations colored in #1f77b4 (blue).
Header text near the top reads `Ladder A: M = …` in blue.

If the synthetic seed (3300, z=8) doesn't fit your real spectrum, pick a
plausible (m/z, z) pair from a peak you can see in the plot.

- [ ] **Step 4: Commit**

```bash
git add build_lcr_viewer.py
git commit -m "feat(labeler): wire LadderLabeler.buildAnnotations into recompute()

Adds a small block in recompute() that calls LadderLabeler.refreshAll(),
merges its shapes + annotations into Plotly's layout, then calls
renderLadderPanel() if defined (next task wires the panel). The merge
is guarded so the existing MS1 layout is unchanged when the labeler
is disabled (default).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Panel ↔ state binding — `renderLadderPanel` and control event handlers

**Files:**
- Modify: `build_lcr_viewer.py` (`TEMPLATE`, new JS appended after `recompute`'s definition)

- [ ] **Step 1: Locate the end of the existing JS block in TEMPLATE**

In `build_lcr_viewer.py`, scroll to the end of `TEMPLATE` and find the
closing `</script>` of the second viewer-JS `<script>` block (the one
that contains `recompute()` and the existing button event listeners).

- [ ] **Step 2: Append the panel binding JS just before that `</script>`**

Find the existing handler attachments (lines that read like
`document.getElementById('dl').addEventListener('click', …)`) and the
final initial `recompute();` call. **Immediately after** the initial
`recompute();` call, insert:

```javascript
// ---------- ladder labeler: panel binding ----------
// Hooks the LadderLabeler module to the control panel inserted in Task 9
// and re-renders the panel + plot whenever the labeler state changes.
function renderLadderPanel() {
  const list = document.getElementById('ladder-list');
  if (!list) return;
  const st = LadderLabeler.state;
  document.getElementById('ladder-enabled').checked = st.enabled;
  document.getElementById('ladder-tol').value = st.tolMz;
  if (st.ladders.length === 0) {
    list.innerHTML = '<span style="color:#888">(none — use Add buttons)</span>';
    return;
  }
  let html = '';
  for (const L of st.ladders) {
    const active = L.id === st.activeLadderId;
    const foundCount = L.labels.filter(lb => lb.mzObs !== null).length;
    const totalCount = L.labels.length;
    html += '<div style="display:flex;align-items:center;gap:6px;'
          + 'padding:2px 0;border-bottom:1px solid #eee">'
          + '<input type="radio" name="ladder-active" data-id="' + L.id + '"'
          + (active ? ' checked' : '') + '>'
          + '<span style="display:inline-block;width:10px;height:10px;'
          + 'background:' + L.color + ';border-radius:2px"></span>'
          + '<b>' + L.id + '</b>'
          + ' z₀=<input type="number" data-id="' + L.id + '" data-field="z" '
          + 'value="' + L.seed.z + '" min="2" step="1" '
          + 'style="width:46px;padding:1px 3px;font-size:11px">'
          + ' m/z=<input type="number" data-id="' + L.id + '" data-field="mz" '
          + 'value="' + L.seed.mz + '" step="0.1" '
          + 'style="width:70px;padding:1px 3px;font-size:11px">'
          + ' <span style="color:#666">'
          + foundCount + '/' + totalCount + ' rungs</span>'
          + ' <button data-id="' + L.id + '" data-action="remove" '
          + 'style="margin-left:auto;padding:1px 6px;font-size:11px">✕</button>'
          + '</div>';
  }
  list.innerHTML = html;

  // Wire the per-row controls.
  list.querySelectorAll('input[name="ladder-active"]').forEach(el => {
    el.addEventListener('change', () => {
      LadderLabeler.setActive(el.dataset.id);
      recompute();
    });
  });
  list.querySelectorAll('input[data-field]').forEach(el => {
    el.addEventListener('change', () => {
      const L = LadderLabeler.state.ladders.find(x => x.id === el.dataset.id);
      if (!L) return;
      const val = parseFloat(el.value);
      if (el.dataset.field === 'z') {
        if (!Number.isInteger(val) || val < 2) {
          document.getElementById('ladder-status').textContent =
            'z₀ must be an integer ≥ 2';
          el.value = L.seed.z;
          return;
        }
        L.seed.z = val;
      } else if (el.dataset.field === 'mz') {
        L.seed.mz = val;
      }
      LadderLabeler.refreshLadder(L.id, PROC_X, PROC_Y);
      recompute();
    });
  });
  list.querySelectorAll('button[data-action="remove"]').forEach(el => {
    el.addEventListener('click', () => {
      LadderLabeler.removeLadder(el.dataset.id);
      recompute();
    });
  });
}

// Top-level panel controls (enable checkbox, tolerance input).
document.getElementById('ladder-enabled').addEventListener('change', e => {
  LadderLabeler.state.enabled = e.target.checked;
  recompute();
});
document.getElementById('ladder-tol').addEventListener('change', e => {
  const v = parseFloat(e.target.value);
  if (isFinite(v) && v > 0) {
    LadderLabeler.state.tolMz = v;
    LadderLabeler.refreshAll(PROC_X, PROC_Y);
    recompute();
  }
});

// Render once on load.
renderLadderPanel();
```

- [ ] **Step 3: Smoke test**

Rebuild a viewer and open in a browser. In the console:

```javascript
document.getElementById('ladder-enabled').click();   // turn on the labeler
LadderLabeler.addLadderFromSeed({ mz: 3300, z: 8 }, PROC_X, PROC_Y);
recompute();
```

Expected: the panel list now shows a row `● A z₀=[8] m/z=[3300] N/M rungs ✕`.
Edit the z₀ input to 7 and tab away — the plot re-renders with a different
ladder (annotations now use M derived from z=7 at 3300). Click the radio
"active" button to switch active ladder, click `✕` to remove the row,
toggle the **Ladder labels** checkbox to disable/enable.

- [ ] **Step 4: Commit**

```bash
git add build_lcr_viewer.py
git commit -m "feat(labeler): panel-state binding (renderLadderPanel + control listeners)

Renders the ladders list from LadderLabeler.state, with per-row radio
(active), z₀/m/z editable inputs (validated; non-integer/<2 z reverts),
remove ✕ buttons, and rung counts. Top-level enable checkbox + snap
tolerance input wired to module state. Every change triggers
LadderLabeler.refreshAll() + recompute() so the plot stays in sync.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: `handlePlotClick` + Plotly click wiring + Add buttons

**Files:**
- Modify: `ladder_labeler.js`
- Modify: `tests/ladder_labeler_test.html`
- Modify: `build_lcr_viewer.py` (`TEMPLATE`, button handlers + Plotly click subscribe)

- [ ] **Step 1: Add `handlePlotClick` to the labeler module**

In `ladder_labeler.js`, inside the `LadderLabeler` IIFE, add **after**
`buildAnnotations` and **before** the `return`:

```javascript
  // Routes a Plotly click event. Caller passes the click m/z and the
  // current processed-trace arrays. Returns one of:
  //   { status: '…' }  — informational; caller may show in a status line
  //   { error: '…' }   — recoverable problem; caller may show as a warning
  //   { id: '…' }      — a ladder was created (its id is returned)
  //   undefined        — nothing notable; caller should still re-render.
  // Manual override convention (spec §4.4):
  //   integer       → override the clicked label's z (no re-seed)
  //   integer+'s'   → set the clicked peak as the new seed for its ladder
  //   empty/cancel  → delete the clicked label
  function handlePlotClick(clickedMz, specX, specY) {
    if (!state.enabled) return { status: 'labeler disabled' };

    // Two-click seed flow.
    if (state.pendingMode === 'two-click') {
      if (state.twoClickBuffer === null) {
        state.twoClickBuffer = clickedMz;
        return { status: 'first click recorded; click second rung' };
      }
      const m1 = state.twoClickBuffer;
      state.twoClickBuffer = null;
      state.pendingMode = null;
      return addLadderFromTwoClicks(m1, clickedMz, specX, specY);
    }

    if (state.ladders.length === 0) {
      return { error: 'no ladders yet — use + Type seed or + 2-click seed' };
    }

    // Check whether the click lands near an existing label.
    for (const L of state.ladders) {
      for (const lb of L.labels) {
        if (lb.mzObs === null) continue;
        if (Math.abs(lb.mzObs - clickedMz) <= state.tolMz) {
          const ans = prompt(
            'Edit label at m/z=' + lb.mzObs.toFixed(2) + ' (ladder ' + L.id + ').\n'
            + 'Enter integer to override z, integer+s to set as new seed,'
            + ' empty to delete.', String(lb.z));
          if (ans === null) return;     // user cancelled
          if (ans === '') {
            L.labels = L.labels.filter(x => x !== lb);
            return;
          }
          const seedFlag = /s$/i.test(ans);
          const zStr = seedFlag ? ans.slice(0, -1) : ans;
          const z = parseInt(zStr, 10);
          if (!Number.isInteger(z) || z < 1 || String(z) !== zStr.trim()) {
            return { error: 'unrecognized — expected integer, integer+s, or empty' };
          }
          if (seedFlag) {
            L.seed = { mz: lb.mzObs, z };
            refreshLadder(L.id, specX, specY);
          } else {
            lb.z = z;
            lb.mImplied = C.computeM(z, lb.mzObs);
            lb.manual = true;
          }
          return;
        }
      }
    }

    // No existing label nearby — try to create a manual one in the active ladder.
    if (state.activeLadderId === null) {
      return { error: 'no active ladder selected' };
    }
    const L = state.ladders.find(x => x.id === state.activeLadderId);
    const mzObs = C.snapToMaxInWindow(clickedMz, specX, specY, state.tolMz);
    if (mzObs === null) return { error: 'no peak in snap window' };
    const ans = prompt(
      'Add label at m/z=' + mzObs.toFixed(2) + ' (ladder ' + L.id + ').\n'
      + 'Enter charge z (integer), or integer+s to set as new seed.');
    if (ans === null || ans === '') return;
    const seedFlag = /s$/i.test(ans);
    const zStr = seedFlag ? ans.slice(0, -1) : ans;
    const z = parseInt(zStr, 10);
    if (!Number.isInteger(z) || z < 1 || String(z) !== zStr.trim()) {
      return { error: 'unrecognized — expected integer or integer+s' };
    }
    if (seedFlag) {
      if (z < 2) return { error: 'seed z must be ≥ 2' };
      L.seed = { mz: mzObs, z };
      refreshLadder(L.id, specX, specY);
    } else {
      L.labels.push({ z, mzPred: mzObs, mzObs,
                      mImplied: C.computeM(z, mzObs),
                      manual: true, stale: false });
    }
  }
```

Add `handlePlotClick` to the `return` object:

```javascript
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
    buildAnnotations,
    handlePlotClick,
  };
```

- [ ] **Step 2: Add tests for the non-prompt flow** (two-click mode, status messages)

Append to `tests/ladder_labeler_test.html`'s script (before summary):

```javascript
// ---------- Task 13 tests: handlePlotClick (non-prompt paths) ----------
resetLabelerState();
const spec4 = makeLadderSpectrum();

// Disabled module → status message, no state change
LadderLabeler.state.enabled = false;
let r = LadderLabeler.handlePlotClick(3300, spec4.X, spec4.Y);
check('handlePlotClick disabled → status message',
      r && r.status === 'labeler disabled');

// Enabled, two-click mode: first click buffers; second click solves.
LadderLabeler.state.enabled = true;
LadderLabeler.state.pendingMode = 'two-click';
LadderLabeler.state.twoClickBuffer = null;
r = LadderLabeler.handlePlotClick(3300, spec4.X, spec4.Y);
check('two-click first click → buffers',
      r && r.status && r.status.indexOf('first click') >= 0);

r = LadderLabeler.handlePlotClick(3771, spec4.X, spec4.Y);
check('two-click second click → creates a ladder',
      r && r.id === 'A',
      JSON.stringify(r));

check('after two-click, pendingMode is cleared',
      LadderLabeler.state.pendingMode === null
      && LadderLabeler.state.twoClickBuffer === null);

// Click with no ladders and not in two-click mode → error
resetLabelerState();
LadderLabeler.state.enabled = true;
r = LadderLabeler.handlePlotClick(3300, spec4.X, spec4.Y);
check('click with no ladders → error suggesting Add buttons',
      r && r.error && r.error.indexOf('no ladders') >= 0);
```

- [ ] **Step 3: Verify test page passes**

Reload `tests/ladder_labeler_test.html`. Expected: all tests still pass
(60 total — the prompt-driven paths are not covered automatically).

- [ ] **Step 4: Wire Plotly's `plotly_click` and the Add buttons**

In `build_lcr_viewer.py`, locate the panel-binding JS appended in Task 12.
**Immediately after** the `renderLadderPanel();` final call (the very last
line of the snippet you added), append:

```javascript
// "+ Type seed" — prompt for z₀ + m/z, create a ladder
document.getElementById('ladder-add-type').addEventListener('click', () => {
  if (!LadderLabeler.state.enabled) {
    document.getElementById('ladder-enabled').click();   // turn on automatically
  }
  const zStr = prompt('Precursor charge state z₀ (positive integer ≥ 2):');
  if (zStr === null) return;
  const z = parseInt(zStr, 10);
  if (!Number.isInteger(z) || z < 2) {
    document.getElementById('ladder-status').textContent =
      'z₀ must be an integer ≥ 2';
    return;
  }
  const mzStr = prompt('Precursor m/z:', String(precursor_from_name() || ''));
  if (mzStr === null) return;
  const mz = parseFloat(mzStr);
  if (!isFinite(mz) || mz <= 0) {
    document.getElementById('ladder-status').textContent =
      'precursor m/z must be a positive number';
    return;
  }
  const res = LadderLabeler.addLadderFromSeed({ mz, z }, PROC_X, PROC_Y);
  if (res.error) {
    document.getElementById('ladder-status').textContent = res.error;
  } else {
    document.getElementById('ladder-status').textContent =
      'added ladder ' + res.id;
  }
  recompute();
});

// "+ 2-click seed" — switch into two-click capture mode
document.getElementById('ladder-add-twoclick').addEventListener('click', () => {
  if (!LadderLabeler.state.enabled) {
    document.getElementById('ladder-enabled').click();
  }
  LadderLabeler.state.pendingMode = 'two-click';
  LadderLabeler.state.twoClickBuffer = null;
  document.getElementById('ladder-status').textContent =
    'two-click mode: click first ladder rung in the plot…';
});

// "Clear all"
document.getElementById('ladder-clear').addEventListener('click', () => {
  LadderLabeler.state.ladders.length = 0;
  LadderLabeler.state.activeLadderId = null;
  LadderLabeler._resetIdCounter();
  document.getElementById('ladder-status').textContent = 'cleared';
  recompute();
});

// Subscribe to Plotly clicks (once, after first render).
function attachPlotClick() {
  const plot = document.getElementById('plot');
  if (!plot || !plot.on) {
    setTimeout(attachPlotClick, 50);
    return;
  }
  plot.on('plotly_click', evt => {
    if (!evt || !evt.points || evt.points.length === 0) return;
    const clickedMz = evt.points[0].x;
    const out = LadderLabeler.handlePlotClick(clickedMz, PROC_X, PROC_Y);
    if (out) {
      if (out.status) document.getElementById('ladder-status').textContent = out.status;
      if (out.error)  document.getElementById('ladder-status').textContent = out.error;
      if (out.id)     document.getElementById('ladder-status').textContent =
                        'added ladder ' + out.id;
    }
    recompute();
  });
}
attachPlotClick();

// Helper for the type-seed default: read the precursor from window.location
// (the build filename pattern LCR_mz<precursor>_...) if the user opened a
// build-time viewer file. Falls back to '' if no match.
function precursor_from_name() {
  const m = (document.title + ' ' + (window.location.pathname || ''))
              .match(/mz([0-9]+(?:\.[0-9]+)?)/);
  return m ? parseFloat(m[1]) : '';
}
```

- [ ] **Step 5: End-to-end smoke**

Rebuild a viewer for a real spectrum, open it, and:

1. Click **+ Type seed** → enter `8` → enter `3300` (or another peak's m/z).
   Verify a ladder appears in the panel and labels appear on the plot.
2. Click **+ 2-click seed** → status reads "two-click mode: click first…" →
   click two adjacent ladder rungs in the plot. Verify a second ladder is
   created with a different color.
3. Click on a labeled peak in the plot → a prompt opens → enter a different
   integer; verify the on-plot text updates. Cancel the prompt → no change.
4. Click an unlabeled peak with an active ladder selected → prompt to add
   a manual label → enter a z → label appears, shaded slightly differently
   (the `M ` prefix in the text).
5. Edit a ladder's z₀ in the panel → the rest of the ladder re-snaps.
6. Click `✕` on a ladder row → ladder removed.
7. Toggle **Ladder labels** off → all annotations gone, plot reverts.

- [ ] **Step 6: Commit**

```bash
git add ladder_labeler.js tests/ladder_labeler_test.html build_lcr_viewer.py
git commit -m "feat(labeler): click handling, Add buttons, plotly_click wiring

Implements handlePlotClick on the module (two-click solve, manual override
prompts, seed-promotion via 'Ns' input) per spec §4.4. Wires the panel's
+ Type seed, + 2-click seed, and Clear all buttons. Subscribes to Plotly's
plotly_click event so any plot click routes through the labeler.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Docs — README + AGENTS.md

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: README — add "Labeling the LCR ladder" section**

In `README.md`, after the existing **Saving a preset** section (before
the `## Tests` section), add:

```markdown
## Labeling the LCR ladder (opt-in)

The viewer can label charge-reduced (CR) ladder peaks in a native-MS LCR
spectrum with their charge state `z`, observed m/z, and the back-calculated
parent neutral mass `M`. The feature is off by default — turn it on with
the **Ladder labels** checkbox in the toolbar.

A ladder is the family of charge-reduced products of one parent species:
same `M`, different `z`. The precursor envelope at the picked precursor
m/z is itself a mixture of multiple species/charges (that is what LCR
exists to resolve), so it is **not** labeled — only the charge-reduced
rungs are. The precursor m/z and `z₀` you provide are the math anchor,
not a per-peak claim about the precursor envelope.

### Adding a ladder

- **Type seed** — click *+ Type seed*, enter `z₀` (positive integer ≥ 2),
  enter the precursor m/z (auto-filled from the viewer filename). The
  viewer predicts m/z(z) = (M + z·m_H)/z for z = z₀−1, z₀−2, …, 1 and
  snaps each predicted rung to the highest-intensity sample within the
  **Snap tol (m/z)** window.
- **2-click seed** — click *+ 2-click seed*, then click two ladder peaks
  in the plot. A closed-form solver recovers `z` and `M` from the two
  m/z values (it sweeps charge-reduction step `k ∈ {1..5}` automatically,
  so non-adjacent picks work too).

### Manually overriding a label

Click on any labeled peak: a prompt opens, pre-filled with the current
`z`. Enter:
- a **positive integer** to override the label's charge (does *not*
  re-seed `M` — useful when one rung disagrees with the rest);
- a positive integer **suffixed with `s`** (e.g. `8s`) to promote that
  peak as the new seed of its ladder (re-seeds `M`, re-snaps the ladder);
- **empty** (or Cancel) to delete the label.

Clicking an *unlabeled* peak (after a ladder is active) creates a manual
label there with the prompted `z`. Manual labels are shown with an `M`
prefix on the on-plot text.

### Per-ladder controls

Each ladder appears in the panel with editable `z₀` and precursor m/z
inputs, a remove (`✕`) button, and a radio for which ladder is *active*
(takes plot clicks). The header annotation summarises each ladder's
mass: `Ladder A:  M = 26.4 kDa ± 0.4%  (z₀ = 8+, 6 rungs)`. Mass display
precision is picked from σ_M; the line turns amber if σ_M / M exceeds
1% (configurable via preset).

### Persistence

Three keys join `preset.json`:

```json
"ladder_labels": {
  "enabled": false,
  "tol_mz": 5.0,
  "sigma_amber_relative": 0.01
}
```

The ladders themselves are spectrum-specific and not persisted; create
them per spectrum.

### Caveats and limitations

- The labeler is a v1 prototype: manual input uses browser `prompt()`
  dialogs, which work but are visually plain.
- Designed for **native MS positive mode** (Synapt G2 QTOF) — formula:
  `M = z·(m/z) − z·m_H`. Negative mode is not supported in v1.
- Per-rung implied-`M` cross-check is visible only in the hover tooltip
  on each labeled peak. The header `M` is computed from the seed alone.
- No CSV export of labels in v1; processed CSV is unaffected.
```

- [ ] **Step 2: AGENTS.md — add a "How it works" bullet**

In `AGENTS.md`, in the **How it works** section (after the "Standalone
CSV buttons" bullet), append:

```markdown
- **Ladder labels** (opt-in, default off) — a self-contained JS module
  (`ladder_labeler.js`, inlined into the HTML at build time the same way
  Plotly is) annotates LCR charge-reduction ladders. Per ladder: typed
  `z₀` + precursor m/z OR closed-form solve from two clicked rungs;
  predicts m/z(z) = (M + z·m_H)/z for z = z₀−1 → 1; snaps each rung to
  the global max within ±`tol_mz` of the prediction. Multiple ladders
  per spectrum (distinct colors). Manual override per peak via
  click-prompt: integer → override z, `Ns` → re-seed, empty → delete.
  Default off in `preset.json`; full MS1 workflow is bit-identical when
  the labeler is disabled. Pure-math tests in
  `tests/ladder_labeler_test.html` (open in a browser). Spec:
  `docs/superpowers/specs/2026-05-22-ladder-labeling-design.md`.
```

- [ ] **Step 3: Run the full test suite one more time**

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 4: Open `tests/ladder_labeler_test.html` and confirm green summary**

Open the file in a browser. Expected: "60 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs(labeler): document ladder-labeling feature in README + AGENTS.md

README gets a 'Labeling the LCR ladder (opt-in)' section covering
type/two-click seeding, manual override prompts, per-ladder controls,
preset persistence, and caveats. AGENTS.md gets a one-paragraph 'How
it works' bullet pointing at ladder_labeler.js and the spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-review

After completing all tasks, verify against the spec:

| Spec section | Task(s) implementing it |
|---|---|
| §1 Problem & physical model | Documented in README + AGENTS.md (Task 14) |
| §2 Goals / non-goals | Architecture honored throughout; non-goals enforced (no CSV labels, no isotope math, no fragment ID) |
| §3.1 Module contract | Tasks 2–7, 10, 13 |
| §3.2 Ladder data model | Task 6 (and updated in Task 7) |
| §4.1 Ladder generation | Task 6 (`refreshLadder`) |
| §4.2 Snap algorithm | Task 4 (`snapToMaxInWindow`) |
| §4.3 Two-click solver | Task 3 (with multi-k sweep) |
| §4.4 Manual override | Task 13 (`handlePlotClick`) |
| §4.5 Re-snap on parameter change | Task 6 (manual labels preserved) + Task 11 (`refreshAll` called from `recompute`) |
| §5.1 Control panel | Task 9 (markup) + Task 12 (binding) |
| §5.2 On-plot layer (seed line + annotations) | Task 10 (`buildAnnotations`) |
| §5.3 Hover tooltip | Task 10 (`hovertext` on annotation) |
| §5.4 Header annotation + precision rule | Tasks 5 (`formatMass`/`formatSigma`) + 10 (header annotation) |
| §6 Edge cases | Distributed: z₀=1 in Task 6, two-click rejection in Task 3, snap window empty in Task 4, 0/N rungs in Task 10, overlapping rungs via `ay` offset in Task 10, smoothing change in Task 11 (`refreshAll` in `recompute`) |
| §7 Preset persistence | Task 1 |
| §8 File touchpoints | All tasks |
| §9 Testing | Tasks 2–7 (browser), Tasks 1/8/9 (Python) |
| §10 Integration story | Default off in Task 1; bit-identical when disabled enforced in Task 11 |
| Appendix A worked example | Implicitly verified by Task 6 tests (the synthetic spectrum is the worked-example geometry) |
| Appendix B derivation | Embodied in Task 3 (multi-k sweep) |

**Placeholder scan:** none in the plan — every code step has the actual code.

**Type/name consistency check:**
- `LadderLabelerCore` and `LadderLabeler` — both used consistently.
- `state.tolMz` (camelCase JS) ↔ `tol_mz` (snake_case Python preset) — keys match the spec; the JS reads the preset only via Python placeholders, so no name collision.
- `addLadderFromSeed({ mz, z }, specX, specY)` — same signature in Tasks 6, 7, 12, 13.
- `refreshLadder(id, specX, specY)` and `refreshAll(specX, specY)` — consistent throughout.
- `buildAnnotations(specX, specY)` — used the same way in Task 10 and Task 11.
- `handlePlotClick(clickedMz, specX, specY)` — consistent in Task 13.
- `__LADDER_LABELER__` placeholder — added in Task 8, referenced from `build_html` and the test there.
- `__LADDER_ENABLED__` / `__LADDER_TOL__` — added and substituted in Task 9.
- `renderLadderPanel` — defined in Task 12, called from Task 11's `recompute` hook (guarded with `typeof === 'function'`).

**Scope check:** focused on a single, opt-in module inside one existing file (with one small extracted JS file). Single implementation plan is appropriate.
