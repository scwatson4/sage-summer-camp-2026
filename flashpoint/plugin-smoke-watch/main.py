#!/usr/bin/env python3
"""FlashPoint smoke-watch plugin (Tier-3) — 72 h holdover patrol packaged
for Sage nodes.

WHAT THIS IS (honestly): patrol orchestration + a deterministic
change-detection PLACEHOLDER head. SmokeyNet horizon-band tiles are the
planned upgrade; there is no real PTZ driver yet. YOLO-COCO was measured
useless on sky cams (0 relevant detections, live H03E exercise 2026-07-28)
and SmokeyNet is not wired anywhere, so the head here is per-tile mean-luma
abs diff over a before/after dwell pair — real plumbing, placeholder physics.
The RTSP gateway records commanded pan/tilt as METADATA ONLY; it cannot aim
a physical camera.

Loop: sort strike sectors highest-risk-first (the vendored
holdover_smoke_watch skill, unchanged) -> per sector: move (sim crop / rtsp
metadata), before frame, dwell, after frame, tile-diff head -> publish
counts + per-flagged-sector detail, upload the raw frame pair for flagged
sectors only. Raw frames for quiet sectors never leave the node.

Published measurements:
  fire.smokewatch.sectors_visited   count
  fire.smokewatch.flagged           count
  fire.smokewatch.sector.flagged    detections count per flagged sector
                                    (meta: bearing_deg, pan_deg, range_km)

Offline demo (zero credentials/network/camera — the no-args container
smoke test): patrols the bundled W097 panorama, 6 sectors, 0 flags.
Local test:  PYWAGGLE_LOG_DIR=test-run python3 main.py
Flag-path test (SIM ONLY):  ... python3 main.py --sim-inject-plume
Node test:  sudo pluginctl run --name smokewatch \
    localhost:5000/local/plugin-smoke-watch
"""
import argparse
import json
import pathlib
import tempfile
import time

import numpy as np
from PIL import Image
from waggle.plugin import Plugin

from vendored import holdover_smoke_watch as hw
from vendored import strike_sectors

HERE = pathlib.Path(__file__).resolve().parent
SIM_PANO = HERE / "sim-assets" / "panorama.jpg"
SIM_SECTORS = HERE / "sim-assets" / "sectors.json"
GRID = (5, 9)  # SmokeyNet tile-grid convention (NDP workflow preprocessing)
META_HEAD = {"head": "tile-diff-placeholder",
             "note": "deterministic change detection; SmokeyNet upgrade planned"}


def tile_diff(before_path, after_path, band, thresh, grid=GRID):
    """The placeholder detection head: crop the horizon band (fractions of
    image height, SmokeyNet convention), split into a rows x cols grid,
    per-tile mean-luma abs diff between the dwell pair. A hit = a tile whose
    scene changed during the dwell — NOT a smoke classification."""
    a = np.asarray(Image.open(before_path).convert("L"), dtype=float)
    b_im = Image.open(after_path).convert("L")
    if b_im.size != (a.shape[1], a.shape[0]):
        b_im = b_im.resize((a.shape[1], a.shape[0]))
    b = np.asarray(b_im, dtype=float)
    H, W = a.shape
    y0, y1 = int(H * band[0]), int(H * band[1])
    d = np.abs(b[y0:y1] - a[y0:y1])
    rows, cols = grid
    th, tw = (y1 - y0) / rows, W / cols
    dets = []
    for r in range(rows):
        for c in range(cols):
            tile = d[int(r * th):int((r + 1) * th), int(c * tw):int((c + 1) * tw)]
            m = float(tile.mean()) if tile.size else 0.0
            if m > thresh:
                dets.append({"label": "luma-change", "tile": [r, c],
                             "confidence": round(min(m / 255.0, 1.0), 3),
                             "mean_abs_diff": round(m, 1)})
    return dets


class TileDiffGateway:
    """Abstract PTZ gateway speaking the skill's four calls (move/snapshot/
    detect/caption). Subclasses implement _capture(path). The detect head
    compares the two most recent snapshots since the last move; with <2
    frames captured it reports nothing (so the skill's pre-dwell det0 call
    is always quiet). ptz_caption returns "" — no LLM on the node."""

    def __init__(self, outdir, band, tile_thresh):
        self.outdir = pathlib.Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.band, self.tile_thresh = band, tile_thresh
        self.pan, self.tilt = 180.0, 0.0
        self.moves = []
        self._frames = []  # snapshots since last move

    def ptz_move_to(self, pan, tilt):
        self.pan, self.tilt = pan % 360.0, tilt
        self.moves.append(self.pan)
        self._frames = []
        return json.dumps({"ok": True, "result":
                           {"pan_deg": self.pan, "tilt_deg": self.tilt}})

    def ptz_snapshot(self, filename=None):
        p = self.outdir / (filename or "snap.jpg")
        self._capture(p)
        self._frames.append(p)
        return json.dumps({"ok": True, "result": {"path": str(p)}})

    def ptz_detect(self, model="tile-diff", targets="*", **kw):
        if len(self._frames) < 2:
            return json.dumps({"ok": True, "result": {"detections": []}})
        dets = tile_diff(self._frames[-2], self._frames[-1],
                         self.band, self.tile_thresh)
        return json.dumps({"ok": True, "result": {"detections": dets}})

    def ptz_caption(self, model="none", prompt=""):
        return json.dumps({"ok": True, "result": {"caption": ""}})


