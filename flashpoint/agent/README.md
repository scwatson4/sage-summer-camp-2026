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

**Validated through the real sage-agent gateway (H03E, 2026-07-27) — two
required settings:**

- **Tilt:** the skill's `tilt_deg` default (0 = horizon on real hardware) goes
  straight to the upstream sim, whose tilt origin is the BOTTOM of the image
  (range = img_h/ppd = 67.5° for these 11520×2160 panos). Pass
  `"tilt_deg": 34` (≈ range/2 = the real frame band) or every dwell stares at
  the synthetic edge-extension band and sees nothing. The standalone test
  centers tilt itself, so it cannot catch this. Proper fix = per-backend tilt
  calibration in the gateway driver (raise with upstream alongside the SUNAPI
  driver).
- **Caption determinism:** the vendored gemma4 wrapper defaults to
  temperature 1.0; on the real (small, distant) Halemaumau plume,
  `gemma4:e2b` then answers plume/none/'' at random across identical calls.
  `export GEMMA4_TEMPERATURE=0` makes it deterministic and correct (3/3
  "plume" on the plume sector, "none" elsewhere). A detection head should
  never sample at temp 1.0 — pin it in config when the SmokeyNet upgrade
  lands.
- **Caption model:** even at temp 0, `e2b` calls pano B's night
  eruption-glow-on-cloud-deck confuser "plume" (false positive).
  `gemma4:31b` gets both sides right (plume on A, haze on B) — but it is a
  THINKING model under Ollama: the wrapper reads only `message.content`, and
  the default `GEMMA4_MAX_NEW_TOKENS=512` can be consumed entirely by the
  thinking channel, returning an empty caption. Demo-validated env:
  `GEMMA4_OLLAMA_MODEL=gemma4:31b GEMMA4_TEMPERATURE=0
  GEMMA4_MAX_NEW_TOKENS=2048` (env beats the config's
  `vision.gemma4_model`).

## Model ladder (config/flashpoint.yaml)

| Rung | Provider | Notes |
|---|---|---|
| Patrol | none | deterministic skill under the scheduler |
| Routine triage | `ollama` local (`gemma4:31b` default) | offline-resilient |
| **Escalation (default)** | `openai_compat` → **Hermes' NIM endpoint (glm-5.2)** | reuse the key already on H03E; check image-input support + quota |
| Fallback escalation | openrouter / argo-proxy (at ANL) | only if NIM quota or vision-input requires |

## Cloud rung: NIM glm-5.2 — H03E-validated 2026-07-28

Profile: `config/flashpoint-nim.yaml` (`PTZ_GRAPH_CONFIG` → it;
`export OPENAI_API_KEY="$NVIDIA_API_KEY"` from the node env — key never in
the repo). Findings from the live exercise:

- **Plumbing works:** `integrate.api.nvidia.com` reachable from H03E; the
  sage-agent graph answered through `openai_compat` end-to-end in 8.0 s.
- **TEXT-ONLY — do not send pixels.** The endpoint accepts OpenAI-style
  `image_url` parts but silently drops them (no API error), and with an
  image attached glm-5.2 may **hallucinate a detailed scene** (it invented
  a building fire for a forest frame; with corrupt bytes it correctly
  disclaims). Frame reads therefore stay on the local gemma4:31b rung —
  which matches the skill design: the LLM is the CALLER-side triage on
  hits, not a vision head.
- **Escalation triage on the real patrol JSONs:** pano A → `ESCALATE` with
  a faithful 3-sentence draft (sector 150, 2.3 km, age 4 h, risk 87, caption
  evidence; correctly notes YOLO had no detections) in **2.3 s**; pano B →
  `QUIET` in **2.2 s**. Text calls run 2–17 s vs the ~2–3 min local frame
  reads, so triage adds negligible latency to a patrol.

## Evidence rule (Slack cards)

Every frame ships as a **pair: raw capture + annotated copy** (SmokeyNet tile
highlights / YOLO boxes drawn on the copy, never on the original). The W097
archive is the cautionary tale — its fire-detection frames have boxes burned
into the only stored copy, which contaminates every downstream reuse (we had
to scrub them to build the sim panoramas). Raw = source of truth; annotation
= derived view; both attach to the card along with the dwell's before/after
pair, model confidences, and the cross-bearing mini-map.
