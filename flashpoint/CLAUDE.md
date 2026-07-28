# Sage FlashPoint — Multi-Node Lightning Localization & Wildfire Ignition Watch (Sage Grande Testbed)

(Official name as of 2026-07-28: **Sage FlashPoint**; "FlashPoint" remains the shorthand in code and older docs.)

Hackathon project for Sage Summer Camp 2026 (UIC, July 2026). Owner: Samuel Watson (Sage user `scwatson`, camp Thor blade `H03E`). Sibling project: EchoGuard (acoustic emergency localization) — shares the onset/fusion stack. Full plan: `docs/echoguard-flashpoint-plan.md` (read Part II first). Pitch deck: `deck/`.

## Mission

Detect lightning with node cameras (flash) + microphones (thunder), localize strikes (flash-to-bang ranges → trilateration; thunder-TDOA fallback), switch nodes to continuous "storm mode" when weather warrants, then run a 72-hour holdover-fire watch (PTZ re-aim + smoke detection) and send human-reviewed ignition-risk notifications.

## Verified ground truth (all checked live against the fleet, 2026-07-21)

- Chicagoland: 103 deployed nodes; **51 with microphones, 51 with cameras**, spanning 32 × 49 km — one connected thunder array (co-detection radius ~12 km).
- Argonne campus cluster: 16 deployed mic+GPS nodes (best spread: W023, W0AE, W027, W030, W0A4, V032).
- TDOA Monte Carlo on real coordinates (thunder-onset σ 50/100/200 ms): median error **135 / 216 / 331 m**; ~55% metro coverage with ≥3 detectors; fringe fixes degenerate → require GDOP gate + uncertainty ellipse. Flash-anchored ranges (no cross-node sync needed) stabilize the solver.
- Audio archive: fleet `audio-sampler` uploads ≈ 1 clip / 5.5 min (~261/day/node), FLAC. ~118.8k clips fleet-wide per 30 days. **Snapshots, not continuous** → useless for retro gunshot/strike positives, gold for domain-matched negatives.
- **Case study #1 (flagship): Kitten Fire**, natural cause, discovered 2025-07-03, **6 km from W06C** (Moran WY / Grand Teton). W06C archive for Jul 1–4 2025: **779 audio clips, 2,739 ptz-yolo frames, mobotix (thermal) + top/bottom images, 51,701 met records**. Second event same node: Signal Flat, 7.7 ac, 12 km, 2025-07-26.
- **Case study #2: Selma bust** — 4 natural-cause fires discovered 2025-07-08, 14–22 km from W067 (Selma OR): N Fork Deer Creek 39.8 ac, Holcomb Peak, Cedar Flat, Esterly Mine. W067 archive Jul 6–9: 216 images (top/left/bottom, hourly), 25,911 met records incl. `wxt.rain.accumulation`. **No audio** (audio-sampler wasn't running there).
- **No soil/leaf/fuel-moisture sensor publishes anywhere on the fleet** (verified 3-day sweep 2026-07-23). Ignition-risk moisture factors therefore come from: on-node computed proxies (VPD, estimated 10-hr dead-fuel moisture, KBDI, days-since-rain — all from met streams that DO flow) + public feeds at the strike point (NASA SMAP soil moisture, WFAS/NFDRS ERC & fuel-moisture grids, US Drought Monitor). Full feature stack + back-test plan: docs plan §F4. Camp bonus: a LoRaWAN soil probe (Friday hardware session) would be the fleet's first real soil-moisture stream.
- Fire-country nodes with mic+cam: W084+W06F (co-located twins, Lakeview MT, active since ≥Jul 2023), W070 (Palomar CA), W067 (Selma OR), W06C (Moran WY), W02B (Lubbock TX), W045+W029 (SLC pair ~4–5 km), W019+W041 (Eugene). Hawaii: W069 Lahaina (thermal+PTZ), W097 HVNP, W071 Kaneohe — HI lightning rare → wind-trigger variant. Colorado: 6 nodes, **zero mics** (gap finding).

