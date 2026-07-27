# FlashPoint detectors — D1–2

Noise-adaptive thunder detection with external anchoring. Standalone-portable
(numpy/scipy/soundfile only) so it drops into the M2 ECR plugin fork unchanged.

## Why it looks like this (the M1 post-mortem, `docs/m1-results.md`)

The v0/v1 detectors measured absolute low-band energy — in storm rain that
metric fails **both ways** (17/17 standalone candidates falsified by
dual-satellite GLM; 22 real arrivals sat inaudible under rain; AUC 0.163).
Design consequences implemented here:

1. **Noise-adaptive**: per-frequency stationary floor (percentile over STFT
   frames) → *whitened excess*. Quasi-stationary rain/wind noise is absorbed
   into the floor whatever its absolute level.
2. **Anchored listening** (`anchors.py`): known flash times (GLM satellite,
   Xweather live strikes, camera flash) open windows `flash + [r_min, r_max]/c`
   with a more sensitive extraction pass — the changed prior justifies the
   lower threshold. When the anchor's distance is known (GLM gives one), an
   arrival must also be **range-consistent** (implied vs expected range,
   ±5 km — generous because GLM pixels are 8–14 km).
3. **Mode-dependent gates**: distant (10–30 km) thunder arrives atmosphere-
   low-passed — sub-band-heavy, smeared onset — so anchored mode gates loose
   (range consistency does the work) while standalone mode gates strict.
   Wind defense is primarily the **anemometer veto** (nodes publish wind even
   while audio snapshots); spectral sub-band dominance is the backstop.
4. **Honest output contract**: standalone passes are *candidates only* —
   audio alone never claims a strike (the M1 lesson). Anchored passes carry
   the matched flash time and implied range, ready for the range engine.

## Results on the real ignition storm (run from this repo, cached clips)

`eval_kitten.py`, W06C archive Jul 2 2025 21:00 → Jul 3 01:30 UT, ground truth
= the 22 satellite-anchored arrivals in `data/kitten_glm.json`:

| Metric | Value |
|---|---|
| Anchored recall of the 22 arrivals | **20/22** (±4 s), median range error **0.6–0.8 km** |
| Unmatched anchored passes | 72 (candidate arrivals beyond the 22 — NLDN arbitration material, not claimed) |
| Standalone passes in the storm window | 60 (labeled candidates only) |
| Standalone false alarms, rain-shower control (no anchors) | ~36/h — the number that justifies the nominate-only contract |
| Clip-level AUC (ours / v0 ratio) | 0.39 / 0.28 — standalone clip scoring stays unreliable in rain; the detector's value is anchored mode |

Synthetic separation suite: `tests/test_thunder.py` (thunder/quiet,
thunder-under-rain recovered via anchoring, rain-only rejected standalone AND
anchored via range consistency, wind rejected, implied-range accuracy).

## Files

- `thunder.py` — detector core (`detect(y, sr, anchor_times_s=…, wind_ms=…)`)
- `anchors.py` — GLM/Xweather/camera anchor sources → clip-relative windows
- `physics.py` — speed of sound, flash-to-bang
- `extract_ui_data.py` — regenerates `data/kitten_glm.json` from `ui/index.html`
- `eval_kitten.py` — the real-storm evaluation (`--control` adds the rain window)
- `tests/test_thunder.py` — synthetic suite

```bash
python detectors/tests/test_thunder.py
SAGE_VIA_PROXY=1 python detectors/eval_kitten.py --control   # sandbox
python detectors/eval_kitten.py --control                    # laptop/node
```

## Next

- Flash detector on ring-buffer frames (the other D1–2 half) → camera anchors
  feed the same `detect(anchor_times_s=…)` API.
- Feed anchored arrivals + implied ranges into the multi-node range engine
  (`flashpoint/dashboard/fp/geo.py` trilateration is the reference
  implementation).
- Neural classifier pass (open science thread) to characterize the rain
  false-alarm class the DSP gates can't separate.
- Port into the `sound-event-detection` plugin fork for on-node M2 deployment.
