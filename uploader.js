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
      const allNumeric = tokens.length === 2 && nums.every(n => Number.isFinite(n));
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
                   `(line ${i + 1} has ${tokens.length} columns).`,
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

  function createStore() {
    const entries = [];      // array of spectrum objects
    let activeIdx = -1;

    function add(entry) {
      // Default fields so consumers can rely on the shape.
      const e = Object.assign({
        name: '<unnamed>',
        mz: [],
        intensity: [],
        precursor: null,
        parseStatus: 'ok',
        parseMessage: '',
        ladders: [],
        perSpectrumOverrides: {},
      }, entry);
      entries.push(e);
      if (activeIdx < 0 && e.parseStatus === 'ok') activeIdx = entries.length - 1;
      return e;
    }
    function all() { return entries; }
    function active() { return activeIdx >= 0 ? entries[activeIdx] : null; }
    function activeName() { return active() ? active().name : null; }
    function setActive(name) {
      const i = entries.findIndex(e => e.name === name);
      if (i >= 0 && entries[i].parseStatus === 'ok') activeIdx = i;
    }
    function remove(name) {
      const i = entries.findIndex(e => e.name === name);
      if (i < 0) return;
      entries.splice(i, 1);
      if (activeIdx === i) {
        // Activate the next ok spectrum, if any.
        activeIdx = entries.findIndex(e => e.parseStatus === 'ok');
      } else if (activeIdx > i) {
        activeIdx--;
      }
    }
    function clear() { entries.length = 0; activeIdx = -1; }

    return { add, all, active, activeName, setActive, remove, clear };
  }

  // ---- DOM glue: drop zone, picker, "Try example" ----
  // Pure functions above are unit-tested; the DOM glue below is exercised by
  // the manual smoke test (docs/uploader-release-smoke.md).

  function readFileText(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error('read failed'));
      r.readAsText(file);
    });
  }

  async function ingestFiles(files, store, onChange) {
    for (const f of files) {
      try {
        const text = await readFileText(f);
        const parsed = parseSpectrum(text);
        if (parsed.ok) {
          store.add({
            name: f.name,
            mz: parsed.mz,
            intensity: parsed.intensity,
            precursor: precursorFromName(f.name),
            parseStatus: 'ok',
          });
        } else {
          store.add({
            name: f.name, mz: [], intensity: [],
            parseStatus: 'error', parseMessage: parsed.message,
          });
        }
      } catch (e) {
        store.add({
          name: f.name, mz: [], intensity: [],
          parseStatus: 'error',
          parseMessage: 'Could not read this file.',
        });
      }
    }
    if (onChange) onChange();
  }

  // Recursively collect File objects from a dropped DataTransferItem entry.
  async function collectFilesFromEntry(entry, files) {
    if (entry.isFile) {
      await new Promise((res, rej) => entry.file(f => { files.push(f); res(); }, rej));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      // readEntries returns up to ~100 entries per call (Chrome's batch size).
      // Loop until it yields an empty array so folders >100 files load fully.
      let batch;
      do {
        batch = await new Promise(res => reader.readEntries(res));
        for (const sub of batch) await collectFilesFromEntry(sub, files);
      } while (batch.length > 0);
    }
  }

  async function ingestDataTransfer(dt, store, onChange) {
    const files = [];
    if (dt.items && dt.items.length && dt.items[0].webkitGetAsEntry) {
      for (const item of dt.items) {
        const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
        if (entry) await collectFilesFromEntry(entry, files);
        else if (item.getAsFile) { const f = item.getAsFile(); if (f) files.push(f); }
      }
    } else {
      for (const f of dt.files) files.push(f);
    }
    // Filter obvious non-spectra (e.g. .DS_Store, hidden files).
    const usable = files.filter(f =>
      !f.name.startsWith('.') && /\.(xy|csv|txt)$/i.test(f.name));
    await ingestFiles(usable, store, onChange);
  }

  function loadExampleSpectrum(store, onChange) {
    const b64 = (typeof window !== 'undefined' && window.__LCR_EXAMPLE_B64__) || '';
    if (!b64) return;
    const text = atob(b64);
    const parsed = parseSpectrum(text);
    if (!parsed.ok) return;
    store.add({
      name: 'example_spectrum.xy',
      mz: parsed.mz, intensity: parsed.intensity,
      precursor: precursorFromName('example_spectrum.xy'),
      parseStatus: 'ok',
    });
    if (onChange) onChange();
  }

  root.LCRUploader = root.LCRUploader || {};
  root.LCRUploader.parseSpectrum = parseSpectrum;
  root.LCRUploader.precursorFromName = precursorFromName;
  root.LCRUploader.createStore = createStore;
  root.LCRUploader.ingestFiles = ingestFiles;
  root.LCRUploader.ingestDataTransfer = ingestDataTransfer;
  root.LCRUploader.loadExampleSpectrum = loadExampleSpectrum;
})(typeof window !== 'undefined' ? window : global);
