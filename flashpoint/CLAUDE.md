# FlashPoint — Lightning Localization & Wildfire Ignition Watch (Sage Grande Testbed)

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
- Fire-country nodes with mic+cam: W084+W06F (co-located twins, Lakeview MT, active since ≥Jul 2023), W070 (Palomar CA), W067 (Selma OR), W06C (Moran WY), W02B (Lubbock TX), W045+W029 (SLC pair ~4–5 km), W019+W041 (Eugene). Hawaii: W069 Lahaina (thermal+PTZ), W097 HVNP, W071 Kaneohe — HI lightning rare → wind-trigger variant. Colorado: 6 nodes, **zero mics** (gap finding).

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

1. **M1 — Kitten Fire retrospective** (needs SAGE_TOKEN): `fetch_case_media.py` → screen the 779 clips for thunder (YAMNet/PANNs embeddings) → storm timeline vs met data → did the node hear the storm that started the fire? (Turns deck slide 7 into a result.)
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

## Context for the human

Sammy works on the Hawaii Climate Data Portal (HCDP; mesonet data) — the Hawaii wind-trigger variant of the storm controller is his take-home. Hermes agent (glm-5.2 via NVIDIA NIM, local Ollama fallback) is installed on H03E; the storm-mode controller's agent layer should target Hermes tools and contribute to the camp's shared `hermes-profile/`.
