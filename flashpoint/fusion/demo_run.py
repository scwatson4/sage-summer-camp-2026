"""Run the full detector -> fusion chain on the demo storm and emit the
strike map. This is the D3-4 end-to-end: flash detection on every node's
frames, thunder detection on every clip (camera-anchored), fusion across
nodes, map out.

Run:  python -m fusion demo        (writes fusion/out/strikes.json + map)
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detectors import anchors, flash, thunder  # noqa: E402
from fusion.engine import FusionEngine  # noqa: E402

MAN = ROOT / "data" / "demo" / "manifest.json"
OUT = pathlib.Path(__file__).resolve().parent / "out"


def _epoch(s):
    return datetime.datetime.fromisoformat(s).timestamp()


def node_events(man, vsn, temp_c):
    """One node's frames + clips -> flash/thunder event dicts."""
    events = []
    frames = sorted((_epoch(m["timestamp"]), m["path"]) for m in man["media"]
                    if m["vsn"] == vsn and m["task"] == "storm-cam")
    fl = flash.detect_flashes([t for t, _ in frames],
                              [flash.frame_luma(p) for _, p in frames])
    cam_anchors = flash.anchor_epochs(fl)
    for e in fl:
        if not e.daytime:
            events.append({"type": "flash", "vsn": vsn,
                           "time_epoch": e.time_epoch,
                           "sigma_s": e.timing_sigma_s})
    cfg = thunder.Config(temp_c=temp_c)
    for t_clip, path in sorted((_epoch(m["timestamp"]), m["path"])
                               for m in man["media"]
                               if m["vsn"] == vsn and m["task"] == "storm-audio"):
        y, sr = sf.read(path, dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        rel = anchors.clip_relative(cam_anchors, t_clip, len(y) / sr, cfg)
        for ev in thunder.detect(y, sr, anchor_times_s=rel, cfg=cfg, wind_ms=3.0):
            if ev.passed:
                events.append({"type": "thunder", "vsn": vsn,
                               "time_epoch": t_clip + ev.onset_s,
                               "score": ev.score})
    return events


def run(n_nodes=6, quiet=False):
    man = json.loads(MAN.read_text())
    temp_c = man["temp_c"]
    nodes = {n["vsn"]: (n["lat"], n["lon"]) for n in man["nodes"][:n_nodes]}
    events = []
    for vsn in nodes:
        evs = node_events(man, vsn, temp_c)
        if not quiet:
            nf = sum(1 for e in evs if e["type"] == "flash")
            nt = len(evs) - nf
            print(f"  {vsn}: {nf} flash, {nt} thunder events")
        events.extend(evs)

    engine = FusionEngine(nodes)
    strikes = engine.process(events, temp_c=temp_c)

    truth = [{"time_epoch": _epoch(s["time"]), "lat": s["lat"],
              "lon": s["lon"], "id": s["id"]} for s in man["strikes"]]
    from fp import geo  # noqa: E402  (path set above via detectors import)
    errs = []
    for s in strikes:
        if s.lat is None:
            continue
        d, sid = min((geo.dist_km(s.lat, s.lon, t["lat"], t["lon"]) * 1000,
                      t["id"]) for t in truth)
        errs.append((sid, d, s.quality))
    if not quiet:
        print(f"fused strikes: {len(strikes)} (truth: {len(truth)})")
        for sid, d, q in sorted(errs):
            print(f"  {sid}: err {d:6.0f} m  [{q}]")

    OUT.mkdir(exist_ok=True)
    payload = {
        "generated_from": "replayed test storm, real Argonne node geometry",
        "nodes": [{"vsn": v, "lat": p[0], "lon": p[1]} for v, p in nodes.items()],
        "strikes": [s.to_dict() for s in strikes],
        "truth": truth,
    }
    (OUT / "strikes.json").write_text(json.dumps(payload, indent=1))
    from fusion import strikemap, strikemap_leaflet
    strikemap.render(payload, OUT / "fusion-map.html")            # offline SVG
    strikemap_leaflet.render(payload, OUT / "fusion-map-leaflet.html")  # basemap
    if not quiet:
        print(f"wrote {OUT / 'strikes.json'}, fusion-map.html (offline SVG), "
              "fusion-map-leaflet.html (Leaflet basemap)")
    return strikes, truth, errs
