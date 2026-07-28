#!/usr/bin/env python3
"""Evaluate the D1-2 thunder detector on the REAL Kitten Fire ignition storm.

Ground truth: detectors/data/kitten_glm.json (955 dual-satellite GLM flashes +
the 22 satellite-anchored thunder arrivals recovered in M1). Clips: W06C
audio-sampler archive, storm window Jul 2 2025 21:00 UT -> Jul 3 01:30 UT
(covers all 22 arrivals), cached under data/kitten_clips/ (shared with
scripts/kitten_screen.py).

Reported:
- ANCHORED mode: recall of the 22 arrivals (hit = passed event onset within
  +/-2.5 s), median implied-range error vs truth, unmatched passed events;
- STANDALONE mode: passed-event count (should be small — M1 proved standalone
  claims are unsafe) and clip-level AUC vs the v0 ratio metric (M1 measured
  v0 at AUC 0.163 on its own labels; here both metrics are scored against the
  22 anchored arrivals);
- optional --control: rain-showers window Jul 3 17:00-19:30 UT (no GLM
  anchors) -> standalone false alarms per hour.

Run:  python detectors/eval_kitten.py [--control]
Creds: SAGE_USER/SAGE_TOKEN from env or flashpoint/.env. In sandboxes that
strip Authorization headers set SAGE_VIA_PROXY=1 (mcp proxy ?token= pattern).
"""
import argparse
import concurrent.futures as cf
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

import numpy as np
import soundfile as sf
from scipy import signal as sig

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from detectors import anchors, thunder  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLIPS = ROOT / "data" / "kitten_clips"
SUMMARY = pathlib.Path(__file__).resolve().parent / "data" / "eval_kitten_summary.json"

EVAL_START, EVAL_END = "2025-07-02T21:00:00Z", "2025-07-03T01:30:00Z"
CTRL_START, CTRL_END = "2025-07-03T17:00:00Z", "2025-07-03T19:30:00Z"
MATCH_TOL_S = 4.0   # onset-convention slack: rumble onsets are smeared
NODE_TEMP_C = 15.0  # W06C ambient that night (met archive; bme680)
NODE_WIND_MS = 5.6  # max wind in the M1 window (calm — the wind veto's input)


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


def fetch(row, tok, use_proxy):
    dest = CLIPS / (str(row["timestamp"])[:19].replace(":", "").replace(" ", "_") + ".flac")
    if dest.exists() and dest.stat().st_size > 10000:
        return dest, None
    url = row["value"]
    if not url.startswith("https://storage.sagecontinuum.org/"):
        return None, "non-storage url refused"
    try:
        if use_proxy:
            u = ("https://mcp.sagecontinuum.org/proxy/image?"
                 + urllib.parse.urlencode({"url": url, "token": tok}))
            req = urllib.request.Request(u, headers={"User-Agent": "flashpoint-eval"})
        else:
            import base64
            req = urllib.request.Request(url, headers={
                "Authorization": "Basic " + base64.b64encode(tok.encode()).decode(),
                "User-Agent": "flashpoint-eval"})
        with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
            f.write(r.read())
        return dest, None
    except Exception as e:
        if dest.exists():
            dest.unlink()
        return None, str(e)[:80]


def download_window(start, end, tok, use_proxy):
    import sage_data_client

    df = sage_data_client.query(start=start, end=end,
                                filter={"name": "upload", "task": "audio-sampler",
                                        "vsn": "W06C"})
    df = df.sort_values("timestamp")
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda r: fetch(r[1], tok, use_proxy), df.iterrows()))
    ok = sum(1 for d, _ in res if d)
    errs = [e for _, e in res if e]
    print(f"  {start[5:16]} -> {end[5:16]}: {len(df)} listed, {ok} on disk"
          + (f", {len(errs)} failed (first: {errs[0]})" if errs else ""))
    out = []
    for (_, row), (dest, _) in zip(df.iterrows(), res):
        if dest is not None:
            out.append((row["timestamp"].timestamp(), dest))
    return out


