#!/usr/bin/env python3
"""
build_lcr_viewer.py
Build a self-contained interactive HTML viewer for a polyP limited-charge-reduction
(LCR) MS spectrum.

Pipeline exposed in the HTML (live, editable):
  1. Scale the charge-reduced region (m/z >= threshold) by a factor (PRESET, 10x);
     parent envelope stays 1x.
  2. Smooth the spectrum. Each peak group is linearly interpolated onto a fine
     uniform m/z grid (GRID_DX resolution), so sparse peaks gain enough points
     to form a smooth curve. The smoothing width is given in m/z and converted
     to a point window per segment, with zero-baseline padding past each peak
     group's edge -- the width covers the same m/z span on every peak, matching
     Origin's continuous-profile smoothing. The spectrum is drawn as one
     continuous line. Methods: Savitzky-Golay, adjacent averaging, Gaussian,
     binomial, median/percentile.

Usage:  python3 build_lcr_viewer.py [--serve] INPUT [OUTPUT_DIR]
INPUT is a 2-column m/z, intensity file (whitespace- or comma-delimited),
or a folder of such files. Per spectrum, two files are written into OUTPUT_DIR
(default: output/LCR/<dataset> beside this script, where <dataset> is the input
folder's name): the viewer HTML and a sibling processed CSV with the same stem
-- a preset-parameter snapshot the viewer links to. Processing parameters come
from load_preset() -- the built-in PRESET
overlaid with a viewer-saved preset.json; the scaling threshold is auto-placed
per spectrum. With --serve, the built viewers are also served on localhost so
the viewer's "Save preset" button writes preset.json directly (one click, no
file dialog); plain runs and standalone file:// viewers are unaffected.
The Plotly basic bundle (plotly-basic.min.js) must sit next to this script;
download once from https://cdn.plot.ly/plotly-basic-2.35.2.min.js
"""
import sys, os, json, re, math, datetime, copy

# Built-in fallback preset. load_preset() overlays preset.json (written by the
# viewer's Save preset button) on top of these; these values are used whenever
# no preset.json is present next to the script.
PRESET = {
    "scale_on": True,       # apply the charge-reduced x factor at all; turn off
                            # for plain MS1 smoothing (everything stays x1, and
                            # the threshold line/annotation are hidden)
    "scale": 10,            # charge-reduced x factor (used only when scale_on)
    "method": "avg",        # smoothing method (adjacent averaging)
    "width_mz": 0.04,       # smoothing width in m/z
    "poly": 3,              # SG poly order, retained for the SG control
    "show_overlay": False,  # pre-smoothing overlay checkbox default
    # Ladder-labeling block — opt-in module documented in
    # docs/superpowers/specs/2026-05-22-ladder-labeling-design.md
    "ladder_labels": {
        "enabled": False,           # module default off; turn on via panel checkbox
        "tol_mz": 5.0,              # snap window half-width (m/z); native-MS broad peaks
        "sigma_amber_relative": 0.01,  # amber if sigma_M / M > this
    },
}

def load_preset(here):
    """Effective preset: the built-in PRESET overlaid with preset.json, if a
    readable one sits next to the script. preset.json is written by the
    viewer's Save preset button; only keys also present in PRESET are taken.
    The 'ladder_labels' value is a nested dict; we merge it key-by-key so a
    partial saved block does not drop the other defaults. Returns a deep
    copy so callers can mutate the result without touching the module-level
    PRESET."""
    eff = copy.deepcopy(PRESET)
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
        if k not in saved:
            continue
        if isinstance(PRESET[k], dict):
            if not isinstance(saved[k], dict):
                continue  # malformed; keep the deepcopied default
            merged = dict(PRESET[k])
            for ik in PRESET[k]:
                if ik in saved[k]:
                    merged[ik] = saved[k][ik]
            eff[k] = merged
        else:
            eff[k] = saved[k]
    return eff

def save_posted_csv(out_dir, csv_written, name, body):
    """Write a posted CSV body to a sibling file in out_dir. Used by --serve
    when the viewer's "Update sibling CSV" button POSTs its current on-screen
    CSV. name must be one of the build's csv_written entries -- this both
    prevents path traversal and limits writes to the actual sibling files the
    build produced. Returns the written path."""
    if name not in csv_written:
        raise ValueError("unknown sibling CSV: %r" % name)
    path = os.path.join(out_dir, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path

def save_posted_preset(here, data):
    """Write preset.json next to the script from a posted preset dict; only
    keys present in PRESET are kept, and nested-dict values are sanitized to
    the sub-keys that PRESET declares. This keeps the saved file in a shape
    load_preset will round-trip cleanly."""
    clean = {}
    for k in PRESET:
        if k not in data:
            continue
        if isinstance(PRESET[k], dict):
            if not isinstance(data[k], dict):
                continue  # malformed nested value; skip
            clean[k] = {ik: data[k][ik] for ik in PRESET[k] if ik in data[k]}
        else:
            clean[k] = data[k]
    path = os.path.join(here, "preset.json")
    with open(path, "w") as fh:
        json.dump(clean, fh, indent=2)
    return path

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

def precursor_from_name(path):
    """Precursor m/z parsed from a spectrum filename's trailing number
    (decimals allowed): PF4_polyP_3300.xy -> 3300.0, run_3300.5.xy -> 3300.5.
    Returns None when the name (minus extension) does not end in a number."""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"(\d+(?:\.\d+)?)$", stem)
    return float(m.group(1)) if m else None

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

THRESHOLD_MARGIN = 45.0  # m/z placed past the parent envelope edge

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

def output_filename(precursor, when=None):
    """Per-spectrum viewer filename: LCR_mz<precursor>_<YYYYMMDD-HHMM>.html.
    precursor may be a float (parsed from a filename); it is rounded for the
    integer label."""
    when = when or datetime.datetime.now()
    return "LCR_mz%d_%s.html" % (int(round(precursor)),
                                 when.strftime("%Y%m%d-%H%M"))

def iter_spectrum_files(path):
    """Resolve an input path to a list of spectrum files. A file -> [file];
    a directory -> its sorted non-hidden .txt, .csv and .xy files
    (non-recursive)."""
    if os.path.isdir(path):
        out = []
        for name in sorted(os.listdir(path)):
            if name.startswith("."):
                continue
            if name.lower().endswith((".txt", ".csv", ".xy")):
                out.append(os.path.join(path, name))
        return out
    return [path]

# ---------------------------------------------------------------------------
# Build-time processing pipeline -- a Python mirror of the in-HTML JS pipeline
# (buildGrid + smoothAll + buildCSV). It exists so a build can write the
# sibling processed CSV without a browser: the viewer still owns the live,
# editable pipeline, this just reproduces it for the preset-default snapshot.
# Keep this in lockstep with the TEMPLATE JS if either side changes.
# ---------------------------------------------------------------------------
GRID_DX = 0.002    # target fine-grid resolution (m/z); see TEMPLATE buildGrid
MAX_CELLS = 6000   # per-segment grid-cell cap
PAD_MZ = 0.5       # width of zero-baseline padding on each side of a peak group

def _jround(v):
    """Round half up, matching JavaScript Math.round (Python round() banker-
    rounds, which would drift the grid-cell and window counts off the JS)."""
    return math.floor(v + 0.5)

