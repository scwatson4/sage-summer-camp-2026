#!/usr/bin/env python3
"""M1: download W06C audio around the Kitten Fire and rank clips for thunder.

FIRST RESULTS (run 2026-07-23 in Cowork, 344 clips, Jul 2 evening + Jul 3 2025):
  - Node rain gauge: 2.2 mm @ 2025-07-02 23:00 UTC, 1.1 mm @ 00:00, showers 17/19 UTC Jul 3
  - Thunder confirmed by eye in top-ranked clips:
      2025-07-03 01:46:04 UTC (ratio 31) — broadband <150 Hz rumble @ ~23 s (evening-storm tail)
      2025-07-03 23:14:45 UTC (ratio 20) — sharp onset + double rumble (textbook)
  - Persistent ~250 Hz tone in all clips = station signature; ignore that band.

GOTCHAS: (1) butter() b,a form at 15-120 Hz on 48 kHz audio is numerically unstable ->
NaNs; resample to 1 kHz and use SOS (as below). (2) In sandboxed envs that strip
Authorization headers, download via https://mcp.sagecontinuum.org/proxy/image?url=...&token=user:tok
(works, 257/257); on a laptop/node use direct basic auth instead.

Usage: SAGE_USER=scwatson SAGE_TOKEN=... python scripts/kitten_screen.py [START END]
"""
import concurrent.futures as cf
import os, pathlib, sys, urllib.parse, urllib.request
import numpy as np
import soundfile as sf
from scipy import signal as sig
import sage_data_client

START = sys.argv[1] if len(sys.argv) > 2 else "2025-07-02T20:00:00Z"
END = sys.argv[2] if len(sys.argv) > 2 else "2025-07-04T00:00:00Z"
TOK = os.environ.get("SAGE_USER", "scwatson") + ":" + os.environ["SAGE_TOKEN"]
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "kitten_clips"
OUT.mkdir(parents=True, exist_ok=True)
USE_PROXY = os.environ.get("SAGE_VIA_PROXY", "0") == "1"

def fetch(row):
    dest = OUT / (str(row["timestamp"])[:19].replace(":", "").replace(" ", "_") + ".flac")
    if dest.exists() and dest.stat().st_size > 10000:
        return dest, None
    try:
        if USE_PROXY:
            u = "https://mcp.sagecontinuum.org/proxy/image?" + urllib.parse.urlencode({"url": row["value"], "token": TOK})
            req = urllib.request.Request(u, headers={"User-Agent": "flashpoint-m1"})
        else:
            import base64
            req = urllib.request.Request(row["value"], headers={
                "Authorization": "Basic " + base64.b64encode(TOK.encode()).decode(),
                "User-Agent": "flashpoint-m1"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
        return dest, None
    except Exception as e:
        return None, str(e)[:60]

def thunder_score(path, sos):
    x, sr = sf.read(path)
    if x.ndim > 1:
        x = x.mean(axis=1)
    y = sig.resample_poly(x, 1, sr // 1000)          # -> 1 kHz
    low = sig.sosfiltfilt(sos, y)                    # 15-120 Hz band
    w = 500                                          # 0.5 s windows
    e = np.array([np.sqrt(np.mean(low[k*w:(k+1)*w]**2)) for k in range(len(low)//w)])
    med = np.median(e) + 1e-9
    return float(e.max()/med), float(e.max())

def main():
    df = sage_data_client.query(start=START, end=END,
                                filter={"name": "upload", "task": "audio-sampler", "vsn": "W06C"})
    df = df.sort_values("timestamp")
    print(f"clips in window: {len(df)}")
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(fetch, (r for _, r in df.iterrows())))
    ok = [d for d, e in res if d]
    print(f"downloaded/cached: {len(ok)}, failed: {len(res)-len(ok)}")
    sos = sig.butter(4, [15, 120], btype="band", fs=1000, output="sos")
    scored = []
    for c in sorted(OUT.glob("*.flac")):
        try:
            ratio, peak = thunder_score(c, sos)
            if np.isfinite(ratio):
                scored.append((ratio, peak, c.name))
        except Exception:
            pass
    scored.sort(key=lambda t: -(t[0] * (t[1] > 3e-4)))
    print("\nTOP 15 thunder candidates:")
    for ratio, peak, name in scored[:15]:
        print(f"  {name[:-5]}  ratio={ratio:7.1f}  peak={peak:.4f}")

if __name__ == "__main__":
    main()
