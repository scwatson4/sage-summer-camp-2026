#!/usr/bin/env python3
"""FlashPoint flash-candidate plugin (M2) — the camera half of D1-2,
sibling of plugin-thunder.

The fixed wide/fisheye sky camera is a PHOTOMETER, not a telescope:
lightning lights the whole sky, so a flash registers as a scene-wide
luminance spike whether or not the channel is in frame (plan F1). Loop:
snapshot at --fps for --seconds -> robust-z spike detection over the batch
(detectors.flash) -> publish candidate metadata (~300 bytes) -> upload the
spike frame as evidence. Unflagged frames never leave the node.

Published measurements:
  lightning.flash.candidate       luma jump above the local baseline, per event
  lightning.flash.luma            spike-frame mean luminance (0-255), per event
  lightning.flash.frames_checked  frames in the batch, once per batch
Candidate meta: sparse_cadence (duty-cycle warning: absence proves nothing),
daytime (weak-contrast regime), timing_sigma_s (~±0.5 s anchor regardless of
cadence), azimuth_sector/azimuth_deg (coarse fisheye bearing vs a neighbor
baseline frame, when both are still in the evidence deque).

Offline mode: --input <directory of frames>, sorted by filename; timestamps
come from float-parsable filename stems (epoch seconds) else file mtime.
With no --input and no openable camera (Sage dev blades have none), falls
back to the bundled synthetic demo-frames/ batch once and exits — so a bare
`python3 main.py` is a zero-credential, zero-network smoke test.

Local test (no Sage infra):  PYWAGGLE_LOG_DIR=test-run python3 main.py \
    --input demo-frames
Node test:  sudo pluginctl run --name flash localhost:5000/local/plugin-flash
"""
import argparse
import time
from collections import deque
from pathlib import Path

import numpy as np
from waggle.plugin import Plugin

from detectors import flash

DEMO_DIR = Path(__file__).resolve().parent / "demo-frames"
FRAME_EXTS = {".jpg", ".jpeg", ".png"}
KEEP_FRAMES = 64          # evidence deque length; covers the default 60 s @ 1 fps
EVIDENCE_MAX_SIDE = 640   # kept camera frames are downsampled to bound memory


def frame_time(path):
    """Filename-encoded epoch seconds if the stem parses as float, else mtime."""
    try:
        return float(path.stem)
    except ValueError:
        return path.stat().st_mtime


def load_frame(path):
    """Grayscale float array for azimuth sectoring (PIL; full resolution)."""
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.float32)


