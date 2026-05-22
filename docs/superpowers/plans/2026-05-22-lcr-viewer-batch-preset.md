# LCR Viewer — Preset + Batch + Auto-threshold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `build_lcr_viewer.py` reusable across many polyP LCR spectra — locked-in preset parameters, per-spectrum auto-threshold, folder batch input, named outputs, and a live-synced CSV.

**Architecture:** Keep one Python module (`build_lcr_viewer.py`). Extract the pipeline into small pure functions (parse, segment, auto-threshold, naming, input enumeration, HTML build) so they are unit-testable, then rewrite `main()` to iterate inputs. The generated HTML gains preset defaults and a File System Access API "linked CSV" feature.

**Tech Stack:** Python 3 standard library only (`os`, `sys`, `json`, `datetime`). Tests use stdlib `unittest` (no new dependency). The viewer is self-contained HTML + inlined Plotly + vanilla JS.

**Branch:** All work on `lcr-viewer-batch-preset`. The design spec (`docs/superpowers/specs/2026-05-21-lcr-viewer-batch-preset-design.md`) commit is pending an infrastructure outage — commit it first if `git log` does not show it.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `build_lcr_viewer.py` (modify) | `PRESET` dict; pure functions `parse_spectrum`, `find_segments`, `auto_threshold`, `precursor_mz`, `output_filename`, `iter_spectrum_files`, `build_html`; rewritten `main()`. HTML `TEMPLATE` gains preset placeholders + linked-CSV JS. |
| `tests/__init__.py` (create) | Empty — makes `tests` an importable package. |
| `tests/test_build_lcr_viewer.py` (create) | `unittest` tests for every pure function plus a `main()` integration test. |
| `README.md` (modify) | User-facing: file-or-folder usage, preset, auto-threshold, output location, linked CSV. |
| `AGENTS.md` (modify) | Agent-facing version of the same. |

Run all tests from the repo root: `python3 -m unittest discover -s tests -v`

---

## Task 1: Test scaffold + `parse_spectrum`

Extract the inline file-parsing loop from `main()` into a reusable, comma-tolerant function.

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_build_lcr_viewer.py`
- Modify: `build_lcr_viewer.py` (add function near top, after imports)

- [ ] **Step 1: Create the empty package marker**

Create `tests/__init__.py` with no content (empty file).

- [ ] **Step 2: Write the failing test**

Create `tests/test_build_lcr_viewer.py`:

```python
import os, sys, unittest, tempfile, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_lcr_viewer as blv


class TestParseSpectrum(unittest.TestCase):
    def _write(self, text):
        fh = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        fh.write(text)
        fh.close()
        return fh.name

    def test_whitespace_and_comma_rows(self):
        path = self._write("100.0 5\n200.5\t8\n300.0,3\njunk line\n")
        mz, it = blv.parse_spectrum(path)
        os.unlink(path)
        self.assertEqual(mz, [100.0, 200.5, 300.0])
        self.assertEqual(it, [5.0, 8.0, 3.0])

    def test_empty_file_raises(self):
        path = self._write("not numbers\n")
        with self.assertRaises(ValueError):
            blv.parse_spectrum(path)
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'build_lcr_viewer' has no attribute 'parse_spectrum'`

- [ ] **Step 4: Implement `parse_spectrum`**

In `build_lcr_viewer.py`, after the `import` line (line 23), add:

```python
def parse_spectrum(path):
    """Read a 2-column m/z, intensity file (whitespace- or comma-delimited).
    Returns (mz, it) lists of floats. Raises ValueError if no numeric rows."""
    mz, it = [], []
    with open(path) as fh:
        for line in fh:
            parts = line.replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    mz.append(float(parts[0]))
                    it.append(float(parts[1]))
                except ValueError:
                    pass
    if not mz:
        raise ValueError("No numeric data parsed from " + path)
    return mz, it
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 2 tests in `TestParseSpectrum`

- [ ] **Step 6: Commit**

