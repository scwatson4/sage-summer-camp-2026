# EchoGuard & FlashPoint — Multi-Node Acoustic + Optical Sensing on Sage

*Two sibling projects sharing one fusion spine (edge onset detection → event publishing → multi-node timing geometry → agent triage). Part I localizes impulsive emergency sounds; Part II localizes lightning and closes the loop to wildfire ignition watch.*

# Part I — EchoGuard: Acoustic Emergency Detection & Localization

*A Sage Grande hackathon project plan. Detect impulsive/emergency sounds (gunshots, fireworks, crashes, sirens) with edge AI on individual nodes, confirm and localize them by fusing timestamps across multiple nodes, and route human-reviewable alerts — with raw audio never leaving any node.*

---

## 1. Feasibility — verified before writing this plan

Simulated localization with the **real GPS coordinates** of the Argonne cluster (16 deployed nodes with microphones + GPS; array span ≈ 1.4 × 1.9 km; best-spread six: **W023, W0AE, W027, W030, W0A4, V032**), Monte Carlo over 300 random source positions:

| Clock sync error | Median localization error | 90th percentile |
|---|---|---|
| 1 ms | 16 m | 35 m |
| 10 ms (typical NTP) | 22 m | 55 m |
| 50 ms (bad NTP) | 66 m | 186 m |

**Conclusion:** with ordinary NTP-grade sync, block-level (~22 m) localization is achievable. Sound travels 343 m/s → every millisecond of timing error costs ~34 cm; the whole project's error budget hangs on timing, so Day 1 is devoted to measuring it.

### 1b. Chicago array census — is the city dense enough? Yes, in two pockets.

Chicago proper has **34 deployed nodes with microphone + GPS** (median nearest-neighbor spacing 809 m). Since a gunshot carries ~1–2 km in urban noise, localization needs pockets of ≥3 nodes within mutual earshot. There are exactly two, plus useful leftovers (all sims at the real coordinates):

| Array | Nodes | Max span | Median error @ 10 ms sync | Character |
|---|---|---|---|---|
| **Argonne campus** | 16 w/ mics | ~1.9 km | 22 m | Open ground — develop & calibrate here |
| **The Loop** | 16 (Lake/Dearborn, Jackson/State, Randolph @ Halsted/Wacker/Michigan, +11) | 1.9 km | ~10 m | Urban canyon — hardest multipath, max RANSAC redundancy; the case-study array |
| **South Side triangle** | 3 (W015 87th/Cottage Grove, W080 83rd/Cottage Grove, W081 83rd/Indiana) | 1.5 km | ~9 m | Minimum viable — zero redundancy; the responsible-use discussion case (ex-ShotSpotter territory) |
| UIC med district pair | W05E + W072 | 814 m | — | 2 nodes: confirm + bearing only |
| Bronzeville pair | W07D + W08B | 1.1 km | — | 2 nodes: confirm + bearing only |

Everywhere else: single-node detection/classification only. **Camp ladder: build at Argonne → stress-test on the Loop → discuss the South Side triangle in the writeup.** Sim caveats: timing-noise-only, free-field, all nodes detecting — the Argonne-vs-Loop measured gap is itself a headline result.

## 2. Where the edge AI/computing lives (it's the whole architecture)

**Tier 1 — always-on DSP gate (CPU, on every node).** Cheap impulsive-onset detector: amplitude envelope + spectral flux on 20 ms hops. Runs 24/7 at negligible cost, triggers Tier 2 maybe a few hundred times a day.

**Tier 2 — on-node classifier (GPU, edge AI proper).** A CNN over mel-spectrograms (transfer learning from YAMNet/PANNs embeddings) classifies each trigger: *gunshot / fireworks / vehicle backfire / siren / crash-impact / thunder / construction / other*. Runs on the node in tens of milliseconds.

**Tier 3 — event-only publishing (edge computing rationale).** The node publishes ~300 bytes per event: onset timestamp (ms precision), class, confidence, 128-d embedding, peak level. Continuous 48 kHz audio would be ~8 MB/min/node; events are a **>10,000× data reduction**, and raw audio never leaves the node — that single design choice is the privacy story, the bandwidth story, and the "why edge" story.

