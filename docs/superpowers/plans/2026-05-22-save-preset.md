# Save Preset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the viewer save its current control values to a `preset.json` that `build_lcr_viewer.py` auto-loads, so tuned parameters (mainly smoothing) become the default for future builds.

**Architecture:** Add `load_preset(here)` to the script — it overlays a `preset.json` (next to the script) onto the built-in `PRESET` dict, which stays the fallback. `build_html` takes the effective preset as an argument; `main()` loads it once. The viewer gets a "Save preset" button that writes `preset.json` (File System Access API in Chrome/Edge, download fallback elsewhere). `preset.json` is git-ignored.

**Tech Stack:** Python 3 standard library (`os`, `json`). Tests use stdlib `unittest`. The viewer is self-contained HTML + vanilla JS.

**Branch:** All work on `save-preset`. The design spec (`docs/superpowers/specs/2026-05-22-save-preset-design.md`) is already committed on this branch.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `build_lcr_viewer.py` (modify) | Add `load_preset()`; `build_html` gains a `preset` parameter; `main()` wires it; `TEMPLATE` gains the "Save preset" button + JS. |
| `tests/test_build_lcr_viewer.py` (modify) | `TestLoadPreset` class; update `TestBuildHtml` for the new `preset` argument. |
| `.gitignore` (modify) | Ignore `preset.json`. |
| `README.md` (modify) | "Saving a preset" subsection. |
| `AGENTS.md` (modify) | Note that fixed parameters come from `load_preset()`. |

Run all tests from the repo root: `python3 -m unittest discover -s tests -v`

---

## Task 1: `load_preset()`

Add the function that produces the effective preset by overlaying `preset.json` onto the built-in `PRESET` defaults.

**Files:**
- Modify: `build_lcr_viewer.py` (update the `PRESET` comment; add `load_preset` after the `PRESET` dict)
- Modify: `tests/test_build_lcr_viewer.py` (add `json` import; add `TestLoadPreset`)

- [ ] **Step 1: Write the failing test**

In `tests/test_build_lcr_viewer.py`, change the first line from:

```python
import os, sys, unittest, tempfile, datetime
```

to:

```python
import os, sys, json, unittest, tempfile, datetime
```

Then append this class before the `if __name__ == "__main__":` line:

```python
class TestLoadPreset(unittest.TestCase):
    def test_no_file_returns_builtin_defaults(self):
        d = tempfile.mkdtemp()
        self.assertEqual(blv.load_preset(d), blv.PRESET)
        os.rmdir(d)

    def test_valid_file_overrides(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "preset.json"), "w") as fh:
            json.dump({"scale": 25, "method": "sg", "window": 51,
                       "poly": 4, "show_overlay": True}, fh)
        eff = blv.load_preset(d)
        self.assertEqual(eff["scale"], 25)
        self.assertEqual(eff["method"], "sg")
        self.assertEqual(eff["window"], 51)
        self.assertEqual(eff["show_overlay"], True)
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)

    def test_partial_keys_merge_over_defaults(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "preset.json"), "w") as fh:
            json.dump({"window": 777, "bogus": 1}, fh)
        eff = blv.load_preset(d)
        self.assertEqual(eff["window"], 777)                  # overridden
        self.assertEqual(eff["scale"], blv.PRESET["scale"])   # default kept
        self.assertNotIn("bogus", eff)                        # unknown ignored
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)

    def test_malformed_json_returns_defaults(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "preset.json"), "w") as fh:
            fh.write("{not valid json")
        self.assertEqual(blv.load_preset(d), blv.PRESET)
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'build_lcr_viewer' has no attribute 'load_preset'`

- [ ] **Step 3: Update the `PRESET` comment**

In `build_lcr_viewer.py`, replace these two comment lines above the `PRESET` dict:

```python
# Tuned processing preset applied as the default for every generated viewer.
# Editing these values is the supported way to change the saved parameters.
```

with:

```python
# Built-in fallback preset. load_preset() overlays preset.json (written by the
# viewer's Save preset button) on top of these; these values are used whenever
# no preset.json is present next to the script.
```

- [ ] **Step 4: Implement `load_preset`**

In `build_lcr_viewer.py`, directly after the closing `}` of the `PRESET` dict, add:

