# H03E runbook — the agent realness ladder

Context: the 2026-07-27 validation run already instantiated the real
`waggle-sensor/sage-agent` engine on H03E with FlashPoint's skills — sim PTZ
backend, live gemma4:31b captions, true plume flagged, confuser reel clean
(see STATUS "H03E on-node validation" + agent/README.md sim caveats). This
runbook climbs the remaining rungs from "simulated camera" toward a
non-simulated agent. Work on branch `h03e-agent`. Commit per stage, push at
the end, report in the same summary style as the validation run.

Ground rules (same as always): secrets live in `flashpoint/.env` or the tmux
session only — never committed, never echoed into files that get committed.
Shared infrastructure gets treated gently; stop and report on anything
unexpected rather than forcing it.

## Stage 0 — sync & sanity (5 min)

- `git checkout main && git pull` (h03e-validation is merged into main), then
  `git checkout -b h03e-agent`.
- Confirm the sage-agent venv from the validation run still works
  (`doctor` green). Re-apply the validated env:
  `tilt_deg: 34`, `GEMMA4_TEMPERATURE=0`, `GEMMA4_OLLAMA_MODEL=gemma4:31b`,
  `GEMMA4_MAX_NEW_TOKENS=2048`.

## Stage 1 — cloud escalation rung: NIM glm-5.2 (~30 min, no permissions needed)

The model ladder's escalation tier has only ever run on local Ollama. Exercise
the cloud rung:

- Configure sage-agent's `openai_compat` provider for NVIDIA NIM glm-5.2
  using the key already on H03E (see `agent/config/flashpoint.yaml` for the
  documented base URL/env names; key comes from the node env, not the repo).
- Re-run the two-panorama gateway demo with escalation pointed at NIM.
- Record: correctness on pano A (must flag the plume) and pano B (must stay
  quiet), per-frame latency vs gemma4:31b's ~2–3 min, and any rate/latency
  notes (40 RPM cap is irrelevant at patrol volume).
- Write results into `agent/README.md` (new "cloud rung" subsection) and a
  STATUS bullet. If NIM is unreachable from the node network, record exactly
  that and move on — a documented dead rung is a finding.

## Stage 2 — live-frame perception: real fleet imagery, no actuation (~45 min, no permissions needed)

Make the perception leg non-simulated end to end:

- Pull the freshest top-camera frames from two granted, reporting nodes
  (W096 and W09E; query API for the latest `imagesampler` uploads → storage
  URLs; direct basic-auth downloads work from H03E with SAGE_USER/SAGE_TOKEN).
- For each node grab a pair ~5–15 min apart, then run the caption head and
  YOLO detect on them and build an `agent/evidence.py` pack —
  derived files to `data/evidence-demo-live/`, raw frames untouched (the
  W097 rule).
- Deliverable: two live evidence packs + a note on caption quality against
  real urban Chicago horizons (domain shift vs the HVNP panorama is itself
  a finding worth three sentences).
- Optional: post ONE card to Slack from this, provenance `live`, scene read
  clearly labeled a perception test, not an alert. Skippable — artifacts on
  disk are enough.

## Stage 3 — real PTZ actuation (GATED — skip unless explicitly approved)

Precondition, non-negotiable: the camp organizers (Lebiedzinski is the named
contact) explicitly sanction a reachable camera for this use — either the
UIC Reolink-signature cameras from the camp handout (sage-agent ships a
Reolink driver — exact match) or W0A4 once control credentials are
provisioned. "The credentials circulate in a PDF" is not permission.

When approved:

- Camera host + credentials go in `flashpoint/.env` (gitignored). Verify
  reachability from H03E first (a plain HTTPS probe, no logins hammered).
- Configure sage-agent's Reolink driver; note the camera's starting
  position.
- Run ONE `holdover_smoke_watch` patrol over 2–3 sectors, `dwell_s ≥ 60`,
  evidence pack per sector (raw + derived).
- Restore the camera's starting position afterward. No preset changes, no
  settings changes, no reboots. Stop on any error and report it.
- Deliverable: the project's first real-actuation evidence pack + timing
  notes (move latency, settle time, snapshot latency) — these feed the
  dwell budget in the controller.

## Stage 4 — optional demo-day live loop

For the presentation session, two tmux panes:

- `python -m controller live --dry-run` — real NWS (and Xweather only when
  elevated) driving tier transitions on screen. Every action audit-logged,
  nothing actuated.
- `python -m risk listen` — Socket Mode up so review buttons work live if a
  card gets posted.

If a real storm approaches Chicagoland during the session, screenshot
everything — a live arm during the demo is the best possible closing slide.

## Reporting

Branch `h03e-agent`, one commit per stage, push with `-u origin h03e-agent`.
STATUS section "H03E agent ladder (2026-07-28)". Keep appending blade
gotchas to `../classroom-notes.md`. Summary report: what ran, the numbers,
the gotchas, what stayed blocked and why.
