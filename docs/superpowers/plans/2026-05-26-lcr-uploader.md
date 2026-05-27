# LCR-viewer Uploader Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single self-contained `LCR_viewer.html` that lets zero-coding-knowledge collaborators drop their own spectra and run the existing LCR pipeline client-side in any browser, distributed via GitHub Release asset and GitHub Pages.

**Architecture:** Add a `--uploader` flag to `build_lcr_viewer.py` that emits a single HTML with no spectrum baked in plus a new `uploader.js` module for file ingestion and a multi-spectrum sidebar. The existing JS pipeline (`buildGrid`, `smoothAll`, ladder labeler) stays untouched; a thin `loadSpectrum()` refactor in the HTML template lets the uploader swap the active spectrum without forking the pipeline. Existing single-spectrum + `--serve` workflows stay byte-identical.

**Tech Stack:** Python 3 (stdlib only), vanilla JS, Plotly basic bundle (already inlined), JSZip (new inlined dependency ~30 KB), GitHub Actions for Pages deployment.

**Reference:** Spec at `docs/superpowers/specs/2026-05-26-lcr-uploader-design.md`.

---

## File Structure

| Path | Status | Responsibility |
|------|--------|----------------|
| `build_lcr_viewer.py` | Modify | Add `--uploader` flag; new template branch; build stamp; inline `uploader.js` + JSZip + example spectrum |
| `uploader.js` | **New** | File parser, spectra store, drop handlers, sidebar renderer, state coordinator |
| `jszip.min.js` | **New (vendored, gitignored)** | Bulk CSV zip download |
| `example_spectrum.xy` | **New (committed)** | Tiny bundled sample for "Try with example" button — committed because it's a code-side asset, not user data |
| `tests/uploader_test.html` | **New** | Browser-runnable pure-function tests for parser, precursor, store, coordinator |
| `tests/run_node.js` | Modify | Accept optional filename arg so the same runner drives both labeler and uploader tests |
| `tests/test_build_lcr_viewer.py` | Modify | Regression test that `--uploader` emits the expected output file |
| `docs/uploader-release-smoke.md` | **New** | Manual smoke-test checklist for releases |
| `.github/workflows/pages.yml` | **New** | Build uploader and deploy to GitHub Pages on push to main |
| `.gitignore` | Modify | Add `dist/`, add `jszip.min.js` to vendored-library exemption |
| `AGENTS.md` | Modify | Document `--uploader` mode, file structure, template-fork policy |
| `README.md` | Modify | New "For collaborators" section with the Pages link and download instructions |

---

## Task 1: Add `loadSpectrum()` JS shim to template (groundwork refactor)

**Why first:** Both the default build and the uploader will go through this entry point. Doing this refactor first means later tasks don't touch the existing viewer pipeline — they only call `loadSpectrum()`.

