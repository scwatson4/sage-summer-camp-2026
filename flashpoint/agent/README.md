# flashpoint/agent — holdover smoke-watch on sage-agent (incubating)

FlashPoint's Tier-3 layer, built as **extensions** to
[waggle-sensor/sage-agent](https://github.com/waggle-sensor/sage-agent) —
skills and config only, no fork. Design + verdicts:
[`../docs/agent-smoke-watch-design.md`](../docs/agent-smoke-watch-design.md).

Interfaces are deliberately shaped to upstream (`BaseSkill`, gateway calls,
`skills_dir` auto-discovery) so anything worth contributing lifts out as a PR
— the Hanwha SUNAPI driver being the prime candidate (raise with Peter
Lebiedzinski before building; see design doc).

## Wiring (on H03E)

```bash
git clone https://github.com/waggle-sensor/sage-agent && cd sage-agent
bash scripts/bootstrap_python311.sh && source .venv/bin/activate
pip install -r requirements.txt -r requirements-vision.txt

export MSA_PTZ_BACKEND=sim
export PTZ_GRAPH_SKILLS_DIR=/path/to/flashpoint/agent/skills
export PTZ_GRAPH_CONFIG=/path/to/flashpoint/agent/config/flashpoint.yaml
python -m ptz_node doctor
python -m ptz_node skill run holdover_smoke_watch \
  --args '{"sectors":[{"bearing_deg":150,"range_km":2.3,"age_h":4,"risk":87}]}'
```

Point the sim at our panoramas (real W097 plumes + confusers) by setting the
sim image path to `sim-panoramas/w097-pano-A-day-plume.jpg` (sector→pan map in
`sim-panoramas/sectors.json`; regenerate with `build_panoramas.py`).

**Sim caveats:** patrol at sector centers (30°, 90°, …) — the strip has hard
vertical seams between sectors that no real camera produces; default tilt
keeps the viewport inside the real frame band (top/bottom bands are synthetic
edge-extension). Panorama B is the false-positive reel: a good run flags
NOTHING there.

## Model ladder (config/flashpoint.yaml)

| Rung | Provider | Notes |
|---|---|---|
| Patrol | none | deterministic skill under the scheduler |
| Routine triage | `ollama` local (`gemma4:31b` default) | offline-resilient |
| **Escalation (default)** | `openai_compat` → **Hermes' NIM endpoint (glm-5.2)** | reuse the key already on H03E; check image-input support + quota |
| Fallback escalation | openrouter / argo-proxy (at ANL) | only if NIM quota or vision-input requires |

## Evidence rule (Slack cards)

Every frame ships as a **pair: raw capture + annotated copy** (SmokeyNet tile
highlights / YOLO boxes drawn on the copy, never on the original). The W097
archive is the cautionary tale — its fire-detection frames have boxes burned
into the only stored copy, which contaminates every downstream reuse (we had
to scrub them to build the sim panoramas). Raw = source of truth; annotation
= derived view; both attach to the card along with the dwell's before/after
pair, model confidences, and the cross-bearing mini-map.
