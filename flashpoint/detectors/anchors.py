"""Anchor sources for anchored listening: known lightning times that open
thunder-arrival windows (flash + [r_min, r_max]/c).

Sources, in the order the storm-mode controller will use them:
- GLM satellite flashes (retrospective / near-real-time; data/kitten_glm.json
  for the M1 case, GOES AWS buckets live)
- Xweather `lightning` live strikes (scripts/xweather_lightning.py)
- on-node camera flash detections (the D1 flash detector, when it lands)

All functions return UTC epoch seconds; clip_relative() converts to a clip's
timeline for detectors.thunder.detect(anchor_times_s=...).
"""
import datetime
import json
import pathlib

KITTEN_JSON = pathlib.Path(__file__).resolve().parent / "data" / "kitten_glm.json"


def _epoch(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def load_kitten_truth(path=KITTEN_JSON):
    """The M1 ground-truth set: (glm_flash_epochs, arrivals, node, fire)."""
    d = json.loads(pathlib.Path(path).read_text())
    flashes = [{"epoch": _epoch(f["time"]), **f} for f in d["glm_flashes"]]
    arrivals = [{"epoch": _epoch(a["time"]), **a} for a in d["thunder_arrivals"]]
    return flashes, arrivals, d["node"], d["fire"]


def glm_anchor_epochs(flashes, max_dist_km=30.0):
    """Flash times worth listening for: close enough that thunder can arrive."""
    return sorted(f["epoch"] for f in flashes if f["dist_node_km"] <= max_dist_km)


def dedupe_epochs(epochs, min_sep_s=1.0):
    """GLM resolves a storm into many flashes; collapse near-simultaneous ones
    (their listening windows overlap almost entirely anyway). Items may be
    bare epochs or (epoch, range_km) — the KEPT flash's range survives, and
    among near-simultaneous flashes the NEAREST one is kept (its thunder is
    the loudest arrival and the one worth range-gating against)."""
    items = [a if isinstance(a, (tuple, list)) else (a, None) for a in epochs]
    items.sort(key=lambda x: x[0])
    out = []
    for e, rng in items:
        if out and e - out[-1][0] < min_sep_s:
            if rng is not None and (out[-1][1] is None or rng < out[-1][1]):
                out[-1] = (out[-1][0], rng)  # keep earliest time, nearest range
            continue
        out.append((e, rng))
    if any(r is not None for _, r in out):
        return [(e, r) for e, r in out]
    return [e for e, _ in out]


def clip_relative(anchor_epochs, clip_start_epoch, clip_dur_s, cfg=None):
    """Anchor times relative to one clip's start, keeping only anchors whose
    listening window can intersect the clip (flash may precede the clip).

    Items may be bare epochs or (epoch, expected_range_km) — the range rides
    along so detectors.thunder can apply its range-consistency gate.
    """
    from . import thunder
    c = thunder.Config() if cfg is None else cfg
    speed = 343.0 + 0.6 * (c.temp_c - 20.0)
    d_lo = c.r_min_km * 1000 / speed
    d_hi = c.r_max_km * 1000 / speed
    rel = []
    for a in anchor_epochs:
        e, rng = a if isinstance(a, (tuple, list)) else (a, None)
        t = e - clip_start_epoch
        if t + d_hi >= 0 and t + d_lo <= clip_dur_s:
            rel.append(t if rng is None else (t, rng))
    return rel


def xweather_anchor_epochs(response):
    """Epochs from an Xweather `lightning` API response (see
    scripts/xweather_lightning.py live_strikes())."""
    out = []
    for ob in response.get("response") or []:
        ts = ob.get("ob", {}).get("timestamp") or ob.get("timestamp")
        if ts is not None:
            out.append(float(ts))
    return sorted(out)
