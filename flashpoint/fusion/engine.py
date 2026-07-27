"""Fusion engine: group per-node events into incidents, reconcile candidate
ranges by cross-node consistency, trilaterate, gate on geometry.

Event schema (what the M2 plugins publish, and what replay/demo synthesize):
  flash:   {"type":"flash",   "vsn", "time_epoch", "sigma_s"}
  thunder: {"type":"thunder", "vsn", "time_epoch" (onset),
            "implied_range_km" (from the node's own flash-to-bang), "score"}

Pipeline per incident (plan M5, proven in detectors/tests/test_integration):
1. INCIDENT GROUPING — flash events across nodes within FLASH_COINCIDENCE_S
   are one strike (light is simultaneous fleet-wide at these scales).
2. CANDIDATE COLLECTION — each node contributes the thunder events whose
   implied ranges pair plausibly with that flash time.
3. CONSISTENCY SELECTION — mini-RANSAC: one candidate per node, keep the
   combination with the lowest joint trilateration residual. Random rain
   artifacts don't agree across nodes; real thunder does.
4. GEOMETRY GATE — degenerate/GDOP-poor fixes are demoted to "range-only"
   (never silently dropped, never over-claimed: F2's design consequence).
"""
from __future__ import annotations

import itertools
import pathlib
import sys
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "dashboard"))

from fp import geo  # noqa: E402

FLASH_COINCIDENCE_S = 1.5     # same-strike flash window across nodes
PAIR_WINDOW_S = (0.9, 90.0)   # thunder must trail its flash by r/c in this band
DEFAULT_SIGMA_M = 200.0
GDOP_GATE = 30.0
MAX_RANSAC_COMBOS = 4096


@dataclass
class Strike:
    time_epoch: float
    lat: float | None
    lon: float | None
    semi_major_m: float | None
    semi_minor_m: float | None
    angle_deg: float | None
    gdop: float | None
    rms_m: float | None
    n_nodes: int
    quality: str                    # "fix" | "ambiguous" | "range-only"
    ranges: dict = field(default_factory=dict)   # vsn -> chosen range_km
    note: str = ""

    def to_dict(self):
        return {k: getattr(self, k) for k in (
            "time_epoch", "lat", "lon", "semi_major_m", "semi_minor_m",
            "angle_deg", "gdop", "rms_m", "n_nodes", "quality", "ranges",
            "note")}


class FusionEngine:
    def __init__(self, nodes: dict[str, tuple[float, float]]):
        """nodes: vsn -> (lat, lon)."""
        self.nodes = nodes
        lats = [p[0] for p in nodes.values()]
        lons = [p[1] for p in nodes.values()]
        self.lat0, self.lon0 = sum(lats) / len(lats), sum(lons) / len(lons)

    # ----------------------------------------------------------- grouping
    def group_flashes(self, flash_events):
        """Coincident flashes across nodes -> [(t_strike, [events])]."""
        out = []
        for ev in sorted(flash_events, key=lambda e: e["time_epoch"]):
            if out and ev["time_epoch"] - out[-1][0] <= FLASH_COINCIDENCE_S:
                t, evs = out[-1]
                evs.append(ev)
                out[-1] = (min(t, ev["time_epoch"]), evs)
            else:
                out.append((ev["time_epoch"], [ev]))
        return out

    def candidates_for(self, t_strike, thunder_events, temp_c=20.0):
        """vsn -> [range_km candidates] pairing plausibly with this flash.

        The flash-to-bang range is computed HERE from (onset - flash) x c —
        nodes publish raw onsets and need no pairing logic of their own. An
        event's own implied_range_km (already anchored on-node) wins if set."""
        c = 343.0 + 0.6 * (temp_c - 20.0)
        cands: dict[str, list[float]] = {}
        for ev in thunder_events:
            dt = ev["time_epoch"] - t_strike
            if not (PAIR_WINDOW_S[0] <= dt <= PAIR_WINDOW_S[1]):
                continue
            r_km = (float(ev["implied_range_km"])
                    if ev.get("implied_range_km") is not None
                    else dt * c / 1000.0)
            cands.setdefault(ev["vsn"], []).append(round(r_km, 3))
        return {v: sorted(set(r)) for v, r in cands.items() if v in self.nodes}

    # -------------------------------------------------------------- solve
    def solve(self, t_strike, cands: dict[str, list[float]]):
        vsns = sorted(cands)
        if len(vsns) < 2:
            if len(vsns) == 1:
                v = vsns[0]
                return Strike(t_strike, None, None, None, None, None, None,
                              None, 1, "range-only",
                              ranges={v: cands[v][0]},
                              note=f"single node {v}: range without bearing")
            return None
        anchors = [geo.to_xy(*self.nodes[v], self.lat0, self.lon0) for v in vsns]
        combos = list(itertools.islice(
            itertools.product(*[cands[v] for v in vsns]), MAX_RANSAC_COMBOS))
        best = None
        for combo in combos:
            est = geo.trilaterate(anchors, [r * 1000 for r in combo],
                                  [DEFAULT_SIGMA_M] * len(combo))
            if est and (best is None or est["rms_m"] < best[0]["rms_m"]):
                best = (est, combo)
        if best is None:
            return None
        est, combo = best
        lat, lon = geo.to_latlon(*est["xy"], self.lat0, self.lon0)
        if est.get("degenerate") or est["gdop"] > GDOP_GATE:
            quality, note = "ambiguous", \
                f"geometry gate: gdop={est['gdop']:.1f}"
        elif est["bimodal"] and len(vsns) == 2:
            quality, note = "ambiguous", "two-node mirror ambiguity"
        else:
            quality, note = "fix", ""
        return Strike(
            t_strike, lat, lon,
            est["semi_major_m"] if est["semi_major_m"] == est["semi_major_m"] else None,
            est["semi_minor_m"], est["angle_deg"], est["gdop"], est["rms_m"],
            len(vsns), quality,
            ranges={v: c for v, c in zip(vsns, combo)}, note=note)

    # --------------------------------------------------------------- run
    def process(self, events, temp_c=20.0):
        """Batch: events (mixed flash/thunder dicts) -> [Strike]."""
        flashes = [e for e in events if e.get("type") == "flash"]
        thunder = [e for e in events if e.get("type") == "thunder"]
        strikes = []
        for t_strike, _group in self.group_flashes(flashes):
            cands = self.candidates_for(t_strike, thunder, temp_c=temp_c)
            s = self.solve(t_strike, cands)
            if s is not None:
                strikes.append(s)
        return strikes
