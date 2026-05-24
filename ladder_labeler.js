// ladder_labeler.js — opt-in ladder-labeling module for polyP_LCR_viewer.
// Spec: docs/superpowers/specs/2026-05-22-ladder-labeling-design.md
//
// This file is loaded two ways:
//   1. Inlined into the viewer HTML at build time by build_lcr_viewer.py
//      (via the LADDER_LABELER template placeholder).
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

  // Unscale: divide y by scale when m/z is at or above the LCR scaling
  // threshold; otherwise return y unchanged. scale=1 (or 0, defensive)
  // is a no-op everywhere. Used so AUC integrates the pre-LCR-scale
  // signal regardless of whether the user has scaling toggled on.
  function unscaleY(mz, y, threshold, scale) {
    if (mz >= threshold && scale > 1) return y / scale;
    return y;
  }

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
    return '± ' + (rel * 100).toFixed(1) + '%';
  }

  return { M_H, computeM, predictRung, unscaleY, solveFromTwoClicks,
           snapToMaxInWindow, findValleyBounds, trapzAuc,
           _stdDev, formatMass, formatSigma };
})();

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
    threshold: Infinity,      // m/z at/above which intensity is LCR-scaled
    scale: 1,                 // multiplier the viewer applied above threshold
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
      excludedZ: new Set(),
      aucSum: 0,
      isPartial: false,
      abundance: null,
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
    // Manual labels take precedence over auto rungs at the same z.
    const manualZ = new Set(manualPreserved.map(lb => lb.z));
    for (const z of _candidateRungs(L.seed.z)) {
      if (manualZ.has(z)) continue;  // skip; the preserved manual at this z is re-added below
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

    // Replace label objects with new copies rather than mutating in place,
    // so a caller that holds a reference into L.labels through the call is
    // not surprised by sudden field changes on the object they kept. All
    // fields (mzObs, mzPred, mImplied, manual, stale…) are shallow-copied;
    // only .auc is overwritten.
    const aucByZ = new Map();
    for (const lb of L.labels) {
      aucByZ.set(lb.z, lb.mzObs === null ? null : 0);
    }

    let sum = 0;
    for (let i = 0; i < snapped.length; i++) {
      const lb = snapped[i];
      const prev = snapped[i - 1];
      const next = snapped[i + 1];
      const mzLoCap = prev ? 0.5 * (prev.mzObs + lb.mzObs) : (lb.mzObs - state.tolMz);
      const mzHiCap = next ? 0.5 * (lb.mzObs + next.mzObs) : (lb.mzObs + state.tolMz);
      const vb = C.findValleyBounds(lb.mzObs, mzLoCap, mzHiCap, specX, specY);
      if (vb === null) { continue; }
      const auc = C.trapzAuc(vb.iLo, vb.iHi, specX, specY, unscale);
      aucByZ.set(lb.z, auc);
      if (!lb.stale && !L.excludedZ.has(lb.z)) sum += auc;
    }

    // Replace label objects with updated copies.
    L.labels = L.labels.map(lb => Object.assign({}, lb, { auc: aucByZ.get(lb.z) }));

    L.aucSum = sum;
    L.isPartial = L.labels.some(lb =>
      lb.mzObs === null || lb.stale || L.excludedZ.has(lb.z));
  }

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

      // 2. Per-rung annotations (spec §5.2, §5.3 hover).
      // The neutral-mass M summary (spec §5.4) is rendered in the side-panel
      // ladder row by renderLadderPanel() in build_lcr_viewer.py — keeping the
      // plot clear of the box that previously overlaid low-m/z peaks.
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
          hovertext: 'Ladder ' + L.id + ' — z = ' + lb.z + '+\nM = '
                   + hoverM + ' (this rung)' + (lb.stale ? ' [stale]' : ''),
          opacity: lb.stale ? 0.4 : 1.0,
        });
      }
      ladderIdx++;
    }
    return { annotations: annots, shapes };
  }

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
})();