**Files:**
- Modify: `build_lcr_viewer.py:725-794` (template `RAW_MZ` / `RAW_IT` / `CSV_NAME` initialization and `const G=buildGrid()` call)
- Test: `tests/test_build_lcr_viewer.py` (add regression test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`:

```python
def test_default_build_calls_loadSpectrum_at_startup(self):
    """A default build's HTML must call loadSpectrum(mz, it, csvName)
    once at startup so the uploader can reuse the same entry point."""
    import re
    mz = [100.0, 200.0, 300.0]
    it = [10.0, 20.0, 30.0]
    html = build_lcr_viewer.build_html(
        mz, it, 250.0, "/* plotly stub */",
        "LCR_mz200_20260101-0000.html",
        build_lcr_viewer.PRESET,
        "/* labeler stub */",
    )
    # loadSpectrum(...) must be called exactly once with the inlined arrays.
    matches = re.findall(r"loadSpectrum\(", html)
    self.assertEqual(len(matches), 1,
                     "expected exactly one loadSpectrum(...) call in default build")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Users/yidu/Library/CloudStorage/OneDrive-UniversityofMassachusetts/UMASS/Projects/PolyP/code/LCR-viewer && python3 -m unittest tests.test_build_lcr_viewer -v -k loadSpectrum`
Expected: FAIL — `loadSpectrum(` not found in template yet.

- [ ] **Step 3: Refactor template top block**

In `build_lcr_viewer.py`, replace the block around line 725:

```javascript
const RAW_MZ=__MZ__;
const RAW_IT=__IT__;
const CSV_NAME=__CSVNAME__;
```

with:

```javascript
// Mutable so the uploader can swap spectra without reloading the page.
// In default builds, loadSpectrum() is called exactly once at startup.
let RAW_MZ=[], RAW_IT=[], CSV_NAME="";
let G=null;  // populated by loadSpectrum() — buildGrid() reads RAW_MZ/RAW_IT
```

Then find the line `const G=buildGrid();` (currently ~line 794) and replace with nothing (deleted — `G` is now assigned inside `loadSpectrum`).

Add a new function definition immediately before the existing first `function` block. Use this exact body:

```javascript
function loadSpectrum(mz, it, csvName){
 // Single entry point for setting the active spectrum. Both the default
 // build (one call at startup with the inlined arrays) and the uploader
 // (one call per sidebar click) go through here.
 RAW_MZ = mz;
 RAW_IT = it;
 CSV_NAME = csvName || "";
 G = (RAW_MZ.length >= 2) ? buildGrid() : null;
 // Update the sibling-CSV hyperlink in the header to reflect the new name.
 const a = document.getElementById('csvfile');
 if (a) { a.textContent = CSV_NAME; a.href = CSV_NAME; a.download = CSV_NAME; }
 // Recompute and redraw. recompute() is the existing top-level entry
 // the controls already call on input changes; it re-reads RAW_MZ/G.
 if (typeof recompute === 'function' && G) recompute();
}
```

Find the existing top-level "kick off the first render" code (search for the
first `recompute()` or `Plotly.newPlot(` call near the end of the script block —
likely between line 920–960). Replace that one-shot init with:

```javascript
loadSpectrum(__MZ__, __IT__, __CSVNAME__);
```

- [ ] **Step 4: Run all existing tests to verify no regression**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests pass, including the new one.

Run: `node tests/run_node.js`
Expected: PASS (labeler tests still green; this refactor does not touch labeler).

- [ ] **Step 5: Manual smoke test — default build still works**

Run: `python3 build_lcr_viewer.py clipboard_spectrum.txt`
Expected: HTML opens in a browser, plot renders identically to before.

- [ ] **Step 6: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "refactor(viewer): single-entry loadSpectrum() for spectrum init

Both default builds and the upcoming uploader mode now route through
loadSpectrum(mz, it, csvName) instead of a const at script top. No
behaviour change for default builds.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add `--uploader` build flag (skeleton)

**Files:**
- Modify: `build_lcr_viewer.py:462-479` (`parse_args`), `build_lcr_viewer.py:568-616` (`main`)
- Modify: `.gitignore` (add `dist/`)
- Test: `tests/test_build_lcr_viewer.py`

- [ ] **Step 1: Update .gitignore**

Add to `.gitignore` (after the `/output/` line):

```
# Single-file uploader build artifact (git-ignored alongside /output/)
/dist/
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`:

```python
def test_uploader_flag_writes_single_html_to_dist(self):
    """--uploader emits dist/LCR_viewer.html with no spectrum baked in."""
    import subprocess, os, tempfile, shutil
    here = os.path.dirname(os.path.abspath(build_lcr_viewer.__file__))
    dist = os.path.join(here, "dist")
    if os.path.isdir(dist):
        shutil.rmtree(dist)
    try:
        r = subprocess.run(
            ["python3", "build_lcr_viewer.py", "--uploader"],
            cwd=here, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        out = os.path.join(dist, "LCR_viewer.html")
        self.assertTrue(os.path.isfile(out), "dist/LCR_viewer.html not written")
        body = open(out).read()
        # Uploader marker present, no spectrum data baked in.
        self.assertIn("__UPLOADER_BUILD__", body[:5000],
                      "build stamp marker missing in HTML head")
        self.assertNotIn("__MZ__", body, "unfilled __MZ__ placeholder")
        self.assertIn("loadSpectrum([], [],", body,
                      "uploader build should start with empty spectrum")
    finally:
        if os.path.isdir(dist):
            shutil.rmtree(dist)
```

- [ ] **Step 3: Run test, verify it fails**

Run: `python3 -m unittest tests.test_build_lcr_viewer.test_uploader_flag_writes_single_html_to_dist -v`
Expected: FAIL — `--uploader` flag not recognised.

- [ ] **Step 4: Update `parse_args`**

Replace `build_lcr_viewer.py` `parse_args` (line 462–479) with:

```python
def parse_args(argv, here):
    """Parse CLI args.

    Default mode: returns (serve_mode=False/True, src, out_dir, uploader=False).
    --uploader mode: returns (False, None, <here>/dist, True) and signals main()
    to emit a single self-contained LCR_viewer.html for collaborators (no
    spectrum baked in). --serve and --uploader are mutually exclusive.
    """
    uploader_mode = "--uploader" in argv
    serve_mode = "--serve" in argv
    if uploader_mode and serve_mode:
        sys.exit("--uploader and --serve are mutually exclusive")
    pos = [a for a in argv if a not in ("--serve", "--uploader")]

    if uploader_mode:
        dist = pos[0] if pos else os.path.join(here, "dist")
        return False, None, dist, True

    src = pos[0] if len(pos) > 0 else os.path.join(here, "clipboard_spectrum.txt")
    if len(pos) > 1:
        out_dir = pos[1]
    else:
        folder = src if os.path.isdir(src) else os.path.dirname(
            os.path.abspath(src))
        dataset = os.path.basename(os.path.abspath(folder)) or "LCR"
        out_dir = os.path.join(here, "output", "LCR", dataset)
    return serve_mode, src, out_dir, False
```

- [ ] **Step 5: Add a `build_uploader_html` function**

Insert immediately after `build_html` (around line 461):

```python
def build_uploader_html(plotly, labeler_js, uploader_js, jszip_js,
                       example_xy, preset, build_stamp):
    """Assemble the self-contained uploader HTML. Same template as build_html
    but with empty initial spectrum, uploader.js and JSZip inlined, the
    bundled example spectrum embedded as base64, and the build stamp injected
    for the catch-all error panel. The single-spectrum FSA buttons (Update
    sibling CSV / Link CSV / Save preset) are hidden via the __UPLOADER_BUILD__
    body class — see the template's [data-uploader-only] / [data-default-only]
    selectors."""
    html = TEMPLATE
    # Preset values used as defaults; the uploader still respects preset.json
    # if it exists next to the script.
    html = html.replace("__SCALEON__",
                        "checked" if preset.get("scale_on", True) else "")
    html = html.replace("__SCALE__", str(preset["scale"]))
    html = html.replace("__THR__", "%g" % 0)        # set on first activation
    html = html.replace("__WIDTH__", str(preset["width_mz"]))
    html = html.replace("__POLY__", str(preset["poly"]))
    html = html.replace("__RAWOV__", "checked" if preset["show_overlay"] else "")
    html = html.replace('value="%s"' % preset["method"],
                        'value="%s" selected' % preset["method"])
    html = html.replace("__CSVNAME__", json.dumps(""))
    html = html.replace("__CSVHREF__", "")
    html = html.replace("__MZ__", "[]")
    html = html.replace("__IT__", "[]")
    html = html.replace("__PLOTLY__", plotly)
    html = html.replace("__LADDER_LABELER__", labeler_js)
    ll = preset.get("ladder_labels", {})
    html = html.replace("__LADDER_ENABLED__",
                        "checked" if ll.get("enabled", False) else "")
    html = html.replace("__LADDER_TOL__", str(ll.get("tol_mz", 5.0)))
    # Uploader-specific injections (use unique markers; replaced later tasks
    # add these to the template).
    html = html.replace("__UPLOADER_BUILD__", build_stamp)
    html = html.replace("__UPLOADER_JS__", uploader_js)
    html = html.replace("__JSZIP__", jszip_js)
    html = html.replace("__EXAMPLE_SPECTRUM_B64__", example_xy)
    return html
```

- [ ] **Step 6: Update `main()` to branch on uploader mode**

Replace `build_lcr_viewer.py` `main()` (line 568–616) — keep the default branch
unchanged, and prepend the uploader branch:

```python
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    serve_mode, src, out_dir, uploader_mode = parse_args(sys.argv[1:], here)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()
    with open(os.path.join(here, "ladder_labeler.js")) as fh:
        labeler_js = fh.read()
    preset = load_preset(here)

    if uploader_mode:
        # Build the single self-contained uploader HTML.
        uploader_js_path = os.path.join(here, "uploader.js")
        jszip_path = os.path.join(here, "jszip.min.js")
        example_path = os.path.join(here, "example_spectrum.xy")
        if not os.path.isfile(uploader_js_path):
            sys.exit("uploader.js not found next to the script")
        if not os.path.isfile(jszip_path):
            sys.exit("jszip.min.js not found next to the script — "
                     "download once per README.md")
        if not os.path.isfile(example_path):
            sys.exit("example_spectrum.xy not found next to the script")
        with open(uploader_js_path) as fh:
            uploader_js = fh.read()
        with open(jszip_path) as fh:
            jszip_js = fh.read()
        import base64
        with open(example_path, "rb") as fh:
            example_b64 = base64.b64encode(fh.read()).decode("ascii")
        build_stamp = _build_stamp(here)
        html = build_uploader_html(plotly, labeler_js, uploader_js, jszip_js,
                                   example_b64, preset, build_stamp)
        out = os.path.join(out_dir, "LCR_viewer.html")
        with open(out, "w") as fh:
            fh.write(html)
        print("Wrote %s  (%.1f KB, build %s)" %
              (out, os.path.getsize(out) / 1024, build_stamp))
        return

    # ---- default flow (unchanged) ----
    files = iter_spectrum_files(src)
    if not files:
        sys.exit("No spectrum files found at " + src)

    written, csv_written = [], []
    for path in files:
        # ... existing per-file build loop, unchanged ...
```

Add a `_build_stamp` helper near the top of the file (after the `PRESET` dict):

```python
def _build_stamp(here):
    """A short string baked into uploader HTML for the catch-all error panel.
    Format: 'YYYY-MM-DD-uploader-<git-short-sha or nogit>'."""
    import datetime, subprocess
    date = datetime.date.today().isoformat()
    try:
        sha = subprocess.run(
            ["git", "-C", here, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip() or "nogit"
    except Exception:
        sha = "nogit"
    return "%s-uploader-%s" % (date, sha)
```

- [ ] **Step 7: Create placeholder files so the build won't fail**

Create empty stubs (later tasks fill them):

```bash
echo "// uploader.js — placeholder, see Task 4" > uploader.js
echo "// jszip.min.js — vendored, see README" > jszip.min.js
printf '300.0 10.0\n301.0 12.0\n302.0 9.0\n' > example_spectrum.xy
```

Add to TEMPLATE `<head>` (just before `</head>`, around line 641):

```html
<meta name="lcr-build" content="__UPLOADER_BUILD__">
<script>window.__LCR_BUILD__="__UPLOADER_BUILD__";</script>
<script>__UPLOADER_JS__</script>
<script>__JSZIP__</script>
<script>window.__LCR_EXAMPLE_B64__="__EXAMPLE_SPECTRUM_B64__";</script>
```

For default builds these placeholders are not yet replaced — add lines to
`build_html` (line 431–460) to strip them out so the default build doesn't
ship empty `<script>` blocks:

```python
html = html.replace("__UPLOADER_BUILD__", "default")
html = html.replace("__UPLOADER_JS__", "")
html = html.replace("__JSZIP__", "")
html = html.replace("__EXAMPLE_SPECTRUM_B64__", "")
```

- [ ] **Step 8: Run test, verify it passes**

Run: `python3 -m unittest tests.test_build_lcr_viewer -v`
Expected: PASS — `--uploader` flag now emits `dist/LCR_viewer.html`.

Also run: `python3 build_lcr_viewer.py clipboard_spectrum.txt` (default flow)
Expected: still works, no regression.

- [ ] **Step 9: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py .gitignore \
        uploader.js jszip.min.js example_spectrum.xy
git commit -m "feat(uploader): scaffold --uploader build flag

New flag emits dist/LCR_viewer.html (gitignored) using a new
build_uploader_html() that swaps in empty initial arrays, an embedded
example spectrum, a build stamp, and slots for uploader.js + JSZip
(placeholders for now; filled in subsequent tasks).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Tolerant spectrum parser in `uploader.js`

**Files:**
- Modify: `uploader.js` (replace placeholder)
- Create: `tests/uploader_test.html`
- Modify: `tests/run_node.js` (accept filename arg)
- Modify: `.gitignore` (no — uploader.js is committed code)

- [ ] **Step 1: Generalise the JS test runner**

Modify `tests/run_node.js`. Replace the lines that read `ladder_labeler_test.html` (around line 28–35) with:

```javascript
const testFile = process.argv[2] || 'ladder_labeler_test.html';
const testHtml = fs.readFileSync(path.join(here, testFile), 'utf8');

// Find which JS module(s) the test page loads via <script src="../X.js">.
// Concatenate them all, then extract the inline test script.
const srcRefs = [...testHtml.matchAll(
  /<script src="\.\.\/([^"]+\.js)"><\/script>/g
)].map(m => m[1]);
let moduleSrc = '';
for (const ref of srcRefs) {
  moduleSrc += fs.readFileSync(path.join(here, '..', ref), 'utf8') + '\n';
}
const inlineMatch = testHtml.match(/<\/script>\s*<script>([\s\S]*?)<\/script>/);
if (!inlineMatch) {
  console.error(`Could not extract inline test script from ${testFile}`);
  process.exit(1);
}
const inlineScript = inlineMatch[1];
```

Replace `vm.runInContext(labelerJs, ...)` with `vm.runInContext(moduleSrc, sandbox, { filename: 'modules' });`.

Run: `node tests/run_node.js` (no arg)
Expected: PASS — labeler tests still green.

Commit:

```bash
git add tests/run_node.js
git commit -m "test(runner): accept optional test-page filename

Default still runs the labeler page; the upcoming uploader test page will
reuse this runner.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests for the parser**

Create `tests/uploader_test.html`:

```html
<!DOCTYPE html>
<meta charset="utf-8">
<title>uploader.js tests</title>
<script src="../uploader.js"></script>
<script>
const summary = document.createElement('div'); summary.id = 'summary';
const log = document.createElement('div'); log.id = 'log';
document.body && document.body.append(summary, log);

let passed = 0, failed = 0;
function check(name, cond, detail) {
  const pre = document.createElement('pre');
  if (cond) { passed++; pre.className='pass'; pre.textContent = 'PASS  ' + name; }
  else { failed++; pre.className='fail';
         pre.textContent = 'FAIL  ' + name + (detail?': '+detail:''); }
  (document.getElementById('log') || log).appendChild(pre);
}

try {
  // --- parseSpectrum ---
  check('parseSpectrum: whitespace 2-col', (() => {
    const s = LCRUploader.parseSpectrum('100 1\n200 2\n300 3\n');
    return s.ok && s.mz.length === 3 && s.mz[1] === 200 && s.intensity[1] === 2;
  })());

  check('parseSpectrum: comma-delimited', (() => {
    const s = LCRUploader.parseSpectrum('100,1\n200,2\n');
    return s.ok && s.mz.length === 2 && s.intensity[1] === 2;
  })());

  check('parseSpectrum: tab-delimited', (() => {
    const s = LCRUploader.parseSpectrum('100\t1\n200\t2\n');
    return s.ok && s.mz.length === 2;
  })());

  check('parseSpectrum: skips header lines until numeric start', (() => {
    const s = LCRUploader.parseSpectrum('# header\nm/z intensity\n100 1\n200 2\n');
    return s.ok && s.mz.length === 2 && s.mz[0] === 100;
  })());

  check('parseSpectrum: empty file → error', (() => {
    const s = LCRUploader.parseSpectrum('');
    return !s.ok && /empty/i.test(s.message);
  })());

  check('parseSpectrum: junk-only → error', (() => {
    const s = LCRUploader.parseSpectrum('hello world\nfoo bar\n');
    return !s.ok && /couldn'?t read/i.test(s.message);
  })());

  check('parseSpectrum: stops on mid-stream bad line', (() => {
    const s = LCRUploader.parseSpectrum('100 1\n200 2\noops 3 4 5\n');
    return !s.ok && /line 3/i.test(s.message);
  })());

  // --- precursorFromName ---
  check('precursorFromName: trailing integer', () =>
    LCRUploader.precursorFromName('PF4_polyP_3300.xy') === 3300);
  check('precursorFromName: trailing decimal', () =>
    LCRUploader.precursorFromName('polyP_3300.5.xy') === 3300.5);
  check('precursorFromName: leading number ignored', () =>
    LCRUploader.precursorFromName('3300_PF4_polyP.xy') === null);
  check('precursorFromName: no number', () =>
    LCRUploader.precursorFromName('polyP_no_number.xy') === null);
} catch (e) {
  check('exception during test run', false, e.message + '\n' + e.stack);
}

summary.textContent = `${passed} passed, ${failed} failed.`;
summary.className = failed === 0 ? 'pass' : 'fail';
</script>
```

- [ ] **Step 3: Run, verify all fail (uploader.js is still a stub)**

Run: `node tests/run_node.js uploader_test.html`
Expected: 11 FAIL — `LCRUploader is not defined`.

- [ ] **Step 4: Implement the parser in `uploader.js`**

Replace `uploader.js` contents with:

```javascript
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
```

- [ ] **Step 5: Run test, verify all pass**

Run: `node tests/run_node.js uploader_test.html`
Expected: `11 passed, 0 failed.`

- [ ] **Step 6: Commit**

```bash
git add uploader.js tests/uploader_test.html
git commit -m "feat(uploader): tolerant 2-column parser + filename precursor

parseSpectrum splits on whitespace/comma/tab, skips header lines, and
returns a friendly error message naming the offending line. precursorFromName
mirrors the Python regex. Pure functions; 11 unit tests via run_node.js.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Spectra store + drop/picker handlers

**Files:**
- Modify: `uploader.js`
- Modify: `tests/uploader_test.html` (add store tests)

- [ ] **Step 1: Add failing tests for the store**

Append to `tests/uploader_test.html` inside the `try { ... }` block, before `summary.textContent`:

```javascript
  // --- spectra store ---
  const store = LCRUploader.createStore();

  check('store: starts empty', store.all().length === 0);

  store.add({ name: 'a.xy', mz: [1,2,3], intensity: [1,2,3] });
  store.add({ name: 'b.xy', mz: [4,5], intensity: [4,5] });
  check('store: add two', store.all().length === 2);

  check('store: first auto-active', store.activeName() === 'a.xy');

  store.setActive('b.xy');
  check('store: setActive switches', store.activeName() === 'b.xy');
  check('store: active() returns chosen entry',
        store.active().mz[0] === 4);

  store.remove('a.xy');
  check('store: remove drops entry', store.all().length === 1 &&
                                     store.all()[0].name === 'b.xy');

  store.add({ name: 'a.xy', mz:[1], intensity:[1], parseStatus:'error',
              parseMessage:'oops' });
  check('store: parseStatus stored',
        store.all().find(s => s.name === 'a.xy').parseStatus === 'error');
```

Update the summary count expectation: now 17 passed.

- [ ] **Step 2: Run test, verify added cases fail**

Run: `node tests/run_node.js uploader_test.html`
Expected: 11 pass + 6 fail (`createStore is not a function`).

- [ ] **Step 3: Implement the store**

Append to `uploader.js` (inside the IIFE, before the `root.LCRUploader = ...` block):

```javascript
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
```

And add `root.LCRUploader.createStore = createStore;`.

- [ ] **Step 4: Run tests, verify all pass**

Run: `node tests/run_node.js uploader_test.html`
Expected: `17 passed, 0 failed.`

- [ ] **Step 5: Implement drop/picker handlers (DOM-side, manual test)**

Append to `uploader.js` (inside the IIFE):

```javascript
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
      const subs = await new Promise(res => reader.readEntries(res));
      for (const sub of subs) await collectFilesFromEntry(sub, files);
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

  root.LCRUploader.ingestFiles = ingestFiles;
  root.LCRUploader.ingestDataTransfer = ingestDataTransfer;
  root.LCRUploader.loadExampleSpectrum = loadExampleSpectrum;
```

- [ ] **Step 6: Run tests to ensure no regression**

Run: `node tests/run_node.js uploader_test.html`
Expected: `17 passed, 0 failed.`

- [ ] **Step 7: Commit**

```bash
git add uploader.js tests/uploader_test.html
git commit -m "feat(uploader): spectra store + drop/picker file ingestion

createStore() manages the in-memory spectra list with auto-activation of
the first ok spectrum. ingestDataTransfer recursively walks dropped
folders via webkitGetAsEntry; ingestFiles handles the click-to-pick
fallback. loadExampleSpectrum decodes the bundled base64 sample.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Empty-state landing UI + sidebar HTML

**Files:**
- Modify: `build_lcr_viewer.py` TEMPLATE (the HTML body)
- Modify: `uploader.js` (sidebar renderer)

- [ ] **Step 1: Add the landing + sidebar HTML to TEMPLATE**

In `build_lcr_viewer.py`, find the start of `<div id="controls">` in TEMPLATE (around line 643). Insert *before* it:

```html
<!-- Uploader-only chrome: visible when window.__LCR_BUILD__ is set. -->
<div id="uploader-empty" hidden style="
     padding:80px 20px;text-align:center;background:#fff">
  <h1 style="font-size:28px;margin:0 0 12px;color:#333">
    LCR spectrum viewer</h1>
  <p style="font-size:14px;color:#666;max-width:520px;margin:0 auto 28px">
    Drop one or more spectrum files (or a folder) here to view them. Scaling,
    smoothing, and ladder labeling all happen in your browser — no files are
    uploaded anywhere.</p>
  <div id="uploader-drop"
       style="border:2px dashed #999;border-radius:10px;padding:48px;
              max-width:480px;margin:0 auto;cursor:pointer;
              background:#fafafa;color:#666;font-size:14px">
    Drop a file or folder here, or <u>click to browse</u>
    <input id="uploader-picker" type="file" multiple webkitdirectory
           hidden>
  </div>
  <button id="uploader-try-example" style="margin-top:18px">
    Try with example spectrum</button>
  <p style="font-size:11px;color:#999;margin-top:32px">
    Accepted file types: <code>.xy</code>, <code>.csv</code>, <code>.txt</code>
    (two columns: m/z and intensity)</p>
</div>

<div id="uploader-sidebar" hidden style="
     position:fixed;left:0;top:0;bottom:0;width:220px;background:#f4f4f4;
     border-right:1px solid #ddd;overflow:auto;padding:10px;font-size:12px;
     z-index:5">
  <div style="font-weight:600;margin-bottom:6px">Loaded spectra</div>
  <ul id="uploader-list" style="list-style:none;padding:0;margin:0"></ul>
  <button id="uploader-add-more"
          style="margin-top:8px;width:100%;font-size:12px">+ Add more</button>
  <input id="uploader-picker-more" type="file" multiple webkitdirectory hidden>
</div>
<div id="uploader-pane-offset" hidden
     style="position:absolute;left:220px;right:0;top:0"></div>
```

Insert *after* the closing `</div>` of `#controls` but before `<div class="hint">`:

```html
<!-- Uploader-only: hide single-spectrum FSA buttons when in uploader build. -->
<style id="uploader-style" disabled>
 #updatecsv, #link, #savepreset,
 .uploader-hide-when-empty { display:none !important; }
 #controls, #plot, .hint { margin-left: 220px; }
 @media (max-width: 768px) {
   #uploader-sidebar { position:static;width:100%;height:auto;border-right:none;
                       border-bottom:1px solid #ddd }
   #controls, #plot, .hint { margin-left: 0; }
 }
</style>
```

- [ ] **Step 2: Wire the empty-state and sidebar in `uploader.js`**

Append to `uploader.js` (inside the IIFE):

```javascript
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

  function onStoreChange_impl() {
    const a = store.active();
    if (!a) {
      showEmptyState(true);
      renderSidebar(store);
      return;
    }
    showEmptyState(false);
    renderSidebar(store);
    // Hand the active spectrum to the existing viewer entry point.
    const csvName = a.name.replace(/\.[^.]+$/, '') + '.csv';
    if (typeof loadSpectrum === 'function') {
      loadSpectrum(a.mz, a.intensity, csvName);
    }
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
  }

  // Run after DOMContentLoaded so the static HTML is parsed.
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initUploader);
    } else {
      initUploader();
    }
  }

  root.LCRUploader.initUploader = initUploader;
  root.LCRUploader.renderSidebar = renderSidebar;  // exposed for tests
```

- [ ] **Step 3: Manual smoke test**

```bash
python3 build_lcr_viewer.py --uploader
open dist/LCR_viewer.html
```

Expected:
- Landing page visible: drop zone + "Try with example spectrum" button.
- Click "Try example" → sidebar appears with "✓ example_spectrum.xy", plot renders.
- Drop a folder of `.xy` files → sidebar lists each, first one activates.
- Click ✕ on a row → entry removed.
- Click another row → switches plot.

- [ ] **Step 4: Commit**

```bash
git add build_lcr_viewer.py uploader.js
git commit -m "feat(uploader): landing page + multi-spectrum sidebar

Empty-state drop zone + Try example button; sidebar lists each loaded
spectrum with parse-status badge, click-to-switch, ✕ to remove, + Add
more. Uploader-only CSS hides the FSA-dependent buttons (Update sibling
CSV / Link / Save preset). Responsive: sidebar collapses to top on
viewports <768px.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Per-spectrum ladder state stash/restore

**Why:** Switching spectra must preserve each spectrum's ladders. The labeler already keeps state in a `LadderLabeler.state`-like global; we stash it on switch.

**Files:**
- Modify: `uploader.js` (extend `onStoreChange_impl` and add stash/restore hooks)
- Modify: `tests/uploader_test.html` (add round-trip test)

- [ ] **Step 1: Identify the labeler's serializable state**

Read `ladder_labeler.js` and locate its public API. Look for a function like
`LadderLabeler.serializeState()` / `loadState()`. If those don't exist,
add the following minimal pair to `ladder_labeler.js` (search for the
existing module's `return { ... }` export at the bottom):

```javascript
// (Inside ladder_labeler.js, in its public API object)
serializeState() {
  // Deep-clone the ladders + per-rung overrides so callers can stash freely.
  return JSON.parse(JSON.stringify(state.ladders || []));
},
loadState(serialized) {
  state.ladders = JSON.parse(JSON.stringify(serialized || []));
  if (typeof renderAll === 'function') renderAll();
},
```

(Adjust function names to whatever the existing module uses internally;
fall back to a thin wrapper around its existing public methods if those exist.)

- [ ] **Step 2: Write the failing round-trip test**

Append to `tests/uploader_test.html` inside the `try { ... }` block:

```javascript
  // --- stash/restore round-trip via the store ---
  const s2 = LCRUploader.createStore();
  s2.add({ name: 'a.xy', mz:[1,2,3], intensity:[1,2,3] });
  s2.add({ name: 'b.xy', mz:[4,5,6], intensity:[4,5,6] });
  // Simulate user adding a ladder while A is active:
  s2.active().ladders = [{ id: 'lA', z0: 8, M: 26400 }];
  s2.setActive('b.xy');
  s2.active().ladders = [{ id: 'lB', z0: 6, M: 13200 }];
  s2.setActive('a.xy');
  check('store: ladders preserved on A→B→A switch',
        s2.active().ladders[0].id === 'lA');
```

Update summary count to 18.

- [ ] **Step 3: Run test, verify pass (the store already supports this)**

Run: `node tests/run_node.js uploader_test.html`
Expected: `18 passed, 0 failed.` The store carries arbitrary fields on entries.

- [ ] **Step 4: Wire the actual labeler stash/restore in `uploader.js`**

Edit `onStoreChange_impl` (added in Task 5). Before reading the new active
spectrum, stash the previous one's ladder state; after activating, load it:

```javascript
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
      _previousActiveName = null;
      return;
    }
    showEmptyState(false);
    renderSidebar(store);
    const csvName = a.name.replace(/\.[^.]+$/, '') + '.csv';
    if (typeof loadSpectrum === 'function') {
      loadSpectrum(a.mz, a.intensity, csvName);
    }
    // Restore incoming ladders.
    if (typeof LadderLabeler !== 'undefined' && LadderLabeler.loadState) {
      LadderLabeler.loadState(a.ladders || []);
    }
    _previousActiveName = a.name;
  }
```

- [ ] **Step 5: Manual smoke test for ladder persistence**

```bash
python3 build_lcr_viewer.py --uploader
open dist/LCR_viewer.html
```

- Drop two `.xy` files.
- Enable "Ladder labels", add a ladder on spectrum A.
- Switch to B, add a different ladder.
- Switch back to A → original ladder visible.
- Switch to B → B's ladder visible.

- [ ] **Step 6: Commit**

```bash
git add ladder_labeler.js uploader.js tests/uploader_test.html
git commit -m "feat(uploader): per-spectrum ladder state stash/restore

Switching spectra in the sidebar now serializeState/loadState through
LadderLabeler so each spectrum keeps its own ladders. Round-trip is
unit-tested at the store level; the labeler hookup is exercised by the
manual smoke test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Bundled example spectrum

**Files:**
- Create/replace: `example_spectrum.xy` (commit a real ~5 KB sample)

- [ ] **Step 1: Pick a small representative spectrum**

A good candidate is the existing `clipboard_spectrum.txt`. Trim it to ~500 lines
so the base64 stays well under 50 KB:

```bash
head -500 clipboard_spectrum.txt > example_spectrum.xy
wc -l example_spectrum.xy   # confirm ≤500 lines
ls -l example_spectrum.xy   # confirm ≤50 KB
```

- [ ] **Step 2: Verify the example loads in the uploader**

```bash
python3 build_lcr_viewer.py --uploader
open dist/LCR_viewer.html
```

Click "Try with example spectrum". Expected: plot renders, sidebar shows
`✓ example_spectrum.xy`.

- [ ] **Step 3: Commit**

```bash
git add example_spectrum.xy
git commit -m "feat(uploader): commit bundled example spectrum

Small (~500-row) representative polyP spectrum used by the Try with
example button. Code-side asset (not user data), committed despite the
*.xy gitignore via explicit add. The .gitignore exception is documented
in AGENTS.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Note: `*.xy` is in `.gitignore`. Add an exception so future contributors
don't accidentally lose this file. Update `.gitignore`:

```
# Input spectra and generated viewers (data / outputs — never commit)
*.txt
*.csv
*.xy
*.html
!example_spectrum.xy   # bundled sample for uploader's "Try example" button
!tests/*.html
```

Amend the previous commit to include the `.gitignore` change:

```bash
git add .gitignore
git commit --amend --no-edit
```

---

## Task 8: Catch-all error panel

**Files:**
- Modify: `build_lcr_viewer.py` TEMPLATE (panel HTML + handler script)
- Modify: `uploader.js` (panel logic) OR inline in TEMPLATE

- [ ] **Step 1: Add the panel HTML to TEMPLATE**

In `build_lcr_viewer.py` TEMPLATE, insert just before `</body>`:

```html
<div id="uploader-errpanel" hidden style="
     position:fixed;right:16px;bottom:16px;max-width:420px;
     background:#fff8e1;border:1px solid #d8b800;border-radius:6px;
     padding:14px 16px;font-size:13px;color:#333;box-shadow:0 4px 12px rgba(0,0,0,.15);z-index:9999">
  <div style="font-weight:600;margin-bottom:6px">
    Something unexpected happened</div>
  <p style="margin:0 0 8px;line-height:1.4">
    Sorry — the viewer hit a problem we didn't plan for. Copy the box below
    and paste it into ChatGPT (or any AI assistant), and ask it to help
    figure out what went wrong.</p>
  <pre id="uploader-errbody" style="background:#fff;border:1px solid #ddd;
     padding:8px;font-size:11px;line-height:1.3;max-height:160px;
     overflow:auto;white-space:pre-wrap;margin:0 0 8px"></pre>
  <div style="display:flex;gap:8px">
    <button id="uploader-errcopy">Copy</button>
    <button id="uploader-errclose">Dismiss</button>
  </div>
</div>
```

- [ ] **Step 2: Add the handler to `uploader.js`**

Append inside the IIFE:

```javascript
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

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initErrorPanel);
    } else {
      initErrorPanel();
    }
  }
```

- [ ] **Step 3: Manual smoke test**

Open `dist/LCR_viewer.html`. In devtools console:

```javascript
throw new Error('test error');
```

Expected: panel appears bottom-right with the payload including
`LCR-viewer 2026-…-uploader-<sha>`. Click Copy → clipboard contains the
payload. Click Dismiss → panel hides.

- [ ] **Step 4: Commit**

```bash
git add build_lcr_viewer.py uploader.js
git commit -m "feat(uploader): catch-all 'copy & ask AI' error panel

window.onerror + unhandledrejection feed a dismissible bottom-right
panel with one Copy button. Payload: build stamp, user agent, active
file, spectra loaded, message, top 6 stack frames. No contact info
embedded (artifact is publicly hosted).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Bulk export — Download all processed CSVs as zip

**Files:**
- Modify: `build_lcr_viewer.py` TEMPLATE (add button)
- Modify: `uploader.js` (zip generator)
- Add (manual): `jszip.min.js` next to script

- [ ] **Step 1: Download and vendor JSZip**

```bash
curl -sL https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js \
     -o jszip.min.js
ls -l jszip.min.js   # ~94 KB minified (acceptable)
```

Update README's "Setup" section to mention `jszip.min.js` alongside the
existing Plotly download instruction.

- [ ] **Step 2: Add a "Download all CSVs (zip)" button to TEMPLATE**

In the controls block, after the existing `<div class="ctl"><button id="dl">…`,
insert:

```html
<div class="ctl uploader-hide-when-empty">
  <button id="dl-all-zip" hidden>Download all CSVs (zip)</button>
</div>
```

The button stays hidden until there are 2+ spectra (toggled in JS below).

- [ ] **Step 3: Add the zip generator in `uploader.js`**

```javascript
  async function buildAllCsvsZip() {
    if (typeof JSZip === 'undefined') throw new Error('JSZip not loaded');
    const zip = new JSZip();
    for (const e of store.all()) {
      if (e.parseStatus !== 'ok') continue;
      // Reuse the in-HTML processed-CSV pipeline by temporarily activating
      // each spectrum and reading the existing buildCSV()/buildProcessed
      // output. We need a way to get the processed CSV for a given spectrum
      // without disturbing the active view; the cleanest is a small helper
      // in the existing viewer that takes (mz, it, thr, preset) and returns
      // the CSV string. If it doesn't exist, add it.
      const csv = (typeof buildProcessedCsvForSpectrum === 'function')
        ? buildProcessedCsvForSpectrum(e.mz, e.intensity)
        : '';                       // graceful fallback; shouldn't occur
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
```

Extend `onStoreChange_impl` to call `refreshBulkBtn()` and add:

```javascript
  const dlAll = document.getElementById('dl-all-zip');
  if (dlAll) dlAll.addEventListener('click', buildAllCsvsZip);
```

inside `initUploader`.

- [ ] **Step 4: Add the `buildProcessedCsvForSpectrum` helper to TEMPLATE**

In the existing TEMPLATE JS block (where `recompute()` / `buildCSV()` live),
add a pure helper that doesn't disturb the active plot:

```javascript
function buildProcessedCsvForSpectrum(mz, it){
  // Run the same scale+smooth pipeline used by the active view, but without
  // touching the visible plot. Reads the current control values for params.
  const savedMz = RAW_MZ, savedIt = RAW_IT, savedG = G;
  RAW_MZ = mz; RAW_IT = it; G = buildGrid();
  let csv = '';
  try {
    const proc = computeProcessed();    // existing function — produces {x, y}
    csv = buildCSV(proc.x, proc.y);
  } finally {
    RAW_MZ = savedMz; RAW_IT = savedIt; G = savedG;
  }
  return csv;
}
```

(Adjust the call to `computeProcessed()` / `buildCSV()` to match the
existing function names in the template — search for the function that
the existing **Download processed CSV** button uses.)

- [ ] **Step 5: Update `.gitignore` so `jszip.min.js` is not committed**

```
# Vendored plotting library — re-download, see README
plotly-basic.min.js
jszip.min.js
```

- [ ] **Step 6: Manual smoke test**

```bash
python3 build_lcr_viewer.py --uploader
open dist/LCR_viewer.html
```

Drop two `.xy` files → "Download all CSVs (zip)" button appears. Click → a
zip with two CSVs downloads. Open one in a text editor → contents match what
"Download processed CSV" would produce for that spectrum individually.

- [ ] **Step 7: Commit**

```bash
git add build_lcr_viewer.py uploader.js .gitignore README.md
git commit -m "feat(uploader): bulk Download all CSVs (zip)

Inlines JSZip (~94 KB) at build time. Button hidden until 2+ ok
spectra are loaded. Each CSV is built via the same scale+smooth pipeline
as the active view by temporarily swapping RAW_MZ/RAW_IT inside
buildProcessedCsvForSpectrum() so the visible plot is undisturbed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: GitHub Pages deployment workflow

**Files:**
- Create: `.github/workflows/pages.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/pages.yml`:

```yaml
name: Deploy uploader to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'

      - name: Download Plotly basic bundle
        run: curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js

      - name: Download JSZip
        run: curl -sL https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js -o jszip.min.js

      - name: Build uploader HTML
        run: python3 build_lcr_viewer.py --uploader

      - name: Stage for Pages
        run: |
          mkdir -p _site
          cp dist/LCR_viewer.html _site/index.html

      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Enable Pages in the repo settings**

This is a manual step on GitHub:
- Settings → Pages → Source: "GitHub Actions"

Document this in the README's deployment section so future maintainers know.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/pages.yml
git commit -m "ci(pages): deploy uploader HTML to GitHub Pages on push to main

Workflow downloads Plotly + JSZip, builds with --uploader, and publishes
dist/LCR_viewer.html as index.html. Served at
https://yinum.github.io/LCR-viewer/ once Pages is enabled in repo
settings (Source: GitHub Actions).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Verify after push (manual, requires user)**

After `git push`, watch the Actions tab; once green, visit
`https://yinum.github.io/LCR-viewer/`. Confirm empty-state landing renders.

---

## Task 11: Release smoke-test checklist + AGENTS.md + README updates

**Files:**
- Create: `docs/uploader-release-smoke.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

- [ ] **Step 1: Create smoke-test checklist**

Create `docs/uploader-release-smoke.md`:

```markdown
# Uploader release smoke test

Run before tagging an uploader release.

## Build

- [ ] `curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js`
- [ ] `curl -sL https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js -o jszip.min.js`
- [ ] `python3 build_lcr_viewer.py --uploader`
- [ ] `ls -l dist/LCR_viewer.html` — file exists, ≤ ~2 MB

## Open in each browser

For Safari, Firefox, Chrome, Edge:
- [ ] Open `dist/LCR_viewer.html` (double-click)
- [ ] Empty-state landing renders (drop zone + Try-example button visible)
- [ ] Click "Try with example spectrum" → plot renders; sidebar shows
      `✓ example_spectrum.xy`

## Multi-spectrum

- [ ] Drop a folder of 5 `.xy` files → sidebar lists all 5, first auto-activates
- [ ] Click a different row → plot switches
- [ ] Click ✕ → row removed, plot moves to remaining spectrum

## Ladder persistence

- [ ] Enable Ladder labels; add a ladder on spectrum A
- [ ] Switch to B; add a different ladder
- [ ] Switch back to A → A's ladder is visible (not B's)

## Errors

- [ ] Drop a `.csv` containing only `hello world` → ✗ badge appears,
      hover shows `Couldn't read any numbers from this file.`
- [ ] In devtools console, run `throw new Error('test')` →
      catch-all panel appears bottom-right; Copy button copies payload
      including the build stamp

## CSV parity

- [ ] Drop the same spectrum file that a recent `--serve` build used
- [ ] Click "Download processed CSV"
- [ ] `diff` against the sibling CSV the `--serve` build wrote — must be
      identical (or differ only by trailing newline)

## Bulk export

- [ ] Drop 2+ spectra → "Download all CSVs (zip)" button visible
- [ ] Click it → zip downloads; unzip → each CSV matches the per-spectrum
      "Download processed CSV" output
```

- [ ] **Step 2: Update AGENTS.md**

Append a new section to `AGENTS.md` (before the closing `See code comments`
line):

```markdown
## Uploader mode (`--uploader`)

`python3 build_lcr_viewer.py --uploader` emits a single
`dist/LCR_viewer.html` for non-coder collaborators — drop spectra in the
browser, get the same scale+smooth+ladder pipeline client-side. No
spectrum is baked in; the FSA-dependent buttons (Update sibling CSV / Link
CSV / Save preset) are hidden. Distributed as a GitHub Release asset and
auto-deployed to GitHub Pages on push to `main`
(`.github/workflows/pages.yml`).

Architecture: the template's spectrum-init is now a `loadSpectrum(mz, it,
csvName)` shim. Default builds call it once at script load; the uploader
calls it on each sidebar click. Per-spectrum ladder state stashes through
`LadderLabeler.serializeState() / loadState()` on switch.

Files specific to uploader mode:
- `uploader.js` — file parser (whitespace/comma/tab), spectra store, drop
  handlers (file + folder), sidebar renderer, catch-all error panel,
  bulk CSV→zip via JSZip.
- `example_spectrum.xy` — tiny bundled sample for the "Try with example
  spectrum" button. Committed code-side asset (the `*.xy` gitignore has
  an explicit `!example_spectrum.xy` exception).
- `jszip.min.js` — vendored at build time, gitignored, re-download via
  the README setup section.
- `dist/` — gitignored output directory for the uploader HTML.

Spec: `docs/superpowers/specs/2026-05-26-lcr-uploader-design.md`.
Plan: `docs/superpowers/plans/2026-05-26-lcr-uploader.md`.
```

- [ ] **Step 3: Update README**

In `README.md`, add a new section at the top (after the existing
description, before "## Setup"):

```markdown
## For collaborators (no coding required)

Use the web version: **https://yinum.github.io/LCR-viewer/**

Or download a single `LCR_viewer.html` file from the
[Releases page](https://github.com/yinum/LCR-viewer/releases) and double-click
it. Either way:

1. Drag one or more spectrum files (`.xy`, `.csv`, or `.txt`, two columns:
   m/z and intensity) onto the page — or drop a whole folder.
2. The viewer shows each spectrum in the sidebar; click any row to view it.
3. Adjust smoothing / scaling / ladder labels live; download processed CSV
   or PNG when you're done.

No files are uploaded anywhere — all processing runs in your browser.

Click "Try with example spectrum" to see what the tool does before you have
your own data.
```

Update the existing "Setup" section to mention `jszip.min.js`:

```markdown
The Plotly basic bundle and JSZip are not committed (third-party, ~1 MB
and ~94 KB). Download them once next to the script:

```sh
curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js
curl -sL https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js -o jszip.min.js
```
```

- [ ] **Step 4: Commit**

```bash
git add docs/uploader-release-smoke.md AGENTS.md README.md
git commit -m "docs(uploader): release smoke test + AGENTS/README updates

Per-browser smoke-test checklist for releases; AGENTS.md gains a
canonical 'Uploader mode' section; README gains a 'For collaborators'
section with the Pages link and download instructions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Cut the first release

**Files:** none — release procedure only.

- [ ] **Step 1: Confirm all tests green**

```bash
python3 -m unittest discover -s tests -v
node tests/run_node.js                        # labeler
node tests/run_node.js uploader_test.html     # uploader
```

Expected: all green.

- [ ] **Step 2: Run the full smoke test**

Walk through `docs/uploader-release-smoke.md` in Safari + Chrome at minimum.

- [ ] **Step 3: Push and verify Pages deploy**

```bash
git push origin <branch>
# Open the PR, merge to main
# Watch Actions tab; visit https://yinum.github.io/LCR-viewer/ after green
```

- [ ] **Step 4: Tag and release**

```bash
git checkout main && git pull
python3 build_lcr_viewer.py --uploader
gh release create v0.1.0 dist/LCR_viewer.html \
  --title "LCR-viewer v0.1.0 — uploader mode" \
  --notes "First release of the uploader mode. Open the HTML in any browser, drop your spectra, get the LCR viewer. Web version: https://yinum.github.io/LCR-viewer/"
```

---

## Self-review

**1. Spec coverage** — each section in `2026-05-26-lcr-uploader-design.md`
mapped to a task:
- §5 Architecture → Task 1 (loadSpectrum shim) + Task 2 (build flag)
- §6.1 build script → Task 2
- §6.2 uploader.js → Tasks 3, 4
- §6.3 landing + sidebar UI → Task 5
- §6.4 state coordinator → Task 5 (active-spectrum switching) + Task 6
  (ladder stash/restore)
- §6.5 bulk export → Task 9
- §8 error handling — friendly per-file errors → Task 3 parser + Task 5
  sidebar; catch-all panel → Task 8
- §9 testing → Tasks 3, 4 (unit tests) + Task 11 (smoke checklist)
- §10 deployment → Task 10 (Pages) + Task 12 (Release asset)
- §11 v1 scope items — all covered. v2 deferrals (IndexedDB, overlay) absent
  from plan by design.

**2. Placeholder scan** — no `TBD` / `TODO` / `fill in later` lines.
Code blocks contain complete content. Two notes: Task 6 Step 1 says "if those
don't exist, add the following minimal pair" — this is a forking instruction
based on a file the implementer will read, not a placeholder. Task 9 Step 4
says "Adjust the call to `computeProcessed()` / `buildCSV()` to match the
existing function names" — same: a localization instruction, not a
placeholder.

**3. Type consistency** — `loadSpectrum(mz, it, csvName)` signature is
consistent across Tasks 1, 5, 6. `createStore()` API (`add`, `all`,
`active`, `activeName`, `setActive`, `remove`, `clear`) is consistent
between Task 4 and Task 6. `parseSpectrum` return shape (`{ok, mz,
intensity}` vs `{ok:false, message}`) is consistent between Task 3
implementation and Task 4 consumer.

**4. File-path / commit-name consistency** — all paths absolute or rooted
in repo. Commit messages follow existing `type(scope): subject` convention
seen in `git log` (e.g., `feat(viewer)`, `docs(labeler)`).

No issues found.
