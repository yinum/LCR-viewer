// uploader.js — file ingestion and parsing for LCR-viewer's uploader mode.
// Exposes window.LCRUploader.{ parseSpectrum, precursorFromName, ... }.
// Pure functions are isolated at the top so they can be unit-tested under Node
// without a DOM (see tests/run_node.js + tests/uploader_test.html).

(function (root) {
  'use strict';

  // Tolerant 2-column tokenizer. Splits on whitespace OR comma OR tab; skips
  // blank lines and obvious header lines until it sees the first all-numeric
  // 2-token row. Once numeric parsing has begun, an un-parseable line aborts
  // with a friendly message naming the line number.
  function parseSpectrum(text) {
    if (!text || !text.trim()) {
      return { ok: false, message: 'This file is empty.' };
    }
    const lines = text.split(/\r?\n/);
    const mz = [], it = [];
    let started = false;
    for (let i = 0; i < lines.length; i++) {
      const raw = lines[i].trim();
      if (!raw) continue;
      const tokens = raw.split(/[\s,\t]+/).filter(t => t.length);
      const nums = tokens.map(Number);
      const allNumeric = tokens.length >= 2 && nums.every(n => Number.isFinite(n));
      if (!started) {
        if (allNumeric) {
          started = true;
          mz.push(nums[0]); it.push(nums[1]);
        }
        // else: header / comment, skip silently
        continue;
      }
      if (!allNumeric || tokens.length !== 2) {
        return {
          ok: false,
          message: "This file doesn't look like a 2-column spectrum " +
                   `(line ${i + 1} has ${tokens.length} numbers).`,
        };
      }
      mz.push(nums[0]); it.push(nums[1]);
    }
    if (mz.length === 0) {
      return { ok: false, message: "Couldn't read any numbers from this file." };
    }
    return { ok: true, mz, intensity: it };
  }

  // Filename precursor: trailing number (integer or decimal), as the Python
  // mirror in build_lcr_viewer.py does. The number must be the last numeric
  // run before the extension; a leading number alone does not count.
  function precursorFromName(name) {
    const stem = name.replace(/\.[^.]+$/, '');  // strip extension
    const m = stem.match(/(\d+(?:\.\d+)?)$/);
    return m ? Number(m[1]) : null;
  }

  root.LCRUploader = root.LCRUploader || {};
  root.LCRUploader.parseSpectrum = parseSpectrum;
  root.LCRUploader.precursorFromName = precursorFromName;
})(typeof window !== 'undefined' ? window : global);