## Current access grant (portal CSV 2026-07-23 → docs/granted-nodes-2026-07-23.csv)

- **Granted:** all camp H-blades (Training & Dev, IL — plus H010/H013 in Hawaii), and W-nodes: W01B, W020, W056, W069, W071, W08B, W08D, W08E, W095, W096, W097, W098, W099, W09A–W09F, W0A0–W0A5. **NOT granted (follow-up ask):** the case-study nodes W06C, W067, W084+W06F, the Argonne W0B cluster, Loop/South-Side arrays, Western sentinels.
- **Granted-set dev array (all reporting, mic+cam):** W096 (1020 S Union, UIC-adjacent) ↔ W09E (Museum Campus, ~3.5 km) ↔ W08B (Oakwood Blvd, ~6 km) — a city-core thunder triangle; W0A0 likely a 4th (no GPS in manifest — locate via its data). W0A4 (Argonne ATMOS) and W095 (Villa Park) are solo islands. W099↔W08D pair is dead (W08D not reporting).
- **★ Emiquon twins: W01B + W020, 1 km apart**, both reporting, mic + cam + THERMAL, rural nature preserve (Havana, IL) — the granted-set stand-in for the Lakeview MT twins: pair-mode flash/thunder ranging, quiet-soundscape calibration, July storms guaranteed.
- **Hawaii trio granted but not reporting** (W069 Lahaina — thermal+PTZ+lorawan, W071 Kaneohe, W097 HVNP): archive mining only for now → wind-trigger variant prototype + HCDP tie-in. Handle Lahaina-era archives with care.
- **"Moisture" capability decoded (verified):** it's LoRaWAN WATER sensors, not soil — W096/W099/W0A0 publish `water_depth`, `water_conductivity`, `water_temperature` (~50–140/day) + LoRa `signal.*`. No soil moisture anywhere (soil-proxy plan in §F4 stands). Bonus: granted water_depth streams = free urban-flood tie-in, and proof the LoRaWAN ingestion path works for the planned soil-probe contribution.

## Data access — patterns that work

- Query API (no auth for numeric telemetry): `sage_data_client.query(start=..., end=..., filter={...})`. Filter values are **regex** (`'vsn': 'W06C|W067'`, `'task': '.*top.*'`). Uploads: `filter={'name':'upload','task':'audio-sampler','vsn':'W06C'}` → `value` column = storage URL.
- Manifests (nodes/sensors/GPS): `https://auth.sagecontinuum.org/manifests/?format=json` (fields: vsn, phase, address, gps_lat/gps_lon, sensors[].name).
- **File downloads (FLAC/JPG) require auth**: HTTP Basic, user `scwatson`, password = portal access token (from portal.sagecontinuum.org/account/access). Anonymous & the sage-mcp proxy account both 401. Set env `SAGE_USER` / `SAGE_TOKEN` and use `scripts/fetch_case_media.py`.
- Wildfire records: NIFC ArcGIS `WFIGS_Incident_Locations` layer (see `scripts/wfigs_crossref.py`). Gotchas: the similarly-named layers mostly 400; filter `FireCause='Natural'` client-side; some records have junk InitialLat/Lon (sanity-check distances).
- Lightning ground truth: Blitzortung (community, free), NOAA GOES GLM. Weather triggers: api.weather.gov.

## Gotchas learned the hard way

- Big Sage queries time out — always narrow by vsn + task/name + short window; avoid fleet-wide `name:'upload'` over hours.
- sage-mcp server tool `search_measurements` silently prefixes `W` to node ids (H03E → "WH03E") — H-blades aren't in the production manifest anyway; they publish nothing to Beehive yet.
- W019 is in Eugene OR (not Chicago, despite sitting in the W01x range).
- Storm-mode job control: Sage job API tools exist (`submit_plugin_job`, `suspend_job` via sage-mcp; pluginctl on-node). Camp scheduling permissions on W-nodes: unresolved — ask organizers (see `docs/access-request-list.md`).

