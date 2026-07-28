# Sage FlashPoint / EchoGuard — Project Status (2026-07-24, camp week)

## What this project is

Turn the Sage fleet's existing cameras, microphones, and weather stations into a lightning-
detection and wildfire ignition-watch system: weather feeds arm the nodes (storm mode), flash/RF
gives per-node time-zero, thunder gives range, multi-node geometry gives location, every strike
becomes a 72 h+ holdover watchpoint with smoke monitoring, and high dry-lightning-risk strikes
produce human-reviewed responder notifications. Sibling project EchoGuard shares the fusion spine.

## Where we are (done)

- **Plan & pitch:** two-part plan (docs/echoguard-flashpoint-plan.md), 13-slide deck (deck/),
  feasibility sims on real node geometry, region census, storm-mode tier design.
- **Feeds verified live:** Sage data API + authenticated file downloads (via query-param proxy in
  sandboxes; direct basic-auth locally); Xweather lightning/stormcells/threats (PAYG key);
  NASA POWER (no-auth); NASA SMAP granule downloads (EDL token); GOES-16/18/19 GLM (AWS, anonymous);
  WFIGS wildfire records; NWS API.
- **M1 retrospective EXECUTED — full arc:** 518 W06C clips classified → 17 audio-only "thunder"
  candidates → **dual-satellite GLM cross-validation falsified all 17** (0/17 within 50 km) →
  GLM fire-point scan then **located the real ignition storm** (Jul 2 2025 22:00–00:00 UT, 219
  flashes ≤25 km, closest 3.1 km from the fire point; discovery 02:04 UT, ~3 h later) →
  **satellite-anchored re-listening recovered 22 flash→bang arrivals inside archived clips**
  (thunder buried in the rain noise that blinded audio-only detection) → imagery forensics showed
  the node's PTZ camera pointed at a cabin wall throughout the ignition storm.
  **Net lesson (now the deck's centerpiece): single-modality detection false-alarms confidently;
  fusion + external anchoring is the design, proven on real data.**
- **Selma side:** 14 natural-cause fires in one day near W067; node gauge 0.05 mm all week;
  SMAP PM 0.084. Imagery blocked (no W067 file access).
- **Access state:** open = W06C (full), granted-CSV nodes; denied = W067, W084, W06F, W019.

## In-person asks at camp (today)

1. File access: **W067, W084, W06F, W019** (unblocks Selma imagery + Lakeview archive).
2. PTZ **control** credentials: V032 (Argonne, easy) and W06C (the science case — its PTZ watched
   a wall during the ignition storm; we can show them the frame).
3. Find the **SDR lightning project team** (RF leg hardware) and the **Autonomous Camera Control /
   Dario Dematties group** (PTZ plumbing — see External assets in CLAUDE.md).
4. NLDN: ask which partners hold licenses (final arbiter for the 22 recovered arrivals).

## Build roadmap (camp week)

- **D1–2:** flash detector (ring-buffer luminance) + thunder onset (leading-edge; NOISE-ADAPTIVE —
  rain masking is now a proven failure mode; consider spectral-whitening or GLM/Xweather-anchored
  listening windows) + per-node RF/flash-to-bang range engine.
  - *2026-07-24: thunder side LANDED (`detectors/`) — spectral-whitened noise-adaptive
    detector with GLM/Xweather-anchored listening windows and range-consistency gating.
    Re-validated on the real ignition storm: 20/22 anchored arrivals recovered
    (median range err <1 km), rain-control standalone FA ~36/h documented → the
    nominate-only contract stands. See `detectors/README.md`.*
  - *2026-07-27: flash side LANDED too (`detectors/flash.py`) — scene-luminance
    spike detection on sky-cam frames (photometer, no aiming), fisheye azimuth
    sectors, honest sparse-cadence/daytime flags. Integration test closes D1-2:
    camera anchors + thunder + cross-node consistency localize a demo strike to
    **96 m with no satellite and no clock sync** (tests/test_integration.py).
    Tier-3 incubation started: `agent/` (sage-agent skills + W097 sim panoramas,
    Hermes/NIM glm-5.2 as default escalation).*
- **D2–3:** storm-mode controller (NWS outlook → Xweather stormcells/local sensors arm → continuous
  capture → 72 h+ holdover watch with PTZ re-aim; the cabin-wall frame is the motivation slide).
  - *2026-07-27: LANDED (`controller/`) — tiered state machine (IDLE→OUTLOOK→APPROACH→
    STORM→AFTERMATH) with guardrails (daily capture budget, storm-hour cap, arm
    timeouts, hysteresis), full audit trail, dry-run/agent-scheduler action sinks
    (real job control stays gated on camp scheduling permissions), live feeds
    (NWS free; Xweather polled only when outlook elevated — budget-aware), and a
    replay harness on the REAL Kitten storm: **armed 145 min before the first
    local flash**, watch scheduled, clean expiry. 19/19 tests. Also landed:
    `plugin-thunder/` (M2 packaging, validated locally via PYWAGGLE_LOG_DIR) and
    the smoke-watch skill exercised against the W097 sim panorama (3/3).*
- **D3–4:** multi-node fusion + GDOP-gated live strike map (ui/ prompt exists); Blitzortung replay
  harness = no-storm demo insurance.
  - *2026-07-27: LANDED (`fusion/`) — incident grouping (flash coincidence), cross-node
    candidate-RANSAC, GDOP/degeneracy gating (fix | ambiguous | range-only, never
    over-claimed), self-contained strike-map HTML + strikes.json, live JSONL tail
    mode. Demo e2e (`python -m fusion demo`): **5/5 strikes fused as clean fixes,
    70–273 m error, camera+mic only**.*
- **D5:** ignition-risk card v0.1 (dry flag from node gauge + SMAP/POWER dryness + fuel type;
  back-test table already in docs/m1-results.md) + Slack notification path.
  - *2026-07-27: LANDED (`risk/`) — transparent v0.1 score (m1 weights, factor
    breakdown + provenance on every card), live feeds (node gauge via public API;
    NASA POWER GWETTOP verified live: 0.460 at the Kitten point 2025-07-01),
    markdown + Slack Block Kit cards with the raw+annotated evidence rule and
    publish-the-disagreements posture; dry-run default, SLACK_WEBHOOK_URL to arm.
    15/15 tests.*
- **Presentation:** slide 7 already tells the falsification→recovery arc; add live demo.

## H03E on-node validation (2026-07-27, branch h03e-validation)

The whole stack re-validated on the camp Thor blade (ARM64), end to end:

- **All 7 suites green:** thunder 7/7 · flash 8/8 · integration 96 m ·
  stormmode 19/19 (lead 145.0 min) · risk 15/15 · smoke-watch sim 3/3 ·
  fusion demo 5/5 fixes (70–273 m). Each runs in seconds.
- **Real-data eval reproduced on the node:** anchored recall **20/22**,
  median range err 0.8 km, control FA 35.6/h (direct basic-auth downloads
  work from H03E; 76 clips cached).
- **NEW — audio classifier probe v0** (`detectors/probe_v0.py`): frozen
  YAMNet embeddings + logreg, 5-fold CV → **AUC 0.952** vs DSP 0.699 on the
  same labels (stored eval: 0.389/0.282); recall @ 1 FA/h 9/13 clips /
  15/22 arrivals (DSP: 1/13). The rain-masked-thunder separation the DSP
  can't do lives in the embedding (zero-shot Thunder class alone: 0.59).
  The open neural-classifier thread is now STARTED (see detectors/README.md).
- **M2 milestone first light:** plugin-thunder built with pluginctl and run
  ON A SAGE NODE; candidates published and verified via the public cloud
  query (task=thunder, vsn=H03E, scores 0.65/0.80). Gotchas (image naming,
  no mic in pods → bundled example.flac) in plugin-thunder/README.md.
- **Tier-3 smoke-watch through the REAL sage-agent gateway** (not just the
  standalone stub): pano A flags exactly the true Halemaumau plume
  (risk-first order), pano B confuser reel flags NOTHING — after three
  integration findings the standalone test could not catch (sim tilt origin,
  caption temperature 1.0, e2b→31b thinking-model config; all documented in
  agent/README.md sim caveats). Demo-validated env: `tilt_deg:34`,
  `GEMMA4_TEMPERATURE=0 GEMMA4_OLLAMA_MODEL=gemma4:31b
  GEMMA4_MAX_NEW_TOKENS=2048`. Caption latency with 31b thinking ≈2–3
  min/frame on the Thor — fits the 180 s dwell + 20 min revisit budget, but
  worth remembering when SmokeyNet replaces the placeholder head.
- Blade environment notes (PEP-668 pip, TF-on-ARM, sudo NOPASSWD list,
  registry state) appended to ../classroom-notes.md.

## H03E agent ladder (2026-07-28, branch h03e-agent)

Climbing from "simulated camera" toward a non-simulated agent
(docs/h03e-agent-runbook.md):

- **Stage 0** — doctor green on the existing venv; validated env re-applied.
- **Stage 1, cloud rung LIVE:** sage-agent's `openai_compat` → NVIDIA NIM
  glm-5.2 (`agent/config/flashpoint-nim.yaml`, key from node env). Agent
  graph end-to-end in 8 s. Escalation triage over the real patrol JSONs is
  correct both ways: pano A → ESCALATE with an evidence-faithful draft
  (2.3 s), pano B → QUIET (2.2 s). **Hard finding: the endpoint silently
  drops image parts and glm-5.2 will hallucinate a scene if pixels are
  attached** — cloud rung is text-triage only; frame reads stay local.
- **Stage 2, perception leg is now non-simulated:** live `imagesampler-top`
  frames from W09E (all-sky fisheye) + W08B (skyline) through gemma4:31b +
  YOLO, packaged via `agent/evidence.py` (raw untouched). gemma4 reads urban
  night imagery correctly (haze/none, zero plume FPs, 73–121 s/frame);
  YOLO/COCO is confirmed dead weight on sky cams. W096 imagesampler silent
  ≥24 h; archive cadence is hourly.
- **Stage 3 (real PTZ actuation): SKIPPED — not approved.** Precondition
  unchanged: organizer-sanctioned camera (Lebiedzinski) or W0A4 credentials.
- **Stage 4 smoke:** `controller live --dry-run` verified against real NWS
  from the node (steady IDLE on a calm night, no spurious arms, no audit
  writes without actions — correct). `risk listen` blocked: no
  SLACK_APP_TOKEN/SLACK_BOT_TOKEN in .env yet.

## Open science threads (post-camp / HCDP era)

Neural audio classifier (characterize the 17 false positives + detect rain-masked thunder);
NLDN/STRIKEnet match of the 22 arrivals (now 22 + 72 candidates from the D1-2 detector);
Selma imagery review; wind-trigger Hawaii variant; Vaisala research-data request —
**SUBMITTED 2026-07-24** (three case windows, ~65k km²; package in
docs/nldn-research-request.md; ~2-week review); SDR polarity classification; LoRaWAN soil probe.
