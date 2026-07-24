# Project Story: From One Camera Tunnel to a Volcano

*Sage Summer Camp 2026 — Sammy Watson. A chronological record of the W0A4 camera work
and the W097 PTZ investigation, compiled 2026-07-24, plus the parallel cloud-session
software track (dashboard → hardening → the D1–2 detector). Times are local (HST)
unless marked UTC; data timestamps from the Sage archive are UTC.*

*FlashPoint relevance: W0A4 is the sanctioned PTZ/camera sandbox (access resolved
here — CLAUDE.md's "SSH rejects scwatson's key" note is now stale), and the W097
findings below are the second documented idle-PTZ-misses-the-event case after M1's
cabin wall — plus a labeled smoke/glow validation set for the smoke leg. Collected
frames + per-image analysis: [`w097-imagery/`](w097-imagery/README.md).*

---

## Day 1 — Wednesday, July 23, 2026

### ~11:59 AM — The assignment
Instructor hands out the exercise: SSH-tunnel to `node-W0A4`, forward ports to the
camera at `10.31.81.10` (HTTP 80 → local 8080, RTSP 554 → local 8554), verify with a
digest-auth `curl`, then browse the camera's web UI.

### ~12:00–12:15 PM — Three problems at once
The command fails immediately, and untangling it surfaces three separate issues:

1. **No `node-W0A4` SSH host existed.** My `~/.ssh/config` only knew H03E and V030.
   Fixed by adding a `Host node-W0A4 waggle-dev-node-W0A4` entry using the same
   `ProxyCommand ssh waggle-dev-sshd connect-to-node W0A4` pattern as the others.
2. **Local port 8080 was already taken** by an Apache `httpd` on my machine — the
   first "verification" curl actually got a 404 *from my own Apache*, which looked
   deceptively like a tunnel response. Solution: bind the web tunnel to **8081**.
3. **Git Bash ssh can't see the Windows ssh-agent** that holds the Sage key —
   `Permission denied (publickey)`. Tunnels must use Windows OpenSSH
   (`C:\Windows\System32\OpenSSH\ssh.exe`).

### ~12:15 PM — Blocked: no access
With all that fixed, the gateway answered plainly:
`Sorry... You do not have access to node W0A4 (000048B02DD3C76E)!`
A control test against H03E (same key, same gateway, same config pattern) connected
instantly — proving the setup was fine and the block was purely the per-node access
list. Requested access from the instructors.

### Afternoon — Access granted, tunnel verified
Re-ran the tunnel (Windows OpenSSH, local ports 8081/8554, keepalives added after an
early transient drop). The camera answered:

- **Bottom camera** `10.31.81.10`: Hanwha **XNV-8081Z** fixed dome, serial
  ZLMD6V4T400025X, fw 2.10.02 (2022), `DeviceLocation=bottom`.
- Web UI at `http://localhost:8081`, RTSP at `rtsp://localhost:8554`.

### Afternoon — "What are the commands for moving the PTZ camera?"
Attempting Hanwha SUNAPI PTZ commands (`ptzcontrol.cgi`) returned **Error 609
"Not Authorized"** — and dumping the `waggle` account's permitted CGI list showed
`ptzcontrol` isn't in it at all. Scanning the node's LAN from the inside found the
**top camera** at `10.31.81.13`: a Hanwha **XNF-8010RV fisheye**. Conclusion:
**neither W0A4 camera can pan or tilt**, and the camera account couldn't command
one anyway.

### Afternoon — Which Sage nodes have a real PTZ?
Pulled every node manifest from `auth.sagecontinuum.org/manifests/` and filtered:
**12 nodes carry the Hanwha XNP-6400RW PTZ**: H00F (Argonne, standby), V032, V040,
V041, W029 (Salt Lake City), W069 (Lahaina), W06A, W06C (Grand Teton), W071
(Kaneohe), W084, W097 (Hawaii Volcanoes NP), X001. Sage MCP showed only **W029 and
W06C** publishing data that hour. The MCP also revealed how PTZ is actually driven
on Sage: scheduled ECR plugins that receive camera credentials as parameters —
`ptzapp` / `ptzapp-yolo` (YOLO-guided pointing) and `ptz-sampler` (steps through
preset positions using the same SUNAPI `ptzcontrol.cgi` calls).

---

## Day 2 — Thursday, July 24, 2026

### ~10:25 AM — Tunnel restart
Previous session's tunnel died overnight; restarted with keepalives and re-verified
(same XNV-8081Z deviceinfo response).

### Midday — W097 deep dive: "Is there data of the PTZ watching smoke?"
W097 (Hawaii Volcanoes NP) turned out to be **offline since ~2025-12-30**, but its
archive told the whole story (all timestamps UTC):

| Job | What it did | Record |
|---|---|---|
| `fire-detection` (job 2420, user giorgio808) | YOLOv7 fire/smoke on the **fixed bottom camera**, every 15 min | Jul 24 – Dec 11, 2025: 7,284 samples, **1,168 with smoke/fire detected** |
| `imagesampler-hanwhaptz` (job 2956, user rajesh) | Hourly cron (`20 * * * *`) `wget` snapshot of the **PTZ camera** — no movement commands at all | 4,111 images, Jul 24 – Dec 30, 2025; median gap exactly 3,600 s |
| `ptzfogjob` / `ptz-sampler-fog` (job 2406, user dgiardina) | The one plugin that *would* have moved the PTZ | **Zero data ever published**; job since removed |

No pan/tilt/zoom telemetry was ever published by any W097 plugin. Verdict:
**nothing in the data shows the PTZ reacting to smoke.**

### Afternoon — SSH access sweep of all 12 PTZ nodes
Tested each against the gateway. Result: **access granted to exactly the three
Hawaii nodes — W069, W071, W097** — but all three are offline (reverse-tunnel
socket refused; last data 2025-12-12, 2025-10-07, 2025-12-30 respectively). The two
PTZ nodes currently alive (W029, W06C) are the ones without access. Irony noted.

### ~4:00 PM — Sage token provided; the visual verdict
With a portal token (`scwatson:<token>`, HTTP basic auth, follow the 302), pulled
11 hourly PTZ frames spanning **Jul 24 → Dec 30, 2025**, deliberately covering the
top smoke days (Aug 23, Sep 2–3, Oct 1, Oct 5) plus monthly baselines:

> **The PTZ camera never moved.** Same ʻōhiʻa canopy, same dead branches bottom-left,
> same comms tower on the horizon — in daylight, fog, and the final pre-dawn
> infrared frame of Dec 30. Operator steering ruled out at hourly resolution.

The smoke-day frames show broad haze/vog, not plumes — suggesting many of the
bottom-camera "smoke" hits were volcanic haze or fog (which also explains why
someone tried a `ptz-sampler-fog` plugin here).

### ~4:30 PM — What the fire detector was actually seeing
Pulled the fire-detection frames at the exact detection timestamps — and they're
spectacular. This camera faces **Kīlauea caldera**:

- **2025-08-23 09:54 UTC** (11:54 PM HST): night frame, the **eruption glow**
  saturating the horizon — boxed `fire:42%`, with a moonlit cloud boxed `smoke:48%`.
- **2025-09-02 13:47 UTC** (3:47 AM HST): eruption glow lighting the cloud deck,
  `fire:42%`.
- **2025-10-05 17:33 UTC** (7:33 AM HST): daylight, a **white gas plume rising from
  Halemaʻumaʻu crater** (`smoke:53%`, `smoke:48%`), Mauna Loa on the horizon.

So the detections weren't (all) false positives — **the node was watching the 2025
Kīlauea eruption episodes**. The Mobotix dual-sensor frames confirm it: the
**2025-12-30 08:11 UTC** thermal image — captured hours before the node went dark —
shows a glowing hot spot at the caldera in the thermal channel, with the visible
channel showing a rising plume. (A sampled thermal CSV from a foggy Dec 17 night
reads a flat 12–13 °C across all 84,672 pixels — cold fog, nothing hot in view.)

---

## The parallel track — cloud session: dashboard, hardening, D1–2 detector (Jul 22–24)

While the camera work above ran on the laptop, a Claude Code cloud session carried
the software track on branch `claude/lightning-wildfire-dashboard-qzn6pk`.

### Tuesday, July 22 — dashboard day

- **~3 PM — handoff lands in the camp repo.** The FlashPoint handoff zip became
  `flashpoint/` inside `sage-summer-camp-2026` (plan, deck, feasibility scripts).
- **~3–7 PM — the visualization dashboard** (`dashboard/`, Streamlit): node + fire
  map (WFIGS queried live — Kitten, Signal Flat, and all four featured Selma-bust
  fires located and baked into offline assets), A/B image comparison with per-node
  flash-candidate luminance timelines, synchronized camera/audio/met tracks on one
  UTC clock, a clip inspector (waveform/spectrogram/playback, leading-edge onset
  picking), the flash-to-bang range engine, and multi-ring strike localization with
  uncertainty ellipse + GDOP. A credential-free **synthetic demo storm over the real
  Argonne-six geometry** exercises everything offline; its end-to-end check localized
  a truth strike to **65 m** from four auto-picked thunder onsets.
- **~7 PM — adversarial review, 11 confirmed findings fixed.** A five-lens review
  (physics, Sage-API use, Streamlit semantics, secret hygiene, chart honesty) with
  independent verification caught, among others: the portal token could have been
  sent to any host named in a (publicly writable) upload record — now locked to
  `storage.sagecontinuum.org`; the speed-of-sound temperature was averaging the
  **in-enclosure bme280 (~46 °C) with ambient bme680 (~16 °C)** — verified live on
  W06C, now bme680-only; and GDOP computed via pseudo-inverse reported *good*
  geometry exactly when the ring geometry was degenerate — now an honest ∞ plus an
  "under-constrained" warning. Two-ring/collinear mirror ambiguities are surfaced,
  never hidden.
- **~8 PM — handoff #2 merged** (Xweather helper with verified endpoints,
  `.env.example`, external-asset verdicts), local work preserved by graft-and-diff.

