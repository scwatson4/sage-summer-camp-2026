"""Noise-adaptive thunder detection (STATUS.md D1-2).

Why this design (M1 post-mortem, docs/m1-results.md): the v0/v1 detectors
scored absolute low-band energy ratios, so steady rain — broadband noise plus
low-frequency enclosure drumming — both MASKED real thunder (false negatives:
the 22 recovered arrivals were buried in rain) and IMPERSONATED it (false
positives: all 17 standalone candidates were falsified by dual-satellite GLM).
Absolute energy is the wrong axis in a storm. This detector instead:

1. estimates a per-frequency stationary noise floor from the clip itself
   (percentile over STFT frames), so quasi-stationary rain/wind noise is
   absorbed into the floor whatever its level;
2. measures WHITENED EXCESS — dB above that adaptive floor in the thunder
   band — so only transient structure survives;
3. extracts events from the excess envelope and gates them on thunder
   morphology: rumble-scale duration, fast leading edge with slow decay,
   energy concentrated low but not pure sub-20 Hz rumble (wind buffeting);
4. optionally restricts attention to ANCHOR WINDOWS — [flash + r_min/c,
   flash + r_max/c] after each known lightning time (GLM, Xweather, camera
   flash) — where a lower threshold is justified because the prior changed.

Output events are labeled candidates, never confirmed strikes: standalone
audio can only nominate; anchoring or fusion confirms (the M1 lesson).
"""
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

BAND = (15.0, 200.0)        # analysis band, Hz — thunder's energy lives here
SUB_BAND = (15.0, 60.0)     # deep-rumble part
MID_BAND = (60.0, 200.0)    # clap/crack part


@dataclass
class Config:
    hop_s: float = 0.05          # envelope resolution
    nperseg_s: float = 0.35      # STFT window (~3 Hz resolution at the bottom)
    floor_pct: float = 20.0      # percentile over frames = stationary floor
    excess_margin_db: float = 3.0    # floor headroom before anything counts
    on_db: float = 6.0           # event opens when band excess exceeds this
    off_db: float = 3.0          # ... and closes when it falls below this
    min_gap_s: float = 0.6       # merge events separated by less than this
    max_dur_s: float = 20.0
    # Mode-dependent gates. Distant (10-30 km) thunder arrives low-passed by
    # the atmosphere: sub-band heavy, smeared onset, sometimes brief above
    # the floor — so ANCHORED mode (where range consistency does the heavy
    # lifting) gates much looser than STANDALONE (where M1 proved confident
    # false positives are the failure mode).
    min_dur_s: float = 0.7               # standalone: raindrop hits are ~ms
    anchored_min_dur_s: float = 0.4
    min_decay_rise_ratio: float = 1.2    # standalone: fast attack, slow tail
    anchored_decay_rise_ratio: float = 0.5
    min_mid_fraction: float = 0.12       # pure <60 Hz excess = wind buffeting
    # Wind defense: the anemometer is primary (every node publishes wind even
    # while audio snapshots); spectral dominance is the backstop.
    windy_ms: float = 8.0                # measured wind above this = windy
    windy_sub_over_mid_db: float = 12.0  # gate when windy or standalone-unknown
    extreme_sub_over_mid_db: float = 25.0  # always reject beyond this
    range_tol_km: float = 5.0    # anchored: |implied - anchor's known| gate
                                 # (generous: GLM pixels are 8-14 km)
    standalone_score: float = 0.55      # score gate, unanchored
    anchored_score: float = 0.30        # score gate inside an anchor window
    anchored_on_db: float = 3.5  # sensitive extraction pass inside windows
    anchored_off_db: float = 2.0
    r_min_km: float = 0.3        # anchor window = flash + [r_min, r_max]/c
    r_max_km: float = 30.0
    temp_c: float = 20.0


@dataclass
class Event:
    onset_s: float               # leading edge, seconds from clip start
    duration_s: float
    peak_excess_db: float
    mean_excess_db: float
    rise_s: float
    decay_s: float
    mid_fraction: float          # share of whitened excess in 60-200 Hz
    sub_over_mid_db: float = 0.0  # raw sub-band minus mid-band level (wind ↑)
    score: float = 0.0
    anchored: bool = False
    anchor_time_s: float | None = None   # matched flash time (clip-relative)
    implied_range_km: float | None = None
    passed: bool = False
    reject_reason: str = ""


