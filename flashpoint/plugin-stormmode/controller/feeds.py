"""Live input feeds for the controller. Every fetcher degrades to
"no evidence" on failure — a feed outage must never crash storm mode.

Feeds (all documented working in CLAUDE.md / scripts/):
- NWS alerts (api.weather.gov, free, no key): convective/fire-weather
  watches & warnings for the node's point -> outlook_elevated.
- Xweather (key in .env): stormcells/closest -> nearest_cell_km;
  lightning -> regional strike count. Poll ONLY when outlook is elevated
  to respect the 15k/month budget (the tiering saves API budget too).
- Sage met (public query API): 3 h pressure trend + wind gusts from the
  node's own sensors.
- Local detectors: flash/thunder events arrive from the on-node pipeline
  (file/queue hookup happens in the M2 plugin; replay injects them).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


def _get_json(url, timeout=20, headers=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": "flashpoint-controller", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def nws_outlook_elevated(lat, lon):
    """True if an active NWS alert suggests convective or fire weather."""
    try:
        data = _get_json("https://api.weather.gov/alerts/active?"
                         + urllib.parse.urlencode({"point": f"{lat},{lon}"}))
        kinds = ("thunderstorm", "tornado", "red flag", "fire weather",
                 "severe weather")
        for feat in data.get("features", []):
            ev = str(feat.get("properties", {}).get("event", "")).lower()
            if any(k in ev for k in kinds):
                return True, ev
        return False, None
    except Exception as e:
        return False, f"feed-error: {e}"


def xweather_inputs(lat, lon):
    """(nearest_cell_km, regional_strikes) from the verified endpoints in
    scripts/xweather_lightning.py. Returns (None, 0) without creds/network."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import xweather_lightning as xw

        cells = xw.storm_cells(lat, lon)
        strikes = xw.live_strikes(lat, lon)
        cell_km = None
        for ob in (cells.get("response") or []):
            d = (((ob.get("ob") or {}).get("distanceKM"))
                 or ob.get("distanceKM"))
            if d is not None:
                cell_km = min(cell_km, float(d)) if cell_km else float(d)
        n = len(strikes.get("response") or [])
        return cell_km, n
    except (Exception, SystemExit):
        # SystemExit too: xweather_lightning sys.exit()s when creds are
        # missing, and that is NOT an Exception — without this, live mode
        # crashed the first time the outlook went elevated with no key.
        return None, 0


def sage_met_inputs(vsn):
    """(pressure_drop_hpa_3h, gust_ms) from the node's own met stream."""
    try:
        import sage_data_client

        df = sage_data_client.query(
            start="-3h", filter={"name": "env.pressure|wxt.wind.speed",
                                 "vsn": vsn})
        p = df[df["name"] == "env.pressure"]["value"]
        w = df[df["name"] == "wxt.wind.speed"]["value"]
        drop = float(p.iloc[:20].mean() - p.iloc[-20:].mean()) / 100.0 \
            if len(p) > 40 else 0.0  # Pa -> hPa
        gust = float(w.max()) if len(w) else 0.0
        return max(drop, 0.0), gust
    except Exception:
        return 0.0, 0.0