### Thursday, July 24 — M1 absorbed, then the detector that learns its lesson

- **~4:30 PM UTC — M1-complete handoff merged** (STATUS.md, m1-results.md, evidence
  imagery, granted-nodes CSV, kitten_screen/access_probe/ptz_control scripts, the
  offline strike-replay `ui/index.html`, rebuilt deck). Verified nothing local lost.
- **Sandbox data path confirmed:** direct basic-auth to Sage storage is
  connection-reset from this cloud sandbox, but the mcp proxy `?token=` pattern
  pulls real W06C FLAC in ~1.5 s — so the real archive was workable from the cloud.
- **~5 PM UTC — `detectors/`: the D1–2 anchored, noise-adaptive thunder detector.**
  Ground truth (955 dual-satellite GLM flashes + the 22 recovered arrivals) was
  extracted from the replay UI into `detectors/data/kitten_glm.json`. The detector
  whitens against a per-frequency stationary noise floor (rain absorbs itself),
  opens sensitive listening windows after known flash times, and gates anchored
  arrivals on **range consistency** — the formalized version of M1's falsification
  logic. Re-validated on the actual ignition-storm archive: **20/22 arrivals
  recovered (±4 s), median implied-range error 0.6–0.8 km**; a rain-shower control
  window measured **~36 standalone false alarms/hour** — the number that cements the
  nominate-only contract for unanchored audio. 72 additional range-consistent
  candidates now await NLDN/STRIKEnet arbitration. Synthetic suite: thunder
  recovered *under* rain via anchoring; rain rejected standalone **and** anchored
  (range-inconsistent); wind rejected; onset error ~0.2 s.