**Tier 4 — fusion on one Thor blade.** Collects events from all array nodes, matches them into candidate incidents (time-window + class-compatible), runs TDOA multilateration, outputs location + uncertainty ellipse.

**Tier 5 — agent triage (edge LLM).** A Hermes agent applies alert policy (below), drafts the human-readable incident card with a local model, escalates to glm-5.2 only for ambiguous multi-class incidents. Full audit log.

## 3. Architecture

```
 [Node A mic] → onset gate → CNN classify → event {t, class, conf, emb}
 [Node B mic] → onset gate → CNN classify → event      ─┐
 [Node C mic] → onset gate → CNN classify → event      ─┼→ [Fusion @ Thor]
 [Node D mic] → onset gate → CNN classify → event      ─┘   • incident matching
                                                            • TDOA multilateration
                                                            • uncertainty ellipse
                                                                 ↓
                                                  [Hermes triage agent]
                                                   • policy + dedupe
                                                   • human review queue
                                                   • Slack/webhook alert + map
```

**Confirmation policy (false-positive control):** single-node event → log only. Two nodes → "possible" (review queue). **Three or more nodes with geometrically consistent timing → alert.** Geometric consistency itself is a powerful filter: random false triggers on different nodes almost never form a physically valid TDOA solution.

## 4. The hard problem: time synchronization

- **Day 1 go/no-go measurement:** query `chrony`/NTP stats on candidate nodes; measure pairwise clock offset directly (exchange timestamped packets; or have two nodes record the same calibration chirp).
- **Sample-accurate onsets:** timestamp at the audio capture layer (frame index → ADC clock), not at process time; refine cross-node delay with GCC-PHAT cross-correlation of the 1–2 s event snippets, parabolic peak interpolation (sub-millisecond).
- **Continuous self-calibration:** estimate slow clock drift between node pairs from commonly heard ambient events (aircraft — validated against free ADS-B tracks, which are a *moving, self-reporting calibration source*).
- **Fallback if fleet sync is poor:** build our own 4-pod array — RPi + USB mics (camp provides USB sensor interfaces + WireGuard) at surveyed positions on campus, sharing one NTP server on the local network; 4 pods over ~300 m gives even better accuracy than the sim above.

## 5. Detection & classification

- **Training data (start before camp):** UrbanSound8K (`gun_shot`, `siren` classes), ESC-50, AudioSet clips for fireworks/backfires/thunder; MIVIA audio events. Fine-tune a small head on pretrained audio embeddings — hours, not days, of training on a Thor.

### 5b. Can we mine Sage's own audio history + police data for training? (verified)

**Historical Sage audio exists, abundantly:** ~118,800 audio uploads fleet-wide in the last 30 days (`audio-sampler` task, FLAC), including many Chicago nodes (W096, W095, W099, W09E…). **But it's periodic snapshots — one short clip every ~5.5 minutes (~261/day/node), not continuous.** That single fact decides how it can and can't be used:

- ❌ **Not a source of gunshot positives.** A gunshot is <1 s; with a ~5.5-min sampling period the microphone is "listening" only a few percent of the time, so the odds a real shot landed inside a saved clip are near zero. Cross-referencing police timestamps against this archive will yield essentially **no** captured gunshots. Don't build the positive class this way.
- ✅ **An excellent domain-matched NEGATIVE corpus.** Thousands of hours of *real* audio from the exact microphone model, mounting, and Chicago soundscapes each node will face. False positives on real-world sound are the hardest part of this problem — here's a free, node-specific "what normal sounds like" set to train against, and to mine for naturally occurring confusers (July fireworks, construction, backfires, sirens, thunder).
- ✅ **Self-supervised pretraining + noise-floor characterization** per node.

**Police / incident data exists and is genuinely useful — for a different job than supplying audio:**

