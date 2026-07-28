#!/usr/bin/env python3
"""Xweather (Vaisala) feeds for the storm-mode controller — VERIFIED WORKING on the
PAYG key (2026-07-22): `lightning` (live, past ~5 min, <=100 km), `stormcells`
(radar cell tracks w/ motion), `lightning/threats` (projected threat areas).
`lightning/archive` is REJECTED on PAYG (invalid_request for any date) — do not retry;
the Kitten Fire retrospective ground truth comes via STRIKEnet / research request instead.

Auth: set XWEATHER_CLIENT_ID and XWEATHER_CLIENT_SECRET in the environment or ../.env.
Budget: 15,000 free accesses/month; `lightning` and `threats` cost 10-12x each ->
poll ONLY when NWS outlook is elevated (the tiered controller saves API budget too).

Usage:  python scripts/xweather_lightning.py 41.87 -87.65
"""
import json, os, pathlib, sys, urllib.parse, urllib.request

def _load_env():
    envf = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def _q(path, **params):
    _load_env()
    cid, sec = os.environ.get("XWEATHER_CLIENT_ID"), os.environ.get("XWEATHER_CLIENT_SECRET")
    if not (cid and sec):
        sys.exit("Set XWEATHER_CLIENT_ID / XWEATHER_CLIENT_SECRET (env or .env)")
    params.update({"client_id": cid, "client_secret": sec})
    url = f"https://data.api.xweather.com/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "flashpoint"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try: return json.load(e)
        except Exception: return {"success": False, "error": str(e)}

def live_strikes(lat, lon, radius_km=100, limit=1000):
    """NLDN-derived strikes from the past ~5 minutes within radius. 10x accesses."""
    return _q(f"lightning/{lat},{lon}", radius=f"{radius_km}km", limit=limit)

def storm_cells(lat, lon, radius_km=200, limit=10):
    """Radar-derived cell tracks with motion vectors — the best Tier-1 'approach' signal."""
    return _q("stormcells/closest", p=f"{lat},{lon}", radius=f"{radius_km}km", limit=limit)

def threats(lat, lon, radius_km=100):
    """Projected lightning threat areas for the location. 10x accesses."""
    return _q(f"lightning/threats/{lat},{lon}", radius=f"{radius_km}km")

if __name__ == "__main__":
    lat, lon = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (41.87, -87.65)
    for name, fn in [("live strikes", live_strikes), ("storm cells", storm_cells), ("threats", threats)]:
        r = fn(lat, lon)
        n = len(r.get("response") or [])
        err = r.get("error") or {}
        note = "" if r.get("success") else f" ({err.get('code') if isinstance(err, dict) else err})"
        print(f"{name}: {'OK' if r.get('success') else 'FAIL'}{note} — {n} results")
        for item in (r.get("response") or [])[:3]:
            print("   ", json.dumps(item)[:160])
