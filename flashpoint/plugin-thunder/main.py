#!/usr/bin/env python3
"""FlashPoint thunder-candidate plugin (M2) — fork-of-spirit of
sound-event-detection, built on the D1-2 noise-adaptive detector.

Loop: record a clip from the node microphone -> run detectors.thunder in
STANDALONE mode (candidates only, per the M1 contract) -> publish event
metadata (~300 bytes) -> upload the flagged clip as evidence. Raw audio for
unflagged clips never leaves the node.

Published measurements:
  lightning.thunder.candidate   score (0-1) per passed event
  lightning.thunder.onset_s     onset within the clip
  lightning.thunder.excess_db   peak whitened excess
Meta: duration_s, reject_stats. Anchored mode arrives with the storm-mode
controller feed (GLM/Xweather/flash anchor file -> anchor_times_s).

Local test (no Sage infra):  PYWAGGLE_LOG_DIR=test-run python3 main.py \
    --input ../data/kitten_clips/2025-07-02_221600.flac
Node test:  sudo pluginctl run --name thunder localhost:5000/local/plugin-thunder
"""
import argparse
import time

from waggle.plugin import Plugin

from detectors import thunder


def clip_from_file(path):
    import soundfile as sf
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y, sr, None


def clip_from_mic(seconds):
    from waggle.data.audio import Microphone
    sample = Microphone().record(seconds)
    y = sample.data
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y, sample.samplerate, sample.timestamp


def process(plugin, y, sr, timestamp, wind_ms=None):
    events = thunder.detect(y, sr, cfg=thunder.Config(), wind_ms=wind_ms)
    passed = [e for e in events if e.passed]
    for e in passed:
        meta = {"duration_s": f"{e.duration_s:.2f}",
                "mode": "standalone-candidate"}
        plugin.publish("lightning.thunder.candidate", float(e.score),
                       timestamp=timestamp, meta=meta)
        plugin.publish("lightning.thunder.onset_s", float(e.onset_s),
                       timestamp=timestamp)
        plugin.publish("lightning.thunder.excess_db", float(e.peak_excess_db),
                       timestamp=timestamp)
    return events, passed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None,
                    help="audio file for local testing (default: node mic)")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--interval", type=float, default=0.0,
                    help="loop sleep between clips; 0 = single shot")
    args = ap.parse_args()

    with Plugin() as plugin:
        while True:
            if args.input:
                y, sr, ts = clip_from_file(args.input)
            else:
                y, sr, ts = clip_from_mic(args.seconds)
            events, passed = process(plugin, y, sr, ts)
            plugin.publish("lightning.thunder.events_checked", len(events),
                           timestamp=ts)
            if passed and not args.input:
                import soundfile as sf
                sf.write("candidate.flac", y, sr)
                plugin.upload_file("candidate.flac", timestamp=ts)
            if args.interval <= 0:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