- [Chicago's ShotSpotter Alerts (Historical)](https://data.cityofchicago.org/Public-Safety/Violence-Reduction-Shotspotter-Alerts-Historical/3h7q-7mdb) — timestamped, geolocated acoustic-alert records from the decommissioned system.
- [Victims of Homicides and Non-Fatal Shootings](https://data.cityofchicago.org/Public-Safety/Violence-Reduction-Victims-of-Homicides-and-Non-Fa/gumc-mgzr) — timestamped, block-level shooting incidents.

Use them as an **incident calendar / evaluation ground truth**, not as audio labels:
  1. **Deployment-reality analysis:** how many real shooting incidents fell within earshot (~1.5 km) of a viable node pocket (Loop, South Side triangle)? Quantifies real coverage.
  2. **Retrospective evaluation:** "had EchoGuard run continuously, which known incidents sit inside our arrays' coverage?" — honest recall-potential estimate without firing a gun.
  3. **Benchmark vs. the old system:** compare your array's *potential* coverage/accuracy against ShotSpotter's logged performance in the same blocks — the [reported miss rates](https://southsideweekly.com/shotspotter-routinely-missed-reported-shootings-city-data-shows/) are public. A killer poster figure and a direct tie to §10.

**Getting real positives instead requires forward capture:** a triggered ring-buffer (the onset gate saves the *preceding* few seconds when it fires — cheap, and the right design anyway) or the balloon-pop/speaker field campaign (§8). **Ethics note:** deliberately mining archived audio around real shooting sites is sensitive; the clean path is negatives-from-history + synthetic/field positives, keeping the "no targeted recording of incidents" posture intact.
- **Hard negatives are the project:** fireworks (it's late July — free adversarial examples nightly), car backfires, nail guns, dumpster slams, thunder. The gunshot/fireworks confusion matrix is the single most scrutinized number in this field — measure it honestly and put it on the poster.
- **Scaffold:** the existing `sound-event-detection` (YAMNet) ECR plugin — fork it for the Tier 1/2 pipeline rather than starting from zero.
- **Emergency-response breadth:** same pipeline, more classes — sirens (route/track emergency vehicles), crash impacts, glass break, calls for help. This broadens the story from policing-adjacent to *emergency response infrastructure* (see §10).

## 6. Localization details

- TDOA relative to first-arriving node; solve by coarse grid search + Gauss–Newton refinement (the sim's solver, hardened), RANSAC over node subsets to reject one bad timestamp.
- Report **location + uncertainty ellipse**, never a false-precision dot. Reject solutions outside array's credible region.
- Sanity physics: gunshot audibility ~1–2 km urban → the Argonne array span is well matched; expect 3–6 detecting nodes per event.

## 7. Propagation reality — echoes, building materials, and weather

Sound in a built environment is messy; three effects matter, each with a concrete mitigation:

**Multipath/reflections — the big one.** Every impulse reaches each mic by the direct path *plus* reflections off buildings. Two saving graces. First, the direct path always arrives **first** when it exists — so the onset detector picks the *leading edge* of the impulse, never the loudest peak (reflections are often louder), and GCC-PHAT's phase-whitening is inherently reverb-tolerant. Second, when a building fully blocks the direct path (non-line-of-sight), that node's arrival lands *late and physically inconsistent* with the rest — which is precisely what the RANSAC subset-consistency step catches and discards. With 4–6 detecting nodes per event we can afford to drop one or two NLOS arrivals.

**Building materials — real for amplitude, mostly irrelevant for timing.** Brick vs. glass vs. concrete governs how much energy reflects and how long the reverb tail rings — it shapes loudness and echo character, *not* the arrival time of the first wavefront, which is all TDOA uses. So we don't model materials explicitly; a campus acoustic ray-trace is out of scope for a week, and the **balloon-pop field day beats it empirically**: surveyed test shots per zone measure the real site-specific bias, which becomes per-node corrections and honestly inflated uncertainty ellipses in built-up sectors. (Argonne's low-rise, open campus is also far more benign than a downtown canyon — another reason it's the right first array; a UIC-area rerun later would characterize the harder case.)

**Weather bends the numbers.** Speed of sound rises ~0.6 m/s per °C (343 m/s at 20 °C) — hot afternoon vs. cool night shifts computed ranges by 2–3%. The Sage-native fix is elegant: **read air temperature from the node's own weather sensor at event time and set c accordingly.** Wind advects sound a few m/s directionally, and afternoon surface heating refracts sound upward (shadow zones, shorter audible range at midday; propagation improves at night — when gunshots are statistically more likely anyway). We don't attempt refraction modeling; we widen the uncertainty ellipse under high wind and let the field data price it.

The §1 simulation assumed free-field propagation — the field-calibration day exists precisely to measure what reality adds on top.

## 8. Testing without gunshots (obviously)

- **Controlled sources:** balloon pops and clapboards at ~10 surveyed GPS points across the array (a morning's fieldwork); Bluetooth speaker playing dataset gunshot/siren audio at known spots for classification-under-propagation tests.
- **Natural confusers:** July fireworks nights = free false-positive stress test.
- **Moving ground truth:** aircraft overflights vs. ADS-B tracks for continuous timing validation.

## 9. Day-by-day build plan (4-person team)

| Day | Goal | Detail |
|---|---|---|
| 1 | **Go/no-go on timing** | Measure inter-node clock offsets on 4–6 candidate nodes; pick fleet array vs. DIY RPi pods; assign roles |
| 2 | Edge pipeline v1 | Fork sound-event-detection plugin: onset gate + classifier + event publishing; bench test with speaker |
| 3 | Fusion v1 | Incident matcher + TDOA solver (validated against synthetic delays first); live two-node test |
| 4 | **Field calibration day** | Balloon-pop campaign at surveyed points; measure real localization error; tune GCC-PHAT + RANSAC |
| 5 | Hardening + agent | Fireworks/thunder negatives into classifier; Hermes triage agent, review queue, Slack alerts with map + evidence |
| 6 | Dress rehearsal + writeup | End-to-end latency runs; freeze metrics; poster figures (error map!), project.md, ECR submission |
| Demo | Live localization | Balloon pop outside the venue → alert with map ellipse on screen in <5 s; replay of field-test results |

**Roles:** (1) DSP/edge plugin, (2) ML classifier + datasets, (3) fusion/geometry/timing, (4) agent, alerting, dashboard & demo. Natural pairing with the SageWatch team (shared alerting patterns) and any infrasound team.

## 10. Responsible use — write this section first, not last

This domain has a real, local history: **Chicago ended its ShotSpotter contract in 2024** after years of debate about accuracy, cost, and equity of acoustic gunshot detection. A camp project that ignores that context looks naive; one that engages it looks like research. Design answers built in:

- **No continuous recording, ever** — Tier 1–3 means audio is processed and discarded on-node in seconds; only event metadata leaves. This is a *stronger* privacy posture than commercial systems.
- **Published error bars** — full confusion matrix and localization uncertainty on the poster; no accuracy theater.
- **Human-in-the-loop** — alerts go to a review queue with evidence, not to automated dispatch.
- **Emergency-response framing with breadth** — sirens, crashes, and calls for help make this *aid-routing infrastructure*, not only a policing tool.
- **Transparency artifact** — the audit log records every alert, its evidence, and its disposition; that log *is* a deliverable.

## 11. Evaluation metrics (freeze these Day 1)

- Classifier: per-class precision/recall; the gunshot-vs-fireworks confusion cell explicitly.
- Localization: median + 90th-pct error vs. surveyed balloon-pop truth; compare against the simulation table above (prediction vs. reality — great poster figure).
- System: sound-to-alert latency (<5 s target); false alerts per day under confirmation policy vs. single-node baseline (quantify how much multi-node confirmation buys).
- Timing: measured inter-node sync error and its contribution to the error budget.

## 12. Camp deliverables mapping

- **ECR app:** the Tier 1–3 edge detector plugin (genuinely reusable by Sage).
- **hermes-profile/ contribution:** the triage agent's tools + alert policy.
- **Challenge-problem writeup:** §1 sim + §7 propagation analysis + §10 responsible-use gives it unusual depth.
- **5-min demo:** live balloon-pop localization; **poster:** error map + confusion matrix + architecture.

## 13. Stretch goals

- **Infrasound fusion** (Friday hardware): explosions and distant events below audible range.
- **PTZ handoff:** send the bearing to an Active Eye-style camera — "look at what you just heard."
- **Cross-cluster scale test:** rerun the sim + field method on UIC-area nodes (W096/W077 spacing) to characterize a *city-density* array vs. campus array.
- **Hawaii spinoff:** the identical pipeline pointed at rockfall/surf/eruption acoustics for W097's neighborhood.

# Part II — FlashPoint: Lightning Localization & Wildfire Ignition Watch

*Cameras catch the flash, microphones catch the thunder, weather sensors decide when to listen hard — and every localized strike becomes a 72-hour wildfire ignition watchpoint with responder notification.*

## F1. The physics is kinder than gunshots — and the camera kills the sync problem

Thunder is audible ~10–15 km (vs. ~1–2 km for gunshots), so nodes tens of km apart can co-detect the same strike. Better still: **light arrives effectively instantly, so the flash is a free absolute time anchor.** Each node measures its own flash-to-bang delay *on its own clock* — Δt × 343 m/s = range — meaning a camera+mic node produces an **absolute range with zero cross-node clock synchronization required.** Three self-clocked ranges → stable trilateration. EchoGuard's hardest problem (millisecond sync) largely vanishes here whenever the flash is visible.

- **Night:** flash detection from fisheye luminance spikes is easy (cloud illumination visible tens of km). **Day:** flash contrast is weak → fall back to thunder-only TDOA across nodes (needs sync; simulated below). Honest asymmetry: FlashPoint is a night-strong system, and nocturnal dry-lightning storms are a real ignition scenario.
- Timing budget: thunder onset is a smeared rumble, not an impulse — realistic onset-picking error is 50–200 ms (±17–70 m of range), not the 1 ms of gunshot cracks.
- Multi-strike ambiguity (several flashes/minute in an active storm): pair flash↔thunder by azimuth (fisheye gives flash bearing), rate-gate, and cross-check against public feeds.

## F2. Feasibility — simulated on the real network

**Chicagoland: 51 deployed mic nodes spanning 32 × 49 km** (thunder co-detection radius ~12 km → the metro is one connected lightning array). Monte Carlo, thunder-TDOA mode, ≥3 detecting nodes:

| Thunder onset error | Median strike error | Note |
|---|---|---|
| 50 ms | 135 m | |
| 100 ms | 216 m | realistic |
| 200 ms | 331 m | |

Two honest caveats from the sim: coverage with ≥3 nodes is ~55% of the metro box (fringes have <3 nodes in earshot), and **fringe geometries go degenerate** — 90th-percentile errors blow up to tens of km when detectors are near-collinear. Design consequences: every fix carries an uncertainty ellipse and a GDOP quality gate; degenerate fixes are demoted to "range-only from node X." **Flash-anchored range mode (F1) removes most of this instability** — absolute ranges trilaterate far more stably than TDOA — which is the deep architectural reason to fuse camera + mic rather than mic alone. For calibration: ~200 m-class in-core accuracy would be competitive with community lightning networks (Blitzortung, typically km-class) though short of commercial NLDN (~100–250 m); validation against both [Blitzortung](https://www.blitzortung.org) and NOAA's GOES **GLM** satellite lightning mapper (free, ~8–14 km pixels, total-lightning) is the evaluation backbone.

## F3. Storm-Mode Controller — weather-conditioned always-on sensing

The adaptive-sensing idea, formalized as a tiered state machine (this is the Self-Driving-Testbed pattern with lightning as its first customer):

| Tier | Trigger | Action |
|---|---|---|
| 0 — Outlook | Daily NWS/SPC convective + fire-weather outlook ([api.weather.gov](https://api.weather.gov), free) | Nodes in risk area **pre-armed** |
| 1 — Approach | Local pressure fall + wind shift (node's own sensors) OR Blitzortung cells within ~100 km | **ARM:** swap snapshot samplers for continuous ring-buffer capture (audio + camera) via the job API (`submit_plugin_job` / `suspend_job` — the tools the Sage MCP already exposes); shed non-essential GPU jobs |
| 2 — Storm | First flash or thunder detected locally | **STORM MODE** for event duration + 30 min hysteresis: continuous capture, real-time strike mapping, live map |
| 3 — Aftermath | Storm exits | Revert sensors; enter **72 h HOLDOVER WATCH**: `smoke-detector-top` prioritized, PTZ (where present) periodically sweeps bearings of logged strikes, daily VLM review of strike-sector imagery |

Guardrails throughout: storage/thermal budgets, max continuous-capture hours, auto-revert on timeout, and a full audit log of every mode change and its trigger — the same disciplined-autonomy posture as EchoGuard's §10.

## F4. The wildfire loop — from strike to notification

Lightning starts a large share of Western burned area, and **holdover fires can smolder for days before flaring** — precisely the window the aftermath tier watches. Per localized strike: compute a simple ignition-risk score = dry-lightning flag (strike with <2.5 mm rain at the nearest node — read the node's own rain gauge!) × fuel dryness (days-since-rain locally, or public NFDRS/ERC indices) × land cover. High scores generate a **notification card** — map with uncertainty ellipse, time, dry-lightning flag, follow-up smoke-check schedule — to a Slack/webhook channel as the responder-notification demo. Same responsible posture as Part I: human review, no auto-dispatch claims; real agency integration is future work, and framing it as *ignition watch for faster response* keeps the story about aid.

## F5. Where the fleet can actually do this (verified census)

| Region | Nodes | Capability | Suitability |
|---|---|---|---|
| **Chicagoland** | 103 deployed; **51 mic + 51 cam** | Full multi-node array | **The lab:** peak July storm climatology, dense validation vs. Blitzortung/GLM; low fire stakes — build & calibrate here at camp |
| **Lakeview, MT (Centennial Valley)** | **W084 + W06F, co-located twins**, both mic+cam | Twin flash-to-bang ranges + bearings | **Flagship fire deployment:** sagebrush/grass fuels, lightning-ignition country, remote (today's detection delays are long) |
| **Salt Lake City** | W045 + W029 (~4–5 km apart), both mic+cam | 2-node pair | Monsoon-season lightning + Wasatch WUI fires |
| **Single sentinels, fire country** | W070 Palomar Mtn CA (HPWREN heartland), W067 Selma OR (Siskiyou), W06C Moran WY (Grand Teton), W02B Lubbock TX (Panhandle grass + high flash density), V023 Cuyamaca CA (mic-only) | Per-node range + fisheye bearing (~1 km class at 5–10 km) | Right-sized for "which drainage to patrol" + aiming the holdover smoke watch |
| **Eugene OR** | W019 + W041 mic+cam (+ UO blades) | 2-node pair | Moderate; west-side OR lightning is infrequent |
| **Hawaii** | W069 **Lahaina** (thermal + PTZ!), W097 HVNP, W071 Kaneohe — all mic+cam | Single nodes | **Honest reframe: HI lightning is rare.** Reuse the *same* storm-mode controller with **wind-event triggers** (Lahaina 2023 was wind-driven) → red-flag-wind fire watch with thermal/PTZ. The controller generalizes; the trigger is regional. |
| **Colorado** | 6 nodes — **zero microphones** | — | **Gap finding:** prime lightning territory, no acoustic capability. A concrete hardware recommendation to hand the Sage team — deliverable-worthy on its own. |

## F6. Build plan & the no-storm insurance policy

Shares ~70% of EchoGuard's stack (onset detection, event publishing, fusion, triage agent) — ideal as a sibling team or a second demo from the same team. Day 1: flash detector (frame-luminance spike on ring-buffer frames) + thunder onset (shared code). Day 2: per-node flash-to-bang range engine + azimuth pairing. Day 3: storm-mode controller wired to NWS/Blitzortung triggers and the job API. Day 4: fusion with GDOP gating + live strike map. Day 5: holdover-watch mode + notification cards. Day 6: metrics, writeup, poster.

**Risk — no storm during camp week:** two insurances. (1) **Replay harness:** feed the solver historical Blitzortung strike streams + synthetic onsets — full pipeline demo without weather. (2) **Bench rig:** photo strobe + speaker playing thunder at measured distances validates the flash-to-bang engine end-to-end in a parking lot. (July in Chicago averages storms every few days, so odds are decent nature cooperates.)

## F7. Evaluation

Strike location error and detection recall vs. GLM/Blitzortung matched events (in-core vs. fringe reported separately); false-flash rate (fireworks — abundant in July — camera flicker, headlights); storm-mode value: % of strikes captured in continuous mode vs. what snapshot cadence would have caught (the number that justifies the whole adaptive-sensing idea); trigger lead time (armed before first strike?); data-volume cost of storm mode vs. baseline; holdover-watch latency per strike sector.

## F8. Deliverables & stretch

ECR apps: flash/thunder detector + the storm-mode controller (reusable far beyond lightning); hermes-profile: trigger policies + notification tools; writeup: F2 sim + F5 census give it the same verified-feasibility spine as Part I. Stretch: infrasound (thunder's infrasonic component carries much farther — pairs with Friday hardware), Mobotix thermal difference imaging on strike sectors, and the Hawaii wind-trigger variant wired to HCDP/mesonet data — Sammy's natural take-home.

## F9. Verified retrospective case studies — real lightning fires next to recording nodes

Cross-referencing the federal WFIGS wildfire incident database (natural-cause fires since 2023 within ~35 km of each fire-country node) against each node's actual data archive turned up two genuine case studies:

**★ The Kitten Fire — the flagship.** July 3, 2025: a 0.3-acre natural-cause fire discovered **6 km from W06C (Moran, WY / Grand Teton)** — squarely inside thunder range. During the July 1–4 window the node was capturing: **779 audio clips** (the ~5.5-min cadence — over a multi-hour storm with many strikes, the odds that real thunder landed inside several clips are excellent), **2,739 PTZ-YOLO frames**, Mobotix **thermal** and top/bottom imagery, and **51,701 weather records**. Everything FlashPoint needs to attempt a *post-hoc* thunder detection, storm-timeline reconstruction, and pre/post-ignition environmental analysis — from an archive that already exists. Also nearby: Signal Flat (7.7 ac, 12 km, July 26, 2025) as a second event for the same node.

**★ The Selma bust.** July 8, 2025: **four natural-cause fires discovered the same day** within 14–22 km of W067 (Selma, OR / Siskiyou) — N Fork Deer Creek (39.8 ac), Holcomb Peak, Cedar Flat, Esterly Mine. A classic lightning-bust pattern. The node's archive for July 6–9 holds **72 sky + 72 left + 72 bottom images** (hourly — check for storm clouds, then smoke columns) and **25,911 met records including `wxt.rain.accumulation`** — enough to compute the dry-lightning flag for the actual ignition storm. Caveat: audio-sampler was *not* running on W067 that week, so this one is a camera+met study.

Other results: Palomar/Cuyamaca CA nodes sit among ~1,000 nearby incidents but almost none natural-cause since 2023; Lubbock and Lahaina show zero natural-cause (Lahaina's 2023 fire was not lightning — consistent with the wind-trigger reframe); SLC and Eugene have candidate events not yet checked against archives.

**Why this matters:** these archives can (1) validate the thunder detector against *real* mountain-storm audio from the actual deployment mics, (2) test the dry-lightning flag on a storm that verifiably started fires, and (3) make the camp pitch concrete — "we found a lightning fire 6 km from a Sage node that was recording audio every 5 minutes; here's what it heard." Retrieving the actual FLAC/JPEG files requires authenticated access (portal token), same as §5b.

## Sources & grounding

- Localization sim: real node GPS from [Sage manifests](https://auth.sagecontinuum.org/manifests/), run 2026-07-21 (code reproducible on request)
- [sound-event-detection plugin (YAMNet)](https://github.com/waggle-sensor/yamnet-plugin) via Sage MCP plugin search
- [Sage data API](https://sagecontinuum.org/docs/tutorials/accessing-data); [summer-camp-2026 repo](https://github.com/waggle-sensor/summer-camp-2026)
- Context: Chicago's 2024 ShotSpotter contract termination (public reporting; verify details for the writeup)
- FlashPoint: regional census + both sims run on live manifest coordinates 2026-07-21; validation feeds: [Blitzortung](https://www.blitzortung.org), NOAA GOES GLM (Geostationary Lightning Mapper), [NWS API](https://api.weather.gov) for outlooks/alerts
- F9 case studies: [NIFC WFIGS Incident Locations](https://data-nifc.opendata.arcgis.com/) (queried live 2026-07-21) × Sage data API archive counts for W06C and W067