def build_grid(mz, it):
    """Mirror of the in-HTML buildGrid: split into peak-group segments, linearly
    resample each onto a fine uniform m/z grid, pad with zero-baseline cells.
    Returns (gmz, git, bounds); each bounds entry is [start, end, step]."""
    n = len(mz)
    gaps = sorted(mz[i] - mz[i - 1] for i in range(1, n)
                  if 0 < mz[i] - mz[i - 1] < 0.5)
    dx0 = gaps[(len(gaps) - 1) // 2] if gaps else 0.02
    gmz, git, bounds = [], [], []
    for s, e in find_segments(mz):
        m0, m1 = mz[s], mz[e]
        g_start = len(gmz)
        if e > s and m1 > m0:
            dx_target = min(GRID_DX, dx0)
            ncell = _jround((m1 - m0) / dx_target) + 1
            ncell = max(2, min(ncell, MAX_CELLS))
            step = (m1 - m0) / (ncell - 1)
            npad = _jround(PAD_MZ / step)
            for c in range(npad, 0, -1):           # leading zero-baseline pad
                gmz.append(m0 - c * step); git.append(0.0)
            j = s
            for c in range(ncell):                 # linear-interpolate raw -> grid
                x = m0 + c * step
                while j < e and mz[j + 1] < x:
                    j += 1
                x0, x1 = mz[j], mz[j + 1]
                if x1 == x0:
                    y = max(it[j], it[j + 1])
                else:
                    t = (x - x0) / (x1 - x0)
                    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                    y = it[j] + t * (it[j + 1] - it[j])
                gmz.append(x); git.append(y)
            for c in range(1, npad + 1):           # trailing zero-baseline pad
                gmz.append(m1 + c * step); git.append(0.0)
            bounds.append([g_start, len(gmz) - 1, step])
        else:
            for k in range(s, e + 1):
                gmz.append(mz[k]); git.append(it[k])
            bounds.append([g_start, len(gmz) - 1, 0.0])
    return gmz, git, bounds

def _clamp_win(w):
    """Odd point window in [3, 8001] -- mirror of the in-HTML clampWin."""
    w = _jround(w)
    if w % 2 == 0:
        w += 1
    return max(3, min(w, 8001))

def _vat(y, i):
    """Zero-padded element access (the baseline outside a segment is zero)."""
    return y[i] if 0 <= i < len(y) else 0.0

def _moving_avg(y, w):
    """O(n) running-sum moving average."""
    n, h = len(y), (w - 1) // 2
    o = [0.0] * n
    if n == 0:
        return o
    s = sum(_vat(y, j) for j in range(-h, h + 1))
    o[0] = s / w
    for i in range(1, n):
        s += _vat(y, i + h) - _vat(y, i - h - 1)
        o[i] = s / w
    return o

def _gauss_kernel(w):
    h, sig = (w - 1) // 2, w / 6.0
    k = [math.exp(-(j * j) / (2 * sig * sig)) for j in range(-h, h + 1)]
    s = sum(k)
    return [v / s for v in k]

def _convolve(y, kernel):
    w, n = len(kernel), len(y)
    h = (w - 1) // 2
    return [sum(_vat(y, i + j) * kernel[j + h] for j in range(-h, h + 1))
            for i in range(n)]

def _median_filt(y, w):
    h = (w - 1) // 2
    out = []
    for i in range(len(y)):
        win = sorted(_vat(y, i + j) for j in range(-h, h + 1))
        out.append(win[(len(win) - 1) >> 1])
    return out

def _binomial(y, w):
    o, k = list(y), [0.25, 0.5, 0.25]
    for _ in range((w - 1) // 2):
        o = _convolve(o, k)
    return o

def _invert(M):
    """Gauss-Jordan matrix inverse -- mirror of the in-HTML invert."""
    n = len(M)
    A = [list(M[i]) + [1.0 if i == j else 0.0 for j in range(n)]
         for i in range(n)]
    for c in range(n):
        piv = c
        for r in range(c + 1, n):
            if abs(A[r][c]) > abs(A[piv][c]):
                piv = r
        A[c], A[piv] = A[piv], A[c]
        d = A[c][c] or 1e-12
        for j in range(2 * n):
            A[c][j] /= d
        for r in range(n):
            if r == c:
                continue
            f = A[r][c]
            for j in range(2 * n):
                A[r][j] -= f * A[c][j]
    return [row[n:] for row in A]

def _savgol(y, w, p):
    """Savitzky-Golay smoothing -- mirror of the in-HTML savgol/savgolM."""
    n = len(y)
    if w < 3:
        return list(y)
    if p >= w:
        p = w - 1
    h = (w - 1) // 2
    A = [[float(j) ** k for k in range(p + 1)] for j in range(-h, h + 1)]
    ata = [[sum(A[j][a] * A[j][b] for j in range(w)) for b in range(p + 1)]
           for a in range(p + 1)]
    inv = _invert(ata)
    coef = [sum(inv[0][m] * A[j][m] for m in range(p + 1)) for j in range(w)]
    return [sum(coef[j + h] * _vat(y, i + j) for j in range(-h, h + 1))
            for i in range(n)]

def smooth_all(y, bounds, method, width_mz, p):
    """Apply the chosen smoothing per peak-group segment -- mirror of the
    in-HTML smoothAll. width_mz becomes a point window via each segment's
    grid step, so the smoothing covers the same m/z span on every peak."""
    if method == "none":
        return list(y)
    o = list(y)
    for b0, b1, step in bounds:
        seg = y[b0:b1 + 1]
        if len(seg) < 3:
            continue
        ww = _clamp_win(width_mz / step if step > 0 else 3)
        if method == "avg":
            sm = _moving_avg(seg, ww)
        elif method == "gauss":
            sm = _convolve(seg, _gauss_kernel(ww))
        elif method == "binom":
            sm = _binomial(seg, ww)
        elif method == "median":
            sm = _median_filt(seg, ww)
        elif method == "sg":
            sm = _savgol(seg, ww, p)
        else:
            sm = seg
        for i, v in enumerate(sm):
            o[b0 + i] = v
    return o

def process_spectrum(mz, it, thr, preset):
    """Run the viewer's scale + smooth pipeline in Python with the preset's
    parameters; return (proc_x, proc_y) -- fine-grid m/z and processed
    intensity. Mirrors the in-HTML recompute() so a build-time CSV equals the
    viewer's export at its default (preset) settings."""
    gmz, git, bounds = build_grid(mz, it)
    if preset.get("scale_on", True):
        factor = preset["scale"]
        scaled = [(v * factor if gmz[i] >= thr else v) for i, v in enumerate(git)]
    else:
        # MS1 / no-scale mode: smooth the raw intensities as-is.
        scaled = list(git)
    proc_y = smooth_all(scaled, bounds, preset["method"],
                        preset["width_mz"], preset["poly"])
    return gmz, proc_y

def build_csv(proc_x, proc_y):
    """Processed-CSV text: an 'm/z,intensity_processed' header then one row per
    grid point with positive intensity (zero-baseline grid and pad cells are
    dropped) -- identical in form to the viewer's buildCSV()."""
    lines = ["m/z,intensity_processed"]
    for x, y in zip(proc_x, proc_y):
        if y > 0:
            lines.append("%s,%s" % (x, y))
    return "\n".join(lines) + "\n"

def build_html(mz, it, thr, plotly, html_name, preset, labeler_js):
    """Assemble a self-contained viewer HTML from spectrum data, the
    per-spectrum threshold, the inlined Plotly bundle, and the inlined
    ladder-labeler JS. Control defaults come from the effective preset
    (see load_preset). The processed-CSV download/link/sibling-file
    reuses html_name's stem so the CSV matches its viewer
    (LCR_mz<precursor>_<timestamp>.csv); the header hyperlink points at
    that sibling file written next to the viewer (see main)."""
    csv_name = os.path.splitext(os.path.basename(html_name))[0] + ".csv"
    html = TEMPLATE
    html = html.replace("__SCALEON__",
                        "checked" if preset.get("scale_on", True) else "")
    html = html.replace("__SCALE__", str(preset["scale"]))
    html = html.replace("__THR__", "%g" % thr)
    html = html.replace("__WIDTH__", str(preset["width_mz"]))
    html = html.replace("__POLY__", str(preset["poly"]))
    html = html.replace("__RAWOV__", "checked" if preset["show_overlay"] else "")
    html = html.replace('value="%s"' % preset["method"],
                        'value="%s" selected' % preset["method"])
    html = html.replace("__CSVNAME__", json.dumps(csv_name))
    html = html.replace("__CSVHREF__", csv_name)
    html = html.replace("__MZ__", json.dumps(mz))
    html = html.replace("__IT__", json.dumps(it))
    html = html.replace("__PLOTLY__", plotly)
    html = html.replace("__LADDER_LABELER__", labeler_js)
    ll = preset.get("ladder_labels", {})
    html = html.replace("__LADDER_ENABLED__",
                        "checked" if ll.get("enabled", False) else "")
    html = html.replace("__LADDER_TOL__", str(ll.get("tol_mz", 5.0)))
    return html

def parse_args(argv, here):
    """Parse CLI args into (serve_mode, src, out_dir). A --serve flag anywhere
    in argv enables localhost serve mode; the remaining positionals are INPUT
    then OUTPUT_DIR. When OUTPUT_DIR is omitted it defaults to
    <here>/output/LCR/<dataset> -- a subfolder of the code repo -- where
    <dataset> is the input folder's name (the parent folder's name for a single
    input file), so each dataset's viewers land in their own subfolder."""
    serve_mode = "--serve" in argv
    pos = [a for a in argv if a != "--serve"]
    src = pos[0] if len(pos) > 0 else os.path.join(here, "clipboard_spectrum.txt")
    if len(pos) > 1:
        out_dir = pos[1]
    else:
        folder = src if os.path.isdir(src) else os.path.dirname(
            os.path.abspath(src))
        dataset = os.path.basename(os.path.abspath(folder)) or "LCR"
        out_dir = os.path.join(here, "output", "LCR", dataset)
    return serve_mode, src, out_dir

def serve(out_dir, written, csv_written, here):
    """Serve the freshly built viewers (and their sibling CSVs) on localhost
    (127.0.0.1) and accept the viewer's "Save preset" POSTs, writing preset.json
    next to the script. Runs until interrupted (Ctrl-C). Standalone viewers
    opened as file:// are unaffected -- this is only a convenience launcher;
    no data leaves the host."""
    import http.server, webbrowser

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # keep the console quiet

        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            page = self.path.split("?")[0].lstrip("/")
            if page == "" and len(written) > 1:
                links = "".join('<li><a href="%s">%s</a></li>' % (n, n)
                                for n in written)
                self._send(200, "<!doctype html><meta charset=utf-8>"
                           "<title>LCR viewers</title><h2>LCR viewers</h2>"
                           "<ul>%s</ul>" % links)
                return
            if page == "":
                page = written[0]
            if page in written:
                with open(os.path.join(out_dir, page), "rb") as fh:
                    self._send(200, fh.read())
            elif page in csv_written:
                with open(os.path.join(out_dir, page), "rb") as fh:
                    self._send(200, fh.read(), "text/csv; charset=utf-8")
            else:
                self._send(404, "not found")

        def do_POST(self):
            from urllib.parse import urlsplit, parse_qs
            parts = urlsplit(self.path)
            route = parts.path.rstrip("/")
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n)
            if route == "/preset":
                try:
                    data = json.loads(raw.decode("utf-8"))
                    path = save_posted_preset(here, data)
                    self._send(200, json.dumps({"ok": True}),
                               "application/json")
                    print("preset saved -> %s" % path)
                except (ValueError, OSError) as e:
                    self._send(400, json.dumps({"ok": False, "error": str(e)}),
                               "application/json")
                return
            if route == "/csv":
                try:
                    name = parse_qs(parts.query).get("name", [""])[0]
                    path = save_posted_csv(out_dir, csv_written, name,
                                           raw.decode("utf-8"))
                    self._send(200, json.dumps({"ok": True}),
                               "application/json")
                    print("sibling CSV updated -> %s" % path)
                except (ValueError, OSError) as e:
                    self._send(400, json.dumps({"ok": False, "error": str(e)}),
                               "application/json")
                return
            self._send(404, "not found")

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("\nServing %d viewer(s) at %s" % (len(written), url))
    print('"Save preset" writes preset.json and "Update sibling CSV" '
          "overwrites the build-time CSV directly. Ctrl-C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    serve_mode, src, out_dir = parse_args(sys.argv[1:], here)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()
    with open(os.path.join(here, "ladder_labeler.js")) as fh:
        labeler_js = fh.read()
    preset = load_preset(here)

    files = iter_spectrum_files(src)
    if not files:
        sys.exit("No spectrum files found at " + src)

    written, csv_written = [], []
    for path in files:
        try:
            mz, it = parse_spectrum(path)
        except (ValueError, OSError) as e:
            print("skip %s: %s" % (path, e))
            continue
        named = precursor_from_name(path)
        thr = auto_threshold(mz, it, named)
        if named is not None:
            prec, source = named, "from filename"
        else:
            prec, source = precursor_mz(mz, it), "base peak"
        name = output_filename(prec)
        html = build_html(mz, it, thr, plotly, name, preset, labeler_js)
        out = os.path.join(out_dir, name)
        with open(out, "w") as fh:
            fh.write(html)
        written.append(name)
        # sibling processed CSV -- a preset-default snapshot the viewer's
        # header hyperlink points at (same folder, same stem).
        csv_name = os.path.splitext(name)[0] + ".csv"
        proc_x, proc_y = process_spectrum(mz, it, thr, preset)
        with open(os.path.join(out_dir, csv_name), "w") as fh:
            fh.write(build_csv(proc_x, proc_y))
        csv_written.append(csv_name)
        print("Wrote %s + %s  (precursor m/z %d (%s), threshold %.1f, "
              "%d pts, %.1f KB)" % (name, csv_name, int(round(prec)), source,
                                    thr, len(mz), os.path.getsize(out) / 1024))

    if serve_mode:
        if not written:
            sys.exit("Nothing built to serve.")
        serve(out_dir, written, csv_written, here)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>polyP LCR spectrum - interactive</title>
<style>
 body{font-family:-apple-system,Segoe UI,Arial,sans-serif;margin:0;background:#fafafa;color:#222}
 #controls{padding:10px 14px;background:#fff;border-bottom:1px solid #ddd;
   display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}
 .ctl{display:flex;flex-direction:column;font-size:12px}
 .ctl label{margin-bottom:3px;color:#555;font-weight:600}
 .ctl input,.ctl select{padding:4px 6px;font-size:13px;border:1px solid #bbb;border-radius:4px}
 .ctl input[type=number]{width:96px}
 .chk label{font-weight:400;color:#333;display:block;margin:2px 0}
 #plot{width:100%;height:75vh}
 button{padding:6px 11px;font-size:13px;border:1px solid #888;border-radius:4px;
   background:#f0f0f0;cursor:pointer}
 button:hover{background:#e3e3e3}
 .hint{font-size:11px;color:#888;padding:5px 14px;line-height:1.5}
 #status{color:#0050b3;font-weight:600}
 #csvfile{font-size:11px;color:#0050b3;word-break:break-all;max-width:240px}
</style>
</head>
<body>
<div id="controls">
 <div class="ctl chk">
   <label><input type="checkbox" id="scaleon" __SCALEON__>
     Scale charge-reduced region
     <span style="font-size:11px;color:#888">(off = plain MS1 smoothing)</span></label></div>
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
 <div class="ctl"><label>Smoothing width (m/z)</label>
   <input type="number" id="width" value="__WIDTH__" step="0.005" min="0" max="10"></div>
 <div class="ctl"><label>Poly order (SG)</label>
   <input type="number" id="poly" value="__POLY__" step="1" min="1" max="6"></div>
 <div class="ctl chk">
   <label><input type="checkbox" id="rawov" __RAWOV__> pre-smoothing overlay</label>
   <label><input type="checkbox" id="logy"> log Y axis</label></div>
 <div class="ctl"><button id="dl">Download processed CSV</button></div>
 <div class="ctl"><button id="updatecsv">Update sibling CSV</button>
   <span id="updatecsvstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
 <div class="ctl"><button id="link">Link CSV file (live)</button>
   <span id="csvstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
 <div class="ctl"><button id="savepreset">Save preset</button>
   <span id="presetstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
 <div class="ctl"><label>Sibling CSV file</label>
   <a id="csvfile" href="__CSVHREF__" download="__CSVHREF__"
      title="Processed CSV written next to this viewer at build time, using the preset defaults. Click 'Update sibling CSV' to overwrite it with the current on-screen settings.">__CSVHREF__</a></div>
 <div class="ctl chk" style="border-left:1px solid #ddd;padding-left:14px">
   <label><input type="checkbox" id="ladder-enabled" __LADDER_ENABLED__>
     Ladder labels
     <span style="font-size:11px;color:#888">(opt-in; off by default)</span></label>
   <label style="display:flex;align-items:center;gap:6px;margin-top:4px">
     Snap tol (m/z):
     <input type="number" id="ladder-tol" value="__LADDER_TOL__" step="0.5"
            min="0.1" max="50" style="width:70px;padding:3px 5px"></label>
 </div>
 <div class="ctl" style="min-width:280px">
   <label>Ladders</label>
   <div id="ladder-list"
        style="font-size:11px;border:1px solid #ddd;border-radius:4px;
               padding:4px 6px;min-height:28px;max-height:88px;overflow:auto;
               background:#fafafa">
     <span style="color:#888">(none — use Add buttons)</span>
   </div>
   <div style="display:flex;gap:4px;margin-top:4px">
     <button id="ladder-add-type" style="font-size:11px;padding:3px 8px">
       + Type seed</button>
     <button id="ladder-add-twoclick" style="font-size:11px;padding:3px 8px">
       + 2-click seed</button>
     <button id="ladder-clear" style="font-size:11px;padding:3px 8px">
       Clear all</button>
   </div>
   <span id="ladder-status"
         style="font-size:11px;color:#888;margin-top:3px"></span>
 </div>
</div>
<div class="hint">
 Order: (1) if "Scale charge-reduced region" is on, m/z &ge; threshold x factor and
 the parent envelope stays x1; off skips scaling entirely (plain MS1 smoothing);
 (2) sparse peaks are linearly interpolated onto a fine uniform m/z grid, then smoothed
 with zero-baseline padding - the smoothing width is in m/z, so it covers the same span
 on every peak, drawn as one continuous spectrum. Matches Origin's continuous-profile
 smoothing. Edit any control - plot updates live. <span id="status"></span>
</div>
<div id="plot"></div>
<script>__PLOTLY__</script>
<script>__LADDER_LABELER__</script>
<script>
// Mutable so the uploader can swap spectra without reloading the page.
// In default builds, loadSpectrum is called exactly once at startup.
let RAW_MZ=[], RAW_IT=[], CSV_NAME="";
let G=null;  // populated by loadSpectrum — buildGrid reads RAW_MZ/RAW_IT

// ---------- build uniform per-segment grid (once) ----------
// GRID_DX is the target grid resolution (m/z). Each peak group is linearly
// interpolated onto a uniform grid this fine, so sparse peaks (only a few raw
// points) gain enough points to smooth into a curve. The grid is never coarser
// than the raw data; MAX_CELLS bounds a very wide segment. PAD_MZ is the width
// of zero-baseline cells added on each side of a peak group so a broadened
// (smoothed) peak decays back to zero within its own segment; 0.5 is the
// largest value that cannot make padded neighbours overlap (segments split
// only at gaps > 1.0 m/z), and it keeps the baseline clean for smoothing
// widths up to ~1 m/z (beyond that a peak's skirt outruns its pad).
// GROUP_GAP is the empty-m/z stretch across which the drawn line is held flat
// on the zero baseline (via inserted anchor points), so distant peak groups
// are joined only by a true baseline -- not a connector at an elevated,
// average-looking level. Smoothing is unaffected; it is always per cluster.
const GRID_DX=0.002, MAX_CELLS=6000, PAD_MZ=0.5, GROUP_GAP=30;
function median(arr){const a=arr.slice().sort((x,z)=>x-z);
 return a.length?a[(a.length-1)>>1]:0;}
function buildGrid(){
 const n=RAW_MZ.length, allgaps=[];
 for(let i=1;i<n;i++){const g=RAW_MZ[i]-RAW_MZ[i-1];if(g>0&&g<0.5)allgaps.push(g);}
 const dx0=allgaps.length?median(allgaps):0.02;
 const gapThr=Math.max(1.0,dx0*60);
 // segment the raw data at large gaps
 const segs=[]; let start=0;
 for(let i=1;i<n;i++){
  if(RAW_MZ[i]-RAW_MZ[i-1]>gapThr){segs.push([start,i-1]);start=i;}}
 segs.push([start,n-1]);
 // resample each segment onto a fine uniform grid by linear interpolation.
 // bounds entries are [gridStart, gridEnd, step] -- step lets the smoother
 // turn an m/z width into a point window.
 const gmz=[], git=[], bounds=[];
 for(const seg of segs){
  const s=seg[0], e=seg[1], m0=RAW_MZ[s], m1=RAW_MZ[e];
  const gStart=gmz.length;
  if(e>s && m1>m0){
   // grid step: as fine as GRID_DX, never coarser than the raw data,
   // capped by MAX_CELLS so a very wide segment stays bounded.
   const dxTarget=Math.min(GRID_DX,dx0);
   let ncell=Math.round((m1-m0)/dxTarget)+1;
   if(ncell<2)ncell=2; if(ncell>MAX_CELLS)ncell=MAX_CELLS;
   const step=(m1-m0)/(ncell-1);
   // leading zero-baseline pad so the smoothed peak decays to zero on the left
   const npad=Math.round(PAD_MZ/step);
   for(let c=npad;c>=1;c--){gmz.push(m0-c*step);git.push(0);}
   // linear-interpolate raw intensity onto the uniform cells (two-pointer
   // sweep -- raw m/z and grid cells are both ascending).
   let j=s;
   for(let c=0;c<ncell;c++){
    const x=m0+c*step;
    while(j<e && RAW_MZ[j+1]<x)j++;
    const x0=RAW_MZ[j], x1=RAW_MZ[j+1];
    let y;
    if(x1===x0){y=Math.max(RAW_IT[j],RAW_IT[j+1]);}
    else{let t=(x-x0)/(x1-x0); if(t<0)t=0; if(t>1)t=1;
     y=RAW_IT[j]+t*(RAW_IT[j+1]-RAW_IT[j]);}
    gmz.push(x); git.push(y);}
   // trailing zero-baseline pad (decay to zero on the right)
   for(let c=1;c<=npad;c++){gmz.push(m1+c*step);git.push(0);}
   bounds.push([gStart,gmz.length-1,step]);
  }else{
   for(let k=s;k<=e;k++){gmz.push(RAW_MZ[k]);git.push(RAW_IT[k]);}
   bounds.push([gStart,gmz.length-1,0]);}
 }
 return {gmz,git,bounds,nseg:segs.length};
}
// Single entry point for setting the active spectrum. Both the default
// build (one call at startup with the inlined arrays) and the uploader
// (one call per sidebar click) go through here.
const loadSpectrum = function(mz, it, csvName){
 RAW_MZ = mz;
 RAW_IT = it;
 CSV_NAME = csvName || "";
 G = (RAW_MZ.length >= 2) ? buildGrid() : null;
 // Update the sibling-CSV hyperlink in the header to reflect the new name.
 const a = document.getElementById('csvfile');
 if (a) { a.textContent = CSV_NAME; a.href = CSV_NAME; a.download = CSV_NAME; }
 // Recompute and redraw. recompute is the existing top-level entry
 // the controls already call on input changes; it re-reads RAW_MZ/G.
 if (typeof recompute === 'function' && G) recompute();
};

// ---------- smoothing primitives (zero-padded) ----------
// The baseline outside a peak group is physically zero, so the smoothing
// window is filled with zeros past a segment edge instead of being shrunk.
// Consequence: the smoothing covers the same m/z span on every peak, and the
// result equals Origin smoothing the full continuous zero-baseline profile.
function clampWin(w){w=Math.round(w);if(w%2===0)w++;if(w<3)w=3;if(w>8001)w=8001;return w;}
function vAt(y,i){return (i>=0&&i<y.length)?y[i]:0;}
// running-sum moving average -- O(n) regardless of window, so a wide
// smoothing width stays responsive.
function movingAvg(y,w){const n=y.length,h=(w-1)/2,o=new Array(n);
 if(n===0)return o;
 let s=0; for(let j=-h;j<=h;j++)s+=vAt(y,j);
 o[0]=s/w;
 for(let i=1;i<n;i++){s+=vAt(y,i+h)-vAt(y,i-h-1);o[i]=s/w;}
 return o;}
function gaussKernel(w){const h=(w-1)/2,sig=w/6.0,k=[];let s=0;
 for(let j=-h;j<=h;j++){const v=Math.exp(-(j*j)/(2*sig*sig));k.push(v);s+=v;}
 return k.map(v=>v/s);}
function convolve(y,kernel){const w=kernel.length,h=(w-1)/2,n=y.length,o=new Array(n);
 for(let i=0;i<n;i++){let s=0;
  for(let j=-h;j<=h;j++)s+=vAt(y,i+j)*kernel[j+h];o[i]=s;}return o;}
function medianFilt(y,w){const n=y.length,h=(w-1)/2,o=new Array(n);
 for(let i=0;i<n;i++){const win=[];
  for(let j=-h;j<=h;j++)win.push(vAt(y,i+j));
  win.sort((a,b)=>a-b);o[i]=win[(win.length-1)>>1];}return o;}
function binomial(y,w){let iters=(w-1)/2,o=y.slice();const k=[0.25,0.5,0.25];
 for(let t=0;t<iters;t++)o=convolve(o,k);return o;}
function invert(M){const n=M.length,
 A=M.map((r,i)=>r.concat(Array.from({length:n},(_,j)=>i===j?1:0)));
 for(let c=0;c<n;c++){let piv=c;
  for(let r=c+1;r<n;r++)if(Math.abs(A[r][c])>Math.abs(A[piv][c]))piv=r;
  [A[c],A[piv]]=[A[piv],A[c]];const d=A[c][c]||1e-12;
  for(let j=0;j<2*n;j++)A[c][j]/=d;
  for(let r=0;r<n;r++){if(r===c)continue;const f=A[r][c];
   for(let j=0;j<2*n;j++)A[r][j]-=f*A[c][j];}}
 return A.map(r=>r.slice(n));}
// Savitzky-Golay with proper polynomial edge handling (Origin-style):
// fit a degree-p polynomial in each window, evaluate at the true offset.
function savgolM(w,p){const h=(w-1)/2,A=[];
 for(let j=-h;j<=h;j++){const row=[];
  for(let k=0;k<=p;k++)row.push(Math.pow(j,k));A.push(row);}
 const ATA=[];
 for(let a=0;a<=p;a++){const row=[];
  for(let b=0;b<=p;b++){let s=0;for(let j=0;j<w;j++)s+=A[j][a]*A[j][b];row.push(s);}
  ATA.push(row);}
 const inv=invert(ATA),M=[];
 for(let k=0;k<=p;k++){const row=[];
  for(let j=0;j<w;j++){let s=0;for(let m=0;m<=p;m++)s+=inv[k][m]*A[j][m];row.push(s);}
  M.push(row);}
 return M;}
function savgol(y,w,p){const n=y.length;
 if(w<3)return y.slice(); if(p>=w)p=w-1;
 const h=(w-1)/2,c=savgolM(w,p)[0],o=new Array(n);
 for(let i=0;i<n;i++){let s=0;
  for(let j=-h;j<=h;j++)s+=c[j+h]*vAt(y,i+j);o[i]=s;}
 return o;}

// ---------- apply chosen method per segment ----------
// widthMz (m/z) becomes a point window per segment via that segment's grid
// step, so the smoothing covers the same m/z span on every peak.
function smoothAll(y,method,widthMz,p){
 if(method==='none')return y.slice();
 const o=y.slice();
 for(const bd of G.bounds){
  const b0=bd[0],b1=bd[1],step=bd[2],seg=y.slice(b0,b1+1);
  if(seg.length<3)continue;            // too short to smooth -- leave as-is
  const ww=clampWin(step>0?widthMz/step:3);
  let sm;
  if(method==='avg')sm=movingAvg(seg,ww);
  else if(method==='gauss')sm=convolve(seg,gaussKernel(ww));
  else if(method==='binom')sm=binomial(seg,ww);
  else if(method==='median')sm=medianFilt(seg,ww);
  else if(method==='sg')sm=savgol(seg,ww,p);
  else sm=seg;
  for(let i=0;i<sm.length;i++)o[b0+i]=sm[i];}
 return o;}

// ---------- live pipeline ----------
let PROC_X=[],PROC_Y=[];
function recompute(){
 const scaleOn=document.getElementById('scaleon').checked;
 const factor=scaleOn?(parseFloat(document.getElementById('scale').value)||1):1;
 const thr=parseFloat(document.getElementById('thr').value)||0;
 const method=document.getElementById('method').value;
 const widthMz=parseFloat(document.getElementById('width').value)||0.04;
 const p=parseInt(document.getElementById('poly').value)||3;
 const logy=document.getElementById('logy').checked;
 const rawov=document.getElementById('rawov').checked;
 // scaleOn off => smooth raw intensities as-is (plain MS1 mode).
 const scaled=scaleOn?G.git.map((v,i)=>G.gmz[i]>=thr?v*factor:v):G.git.slice();
 const sm=smoothAll(scaled,method,widthMz,p);
 PROC_X=G.gmz; PROC_Y=sm;
 // Draw as one continuous line. Across an empty stretch wider than GROUP_GAP,
 // insert two zero-baseline anchor points so the line runs flat along the zero
 // baseline between distant peak groups -- a true baseline, not a connector
 // that bridges them at an elevated, average-looking level.
 const px=[],py=[],pov=[];
 for(let b=0;b<G.bounds.length;b++){
  const b0=G.bounds[b][0], b1=G.bounds[b][1];
  if(b>0){
   const prevEnd=G.gmz[G.bounds[b-1][1]], thisStart=G.gmz[b0];
   if(thisStart-prevEnd>GROUP_GAP){
    px.push(prevEnd+1.0,thisStart-1.0); py.push(0,0); pov.push(0,0);}
  }
  for(let i=b0;i<=b1;i++){px.push(G.gmz[i]);py.push(sm[i]);pov.push(scaled[i]);}
 }
 const traces=[];
 if(rawov)traces.push({x:px,y:pov,name:scaleOn?'scaled, pre-smooth':'pre-smooth',
   mode:'lines',line:{width:0.8,color:'rgba(150,150,150,0.55)'}});
 traces.push({x:px,y:py,name:scaleOn?'scaled + smoothed':'smoothed',mode:'lines',
   line:{width:1.3,color:'#0050b3'}});
 const layout={
   margin:{l:66,r:20,t:34,b:50},
   xaxis:{title:'m/z',showgrid:false},
   yaxis:{title:'intensity'+(scaleOn&&factor!==1?' (CR x'+factor+')':''),
          type:logy?'log':'linear',rangemode:'tozero'},
   legend:{orientation:'h',y:1.12},
   // Threshold marker + "x N above" annotation are only meaningful when
   // the charge-reduced scaling is on; hide them in plain MS1 mode.
   shapes:scaleOn?[{type:'line',x0:thr,x1:thr,yref:'paper',y0:0,y1:1,
            line:{color:'#cc4400',width:1,dash:'dot'}}]:[],
   annotations:scaleOn?[{x:thr,yref:'paper',y:1.04,text:'x'+factor+' above',
                 showarrow:false,font:{size:10,color:'#cc4400'}}]:[]
 };
 // Merge ladder-label shapes/annotations from the LadderLabeler module
 // (spec §5.2, §5.4). When disabled, this returns empty arrays so the
 // existing MS1 layout is bit-identical to before.
 if (typeof LadderLabeler !== 'undefined') {
   // Sync the LCR scale/threshold so AUC integrates the unscaled signal.
   LadderLabeler.state.threshold = scaleOn ? thr : Infinity;
   LadderLabeler.state.scale = scaleOn ? factor : 1;
   LadderLabeler.refreshAll(PROC_X, PROC_Y);
   const g = LadderLabeler.buildAnnotations(PROC_X, PROC_Y);
   layout.shapes = (layout.shapes || []).concat(g.shapes);
   layout.annotations = (layout.annotations || []).concat(g.annotations);
   if (typeof renderLadderPanel === 'function') renderLadderPanel();
 }
 Plotly.react('plot',traces,layout,{responsive:true,
   toImageButtonOptions:{format:'png',scale:3,filename:'polyP_LCR_spectrum'}});
 document.getElementById('status').textContent=
   G.nseg+' peak segments, '+G.gmz.length+' grid points.';
 syncCSV();
}
['scaleon','scale','thr','method','width','poly','logy','rawov'].forEach(id=>{
 const el=document.getElementById(id);
 el.addEventListener('input',recompute);
 el.addEventListener('change',recompute);
});
// Dim scale/threshold inputs when the toggle is off -- they're inert in
// plain MS1 mode, so the disabled state is the honest visual.
function syncScaleEnabled(){
 const on=document.getElementById('scaleon').checked;
 document.getElementById('scale').disabled=!on;
 document.getElementById('thr').disabled=!on;
}
document.getElementById('scaleon').addEventListener('change',syncScaleEnabled);
syncScaleEnabled();
function buildCSV(){
 // drop zero-intensity points (the zero-baseline grid and pad cells)
 let csv='m/z,intensity_processed\n';
 for(let i=0;i<PROC_X.length;i++)
  if(PROC_Y[i]>0)csv+=PROC_X[i]+','+PROC_Y[i]+'\n';
 return csv;
}
document.getElementById('dl').addEventListener('click',async()=>{
 const text=buildCSV();
 // FSA path: the Save dialog opens in the sibling CSV's folder thanks to the
 // shared `lcr-sibling-csv` picker id (Chrome remembers the last directory
 // used by any picker with that id). Rename in the dialog if you want a
 // different filename. Cancelling is a no-op.
 if(window.showSaveFilePicker&&location.protocol==='file:'){
  try{
   const h=await window.showSaveFilePicker({
     suggestedName:CSV_NAME,
     id:'lcr-sibling-csv',
     types:[{description:'CSV',accept:{'text/csv':['.csv']}}]});
   const w=await h.createWritable();
   await w.write(text); await w.close();
  }catch(e){/* user cancelled the picker */}
  return;
 }
 // Fallback (served mode, or browsers without FSA): classic download.
 const blob=new Blob([text],{type:'text/csv'}),a=document.createElement('a');
 a.href=URL.createObjectURL(blob);a.download=CSV_NAME;a.click();
});
// ---- update sibling CSV: serve mode POSTs straight to the build-time file;
// standalone uses the File System Access API. The picked handle is persisted
// in IndexedDB (keyed by CSV_NAME) so reloads skip the picker -- a click after
// a reload only needs a one-shot readwrite re-grant. Chrome also remembers
// the last directory for our stable picker id, so the very first pick can
// land in the right folder without navigating the tree each time. ----
let siblingHandle=null;
const updateBtn=document.getElementById('updatecsv');
const updateStat=document.getElementById('updatecsvstat');
const HDB_NAME='lcr-viewer',HDB_STORE='handles';
const HDB_SIBLING='sibling:'+CSV_NAME,HDB_LINK='link:'+CSV_NAME;
function hdbOpen(){return new Promise((res,rej)=>{
 const r=indexedDB.open(HDB_NAME,1);
 r.onupgradeneeded=()=>r.result.createObjectStore(HDB_STORE);
 r.onsuccess=()=>res(r.result); r.onerror=()=>rej(r.error);});}
async function hdbGet(key){try{const db=await hdbOpen();
 return await new Promise((res,rej)=>{
  const t=db.transaction(HDB_STORE,'readonly').objectStore(HDB_STORE).get(key);
  t.onsuccess=()=>res(t.result||null); t.onerror=()=>rej(t.error);});
 }catch(e){return null;}}
async function hdbPut(key,h){try{const db=await hdbOpen();
 await new Promise((res,rej)=>{
  const t=db.transaction(HDB_STORE,'readwrite').objectStore(HDB_STORE).put(h,key);
  t.onsuccess=()=>res(); t.onerror=()=>rej(t.error);});}catch(e){}}
async function ensurePerm(h){const opts={mode:'readwrite'};
 if((await h.queryPermission(opts))==='granted')return true;
 return (await h.requestPermission(opts))==='granted';}
if(window.showSaveFilePicker&&location.protocol==='file:'){
 hdbGet(HDB_SIBLING).then(h=>{if(h){siblingHandle=h;
   updateStat.textContent='linked '+h.name+' (click to update)';}});
}
updateBtn.addEventListener('click',async()=>{
 const text=buildCSV();
 if(location.protocol==='http:'||location.protocol==='https:'){
  try{
   const r=await fetch('/csv?name='+encodeURIComponent(CSV_NAME),{method:'POST',
     headers:{'Content-Type':'text/csv'},body:text});
   const j=await r.json();
   updateStat.textContent=j.ok?'updated '+CSV_NAME
     :'update failed: '+(j.error||r.status);
  }catch(e){updateStat.textContent='update failed: '+e.message;}
  return;
 }
 if(!window.showSaveFilePicker){
  updateStat.textContent='needs Chrome/Edge or --serve';
  return;
 }
 try{
  if(siblingHandle&&!(await ensurePerm(siblingHandle))){
   siblingHandle=null; await hdbPut(HDB_SIBLING,null);
  }
  if(!siblingHandle){
   siblingHandle=await window.showSaveFilePicker({
     suggestedName:CSV_NAME,
     id:'lcr-sibling-csv',
     types:[{description:'CSV',accept:{'text/csv':['.csv']}}]});
   await hdbPut(HDB_SIBLING,siblingHandle);
  }
  const w=await siblingHandle.createWritable();
  await w.write(text); await w.close();
  updateStat.textContent='updated '+siblingHandle.name;
 }catch(e){if(e.name!=='AbortError'){
   updateStat.textContent='write failed: '+e.message;}}
});
if(!window.showSaveFilePicker&&location.protocol==='file:'){
 updateBtn.disabled=true;
 updateBtn.title='Needs Chrome/Edge for direct write, or run with --serve.';
 updateStat.textContent='direct write not supported in this browser';
}
// ---- linked-file live sync: pick an EXISTING CSV to sync into. Uses
// showOpenFilePicker so the dialog is a "Pick file" rather than "Save as",
// requests readwrite permission once, and persists the handle in IndexedDB
// so reloads re-link silently (one click needed to re-grant permission).
// Shares the `lcr-sibling-csv` picker id with the other CSV buttons so the
// dialog lands in the sibling CSV's folder. ----
let csvHandle=null,csvTimer=null;
const linkBtn=document.getElementById('link');
const csvStat=document.getElementById('csvstat');
if(!window.showOpenFilePicker){
 linkBtn.disabled=true;
 linkBtn.title='Live link needs Chrome or Edge; use Download instead.';
 csvStat.textContent='live link not supported in this browser';
}else{
 hdbGet(HDB_LINK).then(h=>{if(h){csvHandle=h;
   csvStat.textContent='linked '+h.name+' (click Link to re-activate)';}});
 linkBtn.addEventListener('click',async()=>{
  try{
   const [h]=await window.showOpenFilePicker({
     id:'lcr-sibling-csv',
     types:[{description:'CSV',accept:{'text/csv':['.csv']}}],
     multiple:false});
   if(!(await ensurePerm(h))){
    csvStat.textContent='readwrite permission denied'; return;
   }
   csvHandle=h; await hdbPut(HDB_LINK,h);
   csvStat.textContent='linked: '+csvHandle.name; syncCSV();
  }catch(e){if(e.name!=='AbortError'){
    csvStat.textContent='link failed: '+e.message;}}
 });
}
function syncCSV(){
 if(!csvHandle)return;
 clearTimeout(csvTimer);
 csvTimer=setTimeout(async()=>{
  try{
   if((await csvHandle.queryPermission({mode:'readwrite'}))!=='granted'){
    csvStat.textContent='click Link CSV file to re-grant permission'; return;
   }
   const w=await csvHandle.createWritable();
   await w.write(buildCSV());
   await w.close();
   csvStat.textContent='synced: '+csvHandle.name;
  }catch(e){csvStat.textContent='write failed: '+e.message;}
 },200);
}
// ---- save preset.json (File System Access API, download fallback) ----
function buildPreset(){
 return {
  scale_on:document.getElementById('scaleon').checked,
  scale:parseFloat(document.getElementById('scale').value)||1,
  method:document.getElementById('method').value,
  width_mz:parseFloat(document.getElementById('width').value)||0.04,
  poly:parseInt(document.getElementById('poly').value)||3,
  show_overlay:document.getElementById('rawov').checked,
  ladder_labels:{
   enabled:document.getElementById('ladder-enabled').checked,
   tol_mz:parseFloat(document.getElementById('ladder-tol').value)||5.0,
   sigma_amber_relative:
    (typeof LadderLabeler!=='undefined')
     ?LadderLabeler.state.sigmaAmberRelative
     :0.01,
  },
 };
}
const presetStat=document.getElementById('presetstat');
document.getElementById('savepreset').addEventListener('click',async()=>{
 const text=JSON.stringify(buildPreset(),null,2);
 // Served by build_lcr_viewer.py --serve: POST straight to preset.json.
 if(location.protocol==='http:'||location.protocol==='https:'){
  try{
   const r=await fetch('/preset',{method:'POST',
     headers:{'Content-Type':'application/json'},body:text});
   const j=await r.json();
   presetStat.textContent=j.ok?'saved to preset.json - applies to next build'
     :'save failed: '+(j.error||r.status);
  }catch(e){presetStat.textContent='save failed: '+e.message;}
  return;
 }
 // Standalone (file://): File System Access API, with a download fallback.
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
loadSpectrum(__MZ__, __IT__, __CSVNAME__);

// ---------- ladder labeler: panel binding ----------
// Hooks the LadderLabeler module to the control panel inserted in Task 9
// and re-renders the panel + plot whenever the labeler state changes.
function renderLadderPanel() {
  const list = document.getElementById('ladder-list');
  if (!list) return;
  const st = LadderLabeler.state;
  document.getElementById('ladder-enabled').checked = st.enabled;
  document.getElementById('ladder-tol').value = st.tolMz;
  if (st.ladders.length === 0) {
    list.innerHTML = '<span style="color:#888">(none — use Add buttons)</span>';
    return;
  }
  function chipsFor(L) {
    // Sort labels by descending z so chips read 7+, 6+, 5+, …
    const sorted = L.labels.slice().sort((a, b) => b.z - a.z);
    let out = '';
    for (const lb of sorted) {
      const live = lb.mzObs !== null && !lb.stale;
      const included = !L.excludedZ.has(lb.z);
      const mark = !live ? '—' : (included ? '✓' : '✗');
      const bg = !live ? '#eee' : (included ? '#d6e9f8' : '#f8dada');
      const fg = !live ? '#bbb' : (included ? '#1a4a7a' : '#7a1a1a');
      const cur = !live ? 'default' : 'pointer';
      out += '<span class="auc-chip" data-ladder="' + L.id + '" data-z="' + lb.z
          + '" style="font-size:10px;padding:1px 4px;border-radius:3px;'
          + 'background:' + bg + ';color:' + fg + ';cursor:' + cur
          + ';user-select:none">' + mark + lb.z + '+</span>';
    }
    return out;
  }
  let html = '';
  for (const L of st.ladders) {
    const active = L.id === st.activeLadderId;
    const foundCount = L.labels.filter(lb => lb.mzObs !== null).length;
    const totalCount = L.labels.length;
    // M readout for this ladder — spec §5.4. Lives in the side panel rather
    // than as an in-plot annotation so it never overlays low-m/z peaks.
    const amber = L.M > 0
                  && (L.sigmaM / L.M) > LadderLabeler.state.sigmaAmberRelative;
    const mColor = amber ? '#cc4400' : L.color;
    const mTxt = 'M = ' + LadderLabelerCore.formatMass(L.M, L.sigmaM)
               + '  ' + LadderLabelerCore.formatSigma(L.M, L.sigmaM)
               + (amber ? '  — check assignments' : '');
    const abTxt = (L.abundance === null) ? 'Abund. = —'
                  : ('Abund. = ' + (L.abundance * 100).toFixed(1) + '%'
                     + (L.isPartial ? ' (partial)' : ''));
    const sumTxt = (L.aucSum === 0) ? 'ΣAUC = —'
                   : 'ΣAUC = ' + L.aucSum.toExponential(1);
    html += '<div style="border-bottom:1px solid #eee;padding:2px 0">'
          + '<div style="display:flex;align-items:center;gap:6px">'
          + '<input type="radio" name="ladder-active" data-id="' + L.id + '"'
          + (active ? ' checked' : '') + '>'
          + '<span style="display:inline-block;width:10px;height:10px;'
          + 'background:' + L.color + ';border-radius:2px"></span>'
          + '<b>' + L.id + '</b>'
          + ' z₀=<input type="number" data-id="' + L.id + '" data-field="z" '
          + 'value="' + L.seed.z + '" min="2" step="1" '
          + 'style="width:46px;padding:1px 3px;font-size:11px">'
          + ' m/z=<input type="number" data-id="' + L.id + '" data-field="mz" '
          + 'value="' + L.seed.mz + '" step="0.1" '
          + 'style="width:70px;padding:1px 3px;font-size:11px">'
          + ' <span style="color:#666">'
          + foundCount + '/' + totalCount + ' rungs</span>'
          + ' <button data-id="' + L.id + '" data-action="remove" '
          + 'style="margin-left:auto;padding:1px 6px;font-size:11px">✕</button>'
          + '</div>'
          + '<div style="padding:1px 0 2px 22px;font-size:11px;color:'
          + mColor + '">' + mTxt
          + '  <span style="color:#444">· ' + abTxt + '</span>'
          + '</div>'
          + '<div style="padding:0 0 2px 22px;font-size:10px;color:#888">'
          + sumTxt + '</div>'
          + '<div data-ladder="' + L.id + '" '
          + 'style="padding:0 0 4px 22px;display:flex;flex-wrap:wrap;gap:3px">'
          + chipsFor(L)
          + '</div>'
          + '</div>';
  }
  list.innerHTML = html;

  // Wire the per-row controls.
  list.querySelectorAll('input[name="ladder-active"]').forEach(el => {
    el.addEventListener('change', () => {
      LadderLabeler.setActive(el.dataset.id);
      recompute();
    });
  });
  list.querySelectorAll('input[data-field]').forEach(el => {
    el.addEventListener('change', () => {
      const L = LadderLabeler.state.ladders.find(x => x.id === el.dataset.id);
      if (!L) return;
      const val = parseFloat(el.value);
      if (el.dataset.field === 'z') {
        if (!Number.isInteger(val) || val < 2) {
          document.getElementById('ladder-status').textContent =
            'z₀ must be an integer ≥ 2';
          el.value = L.seed.z;
          return;
        }
        L.seed.z = val;
      } else if (el.dataset.field === 'mz') {
        if (!isFinite(val) || val <= 0) {
          document.getElementById('ladder-status').textContent =
            'precursor m/z must be a positive number';
          el.value = L.seed.mz;
          return;
        }
        L.seed.mz = val;
      }
      LadderLabeler.refreshLadder(L.id, PROC_X, PROC_Y);
      recompute();
    });
  });
  list.querySelectorAll('button[data-action="remove"]').forEach(el => {
    el.addEventListener('click', () => {
      LadderLabeler.removeLadder(el.dataset.id);
      recompute();
    });
  });
  list.querySelectorAll('span.auc-chip').forEach(el => {
    // Only live chips are clickable.
    if (el.style.cursor !== 'pointer') return;
    el.addEventListener('click', () => {
      LadderLabeler.toggleAucInclude(el.dataset.ladder, parseInt(el.dataset.z, 10));
      renderLadderPanel();
    });
  });
}

// Top-level panel controls (enable checkbox, tolerance input).
document.getElementById('ladder-enabled').addEventListener('change', e => {
  LadderLabeler.state.enabled = e.target.checked;
  recompute();
});
document.getElementById('ladder-tol').addEventListener('change', e => {
  const v = parseFloat(e.target.value);
  if (isFinite(v) && v > 0) {
    LadderLabeler.state.tolMz = v;
    LadderLabeler.refreshAll(PROC_X, PROC_Y);
    recompute();
  }
});

// Render once on load.
renderLadderPanel();

// "+ Type seed" — prompt for z₀ + m/z, create a ladder
document.getElementById('ladder-add-type').addEventListener('click', () => {
  if (!LadderLabeler.state.enabled) {
    document.getElementById('ladder-enabled').click();   // turn on automatically
  }
  const zStr = prompt('Precursor charge state z₀ (positive integer ≥ 2):');
  if (zStr === null) return;
  const z = parseInt(zStr, 10);
  if (!Number.isInteger(z) || z < 2 || String(z) !== zStr.trim()) {
    document.getElementById('ladder-status').textContent =
      'z₀ must be an integer ≥ 2';
    return;
  }
  const mzStr = prompt('Precursor m/z:', String(precursor_from_name() || ''));
  if (mzStr === null) return;
  const mz = parseFloat(mzStr);
  if (!isFinite(mz) || mz <= 0) {
    document.getElementById('ladder-status').textContent =
      'precursor m/z must be a positive number';
    return;
  }
  const res = LadderLabeler.addLadderFromSeed({ mz, z }, PROC_X, PROC_Y);
  if (res.error) {
    document.getElementById('ladder-status').textContent = res.error;
  } else {
    document.getElementById('ladder-status').textContent =
      'added ladder ' + res.id;
  }
  recompute();
});

// "+ 2-click seed" — switch into two-click capture mode
document.getElementById('ladder-add-twoclick').addEventListener('click', () => {
  if (!LadderLabeler.state.enabled) {
    document.getElementById('ladder-enabled').click();
  }
  LadderLabeler.state.pendingMode = 'two-click';
  LadderLabeler.state.twoClickBuffer = null;
  document.getElementById('ladder-status').textContent =
    'two-click mode: click first ladder rung in the plot…';
});

// "Clear all"
document.getElementById('ladder-clear').addEventListener('click', () => {
  LadderLabeler.state.ladders.length = 0;
  LadderLabeler.state.activeLadderId = null;
  LadderLabeler._resetIdCounter();
  document.getElementById('ladder-status').textContent = 'cleared';
  recompute();
});

// Subscribe to Plotly clicks (once, after first render).
function attachPlotClick() {
  const plot = document.getElementById('plot');
  if (!plot || !plot.on) {
    setTimeout(attachPlotClick, 50);
    return;
  }
  plot.on('plotly_click', evt => {
    if (!evt || !evt.points || evt.points.length === 0) return;
    const clickedMz = evt.points[0].x;
    const out = LadderLabeler.handlePlotClick(clickedMz, PROC_X, PROC_Y);
    if (out) {
      if (out.status) document.getElementById('ladder-status').textContent = out.status;
      if (out.error)  document.getElementById('ladder-status').textContent = out.error;
      if (out.id)     document.getElementById('ladder-status').textContent =
                        'added ladder ' + out.id;
    }
    recompute();
  });
}
attachPlotClick();

// Helper for the type-seed default: read the precursor from the document title
// or URL pathname (the build filename pattern LCR_mz<precursor>_...).
function precursor_from_name() {
  const m = (document.title + ' ' + (window.location.pathname || ''))
              .match(/mz([0-9]+(?:\.[0-9]+)?)/);
  return m ? parseFloat(m[1]) : '';
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
