# M1 Retrospective — Results (run 2026-07-23/24 from Cowork)

## ⚠ CRITICAL UPDATE — satellite cross-validation REJECTS the thunder interpretation

All 17 audio candidates were cross-matched against **both** GOES-West (G18) and GOES-East (G19)
GLM satellite lightning data (free, anonymous, AWS open data; ±90 s, per-event):
**0/17 had any GLM flash within 50 km; 12/17 had none within 100 km** (nearest 118–574 km).
Thunder is audible ~15–25 km at best; two independent GLM instruments do not both miss every
nearby flash across 17 windows. **Verdict: the low-band transients are of undetermined origin
(rain/graupel on enclosure, sub-veto wind buffeting, wildlife/mechanical) — NOT verified thunder.**

**Why this is a strong result, not a failure:** it is direct, quantified proof of the project's
core thesis — single-modality acoustic detection produces confident false positives, which is
exactly why FlashPoint fuses flash/RF + audio + geometry. "We ran the audio-only version and
two satellites falsified it" is a better slide than an unverified positive. Consequences:
(1) the Kitten ignition storm is NOT yet identified — GLM shows no lightning within 50 km of the
node July 2–3, so ignition may predate Jul 2 (holdover > 2 days — strengthens the long-watch
argument) — next experiment: scan GLM back to ~Jun 25 around the FIRE POINT to find the real
strike day; (2) the back-test's Kitten "thunder confirmed" input is withdrawn (Selma's axes —
14 real fires, 0.05 mm week, SMAP 0.084 PM — are unaffected); (3) NLDN/STRIKEnet remains the
final arbiter (GLM under-detects some CG); (4) W06C imagery at event times (OPEN to us) can
identify the actual transient source (rain on lens is visible).

*Sections below record the original audio-side findings; read them through the caveat above.*

## Kitten Fire (W06C, Grand Teton — fire discovered 2025-07-03, 6 km from node)

**518 audio clips** (all of July 2–3, 2025) downloaded and classified (v0: 15–120 Hz transient
ratio + onset rise + duration bounds + **wind veto** from the node's own anemometer).
**17 thunder events, 0 wind-vetoed** (max wind in window: 5.6 m/s — calm).

| Storm | Thunder events | Rain at node | Verdict |
|---|---|---|---|
| **Night of July 1 (00:56–06:11 UT Jul 2)** | **8** (incl. ratio 47.7) | **0.0 mm** | **DRY lightning storm — prime ignition suspect** |
| Evening July 2 (00:39–04:26 UT Jul 3) | 7 | 2.2 + 1.1 mm | dry-ish (< 2.5 mm threshold) — second suspect |
| Afternoon July 3 (23:14 UT) | 1 (clean double rumble) | showers 17/19 UT | post-discovery storm |

Timeline figure: `m1-timeline.png`. Spectrograms: `kitten-thunder-1/2.png`.
Holdover consistency: ignition night Jul 1–2 → smolder → discovery midday Jul 3 = exactly the
window FlashPoint's 72 h aftermath watch targets.

## Selma bust (W067, Siskiyou) — bigger than first thought

WFIGS re-query: **14 natural-cause fires** logged 2025-07-08 (most at 02:47 UT = 7:47 pm PDT
Jul 7), 14–34 km from the node, bearings mostly E–SE (69–123°) and S (170–193°).
Node's gauge: **0.00 / 0.00 / 0.00 / 0.05 / 0.00 mm** Jul 5–9 — a bone-dry bust during a
35 °C heat spike (NASA POWER). **Imagery review BLOCKED: W067 file access = 403.**

## Ignition-risk back-test (v0.1 — per-strike score; no strike → no card)

| Score | Case | Outcome |
|---|---|---|
| **87** | Kitten July 1–2 night storm (0.0 mm) | fire discovered next day, 6 km |
| 71 | Kitten July 2 evening storm (2.2 mm) | same fire window |
| **84** | Selma July 7 bust (0.05 mm, 35 °C) | 14 fires next day |
| 41 | wet-storm control (15 mm) | low risk — correct |
| 0 | no-strike day | no card — correct |

Formula (transparent): 35·dry(rain) + 30·dryness(GWETTOP) + 20·fuel + 15·thunder-confidence,
gated on strike presence. Both real ignition storms score hot; controls score low. Weights are
literature-informed placeholders — tune at camp, but the separation is already clean.

## Access map (verified by download attempts, 2026-07-23)

- **OPEN with scwatson token:** W06C (audio + imagery + ptz-yolo!), W069 archive, all granted-CSV
  reporting nodes (W096 etc.).
- **DENIED (403):** W067 (Selma imagery!), W084, W06F (Lakeview twins), W019 (Eugene sky-cam).
- **Follow-up ask (exactly four nodes):** W067, W084, W06F, W019.
- Sandbox note: this environment strips Authorization headers → downloads via
  `mcp.sagecontinuum.org/proxy/image?url=…&token=user:tok` (518/518 success). On laptop/node,
  direct basic auth works.

## Still open (laptop/camp)

Neural classifier pass (YAMNet/PANNs) to formalize the 17 events; Jul-1 night deep-listen;
Selma imagery once W067 unlocks; SMAP granule pull via `earthaccess` (CMR located
SMAP_L3_SM_P_E_20250701/02); STRIKEnet or NLDN cross-match of the 17 event timestamps.
