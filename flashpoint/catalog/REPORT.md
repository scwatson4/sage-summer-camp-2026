# FlashPoint storm–archive–fire catalog

*Generated 2026-07-28 04:49 UTC from public sources only (GOES GLM on AWS anonymous, WFIGS, Sage query API). No Sage token was used.*

## What this is

Every co-occurrence of lightning, node recording, and nearby wildfire across the Sage fleet's fire-country nodes, from first deployment to now. It generalises the M1 Kitten Fire retrospective from one case to the whole fleet.

## Method and scale

- **Nodes.** 118 deployed W/V nodes carry a microphone or camera; 84 of them have a GPS fix in the manifest and can be fire-matched. The remaining 34 publish data but have no coordinates, so they are inventoried and excluded from every distance-based result here.
- **Fires.** 353 natural-cause WFIGS incidents since 2021 within 35 km of such a node.
- **Lightning.** GOES GLM L2 LCFA flash centroids, quality-flag 0, from the best-viewing operational satellite per date and longitude (G16 →2025-04-07, G17 →2023-01-10, G18 2022-09-19→, G19 2025-01-15→; boundaries verified against the S3 buckets).
- **Scan.** 1,140 satellite-days planned ≈ 4,924,800 granules; **7,045,990 granules actually existed and were read** (143.1%). Granules were staged through tmpfs and deleted per hour, so nothing raw was retained.
- **Archive completeness.** 302 of 1,140 satellite-days returned fewer than the nominal 4,320 granules. These are real GLM outages, not fetch failures: re-listing S3 for a sample of short days returned exactly the reduced count. Storm-day counts are therefore a lower bound on those dates.

### The cost lever is dates, not nodes

GLM granules are full-disk, so one download serves every target at once and the scan cost is `|unique (satellite, date)| × 4320`. Measured on this catalog, trimming the Phase-2 census from 17 nodes to 12 or to 10 changed the granule count **not at all** (7,369,920 in every case): the same May–September dates are still required. What did reduce it was dropping the GOES-**East** track — the eastern mic nodes (Great Lakes, Dakotas, central Texas) are the only reason a second satellite's dates are needed — which took Phase 2 from 7.37M to 3.10M granules, under the 4M ceiling. Planning Phase 1 and Phase 2 as one union saved a further 2.14M granules (~1.5 h) versus scanning them separately.

### The manifest is not the archive

Selecting "microphone-equipped" nodes from the manifest would have been wrong in both directions. **97 nodes advertise a Microphone capability, but only 64 have ever published a single audio clip.** 37 advertise a microphone and record nothing; 4 publish audio with no microphone listed at all (V040, V041, W021, W068).

This matters for the census, not just for tidiness. **V040 (Bear Mt., OR) and V041 (Harness Mt., OR) rank #2 and #3 in the fleet by natural-fire proximity — 55 and 53 fires within 35 km — and both genuinely record audio, but neither lists a microphone.** They are included here on the strength of the archive. Conversely V015 and V023 list microphones and have never recorded a second of audio, which is why their audio columns below are zero. **W021 (Fort Collins, CO) also records audio with no microphone listed, contradicting the project's standing note that Colorado has zero microphones** — it has 172,045 audio uploads and 19 natural-cause fires within 35 km. It is *not* in the census below because at 105.1°W it falls on the GOES-East side of the 106.2°W viewing crossover, and adding it would pull in a whole second satellite track: 500 more satellite-days, ~2.16M granules, ~51 min. That is the single highest-value extension to this catalog and it is a deliberate, costed omission.

### Validation against M1

The scanner was checked against the independently derived Kitten Fire result before any bulk run: the nearest GLM flash to the fire point during the 2025-07-02 22–00 UT ignition storm comes out at **3.13 km** (M1 documented 3.1 km). The rain module reproduces M1's dry/wet split for the same node — 0.16 mm across the dry nocturnal storm of 1 July (M1: 0.0 mm) and 2.01 mm across the 2 July evening storm (M1: 2.2 mm).

## (a) Top 20 storm + recording + fire coincidences

