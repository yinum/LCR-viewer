# Filename-Based Precursor Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the precursor m/z from a spectrum filename's trailing number and use it for the output viewer name and the scaling-threshold anchor, falling back to base-peak detection when the filename has no number.

**Architecture:** Add `precursor_from_name()` (regex on the filename) and `_segment_nearest()` (find the cluster at/near a target m/z) to `build_lcr_viewer.py`. `auto_threshold` gains an optional `precursor` argument; `output_filename` rounds floats; `main()` resolves filename-vs-base-peak per spectrum. `precursor_mz` (base-peak detector) is untouched.

**Tech Stack:** Python 3 standard library (`os`, `re`, `datetime`). Tests use stdlib `unittest`.

**Branch:** All work on `filename-precursor`. The design spec (`docs/superpowers/specs/2026-05-22-filename-precursor-design.md`) is already committed on this branch.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `build_lcr_viewer.py` (modify) | `import re`; new `precursor_from_name()` and `_segment_nearest()`; `auto_threshold` gains an optional `precursor` arg; `output_filename` rounds; `main()` resolves the precursor per spectrum. |
| `tests/test_build_lcr_viewer.py` (modify) | `TestPrecursorFromName`, `TestPrecursorThreshold`; one test added to `TestOutputFilename`; `TestMainIntegration` updated (fixture rename + new test). |
| `README.md`, `AGENTS.md` (modify) | Document filename-precursor detection. |

Run all tests from the repo root: `python3 -m unittest discover -s tests -v`
The suite currently has 19 passing tests.

---

## Task 1: `precursor_from_name()`

Parse the precursor m/z from a filename's trailing number.

