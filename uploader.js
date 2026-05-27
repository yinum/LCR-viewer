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

  // Add a spectrum from a pasted text block. Returns {ok, message} so the
  // dialog can show a parse error inline rather than as a new ✗ row.
  function ingestPastedText(text, nameInput, store, onChange) {
    const parsed = parseSpectrum(text);
    if (!parsed.ok) return { ok: false, message: parsed.message };
    let name = (nameInput || '').trim();
    if (!name) name = 'pasted_' + Date.now().toString(36);
    if (!/\.(xy|csv|txt)$/i.test(name)) name += '.xy';
    store.add({
      name: name,
      mz: parsed.mz, intensity: parsed.intensity,
      precursor: precursorFromName(name),
      parseStatus: 'ok',
    });
    if (onChange) onChange();
    return { ok: true };
  }

  function isUploaderBuild() {
    return typeof window !== 'undefined' && !!window.__LCR_BUILD__ &&
           window.__LCR_BUILD__ !== 'default';
  }

  function renderSidebar(store) {
    const ul = document.getElementById('uploader-list');
    if (!ul) return;
    ul.innerHTML = '';
    const entries = store.all();
    for (const e of entries) {
      const li = document.createElement('li');
      li.style.cssText = 'padding:5px 6px;margin:2px 0;border-radius:3px;' +
        'cursor:pointer;display:flex;justify-content:space-between;' +
        'align-items:center;' +
        (store.active() === e ? 'background:#d6e9ff;font-weight:600;' :
                                'background:#fff;');
      const badge = e.parseStatus === 'ok' ? '✓' : '✗';
      const left = document.createElement('span');
      left.title = e.parseStatus === 'ok' ? e.name : e.parseMessage || e.name;
      left.textContent = `${badge}  ${e.name}`;
      left.style.cssText = 'overflow:hidden;text-overflow:ellipsis;' +
        'white-space:nowrap;flex:1';
      const x = document.createElement('button');
      x.textContent = '✕';
      x.style.cssText = 'font-size:10px;padding:0 4px;margin-left:4px;' +
        'border:none;background:transparent;cursor:pointer;color:#999';
      x.addEventListener('click', (ev) => {
        ev.stopPropagation();
        store.remove(e.name);
        onStoreChange();
      });
      li.append(left, x);
      li.addEventListener('click', () => {
        if (e.parseStatus !== 'ok') return;
        store.setActive(e.name);
        onStoreChange();
      });
      ul.appendChild(li);
    }
  }

  function showEmptyState(show) {
    const empty = document.getElementById('uploader-empty');
    const sidebar = document.getElementById('uploader-sidebar');
    const offset = document.getElementById('uploader-pane-offset');
    const style = document.getElementById('uploader-style');
    if (!empty) return;
    empty.hidden = !show;
    if (sidebar) sidebar.hidden = show;
    if (offset) offset.hidden = show;
    if (style) style.disabled = show;
    // Hide the rest of the viewer when on the landing page.
    for (const id of ['controls', 'plot']) {
      const el = document.getElementById(id);
      if (el) el.style.display = show ? 'none' : '';
    }
    document.querySelectorAll('.hint').forEach(el =>
      el.style.display = show ? 'none' : '');
  }

  let store, onStoreChange;
  let _previousActiveName = null;

  function onStoreChange_impl() {
    // Stash outgoing ladders.
    if (_previousActiveName && typeof LadderLabeler !== 'undefined' &&
        LadderLabeler.serializeState) {
      const prev = store.all().find(e => e.name === _previousActiveName);
      if (prev) prev.ladders = LadderLabeler.serializeState();
    }
    const a = store.active();
    if (!a) {
      showEmptyState(true);
      renderSidebar(store);
      refreshBulkBtn();
      _previousActiveName = null;
      return;
    }
    showEmptyState(false);
    renderSidebar(store);
    refreshBulkBtn();
    // Restore incoming ladders BEFORE loadSpectrum triggers recompute,
    // so refreshAll / Plotly.react draw the correct annotations on the first pass.
    if (typeof LadderLabeler !== 'undefined' && LadderLabeler.loadState) {
      LadderLabeler.loadState(a.ladders || []);
    }
    // Hand the active spectrum to the existing viewer entry point.
    const csvName = a.name.replace(/\.[^.]+$/, '') + '.csv';
    if (typeof loadSpectrum === 'function') {
      loadSpectrum(a.mz, a.intensity, csvName);
    }
    _previousActiveName = a.name;
  }

  function initUploader() {
    if (!isUploaderBuild()) return;
    store = createStore();
    onStoreChange = onStoreChange_impl;
    showEmptyState(true);

    const drop = document.getElementById('uploader-drop');
    const picker = document.getElementById('uploader-picker');
    const pickerMore = document.getElementById('uploader-picker-more');
    const addMore = document.getElementById('uploader-add-more');
    const example = document.getElementById('uploader-try-example');

    if (drop) {
      drop.addEventListener('click', () => picker && picker.click());
      drop.addEventListener('dragover', ev => {
        ev.preventDefault();
        drop.style.background = '#eaeaea';
      });
      drop.addEventListener('dragleave', () => drop.style.background = '#fafafa');
      drop.addEventListener('drop', async (ev) => {
        ev.preventDefault();
        drop.style.background = '#fafafa';
        await ingestDataTransfer(ev.dataTransfer, store, onStoreChange);
      });
    }
    if (picker) picker.addEventListener('change', async (ev) => {
      await ingestFiles(ev.target.files, store, onStoreChange);
      ev.target.value = '';
    });
    if (pickerMore) pickerMore.addEventListener('change', async (ev) => {
      await ingestFiles(ev.target.files, store, onStoreChange);
      ev.target.value = '';
    });
    if (addMore) addMore.addEventListener('click', () =>
      pickerMore && pickerMore.click());
    if (example) example.addEventListener('click', () =>
      loadExampleSpectrum(store, onStoreChange));

    const dlAll = document.getElementById('dl-all-zip');
    if (dlAll) dlAll.addEventListener('click', buildAllCsvsZip);

    const pasteOpenA = document.getElementById('uploader-paste');
    const pasteOpenB = document.getElementById('uploader-paste-more');
    const pasteModal = document.getElementById('uploader-paste-modal');
    const pasteText = document.getElementById('uploader-paste-text');
    const pasteName = document.getElementById('uploader-paste-name');
    const pasteErr = document.getElementById('uploader-paste-err');
    const pasteCancel = document.getElementById('uploader-paste-cancel');
    const pasteAdd = document.getElementById('uploader-paste-add');
    function openPaste() {
      if (!pasteModal) return;
      pasteText.value = ''; pasteName.value = ''; pasteErr.textContent = '';
      pasteModal.hidden = false;
      setTimeout(() => pasteText.focus(), 0);
    }
    function closePaste() { if (pasteModal) pasteModal.hidden = true; }
    if (pasteOpenA) pasteOpenA.addEventListener('click', openPaste);
    if (pasteOpenB) pasteOpenB.addEventListener('click', openPaste);
    if (pasteCancel) pasteCancel.addEventListener('click', closePaste);
    if (pasteModal) pasteModal.addEventListener('click', (ev) => {
      if (ev.target === pasteModal) closePaste();
    });
    if (pasteAdd) pasteAdd.addEventListener('click', () => {
      const res = ingestPastedText(pasteText.value, pasteName.value,
                                   store, onStoreChange);
      if (res.ok) closePaste();
      else pasteErr.textContent = res.message || 'Could not parse.';
    });

    const collapseBtn = document.getElementById('uploader-collapse');
    const expandBtn = document.getElementById('uploader-expand');
    if (collapseBtn) collapseBtn.addEventListener('click', () => {
      document.body.classList.add('sidebar-collapsed');
      if (typeof Plotly !== 'undefined' && Plotly.Plots && Plotly.Plots.resize) {
        Plotly.Plots.resize('plot');
      }
    });
    if (expandBtn) expandBtn.addEventListener('click', () => {
      document.body.classList.remove('sidebar-collapsed');
      if (typeof Plotly !== 'undefined' && Plotly.Plots && Plotly.Plots.resize) {
        Plotly.Plots.resize('plot');
      }
    });
  }

  // Run after DOMContentLoaded so the static HTML is parsed.
  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initUploader);
    } else {
      initUploader();
    }
  }

  function showErrorPanel(err) {
    const panel = document.getElementById('uploader-errpanel');
    const body = document.getElementById('uploader-errbody');
    if (!panel || !body) return;
    const a = store && store.active && store.active();
    const stack = (err && err.stack) ? err.stack.split('\n').slice(0, 6).join('\n')
                                     : '(no stack)';
    body.textContent =
      `LCR-viewer ${window.__LCR_BUILD__ || 'unknown'}\n` +
      `Browser: ${navigator.userAgent}\n` +
      `Active file: ${a ? a.name : 'none'}\n` +
      `Spectra loaded: ${store ? store.all().length : 0}\n` +
      `Error: ${err && err.message || String(err)}\n` +
      `Stack: ${stack}`;
    panel.hidden = false;
  }

  async function buildAllCsvsZip() {
    if (typeof JSZip === 'undefined') throw new Error('JSZip not loaded');
    if (!store) return;
    const zip = new JSZip();
    for (const e of store.all()) {
      if (e.parseStatus !== 'ok') continue;
      const csv = (typeof buildProcessedCsvForSpectrum === 'function')
        ? buildProcessedCsvForSpectrum(e.mz, e.intensity)
        : '';
      const name = e.name.replace(/\.[^.]+$/, '') + '_processed.csv';
      zip.file(name, csv);
    }
    const blob = await zip.generateAsync({ type: 'blob' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'LCR_processed_csvs.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  }

  function refreshBulkBtn() {
    const btn = document.getElementById('dl-all-zip');
    if (!btn) return;
    const ok = store ? store.all().filter(e => e.parseStatus === 'ok').length : 0;
    btn.hidden = ok < 2;
  }

  function initErrorPanel() {
    if (!isUploaderBuild()) return;
    window.addEventListener('error', ev => showErrorPanel(ev.error || ev));
    window.addEventListener('unhandledrejection', ev =>
      showErrorPanel(ev.reason || ev));
    const copy = document.getElementById('uploader-errcopy');
    const close = document.getElementById('uploader-errclose');
    const body = document.getElementById('uploader-errbody');
    if (copy) copy.addEventListener('click', () => {
      if (!body) return;
      navigator.clipboard.writeText(body.textContent).catch(() => {
        // Fallback: select-all so the user can Cmd-C manually.
        const r = document.createRange(); r.selectNode(body);
        getSelection().removeAllRanges(); getSelection().addRange(r);
      });
      copy.textContent = 'Copied!';
      setTimeout(() => copy.textContent = 'Copy', 1500);
    });
    if (close) close.addEventListener('click', () => {
      const p = document.getElementById('uploader-errpanel');
      if (p) p.hidden = true;
    });
  }

  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initErrorPanel);
    } else {
      initErrorPanel();
    }
  }

  root.LCRUploader = root.LCRUploader || {};
  root.LCRUploader.parseSpectrum = parseSpectrum;
  root.LCRUploader.precursorFromName = precursorFromName;
  root.LCRUploader.createStore = createStore;
  root.LCRUploader.ingestFiles = ingestFiles;
  root.LCRUploader.ingestDataTransfer = ingestDataTransfer;
  root.LCRUploader.loadExampleSpectrum = loadExampleSpectrum;
  root.LCRUploader.ingestPastedText = ingestPastedText;
  root.LCRUploader.isUploaderBuild = isUploaderBuild;
  root.LCRUploader.renderSidebar = renderSidebar;  // exposed for tests
  root.LCRUploader.initUploader = initUploader;
  root.LCRUploader.showErrorPanel = showErrorPanel;
  root.LCRUploader.buildAllCsvsZip = buildAllCsvsZip;
  root.LCRUploader.refreshBulkBtn = refreshBulkBtn;
})(typeof window !== 'undefined' ? window : global);
