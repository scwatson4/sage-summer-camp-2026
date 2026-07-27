# FlashPoint / EchoGuard — Project Status (2026-07-24, camp week)

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
- **D3–4:** multi-node fusion + GDOP-gated live strike map (ui/ prompt exists); Blitzortung replay
  harness = no-storm demo insurance.
- **D5:** ignition-risk card v0.1 (dry flag from node gauge + SMAP/POWER dryness + fuel type;
  back-test table already in docs/m1-results.md) + Slack notification path.
- **Presentation:** slide 7 already tells the falsification→recovery arc; add live demo.

## Open science threads (post-camp / HCDP era)

Neural audio classifier (characterize the 17 false positives + detect rain-masked thunder);
NLDN/STRIKEnet match of the 22 arrivals (now 22 + 72 candidates from the D1-2 detector);
Selma imagery review; wind-trigger Hawaii variant; Vaisala research-data request —
**SUBMITTED 2026-07-24** (three case windows, ~65k km²; package in
docs/nldn-research-request.md; ~2-week review); SDR polarity classification; LoRaWAN soil probe.
