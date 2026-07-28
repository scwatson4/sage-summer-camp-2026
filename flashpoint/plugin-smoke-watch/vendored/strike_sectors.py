"""strike_sectors — bridge from FlashPoint fusion output to watch sectors.

Pure geometry, no sage-agent dependency: given strike estimates (from the
strike board / detectors fusion / GLM+Xweather) and the node position,
produce the prioritized sector list holdover_smoke_watch consumes.
"""
from __future__ import annotations

import math

M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQ = 111_320.0


def bearing_range(node_lat, node_lon, lat, lon):
    """Compass bearing (deg, 0=N CW) and range (km) node -> point."""
    x = (lon - node_lon) * M_PER_DEG_LON_EQ * math.cos(math.radians(node_lat))
    y = (lat - node_lat) * M_PER_DEG_LAT
    return (math.degrees(math.atan2(x, y)) % 360.0, math.hypot(x, y) / 1000.0)


def sectors_for_node(node_lat, node_lon, strikes, now_epoch,
                     max_age_h=72.0, max_range_km=30.0):
    """strikes: [{lat, lon, time_epoch, risk (0-100, optional)}] ->
    [{bearing_deg, range_km, age_h, risk}] sorted by risk desc, then age.

    Age gates the 72 h watch window; range gates what a camera can plausibly
    resolve. Risk defaults to a recency ramp when the ignition-risk score
    isn't attached yet."""
    out = []
    for s in strikes:
        age_h = (now_epoch - float(s["time_epoch"])) / 3600.0
        if not (0.0 <= age_h <= max_age_h):
            continue
        b, r = bearing_range(node_lat, node_lon, s["lat"], s["lon"])
        if r > max_range_km:
            continue
        # unscored strikes get a recency ramp CAPPED at 50 so they never
        # outrank a strike the ignition-risk scorer actually rated
        risk = float(s.get("risk", max(5.0, 50.0 * (1.0 - age_h / max_age_h))))
        out.append({"bearing_deg": round(b, 1), "range_km": round(r, 2),
                    "age_h": round(age_h, 1), "risk": round(risk, 1)})
    return sorted(out, key=lambda v: (-v["risk"], v["age_h"]))