```bash
git add tests/__init__.py tests/test_build_lcr_viewer.py build_lcr_viewer.py
git commit -m "Add parse_spectrum function and unittest scaffold" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `find_segments` — gap-based peak segmentation

Split the spectrum indices into contiguous peak-group segments at large m/z gaps, mirroring the in-HTML `buildGrid` logic so Python and JS agree.

**Files:**
- Modify: `build_lcr_viewer.py` (add function after `parse_spectrum`)
- Modify: `tests/test_build_lcr_viewer.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__` line:

```python
class TestFindSegments(unittest.TestCase):
    def test_two_clusters_split_at_large_gap(self):
        # cluster A: 100.0..100.6 step 0.2 ; big gap ; cluster B: 150.0..150.4
        mz = [100.0, 100.2, 100.4, 100.6, 150.0, 150.2, 150.4]
        segs = blv.find_segments(mz)
        self.assertEqual(segs, [(0, 3), (4, 6)])

    def test_single_cluster_one_segment(self):
        mz = [100.0, 100.2, 100.4, 100.6]
        self.assertEqual(blv.find_segments(mz), [(0, 3)])

    def test_empty_input(self):
        self.assertEqual(blv.find_segments([]), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'find_segments'`

- [ ] **Step 3: Implement `find_segments`**

In `build_lcr_viewer.py`, after `parse_spectrum`, add:

```python
def find_segments(mz):
    """Split indices into contiguous peak-group segments at large m/z gaps.
    Returns a list of (start, end) inclusive index pairs. Mirrors the
    gap-detection in the in-HTML buildGrid: median small gap x 60, floored
    at 1.0 m/z."""
    n = len(mz)
    if n == 0:
        return []
    small = sorted(mz[i] - mz[i - 1] for i in range(1, n)
                   if 0 < mz[i] - mz[i - 1] < 0.5)
    dx0 = small[(len(small) - 1) // 2] if small else 0.02
    gap_thr = max(1.0, dx0 * 60)
    segs, start = [], 0
    for i in range(1, n):
        if mz[i] - mz[i - 1] > gap_thr:
            segs.append((start, i - 1))
            start = i
    segs.append((start, n - 1))
    return segs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 3 tests in `TestFindSegments`

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add find_segments gap-based peak segmentation" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `auto_threshold` + `precursor_mz`

Both rest on the base peak (the parent envelope apex). `precursor_mz` rounds the base-peak m/z; `auto_threshold` places the scaling threshold just past the right edge of the base-peak's segment.

**Files:**
- Modify: `build_lcr_viewer.py` (add functions + `THRESHOLD_MARGIN` constant after `find_segments`)
- Modify: `tests/test_build_lcr_viewer.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__` line:

```python
class TestBasePeakAnalysis(unittest.TestCase):
    # parent envelope 100.0..100.6 (base peak at 100.2, intensity 90);
    # charge-reduced cluster 150.0..150.4 (small)
    MZ = [100.0, 100.2, 100.4, 100.6, 150.0, 150.2, 150.4]
    IT = [40.0, 90.0, 50.0, 10.0, 4.0, 6.0, 3.0]

    def test_precursor_mz_is_rounded_base_peak(self):
        self.assertEqual(blv.precursor_mz(self.MZ, self.IT), 100)

    def test_threshold_sits_just_past_parent_edge(self):
        thr = blv.auto_threshold(self.MZ, self.IT)
        # parent segment right edge is 100.6; threshold lands in the valley
        # before the next cluster at 150.0
        self.assertGreater(thr, 100.6)
        self.assertLess(thr, 150.0)

    def test_threshold_margin_clamped_to_half_gap(self):
        # fine 0.01 spacing -> gap threshold floors at 1.0, so a 1.5 m/z gap
        # splits the clusters; gap/2 (0.75) is below THRESHOLD_MARGIN (2.0),
        # so the margin is clamped to 0.75
        mz = [100.00, 100.01, 100.02, 100.03, 101.53, 101.54, 101.55]
        it = [40.0, 90.0, 50.0, 10.0, 5.0, 6.0, 4.0]
        thr = blv.auto_threshold(mz, it)
        self.assertAlmostEqual(thr, 100.78, delta=1e-4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'precursor_mz'`

- [ ] **Step 3: Implement the functions**

In `build_lcr_viewer.py`, after `find_segments`, add:

```python
THRESHOLD_MARGIN = 2.0  # m/z placed just past the parent envelope


def _base_peak_index(it):
    """Index of the most intense point."""
    bi = 0
    for i in range(1, len(it)):
        if it[i] > it[bi]:
            bi = i
    return bi


def precursor_mz(mz, it):
    """Precursor ion m/z = base-peak (parent envelope apex) m/z, rounded."""
    return int(round(mz[_base_peak_index(it)]))


def auto_threshold(mz, it):
    """Scaling threshold m/z, placed just past the right edge of the parent
    envelope (the segment containing the base peak), clamped to stay within
    the empty valley before the next cluster."""
    bi = _base_peak_index(it)
    segs = find_segments(mz)
    parent = next(s for s in segs if s[0] <= bi <= s[1])
    right_mz = mz[parent[1]]
    later = [s for s in segs if s[0] > parent[1]]
    if later:
        gap = mz[later[0][0]] - right_mz
        margin = min(THRESHOLD_MARGIN, gap / 2)
    else:
        margin = THRESHOLD_MARGIN
    return right_mz + margin
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 3 tests in `TestBasePeakAnalysis`

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add auto_threshold and precursor_mz" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `output_filename`

Build the per-spectrum output filename `LCR_mz<precursor>_<YYYYMMDD-HHMM>.html`.

**Files:**
- Modify: `build_lcr_viewer.py` (add `import datetime` to the import line; add function)
- Modify: `tests/test_build_lcr_viewer.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__` line:

```python
class TestOutputFilename(unittest.TestCase):
    def test_name_format(self):
        when = datetime.datetime(2026, 5, 22, 9, 7)
        name = blv.output_filename(2092, when)
        self.assertEqual(name, "LCR_mz2092_20260522-0907.html")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'output_filename'`

- [ ] **Step 3: Implement `output_filename`**

In `build_lcr_viewer.py`, change the import line `import sys, os, json` to:

```python
import sys, os, json, datetime
```

Then add after `auto_threshold`:

```python
def output_filename(precursor, when=None):
    """Per-spectrum viewer filename: LCR_mz<precursor>_<YYYYMMDD-HHMM>.html"""
    when = when or datetime.datetime.now()
    return "LCR_mz%d_%s.html" % (precursor, when.strftime("%Y%m%d-%H%M"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 1 test in `TestOutputFilename`

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add output_filename naming helper" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `iter_spectrum_files`

Resolve an input path to a list of spectrum files: a file yields itself, a directory yields its sorted `.txt`/`.csv` contents.

**Files:**
- Modify: `build_lcr_viewer.py` (add function after `output_filename`)
- Modify: `tests/test_build_lcr_viewer.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__` line:

```python
class TestIterSpectrumFiles(unittest.TestCase):
    def test_single_file_yields_itself(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        fh.close()
        self.assertEqual(blv.iter_spectrum_files(fh.name), [fh.name])
        os.unlink(fh.name)

    def test_directory_yields_sorted_txt_and_csv(self):
        d = tempfile.mkdtemp()
        for name in ["b.txt", "a.csv", "skip.json", ".hidden.txt"]:
            open(os.path.join(d, name), "w").close()
        got = [os.path.basename(p) for p in blv.iter_spectrum_files(d)]
        self.assertEqual(got, ["a.csv", "b.txt"])
        for name in os.listdir(d):
            os.unlink(os.path.join(d, name))
        os.rmdir(d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'iter_spectrum_files'`

- [ ] **Step 3: Implement `iter_spectrum_files`**

In `build_lcr_viewer.py`, after `output_filename`, add:

```python
def iter_spectrum_files(path):
    """Resolve an input path to a list of spectrum files. A file -> [file];
    a directory -> its sorted non-hidden .txt and .csv files (non-recursive)."""
    if os.path.isdir(path):
        out = []
        for name in sorted(os.listdir(path)):
            if name.startswith("."):
                continue
            if name.lower().endswith((".txt", ".csv")):
                out.append(os.path.join(path, name))
        return out
    return [path]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 2 tests in `TestIterSpectrumFiles`

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add iter_spectrum_files input enumeration" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `PRESET` + HTML template placeholders + `build_html`

Add the preset dict, convert the HTML `TEMPLATE` control defaults to placeholders, and add `build_html` to assemble a viewer from data + threshold.

**Files:**
- Modify: `build_lcr_viewer.py` (add `PRESET`; edit `TEMPLATE` control block; add `build_html`)
- Modify: `tests/test_build_lcr_viewer.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__` line:

```python
class TestBuildHtml(unittest.TestCase):
    MZ = [100.0, 100.2, 100.4, 150.0, 150.2]
    IT = [40.0, 90.0, 50.0, 4.0, 6.0]

    def test_preset_values_baked_in(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/")
        self.assertIn('id="scale" value="10"', html)
        self.assertIn('id="win" value="299"', html)
        self.assertIn('id="thr" value="123.45"', html)
        self.assertIn('value="avg" selected', html)
        # overlay preset is False -> rawov checkbox must NOT be checked
        self.assertNotIn('id="rawov" checked', html)
        # data and plotly are inlined
        self.assertIn("/*plotly*/", html)
        self.assertNotIn("__MZ__", html)
        self.assertNotIn("__SCALE__", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_html'`

- [ ] **Step 3: Add the `PRESET` dict**

In `build_lcr_viewer.py`, after the import line, before `parse_spectrum`, add:

```python
# Tuned processing preset applied as the default for every generated viewer.
# Editing these values is the supported way to change the saved parameters.
PRESET = {
    "scale": 10,            # charge-reduced x factor
    "method": "avg",        # smoothing method (adjacent averaging)
    "window": 299,          # smoothing window (odd)
    "poly": 3,              # SG poly order, retained for the SG control
    "show_overlay": False,  # pre-smoothing overlay checkbox default
}
```

- [ ] **Step 4: Convert the `TEMPLATE` control defaults to placeholders**

In the `TEMPLATE` string, replace this block:

```
 <div class="ctl"><label>Charge-reduced x factor</label>
   <input type="number" id="scale" value="50" step="1" min="1"></div>
 <div class="ctl"><label>Scale applies above m/z</label>
   <input type="number" id="thr" value="2160" step="5"></div>
 <div class="ctl"><label>Smoothing method</label>
   <select id="method">
     <option value="none">None (raw)</option>
     <option value="sg" selected>Savitzky-Golay</option>
     <option value="avg">Adjacent averaging</option>
     <option value="gauss">Gaussian</option>
     <option value="binom">Binomial</option>
     <option value="median">Median / percentile</option>
   </select></div>
 <div class="ctl"><label>Window (odd pts)</label>
   <input type="number" id="win" value="11" step="2" min="3"></div>
 <div class="ctl"><label>Poly order (SG)</label>
   <input type="number" id="poly" value="3" step="1" min="1" max="6"></div>
 <div class="ctl chk">
   <label><input type="checkbox" id="rawov" checked> pre-smoothing overlay</label>
```

with (note: no `selected` on any option — Python adds it; `value` attributes become placeholders):

```
 <div class="ctl"><label>Charge-reduced x factor</label>
   <input type="number" id="scale" value="__SCALE__" step="1" min="1"></div>
 <div class="ctl"><label>Scale applies above m/z</label>
   <input type="number" id="thr" value="__THR__" step="5"></div>
 <div class="ctl"><label>Smoothing method</label>
   <select id="method">
     <option value="none">None (raw)</option>
     <option value="sg">Savitzky-Golay</option>
     <option value="avg">Adjacent averaging</option>
     <option value="gauss">Gaussian</option>
     <option value="binom">Binomial</option>
     <option value="median">Median / percentile</option>
   </select></div>
 <div class="ctl"><label>Window (odd pts)</label>
   <input type="number" id="win" value="__WIN__" step="2" min="3"></div>
 <div class="ctl"><label>Poly order (SG)</label>
   <input type="number" id="poly" value="__POLY__" step="1" min="1" max="6"></div>
 <div class="ctl chk">
   <label><input type="checkbox" id="rawov" __RAWOV__> pre-smoothing overlay</label>
```

- [ ] **Step 5: Implement `build_html`**

In `build_lcr_viewer.py`, after `iter_spectrum_files`, add:

```python
def build_html(mz, it, thr, plotly):
    """Assemble a self-contained viewer HTML from spectrum data, the
    per-spectrum threshold, and the inlined Plotly bundle. Control defaults
    come from PRESET."""
    html = TEMPLATE
    html = html.replace("__SCALE__", str(PRESET["scale"]))
    html = html.replace("__THR__", "%g" % thr)
    html = html.replace("__WIN__", str(PRESET["window"]))
    html = html.replace("__POLY__", str(PRESET["poly"]))
    html = html.replace("__RAWOV__", "checked" if PRESET["show_overlay"] else "")
    html = html.replace('value="%s"' % PRESET["method"],
                        'value="%s" selected' % PRESET["method"])
    html = html.replace("__MZ__", json.dumps(mz))
    html = html.replace("__IT__", json.dumps(it))
    html = html.replace("__PLOTLY__", plotly)
    return html
```

Note: the test expects `value="123.45"`; `"%g" % 123.45` yields `123.45`. The `value="%s"` method replacement targets the single `<option value="avg">` line.

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 1 test in `TestBuildHtml`

- [ ] **Step 7: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add PRESET defaults and build_html with template placeholders" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Linked-CSV live sync in the viewer

Add a "Link CSV file" button to the viewer that uses the File System Access API to auto-rewrite a chosen CSV on every parameter change; keep the existing download button as a universal fallback.

**Files:**
- Modify: `build_lcr_viewer.py` (`TEMPLATE`: controls block + script block)
- Modify: `tests/test_build_lcr_viewer.py` (extend `TestBuildHtml`)

- [ ] **Step 1: Write the failing test**

In `tests/test_build_lcr_viewer.py`, add this method inside the existing `TestBuildHtml` class:

```python
    def test_linked_csv_feature_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/")
        self.assertIn('id="link"', html)          # Link CSV button
        self.assertIn("showSaveFilePicker", html)  # File System Access API
        self.assertIn("buildCSV", html)            # shared CSV helper
        self.assertIn('id="dl"', html)             # download fallback kept
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AssertionError: 'id="link"' not found`

- [ ] **Step 3: Add the Link button to the controls block**

In `TEMPLATE`, replace this line:

```
 <div class="ctl"><button id="dl">Download processed CSV</button></div>
```

with:

```
 <div class="ctl"><button id="dl">Download processed CSV</button></div>
 <div class="ctl"><button id="link">Link CSV file (live)</button>
   <span id="csvstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
```

- [ ] **Step 4: Replace the download handler with the shared helper + linked-CSV sync**

In `TEMPLATE`'s script block, replace this:

```
document.getElementById('dl').addEventListener('click',()=>{
 let csv='m/z,intensity_processed\n';
 for(let i=0;i<PROC_X.length;i++)csv+=PROC_X[i]+','+PROC_Y[i]+'\n';
 const blob=new Blob([csv],{type:'text/csv'}),a=document.createElement('a');
 a.href=URL.createObjectURL(blob);a.download='polyP_LCR_processed.csv';a.click();
});
recompute();
```

with:

```
function buildCSV(){
 let csv='m/z,intensity_processed\n';
 for(let i=0;i<PROC_X.length;i++)csv+=PROC_X[i]+','+PROC_Y[i]+'\n';
 return csv;
}
document.getElementById('dl').addEventListener('click',()=>{
 const blob=new Blob([buildCSV()],{type:'text/csv'}),a=document.createElement('a');
 a.href=URL.createObjectURL(blob);a.download='polyP_LCR_processed.csv';a.click();
});
// ---- linked-file live sync (File System Access API, Chromium only) ----
let csvHandle=null,csvTimer=null;
const linkBtn=document.getElementById('link');
const csvStat=document.getElementById('csvstat');
if(!window.showSaveFilePicker){
 linkBtn.disabled=true;
 linkBtn.title='Live link needs Chrome or Edge; use Download instead.';
 csvStat.textContent='live link not supported in this browser';
}else{
 linkBtn.addEventListener('click',async()=>{
  try{
   csvHandle=await window.showSaveFilePicker({
     suggestedName:'polyP_LCR_processed.csv',
     types:[{description:'CSV',accept:{'text/csv':['.csv']}}]});
   csvStat.textContent='linked: '+csvHandle.name;
   syncCSV();
  }catch(e){/* user cancelled the picker */}
 });
}
function syncCSV(){
 if(!csvHandle)return;
 clearTimeout(csvTimer);
 csvTimer=setTimeout(async()=>{
  try{
   const w=await csvHandle.createWritable();
   await w.write(buildCSV());
   await w.close();
   csvStat.textContent='synced: '+csvHandle.name;
  }catch(e){csvStat.textContent='write failed: '+e.message;}
 },200);
}
recompute();
```

- [ ] **Step 5: Add the `syncCSV()` call into `recompute()`**

In `TEMPLATE`'s script block, find the end of `recompute()`:

```
 document.getElementById('status').textContent=
   G.nseg+' peak segments, '+G.gmz.length+' grid points.';
}
```

and change it to:

```
 document.getElementById('status').textContent=
   G.nseg+' peak segments, '+G.gmz.length+' grid points.';
 syncCSV();
}
```

Note: `syncCSV` is a hoisted function declaration, so calling it inside `recompute()` is valid even though it is defined later in the script; `recompute()` itself only runs at the final `recompute();` line, after all declarations.

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — `TestBuildHtml` now has 2 tests passing

- [ ] **Step 7: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add linked-CSV live sync to the viewer" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Rewrite `main()` for file-or-folder batch input

Replace the old single-spectrum `main()` with one that enumerates inputs, computes per-spectrum threshold/precursor, and writes named viewers into the output folder.

**Files:**
- Modify: `build_lcr_viewer.py` (replace the whole `main()` function)
- Modify: `tests/test_build_lcr_viewer.py` (add integration test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__` line:

```python
class TestMainIntegration(unittest.TestCase):
    def test_folder_input_writes_named_viewers(self):
        src = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        # one spectrum: parent envelope near m/z 200, small cluster near 260
        spec = "".join("%.1f %.1f\n" % (m, i) for m, i in [
            (200.0, 40), (200.2, 90), (200.4, 50), (200.6, 10),
            (260.0, 4), (260.2, 6), (260.4, 3)])
        open(os.path.join(src, "run1.txt"), "w").write(spec)
        # fake plotly bundle next to a fake script dir is awkward; instead
        # call the pieces main() relies on through main() with argv patched.
        argv = sys.argv
        sys.argv = ["build_lcr_viewer.py", src, out]
        try:
            blv.main()
        finally:
            sys.argv = argv
        files = os.listdir(out)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("LCR_mz200_"))
        self.assertTrue(files[0].endswith(".html"))
        # cleanup
        for d in (src, out):
            for n in os.listdir(d):
                os.unlink(os.path.join(d, n))
            os.rmdir(d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — old `main()` ignores argv[2] as an output dir and writes a single `OUTPUT.html`; the assertion on `LCR_mz200_` fails (or it errors on the missing plotly bundle path, depending on cwd).

- [ ] **Step 3: Rewrite `main()`**

In `build_lcr_viewer.py`, replace the entire existing `main()` function (from `def main():` through its final `print(...)` line) with:

```python
def main():
    args = sys.argv[1:]
    here = os.path.dirname(os.path.abspath(__file__))
    src = args[0] if len(args) > 0 else os.path.join(here, "clipboard_spectrum.txt")
    out_dir = args[1] if len(args) > 1 else os.path.normpath(
        os.path.join(here, "..", "..", "outputs", "LCR", "individual peaks"))
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()

    files = iter_spectrum_files(src)
    if not files:
        sys.exit("No spectrum files found at " + src)

    for path in files:
        try:
            mz, it = parse_spectrum(path)
        except (ValueError, OSError) as e:
            print("skip %s: %s" % (path, e))
            continue
        thr = auto_threshold(mz, it)
        prec = precursor_mz(mz, it)
        html = build_html(mz, it, thr, plotly)
        out = os.path.join(out_dir, output_filename(prec))
        with open(out, "w") as fh:
            fh.write(html)
        print("Wrote %s  (precursor m/z %d, threshold %.1f, %d pts, %.1f KB)"
              % (out, prec, thr, len(mz), os.path.getsize(out) / 1024))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — `TestMainIntegration` passes. Note this test reads the real `plotly-basic.min.js`; ensure it has been downloaded per `README.md` first (`curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js`).

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Rewrite main() for file-or-folder batch input" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Update the module docstring and project docs

Bring the `build_lcr_viewer.py` docstring, `README.md`, and `AGENTS.md` in line with the new behavior.

**Files:**
- Modify: `build_lcr_viewer.py` (module docstring + the `__MZ__`/`Usage` lines)
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the module docstring**

In `build_lcr_viewer.py`, replace the `Usage:` line in the top docstring:

```
Usage:  python3 build_lcr_viewer.py INPUT.txt OUTPUT.html
INPUT is whitespace/tab-delimited two columns: m/z  intensity
```

with:

```
Usage:  python3 build_lcr_viewer.py INPUT [OUTPUT_DIR]
INPUT is a 2-column m/z, intensity file (whitespace- or comma-delimited),
or a folder of such files. One viewer is written per spectrum, named by
precursor ion m/z, into OUTPUT_DIR (default: ../../outputs/LCR/individual
peaks). Processing parameters come from PRESET; the scaling threshold is
auto-placed per spectrum.
```

- [ ] **Step 2: Update `README.md`**

Replace the `## Usage` section of `README.md` with:

```markdown
## Usage

Input is a 2-column m/z, intensity file (whitespace-, tab-, or comma-delimited),
or a folder of such files.

```sh
python3 build_lcr_viewer.py INPUT [OUTPUT_DIR]
```

- `INPUT` — a single spectrum file, or a folder; a folder builds one viewer
  per `.txt`/`.csv` file inside it.
- `OUTPUT_DIR` — optional; defaults to `../../outputs/LCR/individual peaks`
  (the workspace `outputs/` data area).

Each viewer is named `LCR_mz<precursor>_<YYYYMMDD-HHMM>.html`, where
`<precursor>` is the parent-envelope (base-peak) m/z. The timestamp means
re-runs never overwrite a prior viewer.

Processing parameters are fixed by the `PRESET` dict at the top of the script
(charge-reduced ×10, adjacent-averaging smoothing, window 299, pre-smoothing
overlay hidden). The "scale applies above m/z" threshold is auto-placed per
spectrum, just past the parent envelope. All values stay live-editable in the
viewer; the preset only sets the starting point.

### Live-synced CSV

The viewer has a **Link CSV file** button: in Chrome or Edge, pick a `.csv`
once and it is rewritten automatically on every parameter change. Other
browsers fall back to the **Download processed CSV** button, which regenerates
the CSV from current parameters on each click.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
```

- [ ] **Step 3: Update `AGENTS.md`**

In `AGENTS.md`, replace the `## Run` section body:

```
```sh
python3 build_lcr_viewer.py INPUT.txt OUTPUT.html
```

INPUT is whitespace/tab-delimited `m/z  intensity`. `plotly-basic.min.js` must
sit next to the script (git-ignored — download once per `README.md`).
```

with:

```
```sh
python3 build_lcr_viewer.py INPUT [OUTPUT_DIR]
```

`INPUT` is a 2-column m/z, intensity file (whitespace- or comma-delimited) or a
folder of them; a folder builds one viewer per `.txt`/`.csv` file. `OUTPUT_DIR`
defaults to `../../outputs/LCR/individual peaks`. Each viewer is named
`LCR_mz<precursor>_<timestamp>.html`. `plotly-basic.min.js` must sit next to the
script (git-ignored — download once per `README.md`). Tests:
`python3 -m unittest discover -s tests -v`.
```

And in the `## How it works` section, replace the `**Scaling**` bullet:

```
- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1.
```

with:

```
- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1. The threshold is auto-placed per spectrum just past the parent
  envelope (`auto_threshold`); fixed parameters live in the `PRESET` dict.
```

- [ ] **Step 4: Verify tests still pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — all tests (docs changes do not affect them)

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py README.md AGENTS.md
git commit -m "Update docs for batch input, preset, auto-threshold, linked CSV" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Save the current spectrum

Generate the first viewer in the output folder from the existing `clipboard_spectrum.txt`, and verify it in a browser.

**Files:** none modified — this is an execution + verification step.

- [ ] **Step 1: Confirm the Plotly bundle is present**

Run: `ls -la plotly-basic.min.js`
Expected: the ~1 MB file exists. If not:
`curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js`

- [ ] **Step 2: Build the viewer for the current spectrum**

Run: `python3 build_lcr_viewer.py clipboard_spectrum.txt`
Expected: prints `Wrote .../outputs/LCR/individual peaks/LCR_mz<precursor>_<timestamp>.html (precursor m/z ..., threshold ..., ... pts, ... KB)`

- [ ] **Step 3: Verify the output folder**

Run: `ls -la "../../outputs/LCR/individual peaks/"`
Expected: one `LCR_mz*_*.html` file, roughly 1.2 MB.

- [ ] **Step 4: Visually verify the viewer**

Open the generated HTML in a browser and confirm:
- Charge-reduced ×factor shows **10**; Smoothing method shows **Adjacent averaging**; Window shows **299**; pre-smoothing overlay checkbox is **unchecked**.
- The "Scale applies above m/z" field is pre-filled and the dotted threshold line sits in the valley just past the parent envelope (before the charge-reduced peaks). Adjust live if it looks off.
- The spectrum renders as one continuous line.
- In Chrome/Edge: click **Link CSV file**, pick a file, change the window value, and confirm the linked file's contents update (status shows `synced: ...`).

- [ ] **Step 5: No commit**

This task produces a viewer in the workspace `outputs/` data area, which is git-ignored and never committed. Nothing to commit.

---

## Done

After Task 10, integrate the branch via the finishing-a-development-branch skill (merge to `main` or open a PR per the user's preference).
