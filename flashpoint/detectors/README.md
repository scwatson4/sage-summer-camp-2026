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
  false-alarm class the DSP gates can't separate — **started: see "Audio
  classifier probe v0" below** (next: more storms/nodes, PANNs comparison,
  event-level windows instead of clip-level).
- Port into the `sound-event-detection` plugin fork for on-node M2 deployment.

## Audio classifier probe v0 (camp, H03E)

First pass at the neural-classifier thread: frozen **YAMNet** embeddings
(concat of mean+max frame pooling, 2048-d) + logistic regression,
5-fold stratified CV, pooled out-of-fold scores (`probe_v0.py`, results in
`data/probe_v0_results.json`). Labels: positive = the 13 storm clips
containing the 22 anchored arrivals; negative = the 27 rain-shower control
clips (0.22 h — so the 1 FA/h operating point allows zero control false
alarms). Baselines re-scored on the same label set.

| Score | AUC | Recall @ 1 FA/h (clips / arrivals) |
|---|---|---|
| **Probe v0 (YAMNet + logreg)** | **0.952** | **9/13 · 15/22** |
| DSP clip score (same labels) | 0.699 | 1/13 · 1/22 |
| v0 ratio (same labels) | 0.618 | 0/13 · 0/22 |
| YAMNet Thunder class, zero-shot | 0.593 | 2/13 · 3/22 |
| DSP / v0 vs storm-window negatives (stored eval) | 0.389 / 0.282 | — |

The learned probe separates rain-masked thunder from rain that the DSP
scores cannot (0.95 vs 0.70 on identical labels), and the zero-shot Thunder
class alone does not (0.59) — the separation lives in the embedding, not the
AudioSet label. Context: 28/36 of the ambiguous storm clips (where the 72
unmatched candidates live) score above the probe's operating threshold.
Caveats: 40 labeled clips from a single node/storm; control window is
same-day rain only — treat as a promising v0, not a validated detector.