```python
def load_preset(here):
    """Effective preset: the built-in PRESET overlaid with preset.json, if a
    readable one sits next to the script. preset.json is written by the
    viewer's Save preset button; only keys also present in PRESET are taken."""
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
        if k in saved:
            eff[k] = saved[k]
    return eff
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 4 tests in `TestLoadPreset` (17 tests total)

- [ ] **Step 6: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add load_preset: overlay preset.json on built-in defaults" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `build_html` takes a `preset` argument; `main()` wires `load_preset`

`build_html` currently reads the module-global `PRESET`. Make it take the effective preset explicitly, and have `main()` load it once per run.

**Files:**
- Modify: `build_lcr_viewer.py` (`build_html` signature + body; `main()`)
- Modify: `tests/test_build_lcr_viewer.py` (`TestBuildHtml`: pass the new argument; add a custom-preset test)

- [ ] **Step 1: Update the tests**

In `tests/test_build_lcr_viewer.py`, the `TestBuildHtml` class currently calls `build_html` with five arguments. Update both calls and add a new test.

Replace every occurrence of:

```python
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME)
```

with:

```python
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET)
```

Then, inside the `TestBuildHtml` class, add this method after `test_linked_csv_feature_present`:

```python
    def test_custom_preset_overrides_controls(self):
        custom = {"scale": 7, "method": "sg", "window": 15,
                  "poly": 2, "show_overlay": True}
        html = blv.build_html(self.MZ, self.IT, 50.0, "/*plotly*/", self.NAME, custom)
        self.assertIn('id="scale" value="7"', html)
        self.assertIn('id="win" value="15"', html)
        self.assertIn('value="sg" selected', html)
        self.assertIn('id="rawov" checked', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `TypeError: build_html() takes 5 positional arguments but 6 were given`

- [ ] **Step 3: Update `build_html`**

In `build_lcr_viewer.py`, replace the whole `build_html` function with:

```python
def build_html(mz, it, thr, plotly, html_name, preset):
    """Assemble a self-contained viewer HTML from spectrum data, the
    per-spectrum threshold, and the inlined Plotly bundle. Control defaults
    come from the effective preset (see load_preset). The processed-CSV
    download/link reuses html_name's stem so the CSV matches its viewer
    (LCR_mz<precursor>_<timestamp>.csv)."""
    csv_name = os.path.splitext(os.path.basename(html_name))[0] + ".csv"
    html = TEMPLATE
    html = html.replace("__SCALE__", str(preset["scale"]))
    html = html.replace("__THR__", "%g" % thr)
    html = html.replace("__WIN__", str(preset["window"]))
    html = html.replace("__POLY__", str(preset["poly"]))
    html = html.replace("__RAWOV__", "checked" if preset["show_overlay"] else "")
    html = html.replace('value="%s"' % preset["method"],
                        'value="%s" selected' % preset["method"])
    html = html.replace("__CSVNAME__", json.dumps(csv_name))
    html = html.replace("__MZ__", json.dumps(mz))
    html = html.replace("__IT__", json.dumps(it))
    html = html.replace("__PLOTLY__", plotly)
    return html
```

- [ ] **Step 4: Update `main()` to load and pass the preset**

In `build_lcr_viewer.py`, in `main()`, find:

```python
    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()
```

and add the preset load directly after it:

```python
    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()
    preset = load_preset(here)
```

Then, in the same function, change:

```python
        html = build_html(mz, it, thr, plotly, name)
```

to:

```python
        html = build_html(mz, it, thr, plotly, name, preset)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — `TestBuildHtml` has 3 tests; 18 tests total

- [ ] **Step 6: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Pass effective preset into build_html; main() loads it" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Viewer "Save preset" button

Add a button to the viewer that writes the current control values to `preset.json`.

**Files:**
- Modify: `build_lcr_viewer.py` (`TEMPLATE`: controls block + script block)
- Modify: `tests/test_build_lcr_viewer.py` (add a test to `TestBuildHtml`)

- [ ] **Step 1: Write the failing test**

In `tests/test_build_lcr_viewer.py`, add this method inside the `TestBuildHtml` class, after `test_custom_preset_overrides_controls`:

```python
    def test_save_preset_button_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET)
        self.assertIn('id="savepreset"', html)   # Save preset button
        self.assertIn("buildPreset", html)       # JS gathers control values
        self.assertIn("preset.json", html)       # target filename
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AssertionError: 'id="savepreset"' not found`

- [ ] **Step 3: Add the Save preset button to the controls block**

In `TEMPLATE`, find this line:

```
 <div class="ctl"><button id="link">Link CSV file (live)</button>
   <span id="csvstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
```

and add a new control div directly after it:

```
 <div class="ctl"><button id="link">Link CSV file (live)</button>
   <span id="csvstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
 <div class="ctl"><button id="savepreset">Save preset</button>
   <span id="presetstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