def shrink(a, max_side=EVIDENCE_MAX_SIDE):
    """Integer-stride downsample so the evidence deque stays small."""
    step = max(1, -(-max(a.shape[:2]) // max_side))
    return np.ascontiguousarray(a[::step, ::step])


def neighbor_index(i, n, spike_set):
    """Nearest non-spike frame to serve as the azimuth baseline."""
    for j in (i - 1, i + 1, i - 2, i + 2):
        if 0 <= j < n and j not in spike_set:
            return j
    return None


def publish_batch(plugin, events, times, source, get_frame, ts_of):
    """Common publish path for both modes.

    get_frame(i) -> image array (gray or RGB) for azimuth, or None if the
    frame has left the evidence deque; ts_of(e) -> publish timestamp in ns,
    or None to let pywaggle stamp "now" (offline replays: frame epochs are
    synthetic/mtime, so the real frame time rides in meta instead).
    """
    idxs = [int(np.argmin(np.abs(np.asarray(times, float) - e.time_epoch)))
            for e in events]
    spike_set = set(idxs)
    for e, i in zip(events, idxs):
        meta = {"mode": "standalone-candidate",
                "source": source,
                "frame_epoch_s": f"{e.time_epoch:.2f}",
                "sparse_cadence": str(e.sparse_cadence),
                "daytime": str(e.daytime),
                "timing_sigma_s": f"{e.timing_sigma_s:.2f}"}
        j = neighbor_index(i, len(times), spike_set)
        a = get_frame(i)
        b = get_frame(j) if j is not None else None
        if a is not None and b is not None:
            sector, deg = flash.fisheye_azimuth_sector(a, b)
            meta["azimuth_sector"] = str(sector)
            meta["azimuth_deg"] = f"{deg:.1f}"
        plugin.publish("lightning.flash.candidate", float(e.jump),
                       timestamp=ts_of(e), meta=meta)
        plugin.publish("lightning.flash.luma", float(e.luma),
                       timestamp=ts_of(e))
    plugin.publish("lightning.flash.frames_checked", len(times))
    return idxs


def run_offline(plugin, frames_dir, source):
    """One batch over a directory of frames (demo fallback or archive replay)."""
    paths = sorted(p for p in Path(frames_dir).iterdir()
                   if p.suffix.lower() in FRAME_EXTS)
    if not paths:
        raise SystemExit(f"no frames in {frames_dir}")
    times = [frame_time(p) for p in paths]
    lumas = [flash.frame_luma(p) for p in paths]
    events = flash.detect_flashes(times, lumas)
    publish_batch(plugin, events, times, source,
                  get_frame=lambda i: load_frame(paths[i]),
                  ts_of=lambda e: None)
    print(f"{source}: {len(paths)} frames, {len(events)} candidate(s)")
    return events


def run_camera(plugin, args):
    """One snapshot batch from the node camera, then detect + publish +
    upload spike-frame evidence (downsampled RGB from the deque)."""
    from waggle.data.vision import Camera
    n = max(5, int(round(args.seconds * args.fps)))   # detector needs >=5
    period = 1.0 / args.fps
    times, lumas = [], []
    keep = deque(maxlen=KEEP_FRAMES)   # (index, small RGB uint8 frame)
    with Camera(args.camera) as cam:
        t0 = time.monotonic()
        for i in range(n):
            snap = cam.snapshot()
            times.append(snap.timestamp / 1e9)
            lumas.append(flash.frame_luma(snap.data))
            keep.append((i, shrink(np.asarray(snap.data, dtype=np.uint8))))
            lag = t0 + (i + 1) * period - time.monotonic()
            if lag > 0:
                time.sleep(lag)
    events = flash.detect_flashes(times, lumas)
    kept = dict(keep)
    idxs = publish_batch(plugin, events, times, "camera",
                         get_frame=lambda i: kept.get(i),
                         ts_of=lambda e: int(e.time_epoch * 1e9))
    for k, (e, i) in enumerate(zip(events, idxs)):
        if kept.get(i) is None:
            continue
        from PIL import Image
        name = f"candidate_{k}.jpg"
        Image.fromarray(kept[i]).save(name)
        plugin.upload_file(name, timestamp=int(e.time_epoch * 1e9))
    print(f"camera: {len(times)} frames, {len(events)} candidate(s)")
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None,
                    help="directory of image frames for offline mode "
                         "(default: node camera, demo-frames fallback)")
    ap.add_argument("--camera", default=0,
                    type=lambda s: int(s) if s.isdigit() else s,
                    help="camera device: cv2 index, URL, or data-config id")
    ap.add_argument("--fps", type=float, default=1.0,
                    help="snapshot rate within a batch")
    ap.add_argument("--seconds", type=float, default=60.0,
                    help="batch length (camera mode)")
    ap.add_argument("--interval", type=float, default=0.0,
                    help="loop sleep between batches; 0 = single shot")
    args = ap.parse_args()

    with Plugin() as plugin:
        while True:
            if args.input:
                run_offline(plugin, args.input, source="dir")
            else:
                try:
                    run_camera(plugin, args)
                except Exception as exc:   # dev blades: no camera stack
                    print(f"camera unavailable ({exc!r}); "
                          f"running bundled demo batch")
                    run_offline(plugin, DEMO_DIR, source="demo")
                    break   # synthetic smoke test — never loop it into Beehive
            if args.interval <= 0:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
