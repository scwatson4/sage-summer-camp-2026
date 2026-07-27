"""Exercise holdover_smoke_watch against the W097 sim panorama — no
sage-agent install needed: a minimal PIL gateway implements the same calls
the upstream sensor gateway exposes (move/snapshot/detect/caption), cropping
real 60-degree viewports out of panorama A exactly like the upstream sim
(pan 0-360 -> image width; 16:9 viewport).

Verifies: sectors visited highest-risk-first, correct viewport cropped per
bearing, raw frame pairs written, flag plumbing (stubbed detection at the
plume sector flags exactly that sector; no stub -> no flags).

Run:  python agent/tests/test_smoke_watch_sim.py
"""
import json
import pathlib
import sys
import tempfile

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "skills"))

import holdover_smoke_watch as hw  # noqa: E402

PANO = HERE.parents[0] / "sim-panoramas" / "w097-pano-A-day-plume.jpg"
SECTORS = json.loads((HERE.parents[0] / "sim-panoramas" / "sectors.json")
                     .read_text())["w097-pano-A-day-plume"]


class MiniSimGateway:
    """Just enough of the upstream sensor gateway for the skill."""

    def __init__(self, pano_path, outdir, fov_h=60.0,
                 detect_hook=None):
        self.img = Image.open(pano_path)
        self.w, self.h = self.img.size
        self.pan, self.tilt = 180.0, 0.0
        self.fov_h = fov_h
        self.outdir = pathlib.Path(outdir)
        self.detect_hook = detect_hook or (lambda pan: [])
        self.moves = []

    def ptz_move_to(self, pan, tilt):
        self.pan, self.tilt = pan % 360.0, tilt
        self.moves.append(self.pan)
        return json.dumps({"ok": True, "result": {"pan_deg": self.pan}})

    def _viewport(self):
        ppd = self.w / 360.0
        vw = int(self.fov_h * ppd)
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

    def ptz_snapshot(self, filename=None):
        p = self.outdir / (filename or "snap.jpg")
        self._viewport().save(p, quality=85)
        return json.dumps({"ok": True, "result": {"path": str(p)}})

    def ptz_detect(self, model="yolo", targets="*", **kw):
        return json.dumps({"ok": True, "result":
                           {"detections": self.detect_hook(self.pan)}})

    def ptz_caption(self, model="gemma4", prompt=""):
        return json.dumps({"ok": True, "result": {"caption": ""}})


def run_case(detect_hook, sectors):
    with tempfile.TemporaryDirectory() as td:
        gw = MiniSimGateway(PANO, td, detect_hook=detect_hook)
        skill = hw.HoldoverSmokeWatchSkill()
        ctx = hw.SkillContext(args={"sectors": sectors, "dwell_s": 1,
                                    "frame_pair_gap_s": 1}, gateway=gw)
        res = skill.run(ctx)
        frames_exist = all(pathlib.Path(p).exists()
                           for v in res.data["visits"] for p in v["raw_frames"])
        return res, gw, frames_exist


def main():
    ok_all = []
    plume_pan = SECTORS["sectors"][2]["pan_center_deg"]  # 150.0
    sectors = [
        {"bearing_deg": 30.0, "range_km": 5.0, "age_h": 10, "risk": 40},
        {"bearing_deg": plume_pan, "range_km": 2.3, "age_h": 4, "risk": 87},
        {"bearing_deg": 270.0, "range_km": 8.0, "age_h": 30, "risk": 20},
    ]

    # 1. no detections stubbed -> visits all sectors risk-first, flags none
    res, gw, frames = run_case(lambda pan: [], sectors)
    order_ok = gw.moves[0] == plume_pan  # highest risk first
    ok = res.ok and res.data["flagged"] == 0 and frames and order_ok
    print(f"{'OK ' if ok else 'FAIL'} quiet patrol: visits={len(res.data['visits'])} "
          f"flags={res.data['flagged']} risk-first={order_ok} frames={frames}")
    ok_all.append(ok)

    # 2. stub a smoke detection only at the plume sector -> exactly one flag
    def hook(pan):
        return ([{"label": "smoke", "confidence": 0.61}]
                if abs(pan - plume_pan) < 1 else [])
    res, gw, frames = run_case(hook, sectors)
    flagged = [v for v in res.data["visits"] if v["flagged"]]
    ok = (len(flagged) == 1
          and abs(flagged[0]["pan_deg"] - plume_pan) < 1 and frames)
    print(f"{'OK ' if ok else 'FAIL'} plume flag: flagged={len(flagged)} "
          f"at pan={flagged[0]['pan_deg'] if flagged else '-'}")
    ok_all.append(ok)

    # 3. viewport sanity: snapshot at the plume bearing is a bright day scene
    with tempfile.TemporaryDirectory() as td:
        gw = MiniSimGateway(PANO, td)
        gw.ptz_move_to(plume_pan, 0)
        p = json.loads(gw.ptz_snapshot("plume.jpg"))["result"]["path"]
        import numpy as np
        im = np.asarray(Image.open(p).convert("L"), dtype=float)
        ok = im.mean() > 60  # day sector, not canopy-dark or band-blur
        print(f"{'OK ' if ok else 'FAIL'} viewport crop luma={im.mean():.0f}")
        ok_all.append(ok)

    assert all(ok_all), f"{ok_all.count(False)} smoke-watch check(s) failed"
    print(f"\nALL {len(ok_all)} SMOKE-WATCH SIM CHECKS PASS")


if __name__ == "__main__":
    main()