```

- [ ] **Step 4: Add the Save preset JS**

In `TEMPLATE`'s script block, find the end of the `syncCSV` function followed by the `recompute();` call:

```
 },200);
}
recompute();
```

and replace it with:

```
 },200);
}
// ---- save preset.json (File System Access API, download fallback) ----
function buildPreset(){
 return {
  scale:parseFloat(document.getElementById('scale').value)||1,
  method:document.getElementById('method').value,
  window:parseInt(document.getElementById('win').value)||3,
  poly:parseInt(document.getElementById('poly').value)||3,
  show_overlay:document.getElementById('rawov').checked
 };
}
const presetStat=document.getElementById('presetstat');
document.getElementById('savepreset').addEventListener('click',async()=>{
 const text=JSON.stringify(buildPreset(),null,2);
 if(window.showSaveFilePicker){
  try{
   const h=await window.showSaveFilePicker({
     suggestedName:'preset.json',
     types:[{description:'JSON',accept:{'application/json':['.json']}}]});
   const w=await h.createWritable();
   await w.write(text); await w.close();
   presetStat.textContent='saved '+h.name+' - keep it next to build_lcr_viewer.py';
  }catch(e){/* user cancelled the picker */}
 }else{
  const blob=new Blob([text],{type:'application/json'}),a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download='preset.json';a.click();
  presetStat.textContent='downloaded preset.json - move it next to build_lcr_viewer.py';
 }
});
recompute();
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — `TestBuildHtml` has 4 tests; 19 tests total

- [ ] **Step 6: Sanity-check a generated viewer**

Run:
```bash
python3 -c "import build_lcr_viewer as b; h=b.build_html([1,2],[3,4],10.0,'P','LCR_mz1_x.html',b.PRESET); assert 'savepreset' in h and 'buildPreset' in h and h.count('recompute();')>=1; print('ok')"
```
Expected: prints `ok`

- [ ] **Step 7: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add Save preset button to the viewer" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `.gitignore` + docs

Ignore `preset.json` and document the workflow.

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Ignore `preset.json`**

Append these two lines to the end of `.gitignore`:

```
# local tuned preset written by the viewer's Save preset button
preset.json
```

- [ ] **Step 2: Update `README.md`**

In `README.md`, find:

```
## Tests

```sh
python3 -m unittest discover -s tests -v
```
```

and insert a new subsection directly before the `## Tests` heading, so that section becomes:

```
### Saving a preset

Tune the controls in any viewer, then click **Save preset** to write a
`preset.json`. Keep that file next to `build_lcr_viewer.py`: every later run
loads it and uses its values as the control defaults. The built-in `PRESET`
dict in the script is the fallback when no `preset.json` is present.

In Chrome or Edge, Save preset writes the file directly; other browsers
download `preset.json`, which you then move next to the script. `preset.json`
is git-ignored — it is local tuning state.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
```

- [ ] **Step 3: Update `AGENTS.md`**

In `AGENTS.md`, find this bullet in the `## How it works` section:

```
- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1. The threshold is auto-placed per spectrum just past the parent
  envelope (`auto_threshold`); fixed parameters live in the `PRESET` dict.
```

and replace its last sentence so the bullet reads:

```
- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1. The threshold is auto-placed per spectrum just past the parent
  envelope (`auto_threshold`); fixed parameters come from `load_preset()` — the
  built-in `PRESET` dict overlaid with a viewer-saved `preset.json` (git-ignored).
```

- [ ] **Step 4: Verify tests still pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 19 tests (docs/gitignore changes do not affect them)

- [ ] **Step 5: Commit**

```bash
git add .gitignore README.md AGENTS.md
git commit -m "Document Save preset workflow; git-ignore preset.json" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Round-trip verification

Confirm a saved preset actually changes a future build.

**Files:** none modified — execution + verification only.

- [ ] **Step 1: Write a test `preset.json`**

From the repo root, create a `preset.json` next to the script with a changed window:

```bash
printf '{\n  "window": 175\n}\n' > preset.json
```

- [ ] **Step 2: Rebuild the current spectrum's viewer**

Run: `python3 build_lcr_viewer.py clipboard_spectrum.txt`
Expected: prints a `Wrote .../LCR_mz<precursor>_<timestamp>.html` line.

- [ ] **Step 3: Confirm the window default changed**

Run:
```bash
grep -o 'id="win" value="[0-9]*"' "../../outputs/LCR/individual peaks/"LCR_mz*_*.html | tail -1
```
Expected: `id="win" value="175"` — the `preset.json` override took effect (built-in default is 299).

- [ ] **Step 4: Remove the test `preset.json`**

Run: `rm preset.json`

This leaves no `preset.json`; future builds fall back to the built-in `PRESET`. The real one is created by the user from the viewer's Save preset button. Nothing to commit (`preset.json` is git-ignored).

---

## Done

After Task 5, integrate the branch via the finishing-a-development-branch skill.