- **Evening — Vaisala NLDN research-use request SUBMITTED.** The application the
  plan said to file early went in: 250-word abstract (framing NLDN strictly as
  reference truth for validating our acoustic ranging — the policy restricts
  network intercomparisons), three bounded windows totaling ~65,000 km² / 81 days —
  Grand Teton Jun 25–Aug 1 2025 (Kitten + Signal Flat + holdover scan, arbitration
  of the 22 arrivals + 72 candidates), SW Oregon Jul 1–14 2025 (Selma bust
  risk-score back-test), Chicagoland Jun–Aug 2026 (live array validation). Full
  package archived in [`nldn-research-request.md`](nldn-research-request.md);
  Vaisala's stated review turnaround is ~2 weeks. STRIKEnet single-event report
  (W06C, Jul 2–3 2025) remains the fast paid fallback for the camp deadline.

The through-line of both tracks is the same finding, twice over: **hardware watches
nothing unless something aims it** (cabin wall; five motionless months at a volcano),
and **audio claims nothing unless something anchors it** (0/17 falsified → 20/22
recovered). The M4 storm-mode controller is the answer to both.

## Where things stand

- **W0A4 tunnel**: working (Windows OpenSSH, local 8081/8554); cameras are fixed
  dome + fisheye, no PTZ, and the `waggle` account has no PTZ permission.