def band_excess(y, sr, cfg=Config()):
    """(t, excess_db, sub_db, mid_db, raw_sub_db, raw_mid_db).

    excess_db[t] = mean over band bins of max(0, PSD_db - floor_db - margin);
    the floor is per-bin so rain's spectral shape cancels itself. The raw_*
    envelopes are UN-whitened band levels — needed to tell wind buffeting
    (sub-band dominates by tens of dB in absolute power) from thunder, a
    distinction whitened excess erases because it amplifies quiet bins.
    """
    nperseg = max(256, int(cfg.nperseg_s * sr))
    hop = max(64, int(cfg.hop_s * sr))
    if len(y) < nperseg:
        z = np.array([])
        return z, z, z, z, z, z
    f, t, sxx = signal.spectrogram(y, sr, nperseg=nperseg,
                                   noverlap=nperseg - hop, mode="psd")
    db = 10 * np.log10(sxx + 1e-14)
    floor = np.percentile(db, cfg.floor_pct, axis=1, keepdims=True)
    exc = np.maximum(0.0, db - floor - cfg.excess_margin_db)

    def mean_band(arr, lo, hi):
        m = (f >= lo) & (f <= hi)
        return arr[m].mean(axis=0) if m.any() else np.zeros_like(t)

    return (t, mean_band(exc, *BAND), mean_band(exc, *SUB_BAND),
            mean_band(exc, *MID_BAND), mean_band(db, *SUB_BAND),
            mean_band(db, *MID_BAND))


def _extract_events(t, exc, sub, mid, raw_sub, raw_mid, cfg,
                    on_db=None, off_db=None):
    """Hysteresis event extraction from the excess envelope."""
    if not len(t):
        return []
    on_db = cfg.on_db if on_db is None else on_db
    off_db = cfg.off_db if off_db is None else off_db
    events, open_i = [], None
    for i in range(len(t)):
        if open_i is None and exc[i] >= on_db:
            open_i = i
        elif open_i is not None and exc[i] < off_db:
            events.append((open_i, i))
            open_i = None
    if open_i is not None:
        events.append((open_i, len(t) - 1))

    # merge close events (thunder is multi-burst)
    merged = []
    for a, b in events:
        if merged and t[a] - t[merged[-1][1]] < cfg.min_gap_s:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))

    out = []
    hop = t[1] - t[0] if len(t) > 1 else cfg.hop_s
    for a, b in merged:
        seg = exc[a:b + 1]
        if not len(seg):
            continue
        dur = (b - a + 1) * hop
        pk = int(np.argmax(seg))
        peak = float(seg[pk])
        # rise: first crossing of 50% peak -> peak; decay: peak -> last 50%
        half = peak / 2
        above = np.where(seg >= half)[0]
        rise = (pk - above[0]) * hop if len(above) else dur
        decay = (above[-1] - pk) * hop if len(above) else 0.0
        tot = float(sub[a:b + 1].sum() + mid[a:b + 1].sum()) + 1e-9
        out.append(Event(
            onset_s=float(t[a]),
            duration_s=float(dur),
            peak_excess_db=peak,
            mean_excess_db=float(seg.mean()),
            rise_s=float(max(rise, hop)),
            decay_s=float(max(decay, 0.0)),
            mid_fraction=float(mid[a:b + 1].sum() / tot),
            sub_over_mid_db=float(np.mean(raw_sub[a:b + 1] - raw_mid[a:b + 1])),
        ))
    return out


def _score(ev, cfg):
    """Transparent weighted score in [0, 1] — every factor inspectable."""
    s_energy = np.clip(ev.peak_excess_db / 15.0, 0, 1)              # excess strength
    s_dur = np.clip((ev.duration_s - cfg.min_dur_s) / 4.0, 0, 1)    # rumble length
    s_shape = np.clip((ev.decay_s / max(ev.rise_s, 1e-3)) / 4.0, 0, 1)  # asymmetry
    s_band = np.clip(ev.mid_fraction / 0.4, 0, 1)                   # not pure sub-rumble
    return float(0.35 * s_energy + 0.25 * s_dur + 0.2 * s_shape + 0.2 * s_band)


def _gate(ev, cfg, wind_ms=None):
    min_dur = cfg.anchored_min_dur_s if ev.anchored else cfg.min_dur_s
    shape = cfg.anchored_decay_rise_ratio if ev.anchored else cfg.min_decay_rise_ratio
    if ev.duration_s < min_dur:
        return "too short (raindrop/impulse)"
    if ev.duration_s > cfg.max_dur_s:
        return "too long (stationary noise shift)"
    if ev.decay_s / max(ev.rise_s, 1e-3) < shape:
        return "no fast-attack/slow-decay shape"
    if ev.mid_fraction < cfg.min_mid_fraction:
        return "pure sub-60 Hz excess (wind buffeting)"
    if ev.sub_over_mid_db > cfg.extreme_sub_over_mid_db:
        return (f"sub-band dominates by {ev.sub_over_mid_db:.0f} dB raw "
                "(wind buffeting)")
    # distant thunder is legitimately sub-heavy, so the tighter dominance gate
    # applies only when the node measures wind, or blind in standalone mode
    windy = (wind_ms is not None and wind_ms > cfg.windy_ms) or \
            (wind_ms is None and not ev.anchored)
    if windy and ev.sub_over_mid_db > cfg.windy_sub_over_mid_db:
        return (f"sub-band dominates by {ev.sub_over_mid_db:.0f} dB raw "
                f"({'windy' if wind_ms is not None else 'wind unknown'})")
    return ""


