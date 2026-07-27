"""Flash detector tests: synthetic sequences + the demo storm's frames.

Run:  python detectors/tests/test_flash.py
"""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from detectors import flash  # noqa: E402

RNG = np.random.default_rng(11)


def test_synthetic():
    results = []

    # 1. night sequence at 0.5 s cadence, two flashes -> both found, anchors
    t = np.arange(0, 120, 0.5)
    x = 12 + RNG.normal(0, 1.0, len(t))
    x[100] = 95   # t=50 s
    x[190] = 140  # t=95 s
    ev = flash.detect_flashes(t, x)
    ok = (len(ev) == 2 and all(not e.sparse_cadence and not e.daytime for e in ev)
          and abs(ev[0].time_epoch - 50.0) < 0.01
          and all(e.timing_sigma_s <= 0.5 for e in ev))
    print(f"{'OK ' if ok else 'FAIL'} night 0.5s cadence: {len(ev)} events, "
          f"sigma={ev[0].timing_sigma_s if ev else '-'}s")
    results.append(ok)

    # 2. dawn ramp, no flash -> no events (edge-replicated baseline)
    ramp = np.linspace(10, 120, 80) + RNG.normal(0, 0.5, 80)
    ev = flash.detect_flashes(np.arange(80.0), ramp)
    print(f"{'OK ' if not ev else 'FAIL'} dawn ramp: {len(ev)} events")
    results.append(not ev)

    # 3. snapshot cadence (5 min): flash frame still a timed anchor, but the
    #    sequence is flagged sparse (absence proves nothing at this duty cycle)
    t = np.arange(0, 3600, 300.0)
    x = 14 + RNG.normal(0, 1.0, len(t))
    x[6] = 90
    ev = flash.detect_flashes(t, x)
    ok = len(ev) == 1 and ev[0].sparse_cadence and ev[0].timing_sigma_s <= 0.5
    print(f"{'OK ' if ok else 'FAIL'} snapshot cadence: flagged={len(ev)}, "
          f"sparse={ev[0].sparse_cadence if ev else '-'}, "
          f"sigma={ev[0].timing_sigma_s if ev else '-'}s")
    results.append(ok)

    # 4. daytime flag: bright baseline
    t = np.arange(0, 60, 0.5)
    x = 150 + RNG.normal(0, 1.5, len(t))
    x[60] = 200
    ev = flash.detect_flashes(t, x)
    ok = len(ev) >= 1 and ev[0].daytime
    print(f"{'OK ' if ok else 'FAIL'} daytime flag: {ev[0].daytime if ev else '-'}")
    results.append(ok)

    # 5. fisheye azimuth: bright wedge east of center
    h = w = 200
    base = np.full((h, w), 15.0)
    lit = base.copy()
    yy, xx = np.mgrid[0:h, 0:w]
    ang = (np.degrees(np.arctan2(xx - w / 2, -(yy - h / 2)))) % 360
    lit[(ang > 60) & (ang < 120)] += 120  # east-ish wedge
    sector, deg = flash.fisheye_azimuth_sector(lit, base, n_sectors=8)
    ok = 60 <= deg <= 120
    print(f"{'OK ' if ok else 'FAIL'} fisheye azimuth: sector {sector} "
          f"({deg:.0f} deg, expect ~90)")
    results.append(ok)

    return results


def test_demo_storm():
    """Validate on the synthetic storm: every truth strike's triggered frame
    detected at storm-mode cadence, zero false alarms on cadence frames."""
    import json

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "dashboard"))
    man_path = (pathlib.Path(__file__).resolve().parents[2]
                / "data" / "demo" / "manifest.json")
    if not man_path.exists():
        print("SKIP demo storm (generate via dashboard demo mode first)")
        return []
    man = json.loads(man_path.read_text())
    import datetime

    def epoch(s):
        return datetime.datetime.fromisoformat(s).timestamp()

    truth = [epoch(s["time"]) for s in man["strikes"]]
    results = []
    for node in man["nodes"][:3]:
        frames = sorted(
            (epoch(m["timestamp"]), m["path"]) for m in man["media"]
            if m["vsn"] == node["vsn"] and m["task"] == "storm-cam")
        times = [t for t, _ in frames]
        lumas = [flash.frame_luma(p) for _, p in frames]
        ev = flash.detect_flashes(times, lumas)
        hits = sum(any(abs(e.time_epoch - (ts + 0.2)) < 1.0 for e in ev)
                   for ts in truth)
        extra = len(ev) - hits
        ok = hits == len(truth) and extra == 0
        print(f"{'OK ' if ok else 'FAIL'} demo {node['vsn']}: {hits}/{len(truth)} "
              f"strikes detected, {extra} extra")
        results.append(ok)
        if ok and results.count(True) == 1:
            errs = [min(abs(e.time_epoch - (ts + 0.2)) for ts in truth)
                    for e in ev]
            print(f"     timing err max {max(errs):.2f}s "
                  f"(30s cadence + triggered frames)")
    return results


if __name__ == "__main__":
    r = test_synthetic() + test_demo_storm()
    assert all(r), f"{r.count(False)} flash scenario(s) failed"
    print(f"\nALL {len(r)} FLASH SCENARIOS PASS")