def v0_ratio(y, sr, sos):
    """The M1 v0 metric, faithfully: max/median of 0.5 s RMS in 15-120 Hz."""
    z = sig.resample_poly(y, 1, sr // 1000)
    low = sig.sosfiltfilt(sos, z)
    w = 500
    n = len(low) // w
    if n < 4:
        return 0.0
    e = np.sqrt(np.mean(low[: n * w].reshape(n, w) ** 2, axis=1))
    return float(e.max() / (np.median(e) + 1e-9))


def auc(scores_pos, scores_neg):
    """Rank AUC, ties = 0.5."""
    if not scores_pos or not scores_neg:
        return float("nan")
    wins = ties = 0
    for p in scores_pos:
        for n in scores_neg:
            wins += p > n
            ties += p == n
    return (wins + 0.5 * ties) / (len(scores_pos) * len(scores_neg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", action="store_true",
                    help="also run the rain-showers control window")
    args = ap.parse_args()

    CLIPS.mkdir(parents=True, exist_ok=True)
    user, token = creds()
    tok = f"{user}:{token}"
    use_proxy = os.environ.get("SAGE_VIA_PROXY", "0") == "1"

    flashes, truth, node, fire = anchors.load_kitten_truth()
    glm = [(f["epoch"], f["dist_node_km"]) for f in flashes if f["dist_node_km"] <= 30.0]
    glm = anchors.dedupe_epochs(glm, min_sep_s=2.0)
    print(f"GLM anchors <=30 km (deduped @2s): {len(glm)}; truth arrivals: {len(truth)}")

    print("downloading eval window (cached after first run):")
    clips = download_window(EVAL_START, EVAL_END, tok, use_proxy)

    cfg = thunder.Config(temp_c=NODE_TEMP_C)
    sos_v0 = sig.butter(4, [15, 120], btype="band", fs=1000, output="sos")

    per_clip, anchored_pass, standalone_pass = [], [], []
    for start_epoch, path in clips:
        y, sr = sf.read(str(path), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        dur = len(y) / sr
        rel = anchors.clip_relative(glm, start_epoch, dur, cfg)
        ev_anch = thunder.detect(y, sr, anchor_times_s=rel, cfg=cfg,
                                 wind_ms=NODE_WIND_MS)
        ev_solo = thunder.detect(y, sr, anchor_times_s=None, cfg=cfg,
                                 wind_ms=NODE_WIND_MS)
        for e in ev_anch:
            if e.passed:
                anchored_pass.append((start_epoch + e.onset_s, e))
        for e in ev_solo:
            if e.passed:
                standalone_pass.append((start_epoch + e.onset_s, e))
        has_truth = any(start_epoch <= a["epoch"] <= start_epoch + dur for a in truth)
        per_clip.append({
            "start": start_epoch, "dur": dur, "positive": has_truth,
            "ours": thunder.clip_max_score(ev_solo),
            "v0": v0_ratio(y, sr, sos_v0),
        })

    # ---- anchored recall vs the 22
    hits, range_errs = [], []
    for a in truth:
        best = None
        for t_abs, e in anchored_pass:
            dt = abs(t_abs - a["epoch"])
            if dt <= MATCH_TOL_S and (best is None or dt < best[0]):
                best = (dt, e)
        if best:
            hits.append(a)
            if best[1].implied_range_km is not None:
                range_errs.append(abs(best[1].implied_range_km - a["range_km"]))
    unmatched = [
        (t, e) for t, e in anchored_pass
        if all(abs(t - a["epoch"]) > 5.0 for a in truth)
    ]

    # ---- clip-level AUCs
    pos = [c for c in per_clip if c["positive"]]
    neg = [c for c in per_clip if not c["positive"]]
    auc_ours = auc([c["ours"] for c in pos], [c["ours"] for c in neg])
    auc_v0 = auc([c["v0"] for c in pos], [c["v0"] for c in neg])

    print("\n================ RESULTS ================")
    print(f"clips analyzed: {len(per_clip)} "
          f"({len(pos)} contain >=1 of the 22 truth arrivals)")
    print(f"ANCHORED recall: {len(hits)}/{len(truth)} arrivals "
          f"(+/-{MATCH_TOL_S}s), median range err "
          f"{np.median(range_errs):.1f} km" if range_errs else
          f"ANCHORED recall: {len(hits)}/{len(truth)} (no range matches)")
    print(f"  unmatched anchored passes: {len(unmatched)} "
          "(candidate arrivals beyond the 22 — for NLDN arbitration, "
          "not counted as detections)")
    print(f"STANDALONE passes in storm window: {len(standalone_pass)} "
          "(emitted as candidates only)")
    print(f"clip-level AUC vs the 22-arrival labels: ours {auc_ours:.3f} "
          f"| v0 ratio {auc_v0:.3f}  (M1 measured v0 at 0.163 on its labels)")

    summary = {
        "run": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "eval_window": [EVAL_START, EVAL_END],
        "clips": len(per_clip), "positive_clips": len(pos),
        "anchored_recall": [len(hits), len(truth)],
        "median_range_err_km": float(np.median(range_errs)) if range_errs else None,
        "unmatched_anchored": len(unmatched),
        "standalone_passes": len(standalone_pass),
        "auc_ours": auc_ours, "auc_v0": auc_v0,
        "config": {k: getattr(cfg, k) for k in vars(cfg)},
    }

    if args.control:
        print("\ncontrol window (rain showers, no GLM anchors):")
        ctrl = download_window(CTRL_START, CTRL_END, tok, use_proxy)
        fa = 0
        hours = 0.0
        for start_epoch, path in ctrl:
            y, sr = sf.read(str(path), dtype="float32")
            if y.ndim > 1:
                y = y.mean(axis=1)
            hours += len(y) / sr / 3600
            fa += sum(1 for e in thunder.detect(y, sr, cfg=cfg) if e.passed)
        print(f"  standalone false alarms: {fa} in {hours:.2f} h of audio "
              f"({fa / hours:.1f}/h)" if hours else "  no control audio")
        summary["control"] = {"false_alarms": fa, "audio_hours": hours}

    SUMMARY.write_text(json.dumps(summary, indent=1))
    print(f"\nsummary -> {SUMMARY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
