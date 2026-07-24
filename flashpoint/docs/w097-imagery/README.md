# W097 (Hawaii Volcanoes NP) imagery — collected 2026-07-24

Pulled from Sage storage (`scwatson` + portal token) during the investigation
written up in [`../project-story.md`](../project-story.md). Question under test:
**does any W097 data show the PTZ camera moving to watch smoke?** (Answer: no —
and proving that produced the most useful forensics of the trip.)

All timestamps in filenames are UTC (HST = UTC−10). Node context: W097 carries a
Hanwha XNP-6400RW PTZ, a fixed "bottom" camera used by the `fire-detection` job
(YOLOv7, every 15 min), and a Mobotix dual visible/thermal camera. Node offline
since ~2025-12-30; all files below are archive pulls.

---

## 1. PTZ hourly frames (`ptz-*.jpg`, 11 frames, Jul 24 → Dec 30 2025)

**Why collected:** the PTZ image record (`imagesampler-hanwhaptz`, hourly cron,
no position telemetry anywhere) is the *only* evidence of where the PTZ pointed.
Frames were chosen to bracket the biggest smoke-detection days (Aug 23, Sep 2–3,
Oct 1, Oct 5) plus one per month as baseline, through the final frame before the
node died.

**What they revealed:** the camera **never moved in five months** — identical
framing (same ʻōhiʻa canopy, same dead branches lower-left, same comms tower on
the horizon) in daylight, fog, and night-IR. Operator steering ruled out at
hourly resolution. Smoke-day frames show broad vog/fog, not plumes.

**How this moves FlashPoint forward:** this is the second documented case (after
M1's "PTZ stared at a cabin wall through the ignition storm", see
`../forensics_sheet.jpg`) of a PTZ asset pointing at nothing of value during a
detectable event. It is the core motivating evidence for the **M4 storm-mode
controller / Tier-3 PTZ re-aim**: idle cameras don't watch events unless
something commands them to. Use both cases together on the pitch slide.

Notable frames:
- `ptz-2025-08-23T2220Z-fog.jpg` — full fog-out on a top smoke day; the kind of
  frame that turns "smoke: 1" detections into vog/fog false-positive candidates.
- `ptz-2025-11-01T2020Z-rain.jpg` — rain-blurred lens; sensor-blindness example
  for the controller's data-quality gating.
- `ptz-2025-12-30T1620Z-final-frame-ir.jpg` — the node's last PTZ frame ever
  (pre-dawn IR, illuminator lighting the canopy). Same aim as July. Bookend shot.

## 2. Fire-detection frames at detection moments (`firedet-*.jpg`, 3 frames)

**Why collected:** to see what the YOLOv7 `fire-detection` job (fixed bottom
camera, facing Kīlauea caldera) was actually detecting at its highest-confidence
smoke/fire timestamps — each frame is the upload at the *exact* second of a
nonzero `env.detection` record (dt = 0 s).

**What they revealed:** the detections were substantially **real volcano**:
- `firedet-2025-08-23T0954Z-eruption-glow-night.jpg` — night; eruption glow
  saturating the horizon boxed `fire:42%`; moonlit cloud boxed `smoke:48%`
  (a genuine false positive in the same frame as a genuine true positive).
- `firedet-2025-09-02T1347Z-eruption-glow-clouds.jpg` — eruption glow lighting
  the cloud deck, boxed `fire:42%`; box geometry is sloppy (huge horizon-wide
  rectangles).
- `firedet-2025-10-05T1733Z-halemaumau-plume-day.jpg` — daylight; white gas
  plume rising from Halemaʻumaʻu crater (`smoke:53%`, `smoke:48%`), Mauna Loa
  behind. The cleanest "this camera can see a smoke column at ~3 km" proof.

**How this moves FlashPoint forward:** (1) ground-truth-rich validation set —
1,168 detection timestamps with a known persistent source, perfect for
calibrating the smoke leg (SmokeyNet / smoke-detector-top) against a *labeled*
plume vs vog/cloud confusers, directly addressing the CA-horizon domain-shift
caveat in CLAUDE.md. (2) Night-glow frames are template positives for a
"fire glow at night" detector the current stack lacks. (3) The sloppy YOLOv7
boxes argue for the tile-based SmokeyNet approach (bearing refinement) over
whole-frame boxes.

## 3. Mobotix dual visible+thermal frames (`mobotix-*.jpg`, 2 frames)

**Why collected:** W097's Mobotix is the same thermal asset class as the Emiquon
twins (W01B/W020) and Lahaina (W069); wanted to know what the thermal channel
shows during eruption activity.

**What they revealed:**
- `mobotix-2025-08-23T1200Z-glow-visible-thermal.jpg` — 2 AM HST: eruption glow
  in the visible half; thermal half shows warm ground / cold sky but no discrete
  hot spot (glow is reflected light, not line-of-sight heat).
- `mobotix-2025-12-30T0811Z-caldera-hotspot.jpg` — 10 PM HST, hours before the
  node went offline: **discrete saturated hot spot at the caldera in the thermal
  channel** with a visible-channel plume above it. Direct thermal detection of
  the eruptive vent.

**How this moves FlashPoint forward:** demonstrates the thermal channel detects
a heat source that the visible channel only infers — exactly the confirmation
layer the 72-hour holdover-fire watch needs (a smoldering holdover is a weak
thermal target with little visible signature). Justifies routing Tier-3 dwell
time to thermal-equipped nodes and adding a thermal-anomaly check to the
ignition-risk score.

## 4. Raw thermal grid (`thermal-2025-12-17T1454Z-fog-baseline.celsius.csv`)

**Why collected:** the `mobotix-thermal-metrics` task uploads radiometric CSVs
(336×252, 14-bit, °C) — wanted the machine-readable format, not just rendered
JPEGs. (Note: filename records its true capture time, 2025-12-17 14:54 UTC — a
foggy night.)

**What it revealed:** flat 12.1–13.3 °C across all 84,672 pixels — a fog-filled
scene with zero thermal contrast. A perfect *cold baseline*: even during an
active eruption period, fog reduces the thermal channel to uniformity.

**How this moves FlashPoint forward:** (1) the CSV format means thresholding
(e.g. "any pixel > ambient + N °C") is trivial to run on-node — no image ML
needed for the thermal-anomaly leg; (2) the fog baseline quantifies when thermal
goes blind, feeding the same data-quality gate as the rain-blurred PTZ frame.
Next step: pull the CSV nearest `mobotix-2025-12-30T0811Z` and measure the hot
spot in °C (task `mobotix-thermal-metrics`, vsn W097, name `upload`).

---

## Provenance / how to re-pull

Every file came from a Sage storage URL recorded in the data API. Recipe:

```bash
# find upload URLs (public, no auth)
curl -s -H 'Content-Type: application/json' https://data.sagecontinuum.org/api/v1/query \
  -d '{"start":"-365d","filter":{"vsn":"W097","task":"imagesampler-hanwhaptz","name":"upload"}}'
# download one (auth: portal token; follow the 302)
curl -L -u "scwatson:$SAGE_TOKEN" -o out.jpg "<storage-url>"
```

Job specs that produced these streams: `es.sagecontinuum.org/api/v1/jobs/2420/status`
(fire-detection) and `.../2956/status` (hourly PTZ snapshot).
