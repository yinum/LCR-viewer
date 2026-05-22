#!/usr/bin/env python3
"""
build_lcr_viewer.py
Build a self-contained interactive HTML viewer for a polyP limited-charge-reduction
(LCR) MS spectrum.

Pipeline exposed in the HTML (live, editable):
  1. Scale the charge-reduced region (m/z >= threshold) by a factor (default 50x);
     parent envelope stays 1x.
  2. Smooth the spectrum. Each peak group is resampled onto a uniform m/z grid
     (collapsed baseline restored as zeros) and smoothed with zero-baseline
     padding: past a peak group's edge the window is filled with zeros rather
     than shrunk, so a window of N affects every peak identically and the
     result equals Origin smoothing the full continuous zero-baseline profile.
     The spectrum is drawn as one continuous line. Methods: Savitzky-Golay,
     adjacent averaging, Gaussian, binomial, median/percentile.

Usage:  python3 build_lcr_viewer.py INPUT.txt OUTPUT.html
INPUT is whitespace/tab-delimited two columns: m/z  intensity
The Plotly basic bundle (plotly-basic.min.js) must sit next to this script;
download once from https://cdn.plot.ly/plotly-basic-2.35.2.min.js
"""
import sys, os, json

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

def main():
    src  = sys.argv[1] if len(sys.argv) > 1 else "clipboard_spectrum.txt"
    out  = sys.argv[2] if len(sys.argv) > 2 else "polyP_LCR_viewer.html"
    here = os.path.dirname(os.path.abspath(__file__))

    mz, it = [], []
    with open(src) as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 2:
                try:
                    mz.append(float(p[0])); it.append(float(p[1]))
                except ValueError:
                    pass
    if not mz:
        sys.exit("No numeric data parsed from " + src)

    with open(os.path.join(here, "plotly-basic.min.js")) as fh:
        plotly = fh.read()

    html = TEMPLATE
    html = html.replace("__MZ__", json.dumps(mz))
    html = html.replace("__IT__", json.dumps(it))
    html = html.replace("__PLOTLY__", plotly)

    with open(out, "w") as fh:
        fh.write(html)
    print("Wrote %s  (%d points, %.1f KB)" % (out, len(mz), os.path.getsize(out)/1024))


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
   <label><input type="checkbox" id="logy"> log Y axis</label></div>
 <div class="ctl"><button id="dl">Download processed CSV</button></div>
</div>
<div class="hint">
 Order: (1) charge-reduced region (m/z &ge; threshold) x factor, parent envelope ~m/z 2092 stays x1;
 (2) smoothing on a uniform m/z grid with zero-baseline padding - a window of N affects
 every peak (large or small), drawn as one continuous spectrum. Matches Origin's
 continuous-profile smoothing. Edit any control - plot updates live. <span id="status"></span>
</div>
<div id="plot"></div>
<script>__PLOTLY__</script>
<script>
const RAW_MZ=__MZ__;
const RAW_IT=__IT__;

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
}
['scale','thr','method','win','poly','logy','rawov'].forEach(id=>{
 const el=document.getElementById(id);
 el.addEventListener('input',recompute);
 el.addEventListener('change',recompute);
});
document.getElementById('dl').addEventListener('click',()=>{
 let csv='m/z,intensity_processed\n';
 for(let i=0;i<PROC_X.length;i++)csv+=PROC_X[i]+','+PROC_Y[i]+'\n';
 const blob=new Blob([csv],{type:'text/csv'}),a=document.createElement('a');
 a.href=URL.createObjectURL(blob);a.download='polyP_LCR_processed.csv';a.click();
});
recompute();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