## Milestones (in order)

1. **M1 — Kitten Fire retrospective: COMPLETE — full arc in docs/STATUS.md + docs/m1-results.md (read first).** Final state: 17 audio-only candidates falsified by dual-satellite GLM (0/17) → GLM fire-point scan found the REAL ignition storm (Jul 2 22:00–00:00 UT, 219 flashes ≤25 km, closest **3.1 km** from fire point, discovery +3 h) → satellite-anchored re-listening recovered **22 flash→bang arrivals inside archived clips** (rain noise had blinded the ratio metric — noise-adaptive detection is now a design requirement) → PTZ forensics: camera pointed at a cabin wall during the whole ignition storm (docs/forensics_sheet.jpg; the storm-mode motivation image). Deck slide 7 rewritten around this arc. Headline revision: dual-satellite GLM cross-validation (GOES-18 AND GOES-19, ±90 s) found **zero flashes within 50 km for all 17 audio candidates** → the "thunder" events are falsified/undetermined-origin; audio-only detection produced confident false positives — the strongest possible argument for the multi-modal fusion design. SMAP real retrievals obtained (Jul 1 2025: Kitten 0.179 AM/0.150 PM; Selma 0.181 AM/0.084 PM cm³/cm³ — EDL Bearer downloads WORK from cloud sandboxes; the header-kill was Sage-storage-specific). Next decisive experiments: GLM scan Jun 25→Jul 3 around the fire point (find the true strike day; tests holdover length), W06C imagery at event times to identify the transient source, NLDN/STRIKEnet as final arbiter. 518 clips (all Jul 2–3 2025) classified (v0 DSP + wind veto): **17 thunder events, 0 wind-vetoed.** Headline: **a DRY nocturnal lightning storm the night of July 1 (8 thunder events, 0.0 mm rain)** — prime ignition suspect for the fire discovered midday Jul 3, 6 km away; second (2.2 mm) storm Jul 2 evening. Risk back-test v0.1: both real ignition storms score 87/84, wet control 41, no-strike 0. Selma side: WFIGS re-query shows **14 natural-cause fires** on 2025-07-08, node gauge bone-dry (0.05 mm all week, 35 °C). **Access map correction:** file ACLs are per-node — OPEN: W06C (audio+imagery+ptz-yolo), W069 archive, granted-CSV nodes; **DENIED 403: W067 (blocks Selma imagery), W084, W06F, W019** → follow-up ask = exactly those four. NASA: POWER verified (dry-downs quantified both sites); SMAP granules located via CMR; download via `earthaccess`+EDL_TOKEN on laptop. **Remaining:** neural classifier pass (laptop/camp), Selma imagery once W067 opens, SMAP pull, NLDN/STRIKEnet cross-match of the 17 timestamps.
2. **M2 — Edge detectors**: flash detector (frame-luminance spike on ring-buffer frames) + thunder onset (leading edge, not loudest peak). Fork the existing `sound-event-detection` (YAMNet) ECR plugin.
3. **M3 — Flash-to-bang range engine** + flash↔thunder pairing by fisheye azimuth.
4. **M4 — Storm-mode controller**: tiers Outlook→Approach→Storm→Aftermath (NWS/SPC + local pressure/wind + Blitzortung feed → swap samplers for continuous via job API; 72 h holdover watch: PTZ re-aim on strike bearings, smoke-detector priority). Guardrails: budget caps, auto-revert, audit log.
5. **M5 — Fusion + live strike map** with GDOP gating and uncertainty ellipses (port `tdoa_sim.py` solver to live events).
6. **M6 — Evaluation**: match vs Blitzortung/GLM; storm-mode capture gain vs snapshot cadence; no-storm demo via replay harness + strobe/speaker bench rig.

## Commands

