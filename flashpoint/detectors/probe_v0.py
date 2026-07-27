#!/usr/bin/env python3
"""Audio classifier probe v0 — frozen YAMNet embeddings + logistic regression.

The M1/D1-2 lesson: DSP clip scores rank storm-window thunder clips WORSE than
chance (AUC 0.389 ours / 0.282 v0 vs the 22-arrival labels) because rain noise
dominates the score. This probe asks whether a general audio embedding
(YAMNet, AudioSet-trained, frozen) separates the same clips.

Labels (per the camp runbook):
  positive = storm-window clips containing >=1 of the 22 satellite-anchored
             arrivals in detectors/data/kitten_glm.json;
  negative = the rain-showers control-window clips (Jul 3 2025 17:00-19:30 UT,
             no GLM anchors). Storm clips WITHOUT an arrival are excluded from
             training (ambiguous — unmatched candidates live there) but are
             embedded and scored for context.

Method: 16 kHz mono -> YAMNet frame embeddings [N,1024] -> clip feature =
concat(mean, max) over frames -> StandardScaler + LogisticRegression
(class_weight=balanced), 5-fold stratified CV, pooled out-of-fold scores.
Reported: ROC AUC and recall at a 1-false-alarm-per-hour operating point
(with only ~0.22 h of control audio that allows 0 false alarms, i.e. the
threshold sits just above the highest-scoring control clip). The DSP clip
score and the v0 ratio are re-scored on the SAME label set for a fair
comparison; YAMNet's own Thunder/Thunderstorm class score is included as a
zero-shot baseline.

Run (needs data/kitten_clips/ from eval_kitten.py --control):
  python3 detectors/probe_v0.py [--recompute]
Embeddings are cached under data/kitten_clips/; results land in
detectors/data/probe_v0_results.json.
"""
import argparse
import datetime
import json
import pathlib
import sys

import numpy as np
import soundfile as sf
from scipy import signal as sig

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from detectors import anchors, thunder  # noqa: E402

CLIPS = ROOT / "data" / "kitten_clips"
CACHE = CLIPS / "_probe_v0_embeddings.npz"
RESULTS = pathlib.Path(__file__).resolve().parent / "data" / "probe_v0_results.json"

STORM = ("2025-07-02T21:00:00", "2025-07-03T01:30:00")
CTRL = ("2025-07-03T17:00:00", "2025-07-03T19:30:00")
NODE_TEMP_C = 15.0   # match eval_kitten.py
NODE_WIND_MS = 5.6
FA_PER_HOUR = 1.0
SEED = 0


def _epoch(stamp):
    return datetime.datetime.fromisoformat(stamp).replace(
        tzinfo=datetime.timezone.utc).timestamp()


def list_clips():
    """(epoch, window, path) for every cached clip; window from filename."""
    out = []
    for p in sorted(CLIPS.glob("*.flac")):
        try:  # 2025-07-02_211003.flac -> epoch
            d, t = p.stem.split("_")
            e = _epoch(f"{d}T{t[:2]}:{t[2:4]}:{t[4:6]}")
        except ValueError:
            continue
        if _epoch(STORM[0]) <= e <= _epoch(STORM[1]):
            win = "storm"
        elif _epoch(CTRL[0]) <= e <= _epoch(CTRL[1]):
            win = "control"
        else:
            continue
        out.append((e, win, p))
    return out


def load_mono(path):
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y, sr