- **PTZ access**: authorized on W069 / W071 / W097 — all currently offline. Watching
  for any of them to come back; alternatively request W029, W06C, or standby node
  H00F from the instructors, plus camera credentials or a scheduled PTZ plugin.
- **W097 question answered**: smoke data exists (1,168 detections — many of them the
  real Kīlauea eruption), PTZ imagery exists (4,111 hourly frames), but the two
  never interacted: the PTZ sat motionless for its entire five-month record.
- Downloaded imagery (PTZ sequence, detection frames, Mobotix thermal pairs) lives in
  [`w097-imagery/`](w097-imagery/README.md) with per-image notes on why it was
  collected, what it revealed, and how it feeds FlashPoint.
- **Software track**: the dashboard (`dashboard/`, review-hardened) and the D1–2
  anchored thunder detector (`detectors/`, 20/22 on the real ignition storm) are on
  the branch and pushed. Detector code is deliberately numpy/scipy/soundfile-only so
  it ports into an ECR plugin unchanged — **next stop is M2: package it as a Sage
  app, `pluginctl` it on H03E, then schedule on granted nodes** (the W096↔W09E↔W08B
  city triangle and the Emiquon twins W01B+W020 are the granted-set arrays).
- **Tier-3 chassis identified:** `ptzapp-yolo` (Dematties/Lebiedzinski, ECR) is the
  fleet's existing YOLO/Florence-2-guided PTZ plugin — fork target for strike-sector
  re-aim + SmokeyNet dwell instead of uniform sweeps (see External assets in
  CLAUDE.md and the Day-1 census note that PTZ on Sage is driven by exactly these
  scheduled plugins).
- **NLDN ground truth: application in.** Vaisala research-use request submitted
  2026-07-24 (three case windows; package + submission notes in
  [`nldn-research-request.md`](nldn-research-request.md)). Expected review ~2 weeks
  — data would land right as the 22+72 arrival arbitration becomes the headline
  analysis.

## Reusable facts learned along the way

- Gateway access test: `ssh waggle-dev-sshd connect-to-node <VSN>` — instant
  yes/no ("connecting you" vs "you do not have access"); "Connection refused" on
  `rtun.sock` means access granted but node offline.
- Node manifests (hardware per node): `https://auth.sagecontinuum.org/manifests/`
- Job specs (what ran where, with args): `https://es.sagecontinuum.org/api/v1/jobs/list`
  and `/api/v1/jobs/<id>/status` — public, no auth.
- Data queries: POST `https://data.sagecontinuum.org/api/v1/query` with
  `{"start":"-30d","filter":{"vsn":"W097","task":"..."}}`.
- Storage downloads: `curl -L -u '<user>:<token>'` on the upload URL (expect a 302).
  From cloud sandboxes that reset/strip auth to storage, the mcp proxy pattern works
  instead: `mcp.sagecontinuum.org/proxy/image?url=<storage-url>&token=<user>:<tok>`
  (518/518 in the M1 run; 49/49 + 27/27 again for the detector eval).
- Two temperature sensors publish `env.temperature` per node: bme280 is *inside the
  enclosure* (runs ~30 °C hot); use **bme680** for anything physical (speed of
  sound, fire weather). Verified live on W06C: 46.4 °C vs 15.9 °C same hour.
- Windows gotchas: python writes `\r\n` that breaks curl URL lists (strip with
  `tr -d '\r'`); Git Bash ssh ≠ Windows OpenSSH agent.
