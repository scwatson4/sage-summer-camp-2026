"""Flash detection on sky-camera frame sequences (the other half of D1-2).

The flash sensor is the fixed wide/fisheye "top" camera used as a PHOTOMETER,
not a telescope: lightning illuminates the whole sky, so a flash registers as
a scene-wide luminance spike whether or not the channel is in frame (plan
F1). No aiming is involved anywhere; the PTZ plays no role here.

Timing physics: a lit frame means the flash occurred within roughly one
flash duration BEFORE the frame timestamp (the sky is only lit while the
flash burns, ~0.2-1 s), so a DETECTED flash is a ~±0.5 s time anchor
regardless of frame cadence — that propagates to ~±170 m of range, always
tolerable next to thunder-onset error. What sparse cadence costs instead is
CATCH PROBABILITY: at one frame per 5 minutes the camera is "looking" a
fraction of a percent of the time, so most flashes fall between frames
(the M1 snapshot-archive lesson). Events from sparse sequences are flagged
`sparse_cadence` — meaning "absence of events proves nothing", not "this
event is badly timed". Downstream, every anchor still has to earn its keep
through thunder pairing and range consistency.

Fisheye azimuth: the brightest angular sector around the image center gives
a coarse flash bearing (sector index; calibration to true north is per-node).
"""
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

SPARSE_CADENCE_S = 3.0   # wider frame spacing than this misses most flashes
FLASH_DURATION_S = 0.6   # typical multi-stroke flash envelope
DAY_LUMA = 90.0  # baseline mean-luma above this = daytime (weak flash contrast)


@dataclass
class FlashEvent:
    time_epoch: float          # frame timestamp (s)
    luma: float                # frame mean luminance (0-255)
    baseline: float            # local rolling baseline it spiked above
    jump: float                # luma - baseline
    timing_sigma_s: float      # ~flash-duration envelope + trigger latency
    sparse_cadence: bool       # sequence misses most flashes (duty cycle)
    daytime: bool              # weak-contrast regime; treat with suspicion
    azimuth_sector: int | None = None   # brightest fisheye sector (0..n-1)
    azimuth_deg: float | None = None    # sector center, degrees CW from sensor "up"


def frame_luma(img, thumb=96):
    """Mean luminance of an image array (HxW or HxWx3) or a file path."""
    if isinstance(img, (str, bytes)) or hasattr(img, "__fspath__"):
        from PIL import Image
        with Image.open(img) as im:
            im = im.convert("L")
            im.thumbnail((thumb, thumb))
            return float(np.asarray(im, dtype=np.float32).mean())
    a = np.asarray(img, dtype=np.float32)
    if a.ndim == 3:
        a = a.mean(axis=2)
    return float(a.mean())


def luma_spikes(lumas, z_thresh=4.0, min_jump=8.0):
    """Robust-z spikes in a luminance series -> indices. Edge-replicated
    rolling-median baseline (dawn/brightening ramps don't false-flag); same
    logic validated in the dashboard's flash-candidate marking."""
    x = np.asarray(lumas, float)
    if len(x) < 5:
        return []
    k = min(7, len(x) if len(x) % 2 else len(x) - 1)
    baseline = ndimage.median_filter(x, size=k, mode="nearest")
    d = x - baseline
    mad = np.median(np.abs(d - np.median(d))) + 1e-12
    z = 0.6745 * (d - np.median(d)) / mad
    return [int(i) for i in np.where((z > z_thresh) & (d > min_jump))[0]]


def fisheye_azimuth_sector(img, baseline_img, n_sectors=8):
    """Brightest angular sector of the frame-minus-baseline difference.

    For an upward fisheye, image angle around the center maps to compass
    azimuth (up to a fixed per-node rotation). Returns (sector, center_deg).
    """
    a = np.asarray(img, dtype=np.float32)
    b = np.asarray(baseline_img, dtype=np.float32)
    if a.ndim == 3:
        a = a.mean(axis=2)
    if b.ndim == 3:
        b = b.mean(axis=2)
    d = a - b
    h, w = d.shape
    yy, xx = np.mgrid[0:h, 0:w]
    ang = (np.degrees(np.arctan2(xx - w / 2, -(yy - h / 2)))) % 360.0
    sums = np.zeros(n_sectors)
    step = 360.0 / n_sectors
    for k in range(n_sectors):
        m = (ang >= k * step) & (ang < (k + 1) * step)
        sums[k] = d[m].mean() if m.any() else 0.0
    best = int(np.argmax(sums))
    return best, (best + 0.5) * step


def detect_flashes(times, lumas, z_thresh=4.0, min_jump=8.0,
                   trigger_latency_s=0.2):
    """Scene-wide luminance spikes in a frame sequence -> [FlashEvent].

    times: frame epochs (s), ascending. lumas: mean luminance per frame
    (precompute with frame_luma; keeps IO out of the detector).

    Uses the same robust-z spike logic proven in the dashboard
    (analysis.flash_candidates: rolling-median baseline, MAD z-score, edge-
    replicated so dawn ramps don't false-flag).
    """
    t = np.asarray(times, dtype=float)
    x = np.asarray(lumas, dtype=float)
    if len(t) != len(x):
        raise ValueError("times and lumas must align")
    idx = luma_spikes(x, z_thresh=z_thresh, min_jump=min_jump)
    events = []
    for i in idx:
        left = t[i] - t[i - 1] if i > 0 else np.inf
        right = t[i + 1] - t[i] if i + 1 < len(t) else np.inf
        interval = min(left, right)
        # local baseline: median of up to 5 neighbors outside the spike
        lo, hi = max(0, i - 3), min(len(x), i + 4)
        neigh = np.delete(x[lo:hi], i - lo)
        base = float(np.median(neigh)) if len(neigh) else float(x[i])
        events.append(FlashEvent(
            time_epoch=float(t[i]),
            luma=float(x[i]),
            baseline=base,
            jump=float(x[i] - base),
            timing_sigma_s=float(FLASH_DURATION_S / 2 + trigger_latency_s),
            sparse_cadence=bool(interval > SPARSE_CADENCE_S),
            daytime=bool(base > DAY_LUMA),
        ))
    return events


def anchor_epochs(events, include_daytime=False):
    """Flash times ready for detectors.anchors.clip_relative (no range —
    the camera gives time-zero, thunder gives the range). Daytime spikes are
    excluded by default: weak contrast makes them the least trustworthy, and
    they can re-enter once satellite/RF corroboration exists."""
    return sorted(e.time_epoch for e in events
                  if include_daytime or not e.daytime)
