#!/usr/bin/env python3
"""
build_lcr_viewer.py
Build a self-contained interactive HTML viewer for a polyP limited-charge-reduction
(LCR) MS spectrum.

Pipeline exposed in the HTML (live, editable):
  1. Scale the charge-reduced region (m/z >= threshold) by a factor (PRESET, 10x);
     parent envelope stays 1x.
  2. Smooth the spectrum. Each peak group is resampled onto a uniform m/z grid
     (collapsed baseline restored as zeros) and smoothed with zero-baseline
     padding: past a peak group's edge the window is filled with zeros rather
     than shrunk, so a window of N affects every peak identically and the
     result equals Origin smoothing the full continuous zero-baseline profile.
     The spectrum is drawn as one continuous line. Methods: Savitzky-Golay,
     adjacent averaging, Gaussian, binomial, median/percentile.

Usage:  python3 build_lcr_viewer.py INPUT [OUTPUT_DIR]
INPUT is a 2-column m/z, intensity file (whitespace- or comma-delimited),
or a folder of such files. One viewer is written per spectrum, named by
precursor ion m/z, into OUTPUT_DIR (default: ../../outputs/LCR/individual
peaks). Processing parameters come from load_preset() -- the built-in PRESET
overlaid with a viewer-saved preset.json; the scaling threshold is auto-placed
per spectrum.
The Plotly basic bundle (plotly-basic.min.js) must sit next to this script;
download once from https://cdn.plot.ly/plotly-basic-2.35.2.min.js
"""
import sys, os, json, re, datetime

# Built-in fallback preset. load_preset() overlays preset.json (written by the
# viewer's Save preset button) on top of these; these values are used whenever
# no preset.json is present next to the script.
PRESET = {
    "scale": 10,            # charge-reduced x factor
    "method": "avg",        # smoothing method (adjacent averaging)
    "window": 299,          # smoothing window (odd)
    "poly": 3,              # SG poly order, retained for the SG control
    "show_overlay": False,  # pre-smoothing overlay checkbox default
}

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

def main():
    args = sys.argv[1:]
    here = os.path.dirname(os.path.abspath(__file__))
    src = args[0] if len(args) > 0 else os.path.join(here, "clipboard_spectrum.txt")
    out_dir = args[1] if len(args) > 1 else os.path.normpath(
        os.path.join(here, "..", "..", "outputs", "LCR", "individual peaks"))
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()
    preset = load_preset(here)

    files = iter_spectrum_files(src)
    if not files:
        sys.exit("No spectrum files found at " + src)

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
        html = build_html(mz, it, thr, plotly, name, preset)
        out = os.path.join(out_dir, name)
        with open(out, "w") as fh:
            fh.write(html)
        print("Wrote %s  (precursor m/z %d (%s), threshold %.1f, %d pts, %.1f KB)"
              % (out, int(round(prec)), source, thr, len(mz),
                 os.path.getsize(out) / 1024))


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
</style>
</head>
<body>
<div id="controls">
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
   <label><input type="checkbox" id="logy"> log Y axis</label></div>
 <div class="ctl"><button id="dl">Download processed CSV</button></div>
 <div class="ctl"><button id="link">Link CSV file (live)</button>
   <span id="csvstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
 <div class="ctl"><button id="savepreset">Save preset</button>
   <span id="presetstat" style="font-size:11px;color:#888;margin-top:3px"></span></div>
</div>
<div class="hint">
 Order: (1) charge-reduced region (m/z &ge; threshold) x factor, parent envelope stays x1;
 (2) smoothing on a uniform m/z grid with zero-baseline padding - a window of N affects
 every peak (large or small), drawn as one continuous spectrum. Matches Origin's
 continuous-profile smoothing. Edit any control - plot updates live. <span id="status"></span>
</div>
<div id="plot"></div>
<script>__PLOTLY__</script>
<script>
const RAW_MZ=__MZ__;
const RAW_IT=__IT__;
const CSV_NAME=__CSVNAME__;

