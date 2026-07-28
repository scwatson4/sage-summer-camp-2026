#!/usr/bin/env python3
"""live_evidence_demo.py — agent-ladder stage 2: real fleet frames through the
local perception heads, packaged with agent/evidence.py. No actuation.

For one node: list the freshest `imagesampler-top` uploads (public query API),
download the raw frames (SAGE_USER/SAGE_TOKEN basic auth), run YOLO
(ultralytics yolo11n) and the gemma4 caption head (Ollama, pinned sampling per
agent/README.md), then build the evidence set with evidence.annotate_boxes /
before_after / contact_sheet — raw frames stay byte-identical (the W097
rule); everything derived lands under the pack directory.

  <out>/<vsn>/raw/<utc>.jpg
  <out>/<vsn>/derived/...-annotated.jpg, before-after.jpg, strip.jpg
  <out>/<vsn>/manifest.json   (provenance "live", perception test — NOT an alert)

Run inside the sage-agent venv (has ultralytics + sage-data-client):
  .venv/bin/python flashpoint/agent/live_evidence_demo.py --vsn W09E
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import evidence  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
CAPTION_PROMPT = (
    "Is there a rising smoke PLUME (a column from a point source) anywhere in "
    "this scene, as opposed to diffuse haze, fog, or cloud? Answer "
    "plume/haze/none first, then one sentence describing the scene.")


def creds():
    user = os.environ.get("SAGE_USER", "")
    token = os.environ.get("SAGE_TOKEN", "")
    envf = ROOT / ".env"
    if (not user or not token) and envf.exists():
        for line in envf.read_text().splitlines():
            m = re.match(r"^\s*(?:export\s+)?(SAGE_USER|SAGE_TOKEN)\s*=\s*(.+?)\s*$", line)
            if m:
                if m.group(1) == "SAGE_USER" and not user:
                    user = m.group(2)
                if m.group(1) == "SAGE_TOKEN" and not token:
                    token = m.group(2)
    if not (user and token):
        sys.exit("need SAGE_USER/SAGE_TOKEN (env or flashpoint/.env)")
    return user, token


def latest_uploads(vsn, task, n, window="-24h"):
    import sage_data_client

    df = sage_data_client.query(start=window,
                                filter={"name": "upload", "vsn": vsn, "task": task})
    if not len(df):
        sys.exit(f"no {task} uploads from {vsn} in {window}")
    df = df.sort_values("timestamp").tail(n)
    return [(row["timestamp"], row["value"]) for _, row in df.iterrows()]


def fetch(url, tok, dest):
    if not url.startswith("https://storage.sagecontinuum.org/"):
        raise ValueError("non-storage url refused")
    req = urllib.request.Request(url, headers={
        "Authorization": "Basic " + base64.b64encode(tok.encode()).decode(),
        "User-Agent": "flashpoint-evidence"})
    with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
        f.write(r.read())


def yolo_detect(path):
    from ultralytics import YOLO

    t0 = time.time()
    res = YOLO("yolo11n").predict(str(path), verbose=False)[0]
    dets = [{"label": res.names[int(b.cls)],
             "confidence": round(float(b.conf), 3),
             "box": [round(float(v), 1) for v in b.xyxy[0]]}
            for b in res.boxes]
    return dets, round(time.time() - t0, 2)


def caption(path):
    model = os.environ.get("GEMMA4_OLLAMA_MODEL", "gemma4:31b")
    img = base64.b64encode(open(path, "rb").read()).decode()
    payload = {"model": model, "stream": False,
               "messages": [{"role": "user", "content": CAPTION_PROMPT,
                             "images": [img]}],
               "options": {
                   "temperature": float(os.environ.get("GEMMA4_TEMPERATURE", "0")),
                   "num_predict": int(os.environ.get("GEMMA4_MAX_NEW_TOKENS", "2048"))}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=900))
    return (((r.get("message") or {}).get("content") or "").strip(),
            round(time.time() - t0, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vsn", required=True)
    ap.add_argument("--task", default="imagesampler-top")
    ap.add_argument("--frames", type=int, default=2)
    ap.add_argument("--out", default=str(ROOT / "data" / "evidence-demo-live"))
    args = ap.parse_args()

    user, token = creds()
    tok = f"{user}:{token}"
    node_dir = pathlib.Path(args.out) / args.vsn
    raw_dir, der_dir = node_dir / "raw", node_dir / "derived"
    raw_dir.mkdir(parents=True, exist_ok=True)
    der_dir.mkdir(parents=True, exist_ok=True)

    frames, raw_paths = [], []
    for ts, url in latest_uploads(args.vsn, args.task, args.frames):
        stamp = str(ts)[:19].replace(":", "").replace(" ", "_")
        raw = raw_dir / f"{stamp}.jpg"
        if not raw.exists():
            fetch(url, tok, raw)
        raw_paths.append(raw)

        dets, det_lat = yolo_detect(raw)
        ann = evidence.annotate_boxes(
            raw, dets, out_path=der_dir / f"{stamp}-annotated.jpg",
            title=f"{args.vsn} {args.task} {stamp} · perception test")
        cap, cap_lat = caption(raw)
        frames.append({"utc": str(ts), "storage_url": url,
                       "raw": str(raw.relative_to(node_dir)),
                       "yolo": {"detections": dets, "latency_s": det_lat},
                       "gemma4": {"caption": cap, "latency_s": cap_lat},
                       "annotated": str(pathlib.Path(ann).relative_to(node_dir))})
        print(f"  {args.vsn} {stamp}: {len(dets)} dets ({det_lat}s), "
              f"caption {cap_lat}s: {cap[:70]!r}")

    extras = {}
    if len(raw_paths) >= 2:
        gap = (frames[-1]["utc"], frames[0]["utc"])
        gap_s = abs((__import__("datetime").datetime.fromisoformat(gap[0])
                     - __import__("datetime").datetime.fromisoformat(gap[1])
                     ).total_seconds())
        extras["before_after"] = evidence.before_after(
            raw_paths[0], raw_paths[1], der_dir / "before-after.jpg", gap_s=gap_s)
        extras["strip"] = evidence.contact_sheet(
            [str(p) for p in raw_paths] + [str(node_dir / frames[0]["annotated"])],
            der_dir / "strip.jpg",
            captions=[f"raw {f['utc'][11:16]}Z" for f in frames] + ["detector view"],
            title=f"{args.vsn} {args.task} · live perception test")

    manifest = {"vsn": args.vsn, "provenance": "live",
                "purpose": "perception test — NOT an alert",
                "task_filter": args.task, "frames": frames,
                "derived": {k: str(pathlib.Path(v).relative_to(node_dir))
                            for k, v in extras.items()},
                "raw_rule": "raw/ byte-identical to node uploads; annotations "
                            "only under derived/ (the W097 rule)"}
    (node_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"pack -> {node_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