Ranked as candidate retrospective studies. `study_score` is a transparent weighted blend of flash-to-fire proximity (0.26), archived audio (0.22), fire-to-node distance (0.16), storm size (0.16), archived imagery (0.12) and an attributable holdover gap (0.08); every component is shown so the ranking can be argued with.

**Benchmark check — the Kitten Fire ranks #4** of 448 scored (fire, node) pairs: nearest flash 3.13 km, 328 flashes ≤30 km, 2862 audio clips and 10663 PTZ frames archived in the window.

| fire | discovered (UTC) | st | node | node km | flash→fire km | flashes ≤30km | holdover h | audio | images | ptz | acres | score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Christ Mountain | 2023-08-01 23:48 | US-CO | W021 | 15.6 | 0.14 | 2317 | 0.0 | 2017 | 23106 | 0 | 0.1 | 0.887 |
| Cow Lake | 2026-07-22 02:20 | US-WY | W06C | 13.9 | 0.81 | 985 | 1.2 | 2872 | 466 | 19880 | 0.1 | 0.881 |
| East Pilgrim | 2026-07-27 01:04 | US-WY | W06C | 11.4 | 1.43 | 1093 | 1.1 | 2367 | 451 | 10636 | 0.1 | 0.877 |
| Kitten | 2025-07-03 02:04 | US-WY | W06C | 5.7 | 3.13 | 328 | 2.0 | 2862 | 681 | 10663 | 0.3 | 0.870 |
| Moosehead | 2026-07-22 00:08 | US-WY | W06C | 17.2 | 0.67 | 926 | 0.0 | 2872 | 466 | 19880 | 0.1 | 0.865 |
| Vista | 2026-04-17 20:00 | US-WI | W0AA | 10.0 | 0.81 | 796 | 2.0 | 2598 | 1052 | 0 | 0.2 | 0.861 |
| Snailback | 2024-08-18 00:25 | US-OR | W067 | 6.3 | 0.17 | 154 | 0.2 | 2833 | 707 | 0 | 0.1 | 0.850 |
| Maverick Assist | 2023-07-27 01:46 | US-UT | W045 | 7.5 | 2.16 | 577 | 1.8 | 2863 | 567 | 0 | 2.0 | 0.849 |
| Signal Flat | 2025-07-26 19:44 | US-WY | W06C | 12.3 | 1.12 | 216 | 58.2 | 2637 | 652 | 9104 | 7.7 | 0.845 |
| Otter | 2023-08-01 15:04 | US-CO | W021 | 24.2 | 0.42 | 1953 | 8.3 | 2017 | 23106 | 0 | 0.1 | 0.841 |
| Moose Hollow | 2022-08-12 14:24 | US-UT | W029 | 18.4 | 0.62 | 359 | 13.0 | 2872 | 16064 | 0 | 0.1 | 0.839 |
| Crooks Creek | 2024-07-16 22:41 | US-OR | W067 | 7.7 | 4.21 | 296 | 0.3 | 2192 | 611 | 0 | 0.1 | 0.810 |
| Ridgeline | 2026-07-21 18:03 | US-UT | W045 | 22.2 | 0.21 | 1177 | 6.8 | 2871 | 329 | 0 | 0.1 | 0.807 |
| Camp Creek | 2024-07-17 15:06 | US-OR | W019 | 13.5 | 1.39 | 298 | 8.6 | 2136 | 389 | 0 | 1.0 | 0.803 |
| Southside Road | 2025-08-27 21:29 | US-OR | W067 | 22.4 | 0.42 | 636 | 14.2 | 2861 | 773 | 0 | 0.0 | 0.800 |
| 2025-0624 | 2025-06-24 21:09 | US-ND | W085 | 25.5 | 1.89 | 2544 | 53.4 | 2871 | 529 | 0 | 1.0 | 0.796 |
| Scramble | 2022-09-15 01:45 | US-UT | W029 | 16.5 | 2.09 | 82 | 4.7 | 1685 | 16156 | 0 | 0.1 | 0.791 |
| Cabin Creek | 2026-07-18 13:55 | US-WY | W06C | 30.6 | 1.43 | 707 | 12.4 | 2872 | 488 | 20866 | 0.1 | 0.790 |
| Lake of the Woods | 2025-07-31 23:53 | US-WY | W06C | 23.8 | 2.31 | 347 | 0.2 | 2635 | 661 | 9149 | 0.1 | 0.789 |
| Reed | 2023-07-26 23:41 | US-UT | W045 | 25.1 | 0.69 | 757 | 0.1 | 2863 | 557 | 0 | 0.1 | 0.785 |

