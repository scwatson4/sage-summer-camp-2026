# Case media — provenance

Evidence files embedded by `../../project.md`. The raw/derived rule applies
here exactly as everywhere else in FlashPoint: `-raw.flac` files are
byte-identical copies of what node W06C's microphone uploaded to Sage
storage — never edited, never gain-adjusted. `-listen.flac` files are
clearly-labeled derived copies, peak-normalized to −1 dBFS so a human can
hear what the detector works with (distant thunder arrives around 0.4 % of
full scale — essentially silent without gain).

| file | what it is | gain applied |
|---|---|---|
| `w06c-20250702-222146Z-raw.flac` | 30 s clip, 2025-07-02 22:21:46 UT. Contains a **confirmed flash→bang arrival**: GLM flash 22:20:50 at 20.4 km → thunder onset +59.6 s, at +3.6 s into the clip. Spectrogram: `../flashmatch_222146.png` | none |
| `w06c-20250702-222146Z-listen.flac` | listening copy of the above | +46.9 dB |
| `w06c-20250702-233336Z-raw.flac` | 30 s clip, 2025-07-02 23:33:36 UT. Contains **three confirmed arrivals from three different flashes** (9.8, 18.0, 13.7 km) inside 11 s. Spectrogram: `../flashmatch_233336.png` | none |
| `w06c-20250702-233336Z-listen.flac` | listening copy of the above | +45.4 dB |
| `w06c-20250703-014604Z-falsified-raw.flac` | 30 s clip, 2025-07-03 01:46:04 UT. The **strongest audio-only "thunder" candidate** (low-band transient ratio 31) — and a proven **false positive**: neither GOES-18 nor GOES-19 GLM saw any flash within 50 km (±90 s). Spectrogram: `../kitten-thunder-1.png` | none |
| `w06c-20250703-014604Z-falsified-listen.flac` | listening copy of the above | +37.7 dB |
| `kitten-glm-storm-map.png` | GLM flashes around the Kitten Fire point, from the committed ground-truth fixture (`detectors/data/kitten_glm.json`, a deduplicated 955-flash subset; the full dual-satellite scan holds 219 in-window flashes ≤25 km). | — |
| `selma-dry-bust.png` | W067's own met streams (public Sage query API, `wxt.env.temp` + `wxt.rain.accumulation`, 2025-07-05→10, 10-min means). | — |
| `live-perception-strip-w09e-allsky-20260728.jpg` | Agent-ladder stage 2 contact sheet: W09E all-sky fisheye, raw 03:00Z + 04:00Z UT frames + detector view. gemma4:31b read: `haze` both frames; the lone YOLO/COCO output ("bowl" 0.50 on the fisheye disk) is the documented dead-weight finding. Derived via `agent/evidence.py`; raw source frames in the live pack manifest. | — |
| `live-perception-strip-w08b-skyline-20260728.jpg` | Same run, W08B skyline camera: raw pair + detector view, gemma4:31b `haze`/`none`, zero YOLO detections. Perception test, not an alert. | — |

Source for the audio: Sage storage uploads by `sage-audio-sampler-0.4.1` on
W06C (000048b02d3ae335), fetched with the `scwatson` grant. 48 kHz mono FLAC,
30 s each.
