#!/usr/bin/env python3
"""Phase 2 — node-lifetime storm census joined to archive coverage.

Every day a storm passed within 30 km of a fire-country microphone node, from
that node's deployment start onward (May-September), joined against what the
node's archive actually recorded that day.

Output
  catalog/storm_recording_days.parquet   one row per (vsn, date) with >=1 flash
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C

STORM_MIN_FLASHES = 10       # a "storm day" rather than a stray flash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-name", default="glm")
    ap.add_argument("--radius-km", type=float, default=30.0)
    ap.add_argument("--season", default="5-9")
    args = ap.parse_args()
    m0, m1 = (int(x) for x in args.season.split("-"))

    C.log("Phase 2 — node-lifetime storm census")
    nodes = pd.read_parquet(C.CATALOG / "phase2_nodes.parquet")
    inv = pd.read_parquet(C.CATALOG / "node_inventory.parquet").set_index("vsn")
    flashes = C.read_shards(args.scan_name)
    C.log(f"scan rows {len(flashes):,}; census nodes {len(nodes)}: {', '.join(nodes.vsn)}")

    fl = flashes[flashes.key.str.startswith("node:")].copy()
    fl["vsn"] = fl.key.str.split(":", n=1).str[1]
    fl = fl[fl.vsn.isin(nodes.vsn) & (fl.dist_km <= args.radius_km)]
    fl["time"] = pd.to_datetime(fl.epoch, unit="s", utc=True)
    fl["date"] = fl.time.dt.floor("D")
    C.log(f"node-proximate flashes: {len(fl):,}")

    daily = (fl.groupby(["vsn", "date"])
               .agg(n_flashes=("epoch", "size"),
                    nearest_km=("dist_km", "min"),
                    median_km=("dist_km", "median"),
                    first_flash=("time", "min"),
                    last_flash=("time", "max"),
                    sat=("sat", "first"))
               .reset_index())
    daily["storm_hours"] = ((daily.last_flash - daily.first_flash)
                            .dt.total_seconds() / 3600.0)
    # merge, not .values — positional assignment relies on both groupbys
    # emitting identical key order, which is true today but silently wrong the
    # moment either side is filtered or re-sorted
    ah = (fl.assign(h=fl.time.dt.floor("h")).groupby(["vsn", "date"])
            .h.nunique().rename("active_hours").reset_index())
    daily = daily.merge(ah, on=["vsn", "date"], how="left")
    daily["month"] = daily.date.dt.month
    daily = daily[(daily.month >= m0) & (daily.month <= m1)]

    # only from each node's deployment start
    start = inv.first_data.to_dict()
    # np.array(..., dtype=bool) so an all-empty mask stays a ROW selector; a
    # bare [] would be read as a column selector and silently drop every column.
    keep = np.array([d >= pd.Timestamp(start[v]).floor("D")
                     for v, d in zip(daily.vsn, daily.date)], dtype=bool)
    daily = daily[keep]
    C.log(f"node-days with >=1 flash (season {m0}-{m1}, post-deployment): {len(daily):,}")

    # ---- join archive coverage -------------------------------------------
    cov = pd.read_parquet(C.CATALOG / "node_coverage.parquet")
    cov["day"] = pd.to_datetime(cov["day"]).dt.tz_localize("UTC")
    cov = cov[cov.vsn.isin(nodes.vsn)]

    # Reuse Phase 0's classifier rather than re-deriving it here; the archive
    # spells these plugins several ways (audiosampler, image-sampler-top, ...).
    from phase0_coverage import media_bucket
    cov = cov[cov.n_uploads > 0].copy()
    _NAME = {"audio": "audio_clips", "image": "image_frames", "ptz": "ptz_frames",
             "derived": "other_media", "non_media": "non_media"}
    cov["bucket"] = cov.task.map(lambda t: _NAME[media_bucket(t)])
    piv = (cov.pivot_table(index=["vsn", "day"], columns="bucket",
                           values="n_uploads", aggfunc="sum", fill_value=0)
              .reset_index().rename(columns={"day": "date"}))
    for c in ("audio_clips", "image_frames", "ptz_frames", "other_media"):
        if c not in piv.columns:
            piv[c] = 0

    out = daily.merge(piv, on=["vsn", "date"], how="left")
    for c in ("audio_clips", "image_frames", "ptz_frames", "other_media", "non_media"):
        if c in out.columns:
            out[c] = out[c].fillna(0).astype("int64")
    out["media_uploads"] = (out.audio_clips + out.image_frames
                            + out.ptz_frames + out.get("other_media", 0))
    out["was_recording"] = out.media_uploads > 0
    out["had_audio"] = out.audio_clips > 0
    out["had_imagery"] = (out.image_frames + out.ptz_frames) > 0
    out["storm_day"] = out.n_flashes >= STORM_MIN_FLASHES

    # Audio cadence. NOTE: audio_clips is a whole-UTC-day count — the coverage
    # data is day-granular, so there is no way to know how many of the day's
    # clips fell inside the storm. Dividing a day's clips by the storm's
    # duration would inflate the rate by 24/storm_hours. The samplers are
    # weather-agnostic and run at fixed cadence, so the defensible estimate is
    # the day rate, with expected in-storm clips prorated from it.
    out["clips_per_hour_of_day"] = out.audio_clips / 24.0
    out["expected_clips_in_storm"] = out.clips_per_hour_of_day * out.storm_hours

    out = out.sort_values(["n_flashes"], ascending=False).reset_index(drop=True)
    out.to_parquet(C.CATALOG / "storm_recording_days.parquet", index=False)
    C.log(f"wrote catalog/storm_recording_days.parquet rows={len(out):,}")

    sd = out[out.storm_day]
    C.log(f"storm days (>={STORM_MIN_FLASHES} flashes <=30 km): {len(sd):,}")
    if len(sd):
        C.log(f"  with ANY media recorded : {int(sd.was_recording.sum()):,} "
              f"({100*sd.was_recording.mean():.1f}%)")
        C.log(f"  with audio recorded     : {int(sd.had_audio.sum()):,} "
              f"({100*sd.had_audio.mean():.1f}%)")
        C.log(f"  with imagery recorded   : {int(sd.had_imagery.sum()):,} "
              f"({100*sd.had_imagery.mean():.1f}%)")
        per = (sd.groupby("vsn")
                 .agg(storm_days=("storm_day", "size"),
                      recorded=("was_recording", "sum"),
                      audio=("had_audio", "sum"),
                      imagery=("had_imagery", "sum"),
                      flashes=("n_flashes", "sum"))
                 .assign(pct_recorded=lambda d: 100 * d.recorded / d.storm_days,
                         pct_audio=lambda d: 100 * d.audio / d.storm_days)
                 .sort_values("storm_days", ascending=False))
        C.log("per-node storm-day coverage:\n" + per.to_string())
        per.to_parquet(C.CATALOG / "node_storm_coverage.parquet")
    C.log("PHASE 2 DONE — safe to shelve")


if __name__ == "__main__":
    main()