```bash
pip install -r requirements.txt
python scripts/census_nodes.py            # fleet census: regions, mics, cams, clusters
python scripts/tdoa_sim.py                # Monte Carlo feasibility sims (Argonne + metro)
python scripts/wfigs_crossref.py          # lightning-fire × node cross-reference
python scripts/check_case_archives.py     # what did W06C/W067 record during the fires
SAGE_USER=scwatson SAGE_TOKEN=... python scripts/fetch_case_media.py   # M1 data pull
streamlit run dashboard/app.py            # visualization dashboard (see dashboard/README.md)
```

## Dashboard (dashboard/)

Streamlit workbench for M1/M5: map of nodes + WFIGS fires, multi-node image
comparison (A/B, blend, filmstrip, luminance flash candidates), synchronized
image–audio–met timelines, clip inspector (waveform/spectrogram/playback,
leading-edge onset), flash-to-bang range rings and multi-ring strike
localization with uncertainty ellipse + GDOP. Case presets: Kitten Fire,
Signal Flat, Selma bust (baked from live WFIGS into `dashboard/assets/`), plus
a credential-free synthetic **demo storm** over the real Argonne geometry
(replay-harness insurance, plan §F6). Media downloads use SAGE_USER/SAGE_TOKEN
and cache under `data/`; listings/met are public. `dashboard/bake_assets.py`
refreshes the baked assets.

## Runbook — where to run Claude Code (and how to set it up)