class SimGateway(TileDiffGateway):
    """Offline demo gateway over the bundled W097 panorama: pan 0-360 maps
    to image width, 16:9 viewport at the given horizontal FOV, wrap-around
    at the seam — the crop logic proven by agent/tests/test_smoke_watch_sim.py.
    Class name MUST start with 'Sim': the skill shortens its dwell sleeps
    for Sim* gateways."""

    def __init__(self, pano_path, outdir, band, tile_thresh, fov_deg=60.0,
                 inject_pan=None):
        super().__init__(outdir, band, tile_thresh)
        self.img = Image.open(pano_path).convert("RGB")
        self.w, self.h = self.img.size
        self.fov_deg = fov_deg
        self.inject_pan = inject_pan  # --sim-inject-plume test hook

    def _viewport(self):
        ppd = self.w / 360.0
        vw = int(self.fov_deg * ppd)
        vh = int(vw * 9 / 16)
        cx = int(self.pan * ppd)
        top = max(0, (self.h - vh) // 2)
        box = self.img.crop((0, top, self.w, top + vh))  # tilt centered
        # pan wraps: paste twice if the window crosses the edge
        x0 = cx - vw // 2
        if x0 < 0 or x0 + vw > self.w:
            doubled = Image.new("RGB", (self.w * 2, box.height))
            doubled.paste(box, (0, 0))
            doubled.paste(box, (self.w, 0))
            return doubled.crop((x0 % self.w, 0, x0 % self.w + vw, box.height))
        return box.crop((x0, 0, x0 + vw, box.height))

    def _capture(self, path):
        im = self._viewport()
        # TEST HOOK (sim only, --sim-inject-plume): brighten a compact blob
        # in the AFTER frame at the known plume sector so exactly one sector
        # exercises the flag path deterministically. Never active on RTSP.
        if (self.inject_pan is not None and len(self._frames) == 1
                and abs((self.pan - self.inject_pan + 180.0) % 360.0 - 180.0) < 1.0):
            im = self._inject_blob(im)
        im.save(path, quality=85)

    def _inject_blob(self, im):
        a = np.asarray(im, dtype=np.int16)
        H, W = a.shape[:2]
        cy = int(H * (self.band[0] + self.band[1]) / 2.0)
        cx = W // 2
        ry, rx = max(6, H // 10), max(12, W // 10)
        yy, xx = np.ogrid[:H, :W]
        mask = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0
        # +-80 luma, direction chosen per-pixel so clipping never eats the
        # delta (a dark plume against bright sky, bright against canopy)
        delta = np.where(a[mask][..., :1] >= 176, -80, 80)
        a[mask] = np.clip(a[mask] + delta, 0, 255)
        return Image.fromarray(a.astype(np.uint8))


class RtspGateway(TileDiffGateway):
    """Real-camera gateway: before/after frames via pywaggle's Camera over
    an RTSP/HTTP URL. NO PTZ DRIVER EXISTS YET — ptz_move_to records the
    commanded pan/tilt as metadata only and cannot aim the camera; the
    detect head watches whatever the camera already points at."""

    def __init__(self, url, outdir, band, tile_thresh):
        super().__init__(outdir, band, tile_thresh)
        from waggle.data.vision import Camera
        self.camera = Camera(url)

    def _capture(self, path):
        self.camera.snapshot().save(str(path))


def parse_band(text):
    lo, hi = (float(v) for v in text.split(","))
    if not (0.0 <= lo < hi <= 1.0):
        raise argparse.ArgumentTypeError("band must be 0 <= lo < hi <= 1")
    return (lo, hi)


def demo_sectors():
    """Bundled offline-demo patrol derived from sim-assets/sectors.json:
    one sector per 60-degree pano slice, bearing == pan center (pan offset
    0). The scrubbed-annotation slice is the real Halemaumau plume (index 2,
    pan 150) — it gets the ignition-risk numbers from the agent sim test;
    the canopy negatives get a descending recency ramp."""
    meta = json.loads(SIM_SECTORS.read_text())["w097-pano-A-day-plume"]
    out = []
    for i, s in enumerate(meta["sectors"]):
        if s.get("annotation_scrubbed"):  # THE positive
            out.append({"bearing_deg": s["pan_center_deg"], "range_km": 2.3,
                        "age_h": 4.0, "risk": 87.0})
        else:
            out.append({"bearing_deg": s["pan_center_deg"],
                        "range_km": 5.0 + i, "age_h": 10.0 + 4 * i,
                        "risk": 40.0 - 4 * i})
    return out


def plume_pan():
    meta = json.loads(SIM_SECTORS.read_text())["w097-pano-A-day-plume"]
    return next(s["pan_center_deg"] for s in meta["sectors"]
                if s.get("annotation_scrubbed"))  # 150.0


def load_sectors(args):
    if args.sectors_file:
        return json.loads(pathlib.Path(args.sectors_file).read_text())
    if args.strikes_file:
        if args.lat is None or args.lon is None:
            raise SystemExit("--strikes-file requires --lat and --lon")
        strikes = json.loads(pathlib.Path(args.strikes_file).read_text())
        return strike_sectors.sectors_for_node(
            args.lat, args.lon, strikes, time.time(),
            max_age_h=args.max_age_h, max_range_km=args.max_range_km)
    return demo_sectors()


def main():
    ap = argparse.ArgumentParser(
        description="FlashPoint 72 h holdover smoke-watch patrol "
                    "(deterministic placeholder head; no real PTZ driver)")
    ap.add_argument("--rtsp-url", default=None,
                    help="camera RTSP/HTTP URL; default = offline sim over "
                         "the bundled W097 panorama")
    ap.add_argument("--sectors-file", default=None,
                    help="JSON [{bearing_deg,range_km,age_h,risk}]")
    ap.add_argument("--strikes-file", default=None,
                    help="JSON [{lat,lon,time_epoch[,risk]}] -> sectors via "
                         "strike_sectors (needs --lat/--lon)")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--max-age-h", type=float, default=72.0,
                    help="holdover watch window for --strikes-file")
    ap.add_argument("--max-range-km", type=float, default=30.0)
    ap.add_argument("--dwell-s", type=float, default=2.0,
                    help="per-sector dwell (sim-short default; use ~180 on "
                         "a real camera — SmokeyNet wants steady minutes)")
    ap.add_argument("--frame-pair-gap-s", type=float, default=1.0,
                    help="before->after gap (use ~120 on a real camera)")
    ap.add_argument("--tilt-deg", type=float, default=0.0)
    ap.add_argument("--pan-offset-deg", type=float, default=0.0,
                    help="pan reading when the camera faces true north")
    ap.add_argument("--band-frac", type=parse_band, default=(0.25, 0.65),
                    help="horizon band as height fractions lo,hi (SmokeyNet "
                         "middle-band convention; default 0.25,0.65)")
    ap.add_argument("--tile-thresh", type=float, default=12.0,
                    help="per-tile mean-luma abs-diff flag threshold")
    ap.add_argument("--fov-deg", type=float, default=60.0,
                    help="sim viewport horizontal FOV")
    ap.add_argument("--frames-dir", default=None,
                    help="where snapshots land (default: fresh temp dir)")
    ap.add_argument("--sim-inject-plume", action="store_true",
                    help="TEST HOOK, sim only: brighten a blob in the AFTER "
                         "frame at the known plume sector (pan 150) so "
                         "exactly one sector flags")
    args = ap.parse_args()

    sectors = load_sectors(args)
    frames_dir = args.frames_dir or tempfile.mkdtemp(prefix="smokewatch-")
    if args.rtsp_url:
        gw = RtspGateway(args.rtsp_url, frames_dir,
                         args.band_frac, args.tile_thresh)
    else:
        gw = SimGateway(SIM_PANO, frames_dir, args.band_frac,
                        args.tile_thresh, fov_deg=args.fov_deg,
                        inject_pan=plume_pan() if args.sim_inject_plume
                        else None)

    skill = hw.HoldoverSmokeWatchSkill()
    ctx = hw.SkillContext(args={"sectors": sectors,
                                "dwell_s": args.dwell_s,
                                "frame_pair_gap_s": args.frame_pair_gap_s,
                                "tilt_deg": args.tilt_deg,
                                "pan_offset_deg": args.pan_offset_deg},
                          gateway=gw)
    res = skill.run(ctx)
    if not res.ok:
        raise SystemExit(f"patrol failed: {res.summary}")

    visits = res.data.get("visits", [])
    flagged = [v for v in visits if v["flagged"]]
    with Plugin() as plugin:
        plugin.publish("fire.smokewatch.sectors_visited", len(visits),
                       meta=META_HEAD)
        plugin.publish("fire.smokewatch.flagged", len(flagged),
                       meta=META_HEAD)
        for v in flagged:
            s = v["sector"]
            meta = {"bearing_deg": f"{float(s['bearing_deg']):.1f}",
                    "pan_deg": f"{float(v['pan_deg']):.1f}",
                    "range_km": f"{float(s.get('range_km', 0.0)):.2f}",
                    **META_HEAD}
            plugin.publish("fire.smokewatch.sector.flagged",
                           int(v["detections"]), meta=meta)
            # evidence rule: RAW frames only, flagged sectors only
            for role, p in zip(("before", "after"), v["raw_frames"]):
                if p and pathlib.Path(p).exists():
                    plugin.upload_file(p, meta={"frame": role, **meta},
                                       keep=True)
    print(f"{res.summary} (frames in {frames_dir})")


if __name__ == "__main__":
    main()