// ---------- build uniform per-segment grid (once) ----------
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
 // resample each segment onto its own uniform grid
 const gmz=[], git=[], bounds=[];
 for(const seg of segs){
  const s=seg[0], e=seg[1], m0=RAW_MZ[s], m1=RAW_MZ[e];
  const gStart=gmz.length;
  if(e>s && m1>m0){
   const segGaps=[];
   for(let i=s+1;i<=e;i++){const g=RAW_MZ[i]-RAW_MZ[i-1];if(g>0)segGaps.push(g);}
   const dxs=Math.max(median(segGaps),(m1-m0)/4000); // cap grid size
   const ncell=Math.max(2,Math.round((m1-m0)/dxs)+1);
   const step=(m1-m0)/(ncell-1);
   const cells=new Array(ncell).fill(0);
   for(let k=s;k<=e;k++){
    let idx=Math.round((RAW_MZ[k]-m0)/step);
    if(idx<0)idx=0; if(idx>=ncell)idx=ncell-1;
    if(RAW_IT[k]>cells[idx])cells[idx]=RAW_IT[k];}
   for(let c=0;c<ncell;c++){gmz.push(m0+c*step);git.push(cells[c]);}
  }else{
   for(let k=s;k<=e;k++){gmz.push(RAW_MZ[k]);git.push(RAW_IT[k]);}}
  bounds.push([gStart,gmz.length-1]);
 }
 return {gmz,git,bounds,nseg:segs.length};
}
const G=buildGrid();

// ---------- smoothing primitives (zero-padded) ----------
// The baseline outside a peak group is physically zero, so the smoothing
// window is filled with zeros past a segment edge instead of being shrunk.
// Consequence: a window of N affects every peak (large or small) identically,
// and the result equals Origin smoothing the full continuous zero-baseline
// profile.
function clampWin(w){w=Math.round(w);if(w%2===0)w++;if(w<3)w=3;if(w>999)w=999;return w;}
function vAt(y,i){return (i>=0&&i<y.length)?y[i]:0;}
function movingAvg(y,w){const n=y.length,h=(w-1)/2,o=new Array(n);
 for(let i=0;i<n;i++){let s=0;for(let j=-h;j<=h;j++)s+=vAt(y,i+j);o[i]=s/w;}
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
function smoothAll(y,method,w,p){
 if(method==='none')return y.slice();
 const ww=clampWin(w),o=y.slice();
 for(const bd of G.bounds){
  const b0=bd[0],b1=bd[1],seg=y.slice(b0,b1+1);
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
 const factor=parseFloat(document.getElementById('scale').value)||1;
 const thr=parseFloat(document.getElementById('thr').value)||0;
 const method=document.getElementById('method').value;
 const w=parseInt(document.getElementById('win').value)||11;
 const p=parseInt(document.getElementById('poly').value)||3;
 const logy=document.getElementById('logy').checked;
 const rawov=document.getElementById('rawov').checked;
 const scaled=G.git.map((v,i)=>G.gmz[i]>=thr?v*factor:v);
 const sm=smoothAll(scaled,method,w,p);
 // one continuous line: segment ends sit at the zero baseline, so the
 // connectors simply run along the baseline between peak groups.
 const px=G.gmz, py=sm, pov=scaled;
 PROC_X=G.gmz; PROC_Y=sm;
 const traces=[];
 if(rawov)traces.push({x:px,y:pov,name:'scaled, pre-smooth',mode:'lines',
   line:{width:0.8,color:'rgba(150,150,150,0.55)'}});
 traces.push({x:px,y:py,name:'scaled + smoothed',mode:'lines',
   line:{width:1.3,color:'#0050b3'}});
 const layout={
   margin:{l:66,r:20,t:34,b:50},
   xaxis:{title:'m/z',showgrid:false},
   yaxis:{title:'intensity'+(factor!==1?' (CR x'+factor+')':''),
          type:logy?'log':'linear',rangemode:'tozero'},
   legend:{orientation:'h',y:1.12},
   shapes:[{type:'line',x0:thr,x1:thr,yref:'paper',y0:0,y1:1,
            line:{color:'#cc4400',width:1,dash:'dot'}}],
   annotations:[{x:thr,yref:'paper',y:1.04,text:'x'+factor+' above',
                 showarrow:false,font:{size:10,color:'#cc4400'}}]
 };
 Plotly.react('plot',traces,layout,{responsive:true,
   toImageButtonOptions:{format:'png',scale:3,filename:'polyP_LCR_spectrum'}});
 document.getElementById('status').textContent=
   G.nseg+' peak segments, '+G.gmz.length+' grid points.';
 syncCSV();
}
['scale','thr','method','win','poly','logy','rawov'].forEach(id=>{
 const el=document.getElementById(id);
 el.addEventListener('input',recompute);
 el.addEventListener('change',recompute);
});
function buildCSV(){
 let csv='m/z,intensity_processed\n';
 for(let i=0;i<PROC_X.length;i++)csv+=PROC_X[i]+','+PROC_Y[i]+'\n';
 return csv;
}
document.getElementById('dl').addEventListener('click',()=>{
 const blob=new Blob([buildCSV()],{type:'text/csv'}),a=document.createElement('a');
 a.href=URL.createObjectURL(blob);a.download=CSV_NAME;a.click();
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
     suggestedName:CSV_NAME,
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
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