**Rule of thumb: Milestone 1 on the laptop; Milestones 2–5 on node H03E; no cloud sandbox needed** (a cloud sandbox can't SSH to Sage nodes and the private key must never leave the laptop).

### Laptop (Windows) — for M1
```powershell
irm https://claude.ai/install.ps1 | iex     # native installer (auto-updates)
cd flashpoint
claude                                       # first run: browser login (Pro/Max/Team or Console account)
```

### Before camp: put this folder on GitHub (the laptop↔node sync glue)
```bash
git init && git add -A && git commit -m "FlashPoint handoff"
gh repo create flashpoint --private --source . --push   # or create on github.com and git push
```

### Node H03E — for M2–M5 (GPU, pluginctl, Hermes live here)
```bash
ssh waggle-dev-node-H03E              # jump-host config already in laptop ~/.ssh/config
tmux new -s cc                        # ALWAYS work in tmux; reattach later: tmux attach -t cc
curl -fsSL https://claude.ai/install.sh | bash    # native installer; Ubuntu 24.04 arm64 supported
export PATH="$HOME/.local/bin:$PATH"  # only needed if 'claude' isn't found in this shell
git clone <your-github-url> flashpoint && cd flashpoint
claude --version && claude doctor     # sanity check
claude                                # login: it prints a URL -> open on laptop, paste code back
```

First prompt on either machine: "Read CLAUDE.md, then continue at the current milestone."

### Hygiene on the node (shared research infrastructure)
- Secrets: put `SAGE_USER` / `SAGE_TOKEN` in `.env` (gitignored) or export them in the tmux session only. Never commit tokens; regenerate the Sage token after camp.
- GPU citizenship: coordinate with the team before long training runs; detector/pipeline dev is light.
- If the login browser flow stalls over SSH, run it once from the laptop first so the account is verified, then retry on the node.

## External assets — assessed, with verdicts

- **[sage-nrp-image-search](https://github.com/waggle-sensor/sage-nrp-image-search)** (Gemma captions + CLIP embeddings in Weaviate over Sage imagery, on NRP; needs SAGE + HF tokens). **USE IT — two ways:** (1) mine domain-matched image positives from the fleet archive ("lightning in night sky", "smoke column", "storm shelf cloud") to fix the §5b image-scarcity problem; query it for W067's Jul 8–9 2025 window instead of eyeballing the Selma frames. (2) Its caption+index pattern is the cloud-side forensic layer for the 72 h holdover watch. **Don't self-host the stack during camp** — ask organizers for the live NRP endpoint; if target nodes/dates aren't indexed, run its `weavloader` on just those windows. NRP is Thursday's curriculum — using this aligns with camp.
- **[sage-summer-2026-bioclip](https://github.com/Imageomics/sage-summer-2026-bioclip)** (camp tutorial notebook: zero-shot → few-shot linear probe on frozen embeddings → adaptation → W8A8 quantization → benchmarking). **Don't fine-tune BioCLIP for lightning/smoke** — it's a biological foundation model; its species-ID prior doesn't transfer, and flash/thunder detection isn't image classification anyway. **Do steal its method**: the few-shot-probe-on-frozen-embeddings recipe is exactly right for our low-data smoke/sky-state classifier (use a general CLIP/ImageNet backbone), and its quantization + edge-benchmark flow is the template for putting any of our models on the Thor. **One legit BioCLIP use:** zero-shot habitat/land-cover classification of a node's camera view → the fuel-type input of the ignition-risk score.

- **NDP workspace "Sage Smoke Detection Workflow"** (Sammy has a copy; original by Ismael Perez — find him at camp, NDP/SDSC). Solved gotchas to reuse on H03E: `pip install -r src/requirements.txt && pip uninstall -y opencv-python opencv-python-headless && pip install opencv-python-headless "numpy<2.0"`; model direct-download: `curl https://s3-west.nrp-nautilus.io/smokeynet/model.onnx -o src/model.onnx` (no Docker build needed). Design-critical preprocessing: crop to HORIZON BAND + 5×9 tile grid + two-frame Δt comparison → (1) PTZ must aim strike sectors into the horizon band, (2) tile probabilities localize smoke within frame = free bearing refinement, (3) dwell requirement quantified. Runs on CPU (8 cores, 0 GPU) at watch cadence.
- **[sage-smoke-detection](https://github.com/sagecontinuum/sage-smoke-detection)** — **ADOPT: this is the smoke leg.** Official Sage plugin: SmokeyNet (HPWREN/FIgLib-trained spatiotemporal model, ONNX), Docker+pywaggle, RTSP/HPWREN/MP4 inputs, publishes to data API. Caveats: CA-horizon domain shift (tune thresholds; few-shot probe if needed), v0.7.2 is Jul-2023 old (dep dust-off; read its 4 open issues), and it needs ~60 s of STEADY frames → Tier-3 PTZ sweeps must DWELL 3–5 min per strike sector (controller design constraint). Fleet already runs `smoke-detector-top` in production → on fleet nodes the controller re-prioritizes it; deploy this repo on own cams. MP4 mode = fire-free demo insurance.
- **W0A4 = sanctioned PTZ/camera-control sandbox** (per Sage members at camp). SSH currently rejects scwatson's key at the node (gateway OK) → ask the inviting member to provision the key on W0A4. Starter: `scripts/ptz_control.py` (discovery + ONVIF moves/presets + Hanwha SUNAPI/AXIS VAPIX curl examples). Get camera credentials from node admins — never brute-force shared infra.
- **[Sage Autonomous Camera Control](https://sagecontinuum.org/science/recent/autonomous-camera-control)** (I-JEPA world model + DayDreamer RL, curiosity-driven PTZ exploration; U. Wyoming/Dematties group). **Verdict: borrow the plumbing and the people, not the objective.** Their PTZ control stack (AXIS/Hanwha on Waggle nodes, Dell blade + T4) is exactly the interface FlashPoint's Tier-3 re-aim needs — likely the very system steering W06C's ptz-yolo frames (which stared at a cabin wall through the ignition storm: the perfect joint-pitch image). Their curiosity objective is orthogonal to ours; the natural hybrid = **curiosity exploration in idle weather, event-driven override (strike bearings, smoke sectors) when storm-mode arms** — pitch it to them as adding a "survival instinct" to their curious camera. Dematties also authored the avian/sound-event ECR plugins — one conversation, three assets.
- **Vaisala Xweather API — key in hand, VERIFIED 2026-07-22.** Sammy has a PAYG account (15,000 free accesses/mo, unused; creds go in `.env`). Live-tested with `scripts/xweather_lightning.py`: **working** = `lightning` (NLDN-derived strikes, past ~5 min, ≤100 km, 10x accesses), `stormcells` (radar cell tracks + motion — best Tier-1 approach signal), `lightning/threats` (projected threat areas, 10x). **Not working** = `lightning/archive` → `invalid_request` for ALL dates incl. yesterday (entitlement wall on PAYG despite portal listing; don't retry). Consequences: (1) storm-mode controller gets an NLDN-grade real-time trigger/validation feed — poll only when NWS outlook is elevated to stay in free budget (~1,500 lightning calls/mo); (2) Kitten Fire retrospective still needs STRIKEnet / research request / organizer access. Worth one email to support@xweather.com (billing page pre-fills it with the client ID): ask if archive can be enabled for an .edu research account. Regenerate the secret after camp.
- **Sage SDR lightning project** ([science page](https://sagecontinuum.org/science/recent/lightning-detector)) — existing Sage work: weatherproof software-defined-radio box on Waggle/Sage nodes detecting lightning's EM pulse (sferic); 10 MB/s raw, so they already concluded triggered/batch capture is mandatory. **Adopt as the third modality if hardware is available at camp (ask organizers day one; authors may attend).** **Census verified 2026-07-22: NO active SDR on the fleet** — zero SDR-like sensors in the manifest (keyword hits were Mobotix "radiometric" false positives), zero sdr/radio/sferic/lightning tasks publishing in 14 days, zero SDR plugins in ECR. The prototype box lives with the project team — the RF leg is strictly bring-your-own hardware. Three upgrades: (1) **RF-to-bang** — the sferic arrives at light speed, so it replaces the camera flash as the per-node self-clocked time-zero, making zero-sync ranging work in DAYTIME and through cloud (kills the plan's night-strong asymmetry); (2) **polarity/type classification** — positive CG strikes (<5% of strikes, ~10× charge, disproportionately fire-starting) are readable from RF waveform → add a positive-polarity flag to the ignition-risk score; (3) their batch-capture problem is exactly what the storm-mode controller solves → collaboration pitch. **Caution:** multi-node RF TOA localization needs GPS-disciplined µs timing (1 µs = 300 m at light speed; NTP useless) — stretch goal only; acoustic TDOA (ms-tolerant) stays the localization workhorse. Cheap fallback: RTL-SDR dongle (~$35) on an RPi for sferic burst detection.
- **Vaisala NLDN** (commercial lightning network, ~100–150 m median accuracy, >95% CG detection). **Role: evaluation-grade ground truth only — never an operational dependency.** Free stack (Blitzortung km-class, GLM 8–14 km pixels) can't verify our ~200 m claims — reference noise swamps the signal; say so in the writeup. Three scoped access paths: (1) Vaisala's research-use data request via University of Hawaii (Sammy is eligible; weeks of lead time — for post-camp/paper, apply early; see Unidata lightning page); (2) ask camp organizers day one if Argonne/WIFIRE/NWS partners hold NLDN access to bless one storm case; (3) a single STRIKEnet per-event report centered on W06C, Jul 2–3 2025 — exact NLDN strike times/positions to align with the Kitten Fire audio clips (the strongest possible retrospective slide, for one report's cost). Xweather API trial = optional time-boxed extra. Note: NLDN is CG-focused, which matches what thunder detection hears — cleaner reference than GLM total lightning.

## Context for the human

Sammy works on the Hawaii Climate Data Portal (HCDP; mesonet data) — the Hawaii wind-trigger variant of the storm controller is his take-home. Hermes agent (glm-5.2 via NVIDIA NIM, local Ollama fallback) is installed on H03E; the storm-mode controller's agent layer should target Hermes tools and contribute to the camp's shared `hermes-profile/`.
