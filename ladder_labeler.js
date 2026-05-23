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