def embed_all(clips, recompute=False):
    """YAMNet per-clip features; cached (the model itself is ~17 MB)."""
    names = [p.name for _, _, p in clips]
    if CACHE.exists() and not recompute:
        z = np.load(CACHE, allow_pickle=True)
        if list(z["names"]) == names:
            return z["feat"], z["thunder_zs"], z["durs"]
    import os
    os.environ.setdefault("TFHUB_CACHE_DIR", str(ROOT / "data" / "tfhub_cache"))
    import tensorflow_hub as hub
    model = hub.load("https://tfhub.dev/google/yamnet/1")
    class_names = [ln.split(",")[2].strip() for ln in pathlib.Path(
        model.class_map_path().numpy().decode()).read_text().splitlines()[1:]]
    thunder_ix = [i for i, n in enumerate(class_names)
                  if n in ("Thunder", "Thunderstorm")]
    feat, zs, durs = [], [], []
    for i, (_, _, p) in enumerate(clips):
        y, sr = load_mono(p)
        durs.append(len(y) / sr)
        if sr != 16000:
            g = np.gcd(sr, 16000)
            y = sig.resample_poly(y, 16000 // g, sr // g).astype(np.float32)
        scores, emb, _ = model(y)
        emb, scores = emb.numpy(), scores.numpy()
        feat.append(np.concatenate([emb.mean(0), emb.max(0)]))
        zs.append(float(scores[:, thunder_ix].sum(axis=1).max()))
        print(f"  embedded {i + 1}/{len(clips)}: {p.name}", end="\r")
    print()
    feat, zs, durs = np.array(feat), np.array(zs), np.array(durs)
    np.savez_compressed(CACHE, names=names, feat=feat, thunder_zs=zs, durs=durs)
    return feat, zs, durs


def dsp_scores(clips):
    """The two DSP baselines, exactly as eval_kitten.py computes them."""
    cfg = thunder.Config(temp_c=NODE_TEMP_C)
    sos_v0 = sig.butter(4, [15, 120], btype="band", fs=1000, output="sos")
    ours, v0 = [], []
    for _, _, p in clips:
        y, sr = load_mono(p)
        ev = thunder.detect(y, sr, cfg=cfg, wind_ms=NODE_WIND_MS)
        ours.append(thunder.clip_max_score(ev))
        z = sig.resample_poly(y, 1, sr // 1000)
        low = sig.sosfiltfilt(sos_v0, z)
        n = len(low) // 500
        e = np.sqrt(np.mean(low[: n * 500].reshape(n, 500) ** 2, axis=1))
        v0.append(float(e.max() / (np.median(e) + 1e-9)) if n >= 4 else 0.0)
    return np.array(ours), np.array(v0)


def rank_auc(pos, neg):
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def recall_at_fa(pos_scores, neg_scores, neg_hours, arrivals_per_pos):
    """Operating point: highest threshold whose control-window false alarms
    stay within FA_PER_HOUR (0 allowed when neg_hours < 1/FA_PER_HOUR)."""
    allowed = int(FA_PER_HOUR * neg_hours)
    thr = float(np.sort(neg_scores)[::-1][allowed]) if allowed < len(neg_scores) \
        else float(min(neg_scores))
    hit = pos_scores > thr
    return {
        "threshold": thr, "allowed_false_alarms": allowed,
        "clip_recall": [int(hit.sum()), len(pos_scores)],
        "arrival_recall": [int(sum(a for h, a in zip(hit, arrivals_per_pos) if h)),
                           int(sum(arrivals_per_pos))],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", action="store_true",
                    help="ignore the embedding cache")
    args = ap.parse_args()

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    clips = list_clips()
    if not clips:
        sys.exit("no clips under data/kitten_clips/ — run eval_kitten.py --control first")
    _, truth, _, _ = anchors.load_kitten_truth()

    feat, zs, durs = embed_all(clips, recompute=args.recompute)
    ours, v0 = dsp_scores(clips)

    n_arr = np.array([sum(e <= a["epoch"] <= e + d for a in truth)
                      for (e, _, _), d in zip(clips, durs)])
    win = np.array([w for _, w, _ in clips])
    is_pos = (win == "storm") & (n_arr > 0)
    is_neg = win == "control"
    labeled = is_pos | is_neg
    X, y = feat[labeled], is_pos[labeled].astype(int)
    neg_hours = float(durs[is_neg].sum() / 3600)

    oof = np.zeros(len(y))
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    for tr, te in skf.split(X, y):
        clf = make_pipeline(StandardScaler(), LogisticRegression(
            max_iter=5000, class_weight="balanced", C=1.0))
        clf.fit(X[tr], y[tr])
        oof[te] = clf.decision_function(X[te])

    pos_l, neg_l = oof[y == 1], oof[y == 0]
    arrivals_per_pos = n_arr[labeled][y == 1]
    res = {
        "run": "see git log",
        "model": "YAMNet (tfhub.dev/google/yamnet/1, frozen)",
        "feature": "concat(mean,max) of frame embeddings (2048-d)",
        "cv": f"StratifiedKFold(5, shuffle, seed={SEED}), pooled out-of-fold "
              "decision scores; StandardScaler + LogisticRegression(C=1, balanced)",
        "clips": {"positive": int(is_pos.sum()), "control_negative": int(is_neg.sum()),
                  "storm_unlabeled_excluded": int((win == "storm").sum() - is_pos.sum()),
                  "control_audio_hours": round(neg_hours, 4)},
        "probe": {
            "auc": roc_auc_score(y, oof),
            "operating_point_1fa_per_h": recall_at_fa(
                pos_l, neg_l, neg_hours, arrivals_per_pos),
        },
        "baselines_same_labels": {
            "dsp_clip_score": {
                "auc": rank_auc(ours[is_pos], ours[is_neg]),
                "operating_point_1fa_per_h": recall_at_fa(
                    ours[is_pos], ours[is_neg], neg_hours, arrivals_per_pos)},
            "v0_ratio": {
                "auc": rank_auc(v0[is_pos], v0[is_neg]),
                "operating_point_1fa_per_h": recall_at_fa(
                    v0[is_pos], v0[is_neg], neg_hours, arrivals_per_pos)},
            "yamnet_thunder_zeroshot": {
                "auc": rank_auc(zs[is_pos], zs[is_neg]),
                "operating_point_1fa_per_h": recall_at_fa(
                    zs[is_pos], zs[is_neg], neg_hours, arrivals_per_pos)},
        },
        "stored_eval_reference": {
            "note": "eval_kitten_summary.json AUCs use storm-window negatives "
                    "(13 pos vs 36 storm clips), not the control window",
            "auc_ours": 0.389, "auc_v0": 0.282},
        "storm_unlabeled_context": {
            "note": "probe scores of the 36 ambiguous storm clips (72 unmatched "
                    "anchored candidates live there), scored by a model trained "
                    "on all labeled clips",
        },
    }

    # context pass: how do the ambiguous storm clips score?
    clf = make_pipeline(StandardScaler(), LogisticRegression(
        max_iter=5000, class_weight="balanced", C=1.0)).fit(X, y)
    amb = (win == "storm") & ~is_pos
    if amb.any():
        s = clf.decision_function(feat[amb])
        thr = res["probe"]["operating_point_1fa_per_h"]["threshold"]
        res["storm_unlabeled_context"].update(
            above_probe_threshold=[int((s > thr).sum()), int(amb.sum())])

    p, b = res["probe"], res["baselines_same_labels"]
    print("\n================ PROBE v0 RESULTS ================")
    print(f"clips: {res['clips']['positive']} positive (contain >=1 of the 22 "
          f"arrivals) vs {res['clips']['control_negative']} control negatives "
          f"({neg_hours:.2f} h); {res['clips']['storm_unlabeled_excluded']} "
          "ambiguous storm clips excluded")
    print(f"probe AUC (out-of-fold): {p['auc']:.3f}")
    op = p["operating_point_1fa_per_h"]
    print(f"recall @ {FA_PER_HOUR:g} FA/h (= {op['allowed_false_alarms']} FAs "
          f"in {neg_hours:.2f} h): clips {op['clip_recall'][0]}/"
          f"{op['clip_recall'][1]}, arrivals {op['arrival_recall'][0]}/"
          f"{op['arrival_recall'][1]}")
    for k, lbl in [("dsp_clip_score", "DSP clip score"), ("v0_ratio", "v0 ratio"),
                   ("yamnet_thunder_zeroshot", "YAMNet Thunder zero-shot")]:
        o = b[k]["operating_point_1fa_per_h"]
        print(f"{lbl:26s} same-labels AUC {b[k]['auc']:.3f}, recall @ 1 FA/h "
              f"clips {o['clip_recall'][0]}/{o['clip_recall'][1]}")
    print("(stored eval AUCs vs storm-window negatives: ours 0.389, v0 0.282)")

    RESULTS.write_text(json.dumps(res, indent=1))
    print(f"\nresults -> {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