def anchor_windows(anchors, cfg=Config()):
    """[(w_lo, w_hi, t_flash, expected_range_km|None)] listening windows.

    `anchors` items are clip-relative flash times, either bare floats or
    (time_s, expected_range_km) when the anchor's distance is known (GLM
    gives one) — known distance enables the range-consistency gate.
    """
    c = 343.0 + 0.6 * (cfg.temp_c - 20.0)
    lo, hi = cfg.r_min_km * 1000 / c, cfg.r_max_km * 1000 / c
    out = []
    for a in anchors:
        tf, rng = a if isinstance(a, (tuple, list)) else (a, None)
        out.append((tf + lo, tf + hi, tf, rng))
    return out


def detect(y, sr, anchor_times_s=None, cfg=Config(), wind_ms=None):
    """Run detection on one clip.

    anchor_times_s: flash times relative to clip start (may be negative —
    thunder from a flash before the clip can still arrive inside it). Items
    are floats, or (time_s, expected_range_km) tuples when the anchor's
    distance is known — then arrivals must also be range-consistent.
    wind_ms: optional wind speed (m/s) at clip time; > 8 m/s tightens gates
    (the M1 wind veto, kept as a hook).

    Returns list[Event]; ev.passed marks accepted candidates.
    """
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=1)
    t, exc, sub, mid, raw_sub, raw_mid = band_excess(y, sr, cfg)
    events = _extract_events(t, exc, sub, mid, raw_sub, raw_mid, cfg)
    windows = anchor_windows(anchor_times_s, cfg) if anchor_times_s is not None else []

    # Second, more sensitive extraction pass INSIDE anchor windows — but only
    # windows whose anchor carries a known range (GLM/Xweather): the lower
    # threshold is justified by the range-consistency gate that will prune
    # what it surfaces. Time-only anchors (camera flash) get no sensitivity
    # boost, because nothing downstream could veto the extra weak events.
    if windows:
        in_ranged = lambda ts: any(  # noqa: E731
            w[0] <= ts <= w[1] and w[3] is not None for w in windows)
        sensitive = _extract_events(t, exc, sub, mid, raw_sub, raw_mid, cfg,
                                    on_db=cfg.anchored_on_db,
                                    off_db=cfg.anchored_off_db)
        known = [e.onset_s for e in events]
        for ev in sensitive:
            if in_ranged(ev.onset_s) and not any(abs(ev.onset_s - k) < 1.0 for k in known):
                events.append(ev)
        events.sort(key=lambda e: e.onset_s)
    c = 343.0 + 0.6 * (cfg.temp_c - 20.0)

    for ev in events:
        ev.score = _score(ev, cfg)
        # match to the anchor whose expected range best agrees (if known)
        best = None
        for w_lo, w_hi, tf, exp_rng in windows:
            if not (w_lo <= ev.onset_s <= w_hi):
                continue
            implied = (ev.onset_s - tf) * c / 1000.0
            miss = abs(implied - exp_rng) if exp_rng is not None else 0.0
            if best is None or miss < best[0]:
                best = (miss, tf, implied, exp_rng)
        if best is not None:
            ev.anchored = True
            ev.anchor_time_s = best[1]
            ev.implied_range_km = best[2]
        reason = _gate(ev, cfg, wind_ms)
        if (not reason and best is not None and best[3] is not None
                and best[0] > cfg.range_tol_km):
            reason = (f"range-inconsistent: implied {best[2]:.1f} km vs "
                      f"anchor's {best[3]:.1f} km (Δ{best[0]:.1f} > "
                      f"{cfg.range_tol_km:.0f} km tol)")
        threshold = cfg.anchored_score if ev.anchored else cfg.standalone_score
        if not reason and ev.score < threshold:
            reason = f"score {ev.score:.2f} < {threshold:.2f}"
        ev.reject_reason = reason
        ev.passed = reason == ""
    return events


def clip_max_score(events):
    """Clip-level score = best event score (0 when nothing extracted)."""
    return max((e.score for e in events), default=0.0)
