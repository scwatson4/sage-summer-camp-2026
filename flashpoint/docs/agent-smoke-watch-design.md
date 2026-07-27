# FlashPoint × sage-agent: the holdover smoke-watch agent

*Design for incorporating [waggle-sensor/sage-agent](https://github.com/waggle-sensor/sage-agent)
(Lebiedzinski, "Agentic PTZ Cameras for Edge Science", Jul 2026) as FlashPoint's
Tier-3 aftermath layer. Drafted 2026-07-24 from the deck + a read of the repo.*

## What sage-agent gives us (verified in the code)

- **Engine**: LangChain ReAct loop (`ptz_node/graph_runner.py`) with typed
  gateway tools (`ptz_move_to/pan_by/snapshot/detect/caption`, sensor reads,
  `run_skill`); the **sensor gateway is the single hardware choke point**;
  faults return structured JSON instead of crashing the loop.
- **Swappable brain** (`llm_factory.py`): providers `ollama` (default,
  `gemma4:31b`), `anthropic`, `openrouter`, and `openai_compat`/`argo_proxy`
  (any OpenAI-style endpoint — which includes NVIDIA NIM, i.e. **Hermes on
  H03E plugs in as-is**).
- **Vision stack**: tiled YOLO, BioCLIP 2, Gemma vision via Ollama —
  lazy-loaded against the Orin 61 GB / Thor 122 GB memory budget.
- **Skills auto-discovery**: `BaseSkill` subclasses from `ptz_node/skills/`
  **plus an external `skills_dir`** (`PTZ_GRAPH_SKILLS_DIR` env or config) —
  so FlashPoint skills live in *our* repo, no fork required.
- **Scheduler**: cron-like SQLite-backed jobs (agent / skill / command kinds;
  `interval` bounded by `until`/`max-runs`) — precisely the shape of a
  72-hour holdover watch.
- **Deterministic demo pattern**: big sweeps are scripted skills, one call,
  no LLM wandering (their explicit design rationale) — the right pattern for
  a patrol that must not hallucinate its way off the strike sectors.
- **Camera reality**: drivable today = sim + Reolink. Hanwha/Axis/Mobotix are
  identify+view only — **PTZ control for Hanwha (Sage's actual XNP-6400RW
  fleet PTZs) is an open gap**, and our `scripts/ptz_control.py` already
  contains the SUNAPI calls a driver needs.

Their existing `wildfire_smoke_patrol` demo is a thin placeholder: two
headings, YOLO `targets="smoke,fire"` — which silently widens to `*` because
stock YOLO has no smoke class. That gap is exactly what FlashPoint fills.

## Incorporation design — extend at the edges, upstream the driver

Everything follows the repo's own extension order (config › driver › skill ›
tool). New code lives in `flashpoint/agent/skills/` + `flashpoint/agent/config/`;
sage-agent is a dependency, not a fork.

**1. Skill `holdover_smoke_watch` (deterministic; the workhorse).**
Args: strike sectors `[{bearing_deg, range_km, t_strike, risk_score}]` (from
the strike board / fusion output / GLM+Xweather via `detectors.anchors`),
`dwell_s` (default 180–300: SmokeyNet wants ~60 s of steady frames and
two-frame Δt), revisit budget. Behavior per sector, highest risk first:
`ptz_move_to(bearing→pan calibration)` → settle → capture frame pairs across
the dwell → smoke head on the **horizon band, 5×9 tiles** (NDP workspace
preprocessing) → tile hits refine the in-frame bearing → structured verdict
{sector, p_smoke, tiles, frames} → next sector. No LLM in the loop; runs
under the scheduler even if the brain is down.

**2. Vision backend: SmokeyNet ONNX** (from `sage-smoke-detection`; direct
model URL + dependency pins documented in CLAUDE.md External assets). First
iteration can live inside the skill; promoted to a gateway `ptz_detect`
backend once stable. YOLO stays for motion/objects; Gemma vision gives the
scene-level second read ("vog/fog/cloud or plume?" — the W097 lesson).

**3. Tool `strike_sectors`.** Thin bridge exposing FlashPoint state to the
agent: reads the fusion output (or live GLM/Xweather anchors) and returns
prioritized sectors with ages and risk scores. This is the *only* coupling
point between FlashPoint and sage-agent.

**4. The agent (LLM) is the triage layer, not the patrol.** The scheduled
skill collects evidence; the ReAct agent is invoked on *hits* to: pull met
context (wind, RH via gateway sensors), request a Gemma caption, decide
re-check vs escalate, and draft the notification card for human review —
the same disciplined-autonomy posture as the rest of FlashPoint. Audit trail
comes free (`.local/runs/<id>/`).

**5. Scheduler wiring (storm-mode Tier 3).** On aftermath entry the
controller runs `python -m ptz_node schedule add` — skill job, every 15–30
min, `until` strike_time + 72 h. Auto-revert is the schedule bound itself.

**6. Upstream contribution: Hanwha SUNAPI driver.** Port
`scripts/ptz_control.py`'s SUNAPI moves/presets into a gateway driver so
real fleet PTZs (W029, W06C, W069, W084, W097, V032…) become drivable — the
single highest-leverage PR to sage-agent, and the natural collaboration
opener with the Lebiedzinski/Dematties group (whose ptzapp-yolo remains the
non-agentic fallback chassis).

**Dev/test path without hardware or storms:** the sim backend uses a stitched
panorama — swap in our own panoramas built from **W097 frames** (real
Kīlauea plumes as positives; vog/fog frames as the exact confusers that fooled
the W097 fire-detection job) and demo-storm sky composites. That gives the
whole skill a regression suite before any camera credential exists.

## Model strategy (the "Ollama or what?" question)

Two brains, chosen by config per deployment — no code changes (`llm_factory`):

| Role | Recommendation | Why |
|---|---|---|
| On-node patrol | **none** | the skill is deterministic; runs LLM-free under the scheduler |
| On-node triage (H03E/Thor) | **Ollama, local-first** — start with the repo default `gemma4:31b`; drop to a ~7–14 B tag if RAM contends with SmokeyNet+YOLO | offline-resilient (their design goal), zero API cost, Gemma vision already rides Ollama |
| Hermes integration | point provider `openai_compat` at the NIM endpoint (glm-5.2) | Hermes is already installed on H03E; contributes to the camp's shared hermes-profile |
| Escalation / ambiguous hits | cloud via `anthropic` or `openrouter` (or `argo_proxy` on ANL network at camp) | mirrors the plan's "escalate only for ambiguous incidents"; needs whichever API key Sammy has |

So: **yes, keep Ollama as the local runtime** — it's the repo's native path
and the vision captioner depends on it — but treat the provider as a config
knob: local Gemma for routine triage, Hermes/NIM when the node's agent stack
should be exercised, cloud only on escalation.

## Open questions (for Sammy / the team)

1. **Escalation key**: which cloud provider key should the escalation rung
   use — Anthropic, OpenRouter, or ANL argo-proxy while at camp?
2. **Where to run first**: H03E + sim backend is zero-permission; a Reolink
   (if camp hardware exists) is drivable today; real Hanwha PTZs need the
   driver + camera credentials from node admins. Which do we target for the
   demo?
3. **Upstream posture**: build the Hanwha driver as a PR to sage-agent
   (needs a conversation with Peter Lebiedzinski — he's at Argonne/camp), or
   keep it in our tree first?
4. Scope check: OK to add `flashpoint/agent/` (skills + config + sim test
   panoramas) as the next build item after the flash detector, or ahead of it?