**Files:**
- Modify: `build_lcr_viewer.py` (add `re` to the import line; add the function after `parse_spectrum`)
- Modify: `tests/test_build_lcr_viewer.py` (add `TestPrecursorFromName`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__ == "__main__":` line:

```python
class TestPrecursorFromName(unittest.TestCase):
    def test_integer_trailing_number(self):
        self.assertEqual(blv.precursor_from_name("PF4_polyP_3300.xy"), 3300.0)

    def test_decimal_trailing_number(self):
        self.assertEqual(blv.precursor_from_name("run_3300.5.xy"), 3300.5)

    def test_path_is_handled(self):
        self.assertEqual(blv.precursor_from_name("/data/LCR/PF4_polyP_3700.xy"),
                         3700.0)

    def test_no_trailing_number_returns_none(self):
        self.assertIsNone(blv.precursor_from_name("clipboard_spectrum.txt"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'build_lcr_viewer' has no attribute 'precursor_from_name'`

- [ ] **Step 3: Add `re` to the imports**

In `build_lcr_viewer.py`, change the import line:

```python
import sys, os, json, datetime
```

to:

```python
import sys, os, json, re, datetime
```

- [ ] **Step 4: Implement `precursor_from_name`**

In `build_lcr_viewer.py`, immediately after the `parse_spectrum` function (after its `return mz, it` line, before `def find_segments`), add:

```python
def precursor_from_name(path):
    """Precursor m/z parsed from a spectrum filename's trailing number
    (decimals allowed): PF4_polyP_3300.xy -> 3300.0, run_3300.5.xy -> 3300.5.
    Returns None when the name (minus extension) does not end in a number."""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"(\d+(?:\.\d+)?)$", stem)
    return float(m.group(1)) if m else None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 4 tests in `TestPrecursorFromName` (23 tests total)

- [ ] **Step 6: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "Add precursor_from_name: parse precursor m/z from filename" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `_segment_nearest()` + optional `precursor` argument for `auto_threshold`

When a precursor m/z is known, anchor the threshold to that m/z's cluster instead of the base peak's.

**Files:**
- Modify: `build_lcr_viewer.py` (add `_segment_nearest` before `auto_threshold`; replace `auto_threshold`)
- Modify: `tests/test_build_lcr_viewer.py` (add `TestPrecursorThreshold`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_lcr_viewer.py`, before the `if __name__ == "__main__":` line:

```python
class TestPrecursorThreshold(unittest.TestCase):
    # cluster A near m/z 100 (minor); cluster B near m/z 200 (holds the base peak)
    MZ = [100.0, 100.1, 100.2, 200.0, 200.1, 200.2]
    IT = [20.0, 30.0, 20.0, 40.0, 90.0, 40.0]

    def test_no_precursor_uses_base_peak_cluster(self):
        thr = blv.auto_threshold(self.MZ, self.IT)
        self.assertAlmostEqual(thr, 200.2 + blv.THRESHOLD_MARGIN, delta=1e-6)

    def test_precursor_anchors_to_its_own_cluster(self):
        # base peak is in cluster B (~200), but precursor 100 -> cluster A
        thr = blv.auto_threshold(self.MZ, self.IT, 100.0)
        self.assertAlmostEqual(thr, 100.2 + blv.THRESHOLD_MARGIN, delta=1e-6)

    def test_precursor_in_gap_uses_nearest_cluster(self):
        # precursor 130 lies between the clusters; nearest edge is A's (100.2)
        thr = blv.auto_threshold(self.MZ, self.IT, 130.0)
        self.assertAlmostEqual(thr, 100.2 + blv.THRESHOLD_MARGIN, delta=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `test_precursor_anchors_to_its_own_cluster` and `test_precursor_in_gap_uses_nearest_cluster` fail with `TypeError: auto_threshold() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Add `_segment_nearest` and replace `auto_threshold`**

In `build_lcr_viewer.py`, replace the entire existing `auto_threshold` function:

```python
def auto_threshold(mz, it):
    """Scaling threshold m/z, placed a fixed margin (THRESHOLD_MARGIN) past the
    right edge of the parent envelope -- the segment containing the base peak.
    The charge-reduced ladder sits well above the precursor, so a fixed offset
    is safer than clamping to the nearest peak, which is typically a minor
    satellite just above the envelope rather than a charge-reduced product."""
    bi = _base_peak_index(it)
    segs = find_segments(mz)
    parent = next(s for s in segs if s[0] <= bi <= s[1])
    return mz[parent[1]] + THRESHOLD_MARGIN
```

with:

```python
def _segment_nearest(mz, segs, target):
    """The (start, end) segment whose m/z range contains target; if none
    contains it, the segment whose nearest edge is closest to target."""
    for s in segs:
        if mz[s[0]] <= target <= mz[s[1]]:
            return s
    def edge_dist(s):
        if target < mz[s[0]]:
            return mz[s[0]] - target
        return target - mz[s[1]]
    return min(segs, key=edge_dist)


def auto_threshold(mz, it, precursor=None):
    """Scaling threshold m/z, placed a fixed margin (THRESHOLD_MARGIN) past the
    right edge of the parent envelope. The parent envelope is the cluster
    containing/nearest the precursor m/z when one is given (e.g. parsed from
    the filename); otherwise the cluster containing the base peak. The
    charge-reduced ladder sits well above the precursor, so a fixed offset is
    used rather than clamping to the nearest peak."""
    segs = find_segments(mz)
    if precursor is None:
        bi = _base_peak_index(it)
        parent = next(s for s in segs if s[0] <= bi <= s[1])
    else:
        parent = _segment_nearest(mz, segs, precursor)
    return mz[parent[1]] + THRESHOLD_MARGIN
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 3 tests in `TestPrecursorThreshold`; the existing `test_threshold_is_fixed_margin_past_parent_edge` still passes (26 tests total)

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "auto_threshold: optional precursor anchor via _segment_nearest" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `output_filename` rounds float precursors

A filename precursor arrives as a `float`; the `LCR_mz<N>` label needs an integer.

**Files:**
- Modify: `build_lcr_viewer.py` (`output_filename`)
- Modify: `tests/test_build_lcr_viewer.py` (add a test to `TestOutputFilename`)

- [ ] **Step 1: Write the failing test**

In `tests/test_build_lcr_viewer.py`, add this method inside the existing `TestOutputFilename` class, after `test_name_format`:

```python
    def test_rounds_float_precursor(self):
        when = datetime.datetime(2026, 5, 22, 9, 7)
        self.assertEqual(blv.output_filename(3300.0, when),
                         "LCR_mz3300_20260522-0907.html")
        self.assertEqual(blv.output_filename(3300.7, when),
                         "LCR_mz3301_20260522-0907.html")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `test_rounds_float_precursor` fails: `output_filename(3300.7, ...)` yields `LCR_mz3300_...` (the `%d` format truncates instead of rounding).

- [ ] **Step 3: Update `output_filename`**

In `build_lcr_viewer.py`, replace the entire `output_filename` function:

```python
def output_filename(precursor, when=None):
    """Per-spectrum viewer filename: LCR_mz<precursor>_<YYYYMMDD-HHMM>.html"""
    when = when or datetime.datetime.now()
    return "LCR_mz%d_%s.html" % (precursor, when.strftime("%Y%m%d-%H%M"))
```

with:

```python
def output_filename(precursor, when=None):
    """Per-spectrum viewer filename: LCR_mz<precursor>_<YYYYMMDD-HHMM>.html.
    precursor may be a float (parsed from a filename); it is rounded for the
    integer label."""
    when = when or datetime.datetime.now()
    return "LCR_mz%d_%s.html" % (int(round(precursor)),
                                 when.strftime("%Y%m%d-%H%M"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — `TestOutputFilename` has 2 tests; the existing `test_name_format` still passes (27 tests total)

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "output_filename: round float precursor for the label" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Wire the precursor resolution into `main()`

`main()` parses the filename precursor, feeds it to `auto_threshold`, and names the viewer by it.

**Files:**
- Modify: `build_lcr_viewer.py` (`main()` — the per-spectrum loop body)
- Modify: `tests/test_build_lcr_viewer.py` (`TestMainIntegration` — fixture rename + new test)

- [ ] **Step 1: Update the tests**

In `tests/test_build_lcr_viewer.py`, the `TestMainIntegration` class has one test that writes a fixture file named `run1.txt`. That name now ends in a digit (`1`), which `precursor_from_name` would read as precursor m/z 1. Rename the fixture so it still exercises the base-peak path.

In `test_folder_input_writes_named_viewers`, change:

```python
        with open(os.path.join(src, "run1.txt"), "w") as f:
            f.write(spec)
```

to:

```python
        with open(os.path.join(src, "run.txt"), "w") as f:
            f.write(spec)
```

(The file `run.txt` has no trailing digit, so the test keeps exercising base-peak naming — it still expects `LCR_mz200_`.)

Then add this new test method inside `TestMainIntegration`, after `test_folder_input_writes_named_viewers`:

```python
    def test_filename_precursor_names_the_viewer(self):
        src = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        # base peak is near m/z 600, but the filename says precursor 250
        spec = "".join("%.1f %.1f\n" % (m, i) for m, i in [
            (250.0, 30), (250.2, 45), (250.4, 25),
            (600.0, 40), (600.2, 95), (600.4, 50)])
        with open(os.path.join(src, "sample_250.txt"), "w") as f:
            f.write(spec)
        argv = sys.argv
        sys.argv = ["build_lcr_viewer.py", src, out]
        try:
            blv.main()
        finally:
            sys.argv = argv
        files = os.listdir(out)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("LCR_mz250_"))
        for d in (src, out):
            for n in os.listdir(d):
                os.unlink(os.path.join(d, n))
            os.rmdir(d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `test_filename_precursor_names_the_viewer` fails: `main()` still ignores the filename, so the viewer is named `LCR_mz600_...` (base peak) and the `LCR_mz250_` assertion fails.

- [ ] **Step 3: Update the `main()` loop body**

In `build_lcr_viewer.py`, inside `main()`, replace this block:

```python
        thr = auto_threshold(mz, it)
        prec = precursor_mz(mz, it)
        name = output_filename(prec)
        html = build_html(mz, it, thr, plotly, name, preset)
        out = os.path.join(out_dir, name)
        with open(out, "w") as fh:
            fh.write(html)
        print("Wrote %s  (precursor m/z %d, threshold %.1f, %d pts, %.1f KB)"
              % (out, prec, thr, len(mz), os.path.getsize(out) / 1024))
```

with:

```python
        named = precursor_from_name(path)
        thr = auto_threshold(mz, it, named)
        if named is not None:
            prec, source = named, "from filename"
        else:
            prec, source = precursor_mz(mz, it), "base peak"
        name = output_filename(prec)
        html = build_html(mz, it, thr, plotly, name, preset)
        out = os.path.join(out_dir, name)
        with open(out, "w") as fh:
            fh.write(html)
        print("Wrote %s  (precursor m/z %d (%s), threshold %.1f, %d pts, %.1f KB)"
              % (out, int(round(prec)), source, thr, len(mz),
                 os.path.getsize(out) / 1024))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 28 tests total, including both `TestMainIntegration` tests

- [ ] **Step 5: Commit**

```bash
git add build_lcr_viewer.py tests/test_build_lcr_viewer.py
git commit -m "main(): resolve precursor from filename, fall back to base peak" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Docs

Document filename-based precursor detection.

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update `README.md`**

In `README.md`, find this paragraph in the `## Usage` section:

```
Each viewer is named `LCR_mz<precursor>_<YYYYMMDD-HHMM>.html`, where
`<precursor>` is the parent-envelope (base-peak) m/z. The timestamp means
re-runs never overwrite a prior viewer.
```

and replace it with:

```
Each viewer is named `LCR_mz<precursor>_<YYYYMMDD-HHMM>.html`. The precursor
m/z is read from the spectrum filename's trailing number when present
(`PF4_polyP_3300.xy` → `3300`, decimals allowed); otherwise it is inferred
from the base peak. A filename precursor also anchors the scaling threshold to
that m/z's peak cluster — correct even when a charge-reduced product is more
intense than the precursor. The timestamp means re-runs never overwrite a
prior viewer.
```

- [ ] **Step 2: Update `AGENTS.md`**

In `AGENTS.md`, find this bullet in the `## How it works` section:

```
- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1. The threshold is auto-placed per spectrum just past the parent
  envelope (`auto_threshold`); fixed parameters come from `load_preset()` — the
  built-in `PRESET` dict overlaid with a viewer-saved `preset.json` (git-ignored).
```

and replace it with:

```
- **Scaling** — charge-reduced region (m/z ≥ threshold) ×factor; parent envelope
  stays ×1. The threshold is auto-placed per spectrum just past the parent
  envelope (`auto_threshold`): the cluster at the filename precursor m/z
  (`precursor_from_name`, a trailing number in the name) when present, else the
  base-peak cluster. Fixed parameters come from `load_preset()` — the built-in
  `PRESET` dict overlaid with a viewer-saved `preset.json` (git-ignored).
```

- [ ] **Step 3: Verify tests still pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — 28 tests (docs changes do not affect them)

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md
git commit -m "Document filename-based precursor detection" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Build the five `results/LCR/` viewers

Run the viewer over the real PF4–polyP LCR data and confirm the 3300 file is now handled correctly.

**Files:** none modified — execution + verification only.

- [ ] **Step 1: Confirm the Plotly bundle is present**

Run: `ls plotly-basic.min.js`
Expected: the file exists. If not: `curl -sL https://cdn.plot.ly/plotly-basic-2.35.2.min.js -o plotly-basic.min.js`

- [ ] **Step 2: Build viewers for the whole LCR folder**

Run:
```bash
python3 build_lcr_viewer.py "../../results/LCR"
```
Expected: five `Wrote …` lines. Each should report `(from filename)` as the precursor source, and the viewers should be named `LCR_mz3300_…` through `LCR_mz3700_…`.

- [ ] **Step 3: Confirm the 3300 file is correct**

Run:
```bash
ls -1 "../../outputs/LCR/individual peaks/" | grep -E 'LCR_mz3[0-7]00_'
```
Expected: five files, `LCR_mz3300_*` through `LCR_mz3700_*`. The presence of `LCR_mz3300_*` (not `LCR_mz3595_*`) confirms the filename precursor overrode the base peak.

- [ ] **Step 4: Spot-check the 3300 viewer's threshold**

Run:
```bash
grep -o 'id="thr" value="[0-9.]*"' "../../outputs/LCR/individual peaks/"LCR_mz3300_*.html
```
Expected: a threshold value near 3300 + ~45 (roughly 3340–3360), i.e. just past the precursor cluster — not near 3640 (which is what base-peak detection would have produced). Open the viewer in a browser to confirm the dotted threshold line sits just above the 3300 precursor envelope; adjust live if needed.

- [ ] **Step 5: No commit**

The viewers land in the git-ignored workspace `outputs/` area. Nothing to commit.

---

## Done

After Task 6, integrate the branch via the finishing-a-development-branch skill.
