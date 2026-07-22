#!/usr/bin/env python3
"""Monte Carlo feasibility sims for acoustic TDOA localization on real Sage node geometry.

Reproduces the numbers cited in CLAUDE.md / the deck:
  - Argonne 6-node array, gunshot-class onsets (1/10/50 ms)  -> ~16/22/66 m median
  - Chicagoland metro mic network, thunder onsets (50/100/200 ms) -> ~135/216/331 m median
"""
import json, math, urllib.request
import numpy as np

MANIFEST = "https://auth.sagecontinuum.org/manifests/?format=json"
C = 343.0  # m/s (correct with live node temperature in production: +0.6 m/s per degC over 20C)


def manifest():
    req = urllib.request.Request(MANIFEST, headers={"User-Agent": "flashpoint"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def to_xy(lat, lon, lat0, lon0):
    return ((lon - lon0) * 111320 * math.cos(math.radians(lat0)), (lat - lat0) * 110540)


def mic_nodes(data, box=None, addr_keys=None):
    out = {}
    for n in data:
        if n.get("phase") != "Deployed" or not n.get("gps_lat") or not n.get("gps_lon"):
            continue
        lat, lon = float(n["gps_lat"]), float(n["gps_lon"])
        addr = (n.get("address") or "").lower()
        if box and not (box[0] <= lat <= box[1] and box[2] <= lon <= box[3]):
            continue
        if addr_keys and not any(k in addr for k in addr_keys):
            continue
        if any("microphone" in (s.get("name") or "").lower() for s in n.get("sensors", [])):
            out[n["vsn"]] = (lat, lon)
    return out


def solve_tdoa(toa, A, lo, hi):
    """Two-stage grid search TDOA solver (reference node 0)."""
    best = (lo + hi) / 2
    for span, step in [(max(hi - lo) * 1.2, 1000), (3000, 100)]:
        gx, gy = np.meshgrid(np.arange(best[0] - span, best[0] + span, step),
                             np.arange(best[1] - span, best[1] + span, step))
        td = toa - toa[0]
        d0 = np.hypot(gx - A[0, 0], gy - A[0, 1])
        err = np.zeros_like(gx)
        for i in range(1, len(A)):
            err += ((np.hypot(gx - A[i, 0], gy - A[i, 1]) - d0) / C - td[i]) ** 2
        j = np.unravel_index(np.argmin(err), err.shape)
        best = np.array([gx[j], gy[j]])
    return best


def run(name, pts, sigmas_ms, src_half=600.0, detect_r=None, trials=250, seed=7):
    lat0 = np.mean([p[0] for p in pts.values()]); lon0 = np.mean([p[1] for p in pts.values()])
    A = np.array([to_xy(*p, lat0, lon0) for p in pts.values()])
    print(f"\n== {name}: {len(A)} nodes, extent {(A[:,0].ptp())/1000:.0f} x {(A[:,1].ptp())/1000:.0f} km ==")
    rng = np.random.default_rng(seed)
    lo, hi = A.min(0) - 5000, A.max(0) + 5000
    for s_ms in sigmas_ms:
        errs, miss = [], 0
        for _ in range(trials):
            src = rng.uniform(lo, hi) if detect_r else rng.uniform(-src_half, src_half, 2)
            d = np.hypot(A[:, 0] - src[0], A[:, 1] - src[1])
            det = np.where(d < detect_r)[0] if detect_r else np.arange(len(A))
            if len(det) < 3:
                miss += 1; continue
            toa = d[det] / C + rng.normal(0, s_ms / 1000, len(det))
            est = solve_tdoa(toa, A[det], lo, hi)
            errs.append(float(np.hypot(*(est - src))))
        e = np.array(errs)
        cov = f" | coverage {100*(1-miss/trials):.0f}%" if detect_r else ""
        print(f"  onset sigma {s_ms:>3} ms -> median {np.median(e):6.0f} m | 90th {np.percentile(e,90):7.0f} m{cov}")


if __name__ == "__main__":
    data = manifest()
    argonne = mic_nodes(data, addr_keys=["lemont", "argonne", "cass ave"])
    # best-spread six (greedy max-min) is fine; using all 16 is similar
    run("Argonne cluster (gunshot-class onsets)", argonne, [1, 10, 50], src_half=600)
    chi = mic_nodes(data, box=(41.0, 42.6, -88.5, -87.3))
    run("Chicagoland metro (thunder onsets, 12 km detect radius)", chi, [50, 100, 200], detect_r=12000)
