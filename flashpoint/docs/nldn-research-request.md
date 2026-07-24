# Vaisala NLDN research-use data request — application package

*Prepared 2026-07-24 for the Vaisala lightning-data research request form
(one-time archive request; policy: ≤5 years, ≤1,000,000 km², 250-word abstract
with references). Fill the bracketed personal fields before submitting.*

## Form details

- **Requester:** Samuel Watson — [student/staff status + department],
  University of Hawaiʻi at Mānoa (scwatson@hawaii.edu). Research conducted on
  the NSF Sage cyberinfrastructure (NSF award 1935984) in collaboration with
  the Sage/Argonne team (Sage Summer Camp 2026 participant, Sage user
  `scwatson`).
- **Network:** NLDN (CONUS). Cloud-to-ground stroke- and flash-level data:
  time (ms precision or better), latitude/longitude, polarity, peak current,
  multiplicity, and location-error ellipse if available.
- **Requested windows and areas (total ≈ 65,000 km² — well under limits):**

| Region | Box (lat, lon) | Window | Why |
|---|---|---|---|
| Grand Teton, WY (Sage node W06C) | 43.2–44.7 N, 111.6–109.7 W | 2025-06-25 → 2025-08-01 | Kitten Fire (discovered 2025-07-03, 6 km from node) + Signal Flat (2025-07-26); arbitration of 22 recovered thunder arrivals + 72 candidates; holdover-duration scan back to Jun 25 |
| Southwest Oregon (node W067) | 41.6–43.0 N, 124.5–122.8 W | 2025-07-01 → 2025-07-14 | "Selma bust": 14 natural-cause fires discovered 2025-07-08 within 35 km of the node; dry-lightning risk-score back-test |
| Chicagoland, IL (Sage array) | 41.2–42.5 N, 88.6–87.0 W | 2026-06-01 → 2026-08-31 | Live validation of multi-node acoustic ranging/localization on the 51-microphone metro array |

- **Format:** CSV or similar flat text preferred; any documented format is fine.
- **Deliverables to Vaisala:** conference paper/poster + manuscript courtesy
  review of Vaisala-data-related content before distribution; Vaisala
  acknowledged as data source; no commercial or proprietary restrictions.

## 250-word abstract (verified: 237 words body, 252 incl. title)

**Validating an acoustic–optical lightning localization and wildfire
ignition-watch system on the NSF Sage sensor network**

Lightning ignites much of the western U.S. burned area, and lightning-caused
fires frequently hold over, smoldering for hours to days before discovery
(Schultz et al., 2019; Pineda & Rigo, 2017). We are developing FlashPoint, an
open system on the NSF Sage edge-computing testbed (Beckman et al., 2016),
which turns existing sensor nodes — cameras, microphones, weather stations —
into a lightning detection and ignition-watch network: an optical flash or
satellite report provides each node's time-zero, the thunder arrival delay
yields an acoustic range (Few, 1975; Arechiga et al., 2011), multi-node
geometry localizes the strike, and each strike opens a multi-day smoke watch
with a dry-lightning ignition-risk score computed from co-located rain gauges.

In a Kitten Fire retrospective (Grand Teton National Forest, fire
discovered 2025-07-03, 6 km from Sage node W06C), anchoring on GOES
Geostationary Lightning Mapper flashes (Goodman et al., 2013) recovered 22
thunder arrivals with implied strike ranges from archived audio. GLM's 8–14 km
pixels cannot validate sub-kilometer acoustic ranging; NLDN's ~100 m median
location accuracy and >95% cloud-to-ground flash detection efficiency (Cummins
& Murphy, 2009; Nag et al., 2014) make it the appropriate reference truth, and
its cloud-to-ground focus matches what microphones detect. Requested
cloud-to-ground data (time, location, polarity, peak current) covers three
bounded case windows. Results — localization error, detection recall, and
ignition-risk back-tests against documented fires — will be presented at an
appropriate conference with Vaisala acknowledged; the work carries no
commercial restrictions.

## References (cited in abstract; not part of the 250 words)

- Arechiga, R. O., et al. (2011). Acoustic localization of triggered lightning.
  *J. Geophys. Res.*, 116, D09103.
- Beckman, P., et al. (2016). Waggle: An open sensor platform for edge
  computing. *IEEE SENSORS 2016*.
- Cummins, K. L., & Murphy, M. J. (2009). An overview of lightning locating
  systems: History, techniques, and data uses, with an in-depth look at the
  U.S. NLDN. *IEEE Trans. Electromagn. Compat.*, 51(3), 499–518.
- Few, A. A. (1975). Thunder. *Scientific American*, 233(1), 80–90.
- Goodman, S. J., et al. (2013). The GOES-R Geostationary Lightning Mapper
  (GLM). *Atmos. Res.*, 125–126, 34–49.
- Nag, A., et al. (2014). Recent evolution of the U.S. National Lightning
  Detection Network. *23rd Intl. Lightning Detection Conf. (ILDC)*.
- Pineda, N., & Rigo, T. (2017). The rainfall factor in lightning-ignited
  wildfires in Catalonia. *Agric. For. Meteorol.*, 239, 249–263.
- Schultz, C. J., et al. (2019). Spatial, temporal and electrical
  characteristics of lightning in reported lightning-initiated wildfire
  events. *Fire*, 2(2), 18.

## Submission notes

- The policy restricts "direct comparisons with other lightning detection
  networks" without product-manager approval — the abstract deliberately
  frames NLDN as reference truth for validating OUR acoustic system, not as a
  network intercomparison. Keep that framing in any correspondence.
- Policy encourages including NLDN's research-discount cost in future grant
  proposals — worth a line in any HCDP/UH follow-on proposal.
- A single STRIKEnet per-event report (W06C, Jul 2–3 2025) remains the fast
  paid fallback if this request is slow (see CLAUDE.md External assets).
- Verify the citation details before submission if required in full form —
  they are standard works cited from memory, not fetched.
