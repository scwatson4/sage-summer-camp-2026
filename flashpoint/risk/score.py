"""The v0.1 ignition-risk score (docs/m1-results.md back-test formula):

    35 * dry(rain)  +  30 * dryness  +  20 * fuel  +  15 * thunder_conf
    gated on strike presence (no strike -> no score, no card)

Back-test separation (real cases): Kitten night storm 87, Kitten evening 71,
Selma bust 84, wet-storm control 41, no-strike day 0.
"""
from __future__ import annotations

from dataclasses import dataclass

DRY_LIGHTNING_MM = 2.5   # the classic dry-lightning threshold
WEIGHTS = {"dry": 35.0, "dryness": 30.0, "fuel": 20.0, "thunder": 15.0}


@dataclass
class RiskFactors:
    rain_mm: float               # node gauge, strike time ± 30 min
    dryness: float               # 0-1: 1 = parched (from SMAP/POWER GWETTOP
    #                              inverted, ERC percentile, or days-since-rain)
    fuel: float                  # 0-1: receptive fuel (land cover; BioCLIP later)
    thunder_conf: float          # 0-1: detector score / anchor corroboration
    sources: dict | None = None  # provenance strings per factor, for the card


def dry_component(rain_mm):
    """1.0 bone-dry -> 0.0 at/above the 2.5 mm wetting threshold, graded."""
    return max(0.0, 1.0 - float(rain_mm) / DRY_LIGHTNING_MM)


def score(factors: RiskFactors, strike_present: bool = True):
    """-> {total, breakdown, dry_lightning, factors} or None when no strike
    (the gate: no strike, no card — scores never free-float)."""
    if not strike_present:
        return None
    parts = {
        "dry": WEIGHTS["dry"] * dry_component(factors.rain_mm),
        "dryness": WEIGHTS["dryness"] * min(max(factors.dryness, 0.0), 1.0),
        "fuel": WEIGHTS["fuel"] * min(max(factors.fuel, 0.0), 1.0),
        "thunder": WEIGHTS["thunder"] * min(max(factors.thunder_conf, 0.0), 1.0),
    }
    return {
        "total": round(sum(parts.values()), 1),
        "breakdown": {k: round(v, 1) for k, v in parts.items()},
        "dry_lightning": factors.rain_mm < DRY_LIGHTNING_MM,
        "factors": factors,
    }


def power_dryness(lat, lon, date_yyyymmdd, timeout=30):
    """0-1 dryness from NASA POWER GWETTOP (top-soil wetness, no auth):
    dryness = 1 - GWETTOP. Returns (value, source) or (None, reason)."""
    import json
    import urllib.parse
    import urllib.request

    url = ("https://power.larc.nasa.gov/api/temporal/daily/point?"
           + urllib.parse.urlencode({
               "parameters": "GWETTOP", "community": "AG",
               "longitude": lon, "latitude": lat,
               "start": date_yyyymmdd, "end": date_yyyymmdd, "format": "JSON"}))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "flashpoint"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        v = list(data["properties"]["parameter"]["GWETTOP"].values())[0]
        if v is None or v < 0:  # POWER uses -999 fill
            return None, "POWER GWETTOP fill value"
        return round(1.0 - float(v), 3), f"NASA POWER GWETTOP {v:.3f}"
    except Exception as e:
        return None, f"POWER unavailable: {e}"


def rain_at_strike(vsn, when_epoch, half_window_min=30):
    """Node rain gauge total around the strike (public query API).
    Returns (mm, source) or (None, reason)."""
    import datetime

    try:
        import sage_data_client

        t = datetime.datetime.fromtimestamp(when_epoch, datetime.timezone.utc)
        d = datetime.timedelta(minutes=half_window_min)
        df = sage_data_client.query(
            start=(t - d).isoformat(), end=(t + d).isoformat(),
            filter={"name": "wxt.rain.accumulation|env.rain.accumulation",
                    "vsn": vsn})
        if not len(df):
            return None, "no rain records in window"
        vals = df["value"].astype(float)
        mm = float(max(vals.max() - vals.min(), 0.0))  # accumulation delta
        return round(mm, 2), f"{vsn} gauge over ±{half_window_min} min"
    except Exception as e:
        return None, f"gauge unavailable: {e}"
