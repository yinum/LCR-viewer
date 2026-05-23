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

  // Closed-form charge recovery from any two ladder rungs (positive mode).
  // Multi-k sweep handles non-adjacent picks: when gcd(z₁, k) = 1, only the
  // correct k yields an integer-close result. When gcd(z₁, k) > 1 (e.g.,
  // m₂/m₁ is rational), multiple k's all give integer-close zRaw — argmin_err
  // returns the smallest-err candidate, which in practice is the smallest k
  // (the simplest interpretation). Users can re-seed if a larger-M reading
  // is needed. See spec §4.3 and Appendix B.
  function solveFromTwoClicks(m1, m2) {
    if (m1 > m2) { const t = m1; m1 = m2; m2 = t; }
    if (m2 - m1 < 1.0) return null;            // identical or too-close clicks
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

  return { M_H, computeM, predictRung, solveFromTwoClicks, snapToMaxInWindow };
})();