## (b) Per-node storm-day recording coverage — the duty-cycle argument

Across the census nodes there are **2,263 storm days** (≥10 GLM flashes within 30 km of the node, May–September, after that node's deployment). The archive captured *something* on 52.2% of them and audio on 27.5%.

| node | site | storm days | flashes | % any media | % audio | % imagery | clips | clips/day | audio duty % | exp clips/storm | nat. fires | nearest fire km |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W021 | Fort Collins, CO 80523 | 302 | 58,587 | 41 | 31 | 41 | 20,051 | 66 | 0.8 | 26 | 19 | 3.2 |
| W06F | 27700 South Valley Road La | 216 | 30,797 | 80 | 32 | 78 | 18,137 | 84 | 1.0 | 31 | 18 | 15.2 |
| W084 | 27700 South Valley Road La | 216 | 30,799 | 71 | 19 | 70 | 10,607 | 49 | 0.6 | 18 | 18 | 15.2 |
| W06C | Amk Ranch Rd, Moran, WY 83 | 203 | 20,504 | 26 | 23 | 26 | 11,810 | 58 | 0.7 | 21 | 35 | 5.5 |
| W029 | Utah Natural History Museu | 172 | 23,055 | 100 | 37 | 100 | 15,916 | 93 | 1.1 | 32 | 45 | 5.8 |
| W045 | 102 S 200 E, Salt Lake Cit | 168 | 22,382 | 58 | 48 | 52 | 20,501 | 122 | 1.4 | 41 | 39 | 7.5 |
| W016 | Austin, TX | 159 | 78,664 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | 1 | 16.3 |
| W06A | Lac du Flambeau, WI | 138 | 44,897 | 38 | 7 | 38 | 2,027 | 15 | 0.2 | 4 | 4 | 10.9 |
| W085 | WWC7+Q93, Grand Forks, ND | 138 | 57,051 | 80 | 78 | 80 | 27,516 | 199 | 2.3 | 45 | 3 | 25.5 |
| W083 | 72682 Maple St, New Odanah | 127 | 36,839 | 77 | 0 | 77 | 0 | 0 | 0.0 | 0 | 1 | 34.5 |
| W08C | Marenisco Township, MI | 125 | 37,331 | 24 | 24 | 24 | 7,591 | 61 | 0.7 | 16 | 7 | 11.7 |
| W0AA | 13457W Froemel Rd, Hayward | 86 | 31,489 | 43 | 43 | 43 | 9,383 | 109 | 1.3 | 22 | 3 | 7.8 |
| W070 | 21941 Crestline Rd, Birch  | 61 | 5,638 | 43 | 43 | 43 | 6,591 | 108 | 1.3 | 33 | 4 | 10.9 |
| V023 | Cuyamaca Peak, CA 91916 | 38 | 9,238 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | 4 | 14.7 |
| W067 | Selma, OR | 32 | 4,696 | 44 | 22 | 44 | 1,588 | 50 | 0.6 | 20 | 58 | 1.1 |
| V015 | Prairie Mountain, Alsea, O | 19 | 2,057 | 16 | 0 | 16 | 0 | 0 | 0.0 | 0 | 28 | 5.5 |
| V040 | Bear Mt., OR 97424 | 19 | 2,060 | 53 | 0 | 53 | 0 | 0 | 0.0 | 0 | 55 | 6.2 |
| W019 | 1264 Franklin Blvd, Eugene | 18 | 1,740 | 100 | 33 | 72 | 1,488 | 83 | 1.0 | 11 | 36 | 7.2 |
| V041 | Harness Mt., OR 97424 | 16 | 1,865 | 56 | 0 | 56 | 0 | 0 | 0.0 | 0 | 53 | 3.9 |
| W041 | Eugene, OR | 10 | 443 | 40 | 20 | 40 | 522 | 52 | 0.6 | 8 | 7 | 20.5 |

### Two of the most fire-exposed microphones ran outside storm season

Before duty cycle enters the argument there is a scheduling problem. Most nodes run `audio-sampler` year-round, but it follows no storm-season logic, and where it was scheduled narrowly it landed in the wrong half of the year:

| node | audio from | audio to | audio days | of which May–Sep | months active | storm days | storm days WITH audio |
|---|---|---|---|---|---|---|---|
| W021 | 2021-09-30 | 2024-04-19 | 752 | 206 | 1,2,3,4,5,6,7,8,9,10,11,12 | 302 | 95 |
| W06F | 2025-01-27 | 2026-07-27 | 512 | 238 | 1,2,3,4,5,6,7,8,9,10,11,12 | 216 | 70 |
| W084 | 2022-05-18 | 2023-08-24 | 321 | 131 | 1,2,3,4,5,6,7,8,9,10,11,12 | 216 | 41 |
| W06C | 2023-06-29 | 2026-07-26 | 437 | 165 | 1,2,3,4,5,6,7,8,10,11,12 | 203 | 47 |
| W029 | 2021-11-18 | 2023-07-05 | 539 | 195 | 1,2,3,4,5,6,7,8,9,10,11,12 | 172 | 63 |
| W045 | 2022-02-11 | 2026-07-27 | 643 | 266 | 1,2,3,4,5,6,7,8,9,10,11,12 | 168 | 81 |
| W016 | — | — | 0 | 0 | — | 159 | 0 |
| W06A | 2023-06-29 | 2025-10-15 | 135 | 28 | 1,2,3,4,5,6,7,10,11 | 138 | 9 |
| W085 | 2023-06-01 | 2026-07-27 | 1152 | 515 | 1,2,3,4,5,6,7,8,9,10,11,12 | 138 | 108 |
| W083 | — | — | 0 | 0 | — | 127 | 0 |
| W08C | 2022-05-31 | 2023-08-01 | 149 | 125 | 5,6,7,8,9,10 | 125 | 30 |
| W0AA | 2023-10-07 | 2026-07-27 | 435 | 198 | 1,2,3,4,5,6,7,8,9,10,11,12 | 86 | 37 |
| W070 | 2023-05-01 | 2026-07-27 | 937 | 392 | 1,2,3,4,5,6,7,8,9,10,11,12 | 61 | 26 |
| V023 | — | — | 0 | 0 | — | 38 | 0 |
| W067 | 2023-07-27 | 2025-12-12 | 544 | 169 | 1,2,3,4,5,6,7,8,9,10,11,12 | 32 | 7 |
| V015 | — | — | 0 | 0 | — | 19 | 0 |
| V040 | 2023-09-29 | 2024-01-26 | 120 | 2 | 1,9,10,11,12 | 19 | 0 |
| W019 | 2021-09-30 | 2024-10-07 | 949 | 421 | 1,2,3,4,5,6,7,8,9,10,11,12 | 18 | 6 |
| V041 | 2023-11-08 | 2024-02-21 | 106 | 0 | 1,2,11,12 | 16 | 0 |
| W041 | 2023-08-01 | 2026-07-27 | 526 | 165 | 1,2,3,4,5,6,7,8,9,10,11,12 | 10 | 2 |

**V040, V041 recorded audio on 226 days and caught not one of their 35 storm days.** V040 (Bear Mt.) and V041 (Harness Mt.) are the fleet's #2 and #3 nodes by natural-fire proximity, and their microphones ran from late September through February — autumn and winter, while every storm day they experienced fell in May–September. The most fire-exposed audio-capable nodes in the fleet listened in exactly the wrong months. No amount of detector work recovers a signal that was never sampled; this is a scheduling fix, and it is free.

**The duty-cycle problem, quantified.** `audio duty %` is the fraction of storm wall-clock actually inside an archived clip, at the measured upload cadence and a 10-second clip length (the one assumption here — clip length is not readable without file access). A node can sit under a storm all night and retain only a few percent of it. M1 supplies the independent check: of the 219 GLM flashes within 25 km of the Kitten fire point during the ignition storm, satellite-anchored re-listening recovered **22 flash→bang arrivals** in the archived clips — about 10%, the same order as the cadence predicts. Snapshot sampling is why single-modality retrospective detection fails, and it is the quantitative case for storm mode: the missing signal is not faint, it is *not recorded*.

## (c) Dry-lightning candidates

Storm days with ≤2.5 mm at the node's own gauge, followed within 72 h by a natural-cause WFIGS fire within 35 km of the node. `rain_storm_mm` is measured across the storm window (first flash −3 h to last flash +9 h), which separates a dry nocturnal storm from a wet day far better than a UTC-day total.

**54 candidates** across 11 nodes.

| node | storm day | flashes | nearest km | storm rain mm | day rain mm | audio | ptz | fire | fire km | lag h | acres |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W045 | 2025-07-04 | 552 | 1.5 | 2.09 | 1.77 | 261 | 0 | Duck Club | 30.6 | 0.0 | 98.6 |
| W019 | 2024-07-17 | 329 | 1.1 | 0.30 | 0.30 | 261 | 0 | Camp Creek | 13.5 | 8.7 | 1.0 |
| W06F | 2024-08-14 | 305 | 13.6 | 0.59 | 0.61 | 0 | 0 | Freezeout | 29.3 | 26.7 | 0.1 |
| W019 | 2023-08-25 | 285 | 11.1 | 0.01 | 0.01 | 0 | 0 | Shef Butler | 27.9 | 6.0 | 0.0 |
| W029 | 2025-09-07 | 248 | 7.0 | 0.02 | 0.02 | 0 | 0 | Reed Benson | 22.2 | 35.2 | 0.1 |
| W06C | 2026-07-25 | 240 | 10.1 | 0.33 | 0.44 | 261 | 0 | East Pilgrim | 11.4 | 25.5 | 0.1 |
| W045 | 2023-07-26 | 226 | 1.3 | 2.37 | 2.55 | 261 | 0 | Maverick Assist | 7.5 | 1.8 | 2.0 |
| V040 | 2023-08-25 | 205 | 7.7 | 0.77 | 2.28 | 0 | 0 | Prather | 17.9 | 13.2 | 7.0 |
| W029 | 2026-06-25 | 198 | 1.6 | 1.41 | 1.38 | 0 | 0 | Hogs Back | 26.3 | 45.0 | 0.2 |
| W067 | 2025-08-27 | 188 | 20.5 | 0.61 | 4.66 | 261 | 0 | Southside Road | 22.4 | 14.8 | 0.0 |
| W06C | 2026-07-26 | 186 | 1.8 | 0.62 | 0.79 | 18 | 0 | East Pilgrim | 11.4 | 1.1 | 0.1 |
| W029 | 2026-06-24 | 186 | 12.7 | 0.46 | 0.37 | 0 | 0 | Hogs Back | 26.3 | 67.4 | 0.2 |
| W045 | 2026-06-25 | 181 | 2.7 | 0.82 | 0.77 | 261 | 0 | Hogs Back | 27.1 | 44.6 | 0.2 |
| W045 | 2026-06-24 | 177 | 13.2 | 0.68 | 0.40 | 262 | 0 | Hogs Back | 27.1 | 67.4 | 0.2 |
| W06F | 2026-06-22 | 158 | 3.5 | 1.85 | 1.90 | 261 | 0 | Alex Draw | 29.4 | 12.6 | 0.1 |
| W045 | 2023-07-03 | 134 | 2.6 | 1.06 | 1.35 | 0 | 0 | Mule | 27.6 | 20.7 | 0.1 |
| W06C | 2025-07-30 | 121 | 4.3 | 0.89 | 0.69 | 261 | 916 | Lake of the Woods | 23.8 | 24.0 | 0.1 |
| W06C | 2026-07-17 | 115 | 4.3 | 0.93 | 0.40 | 261 | 1982 | Cabin Creek | 30.6 | 14.1 | 0.1 |
| W029 | 2025-08-28 | 108 | 7.9 | 1.75 | 1.86 | 0 | 0 | Raymond | 20.6 | 11.1 | 0.1 |
| W029 | 2026-07-20 | 91 | 18.2 | 0.49 | 1.77 | 0 | 0 | Ridgeline | 16.8 | 18.7 | 0.1 |
| W045 | 2023-07-25 | 88 | 3.7 | 2.40 | 2.63 | 261 | 0 | Maverick Assist | 7.5 | 45.3 | 2.0 |
| W019 | 2024-07-21 | 72 | 11.7 | 0.02 | 0.02 | 257 | 0 | Eames Creek | 31.6 | 2.5 | 0.1 |
| W06C | 2025-07-01 | 66 | 2.5 | 0.90 | 1.08 | 261 | 957 | Kitten | 5.7 | 26.8 | 0.3 |
| W067 | 2024-07-17 | 64 | 9.7 | 1.68 | 10.25 | 261 | 0 | Bald | 28.4 | 40.7 | 0.5 |
| W021 | 2022-07-21 | 61 | 3.1 | 0.49 | 0.33 | 7 | 0 | Ted | 14.1 | 46.2 | 5.0 |

## Catalog files

- `node_inventory.parquet` — deployed W/V mic/cam nodes: capabilities, GPS, first data
- `node_coverage.parquet` — uploads per (node, task, day) — the archive record
- `node_coverage_monthly.parquet` — the same rolled up per month
- `fires_all.parquet` — every WFIGS incident within 35 km of a node since 2021
- `fires_natural.parquet` — the natural-cause subset that anchors Phase 1
- `fire_node_pairs.parquet` — (fire, node) pairs within 35 km with distances
- `fire_events.parquet` — Phase 1: one row per (fire, node) with GLM + archive summary
- `fire_flashes.parquet` — Phase 1: flash-level detail inside the fire windows
- `storm_recording_days.parquet` — Phase 2: node-days with lightning ≤30 km + archive
- `node_storm_coverage.parquet` — Phase 2: per-node storm-day capture rates
- `node_rain_hourly.parquet` — hourly cumulative rain traces for the census nodes
- `scan_plan.parquet / scan_targets.parquet` — exact scan units and targets (reproducible)

## Caveats

- GLM detects total lightning optically from geostationary orbit with 8–14 km pixels and reduced efficiency by day and toward the limb; it under-detects cloud-to-ground strokes, which are the fire-starting ones. Distances here are flash-centroid to point, not stroke locations. NLDN/STRIKEnet remains the arbiter for metre-scale claims.
- WFIGS discovery time is when a fire was *reported*, not when it ignited; the holdover gap is therefore an upper bound on the true smouldering interval.
- 15 of 353 fire points fall back to the incident geometry because the reported initial point was missing or implausibly far from it (>25 km); those rows are flagged in `coord_source`.
- Rain comes from the node's own gauge, which is a point measurement — a dry gauge does not prove the strike point was dry.
- Nodes without GPS in the manifest cannot be fire-matched and are excluded from Phase 1.
- Phase 0 could not retrieve 76 (node, task, month) units, **all of them `mobotix-scan*` tasks** — those queries return responses large enough to break the connection, and `sage_data_client` calls `urlopen` with no timeout, so they hang rather than fail. The affected census node is W084 (thermal `mobotix-scan`, 2023-05 → 2024-11); its audio-sampler, imagesampler and ptz-yolo coverage is complete, so the audio columns above are unaffected and only W084's thermal-scan frame counts are understated.
- Storm days are counted from GLM alone. A node may have been under a storm that GLM missed (daytime, weak optical signal, limb geometry), so the capture percentages in (b) are, if anything, optimistic about how much the archive holds.
