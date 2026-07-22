# Sage Access Request — Node List (Sammy Watson / scwatson)

*What to request from the Sage Grande team, by priority. Everything below is **data access** (protected file downloads — audio/image uploads — plus job-scheduling where noted). No SSH access is needed beyond H03E, which I already have.*

**First, a 2-minute self-test before requesting anything:** my portal token may already cover most of this. Test: open a storage URL in a browser and log in with username `scwatson` + access token as password. Only request access for whatever still returns 401/403 after that.

---

## Tier 1 — Retrospective case studies (needed first; specific, small, dated)

| Node | Where | What I need | Why |
|---|---|---|---|
| **W06C** | Moran, WY (Grand Teton / AMK Ranch) | Audio (`audio-sampler` FLAC), PTZ/thermal/sky image uploads + met data, **Jul 1–4 and Jul 24–27, 2025** | The **Kitten Fire** (natural cause, Jul 3 2025) ignited 6 km away while the node captured 779 audio clips — post-hoc thunder-detection study. Signal Flat fire (Jul 26) is the second event. |
| **W067** | Selma, OR (Siskiyou) | Camera uploads (top/left/bottom) + met, **Jul 6–9, 2025** | Four-fire lightning bust on Jul 8 2025, 14–22 km away — smoke-column check + dry-lightning flag validation. |
| **W084, W06F** | Lakeview, MT (Centennial Valley twins) | File downloads, 2023 → present (storm windows) | Flagship fire-country deployment for the FlashPoint proposal; continuous archive since 2023. |

## Tier 2 — Camp development arrays (live hackathon work)

**Argonne cluster (acoustic + lightning dev array):**
W023, W027, W030, W0A4, V032, W0AE, W0AF, W0B1, W0B2, W0B3, W0B4, W0B5, W0B6, W0B7, W0B8, W0BA
— audio/image uploads + met; **plus: ask what job-scheduling (pluginctl/ECR deploys) is permitted here for camp teams** — the storm-mode controller and EchoGuard field test need to run detectors on 4–6 of these.

**Chicago Loop array (16-node urban array):**
W01C, W026, W02C, W059, W05A, W05B, W05C, W05D, W073, W074, W075, W076, W077, W079, W07A, W07B
— audio/image uploads + met for the urban-canyon stress test.

**South Side triangle + UIC-area pairs:**
W015, W080, W081 (triangle) · W05E, W072 (UIC med district) · W096, W099 (active sky cams near campus)

## Tier 3 — Fire-country sentinels & regional (stretch / post-camp)

- **West:** W070 (Palomar Mtn, CA), V023 (Cuyamaca, CA — mic only), W02B (Lubbock, TX), W045 + W029 (Salt Lake City pair), W019 + W041 (Eugene, OR)
- **Northern forests:** W083 (New Odanah, WI), W0AA (Hayward, WI), W06A (Lac du Flambeau, WI), W08C (Marenisco, MI)
- **Hawaii (wind-trigger fire-watch variant + HCDP tie-in):** W069 (Lahaina — thermal + PTZ), W097 (Hawaii Volcanoes NP), W071 (Kaneohe)

## Job scheduling (separate ask)

- H03E — already have (my camp blade).
- Ask organizers: which W/V nodes camp teams may schedule plugins on (ideally 4–6 Argonne-cluster nodes above, for the live multi-node demo).

---

## Paste-ready request blurb

> Hi — I'm Samuel Watson (scwatson), a Summer Camp 2026 participant (node H03E). For my hackathon project — multi-node acoustic event localization + lightning/wildfire ignition watch (EchoGuard/FlashPoint) — I'd like protected-data (file download) access for the nodes below, and to know which nodes camp teams may schedule plugins on.
>
> Priority 1 (dated retrospective windows): W06C (Jul 1–4 & 24–27, 2025 — Kitten/Signal Flat fires), W067 (Jul 6–9, 2025 — Selma lightning bust), W084 + W06F (Lakeview MT).
> Priority 2 (camp dev arrays): Argonne cluster — W023, W027, W030, W0A4, V032, W0AE, W0AF, W0B1–W0B8, W0BA; Loop array — W01C, W026, W02C, W059, W05A–W05D, W073–W077, W079, W07A, W07B; plus W015, W080, W081, W05E, W072, W096, W099.
> Priority 3 (stretch): W070, V023, W02B, W045, W029, W019, W041, W083, W0AA, W06A, W08C, W069, W097, W071.
>
> Raw audio/imagery stays within Sage infrastructure; my pipeline publishes derived events only. Happy to scope down if any of these are under separate DUAs.
