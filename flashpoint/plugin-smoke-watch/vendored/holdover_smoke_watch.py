"""holdover_smoke_watch — FlashPoint's Tier-3 patrol as a sage-agent skill.

Deterministic (no LLM in the loop, following upstream's own scripted-demo
rationale): visit strike sectors highest-risk-first, dwell long enough for a
frame-pair comparison, run the available smoke reads, return structured
verdicts. The reasoning LLM is invoked by the CALLER on hits only (triage:
met context, second-opinion caption, notification drafting).

Args (JSON):
  sectors: [{bearing_deg, range_km, age_h, risk}, ...]   (required)
  dwell_s, frame_pair_gap_s: override config defaults
  tilt_deg: fixed tilt for all sectors (default 0 = horizon band)

Evidence rule: every capture is kept RAW; annotations (tile highlights,
boxes) belong on derived copies made by the card assembler — never burned
into the source frame (the W097 lesson).

Discovery: set PTZ_GRAPH_SKILLS_DIR to this directory; sage-agent's registry
imports any BaseSkill subclass found here.
"""
from __future__ import annotations

import json
import sys
import time

try:  # inside sage-agent this import resolves; standalone tests use the stub
    from ptz_node.skills.base import BaseSkill, SkillContext, SkillResult
except ImportError:  # pragma: no cover - standalone import for unit tests
    class BaseSkill:  # minimal stand-in mirroring the upstream interface
        name = ""
        description = ""
        agent_callable = True

        def _write_artifact(self, name, data):
            return None

    class SkillContext:
        def __init__(self, args=None, gateway=None):
            self.args = args or {}
            self._gateway = gateway

        def gateway(self):
            return self._gateway

    class SkillResult:
        def __init__(self, ok, skill, summary, data=None, artifacts=None):
            self.ok, self.skill = ok, skill
            self.summary, self.data = summary, data or {}
            self.artifacts = artifacts or []


def _j(payload):
    try:
        out = json.loads(payload)
        return out if isinstance(out, dict) else {"ok": False, "raw": out}
    except Exception:
        return {"ok": False, "error": "unparseable gateway reply",
                "raw": str(payload)[:300]}


def _progress(msg):
    print(f"[smoke-watch] {msg}", file=sys.stderr, flush=True)


def bearing_to_pan(bearing_deg, pan_offset_deg=0.0):
    """Compass bearing -> camera pan. pan_offset_deg is the per-node mounting
    calibration (pan reading when the camera faces true north)."""
    return (float(bearing_deg) - float(pan_offset_deg)) % 360.0


class HoldoverSmokeWatchSkill(BaseSkill):
    name = "holdover_smoke_watch"
    description = (
        "FlashPoint Tier-3: visit lightning-strike sectors (bearing/range/"
        "age/risk) highest-risk-first, dwell for a frame-pair, run smoke "
        "detection per sector, return structured verdicts with RAW evidence "
        "paths. Deterministic — call an LLM only on the hits it returns. "
        "Args: {'sectors': [{'bearing_deg':150,'range_km':2.3,'age_h':4,"
        "'risk':87}], 'dwell_s':180, 'tilt_deg':0}"
    )
    agent_callable = True

    def run(self, ctx: SkillContext) -> SkillResult:
        args = ctx.args or {}
        sectors = sorted(args.get("sectors") or [],
                         key=lambda s: -float(s.get("risk", 0)))
        if not sectors:
            return SkillResult(ok=False, skill=self.name,
                               summary="no sectors given", data={})
        dwell = float(args.get("dwell_s", 180))
        gap = min(float(args.get("frame_pair_gap_s", 120)), max(dwell - 10, 5))
        tilt = float(args.get("tilt_deg", 0.0))
        pan_offset = float(args.get("pan_offset_deg", 0.0))
        gw = ctx.gateway()

        t0 = time.time()
        visits = []
        for s in sectors:
            pan = bearing_to_pan(s["bearing_deg"], pan_offset)
            _progress(f"sector bearing {s['bearing_deg']}° (pan {pan:.0f}°), "
                      f"risk {s.get('risk', '?')}")
            _j(gw.ptz_move_to(pan, tilt))
            before = _j(gw.ptz_snapshot(
                filename=f"watch_b{int(s['bearing_deg'])}_t0.jpg"))
            det0 = _j(gw.ptz_detect(model="yolo", targets="smoke,fire"))
            time.sleep(min(gap, 2.0) if gw.__class__.__name__.startswith("Sim")
                       else gap)
            after = _j(gw.ptz_snapshot(
                filename=f"watch_b{int(s['bearing_deg'])}_t1.jpg"))
            det1 = _j(gw.ptz_detect(model="yolo", targets="smoke,fire"))
            cap = _j(gw.ptz_caption(
                model="gemma4",
                prompt=("Is there a rising smoke PLUME (a column from a point "
                        "source) anywhere in this scene, as opposed to diffuse "
                        "haze, fog, or cloud? Answer plume/haze/none first.")))

            n_hits = sum(len((d.get("result") or {}).get("detections") or [])
                         for d in (det0, det1))
            visits.append({
                "sector": s,
                "pan_deg": pan,
                "raw_frames": [
                    (before.get("result") or {}).get("path"),
                    (after.get("result") or {}).get("path"),
                ],
                "detections": n_hits,
                "caption": str((cap.get("result") or {}).get("caption", ""))[:400],
                "flagged": n_hits > 0
                or str((cap.get("result") or {}).get("caption", ""))
                .lower().startswith("plume"),
            })

        flagged = [v for v in visits if v["flagged"]]
        data = {"visits": visits, "flagged": len(flagged),
                "elapsed_s": round(time.time() - t0, 1),
                "note": ("smoke head = YOLO+caption placeholder; SmokeyNet "
                         "horizon-band tiles are the planned upgrade "
                         "(see docs/agent-smoke-watch-design.md)")}
        return SkillResult(
            ok=True, skill=self.name,
            summary=(f"{len(visits)} sector(s) visited, {len(flagged)} "
                     f"flagged for triage"),
            data=data,
            artifacts=[p for v in visits for p in v["raw_frames"] if p])
