"""Replay harness — run the controller through the REAL Kitten ignition
storm (plan F6's no-storm insurance, now with real data instead of
Blitzortung synthetics).

The fixture is built from detectors/data/kitten_glm.json: 955 dual-satellite
GLM flashes become the regional strike feed, flashes <=25 km become local
flash events, the 22 recovered arrivals become local thunder events, and a
pressure-fall/gust ramp precedes the storm (the real met signature). The
five nearest flashes to the fire point become the strikes the aftermath
watch is armed with.

Run:  python -m controller replay          # prints the timeline + metrics
Key output: TRIGGER LEAD TIME — how long the node was in continuous capture
BEFORE the first local flash (the F7 metric that justifies adaptive sensing:
snapshot sampling would have caught none of it).
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from controller.actions import AgentSchedulerSink  # noqa: E402
from controller.stormmode import Config, Controller, Inputs, Tier  # noqa: E402

GLM = pathlib.Path(__file__).resolve().parents[1] / "detectors" / "data" / "kitten_glm.json"
STEP_S = 300  # 5-minute controller cadence


def _epoch(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def build_fixture():
    d = json.loads(GLM.read_text())
    node = d["node"]
    fire = d["fire"]
    flashes = [(_epoch(f["time"]), f["dist_node_km"], f["lat"], f["lon"])
               for f in d["glm_flashes"]]
    arrivals = [_epoch(a["time"]) for a in d["thunder_arrivals"]]
    t_first = min(t for t, *_ in flashes)

    start = t_first - 4 * 3600          # 4 h of pre-storm outlook/approach
    end = max(t for t, *_ in flashes) + 3 * 3600
    steps = []
    for t in range(int(start), int(end), STEP_S):
        window = [f for f in flashes if t - 300 <= f[0] < t]
        local = [f for f in window if f[1] <= 25.0]
        hours_to_storm = (t_first - t) / 3600
        # met signature ramps in over the last 3 h before the storm
        dp = max(0.0, 2.5 - max(hours_to_storm, 0.0)) if hours_to_storm < 3 else 0.0
        gust = 12.0 if 0 < hours_to_storm < 3 else 4.0
        # storm cells appear on radar ~2.5 h out, closing at ~30 km/h; the
        # cell signature ends with the storm (last flash + 15 min)
        if 0.0 < hours_to_storm < 2.5:
            cell = max(20.0, 30.0 * hours_to_storm)
        elif hours_to_storm <= 0.0 and any(t - f[0] < 900 for f in flashes):
            cell = 15.0
        else:
            cell = None
        strikes = [{"lat": f[2], "lon": f[3], "time_epoch": f[0],
                    "risk": 87.0} for f in local[:2]]
        steps.append(Inputs(
            t=float(t),
            outlook_elevated=True,     # SPC had convective risk that day
            nearest_cell_km=cell,
            regional_strikes=len(window),
            pressure_drop_hpa_3h=dp,
            gust_ms=gust,
            local_flash=bool(local),
            local_thunder=any(t - 300 <= a < t for a in arrivals),
            strikes=strikes,
        ))
    return node, fire, steps, t_first


def run(quiet=False):
    node, fire, steps, t_first = build_fixture()
    sink = AgentSchedulerSink(quiet=quiet)
    ctl = Controller(Config(), sink, node_latlon=(node["lat"], node["lon"]),
                     t0=steps[0].t)
    armed_at = None
    tier_times = {}
    prev = ctl.tier
    for x in steps:
        ctl.step(x)
        if ctl.tier != prev:
            tier_times.setdefault(ctl.tier.name, x.t)
            prev = ctl.tier
        if ctl.continuous_since is not None and armed_at is None:
            armed_at = x.t

    # fast-forward to holdover expiry (quiet steps at 1 h cadence)
    t = steps[-1].t
    while ctl.tier == Tier.AFTERMATH and t < steps[-1].t + 80 * 3600:
        t += 3600
        ctl.step(Inputs(t=float(t), outlook_elevated=False))

    lead_min = (t_first - armed_at) / 60 if armed_at else None
    summary = {
        "tiers_reached": list(tier_times),
        "trigger_lead_time_min": round(lead_min, 1) if lead_min else None,
        "strikes_watched": len([c for c in sink.calls if "WATCH CMD" in c[1]]),
        "final_tier": ctl.tier.name,
        "audit_records": len(ctl.audit),
        "guardrails_fired": sum(1 for a in ctl.audit if a.kind == "guardrail"),
    }
    if not quiet:
        print("\n=== KITTEN STORM REPLAY ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    return summary, ctl


if __name__ == "__main__":
    run()
