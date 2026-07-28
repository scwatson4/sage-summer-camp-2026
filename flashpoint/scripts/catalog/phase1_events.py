#!/usr/bin/env python3
"""Phase 1b — turn the GLM scan into the fire-anchored event catalog.

For every natural-cause fire within 35 km of a Phase-0 node, summarise the
lightning GLM saw in the 10 days before discovery, near the fire point and
near the node, and measure the holdover gap: the time from the end of the last
storm episode to the moment the fire was reported.

Outputs
  catalog/fire_events.parquet   one row per (fire, node) pair
  catalog/fire_flashes.parquet  flash-level detail for those windows
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C

EPISODE_GAP_H = 6.0     # quiet gap that separates one storm episode from the next


def episodes(epochs: np.ndarray, gap_h: float = EPISODE_GAP_H):
    """Split sorted flash epochs into storm episodes; return list of (t0, t1, n)."""
    if not len(epochs):
        return []
    e = np.sort(epochs)
    brk = np.nonzero(np.diff(e) > gap_h * 3600.0)[0]
    starts = np.concatenate(([0], brk + 1))
    ends = np.concatenate((brk, [len(e) - 1]))
    return [(float(e[s]), float(e[t]), int(t - s + 1)) for s, t in zip(starts, ends)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-name", default="glm")
    ap.add_argument("--lookback-days", type=int, default=10)
    ap.add_argument("--radius-km", type=float, default=30.0)
    args = ap.parse_args()

    C.log("Phase 1b — fire-anchored event catalog")
    fires = pd.read_parquet(C.CATALOG / "fires_natural.parquet")
    pairs = pd.read_parquet(C.CATALOG / "fire_node_pairs.parquet")
    inv = pd.read_parquet(C.CATALOG / "node_inventory.parquet").set_index("vsn")
    flashes = C.read_shards(args.scan_name)
    C.log(f"scan rows: {len(flashes):,}   fires: {len(fires)}")
    if not len(flashes):
        C.log("no scan output yet — run scan_engine first")
        return

    flashes["ref"] = flashes.key.str.split(":", n=1).str[1]
    flashes["kind"] = flashes.key.str.split(":", n=1).str[0]
    fire_fl = flashes[flashes.kind == "fire"]
    node_fl = flashes[flashes.kind == "node"]
    fire_by = {k: g for k, g in fire_fl.groupby("ref", sort=False)}
    node_by = {k: g for k, g in node_fl.groupby("ref", sort=False)}

    # coverage: uploads per node per day, for "was it recording?"
    cov = None
    cov_path = C.CATALOG / "node_coverage.parquet"
    if cov_path.exists():
        from phase0_coverage import media_bucket
        cov = pd.read_parquet(cov_path)
        cov["day"] = pd.to_datetime(cov["day"]).dt.tz_localize("UTC")
        if "bucket" not in cov.columns:          # coverage file predates the classifier
            cov["bucket"] = cov.task.map(media_bucket)
            cov["is_media"] = cov["bucket"] != "non_media"
        cov = cov[cov.n_uploads > 0]

    fmeta = fires.set_index("fire_id")
    pairs = pairs[pairs.fire_id.isin(fires.fire_id)]

    rows, detail = [], []
    for p in pairs.itertuples():
        f = fmeta.loc[p.fire_id]
        disc = f.discovery
        t1 = disc.timestamp()
        t0 = t1 - args.lookback_days * 86400.0

        fg = fire_by.get(p.fire_id)
        fg = fg[(fg.epoch >= t0) & (fg.epoch <= t1) & (fg.dist_km <= args.radius_km)] \
            if fg is not None else pd.DataFrame()
        ng = node_by.get(p.vsn)
        ng = ng[(ng.epoch >= t0) & (ng.epoch <= t1) & (ng.dist_km <= args.radius_km)] \
            if ng is not None else pd.DataFrame()

        eps = episodes(fg.epoch.to_numpy()) if len(fg) else []
        last_ep = eps[-1] if eps else None
        holdover_h = (t1 - last_ep[1]) / 3600.0 if last_ep else np.nan

        # nearest approach in space, and the single closest flash's timing
        if len(fg):
            i = int(np.argmin(fg.dist_km.to_numpy()))
            nearest_km = float(fg.dist_km.iloc[i])
            nearest_t = float(fg.epoch.iloc[i])
            nearest_lead_h = (t1 - nearest_t) / 3600.0
        else:
            nearest_km = nearest_t = nearest_lead_h = np.nan

        nd = inv.loc[p.vsn] if p.vsn in inv.index else None
        rec = dict(
            fire_id=p.fire_id, fire_name=f["name"], discovery=disc,
            fire_lat=f.lat, fire_lon=f.lon, size_acres=f.size_acres,
            cause=f.cause, state=f.POOState, coord_source=f.coord_source,
            vsn=p.vsn, dist_node_km=p.dist_node_km,
            node_lat=(float(nd.lat) if nd is not None else np.nan),
            node_lon=(float(nd.lon) if nd is not None else np.nan),
            node_mic=(bool(nd.mic) if nd is not None else False),
            node_cam=(bool(nd.cam) if nd is not None else False),
            n_flash_fire_30km=len(fg), n_flash_node_30km=len(ng),
            nearest_flash_to_fire_km=nearest_km,
            nearest_flash_epoch=nearest_t,
            nearest_flash_lead_h=nearest_lead_h,
            n_storm_episodes=len(eps),
            first_flash_epoch=(eps[0][0] if eps else np.nan),
            last_flash_epoch=(last_ep[1] if last_ep else np.nan),
            last_episode_flashes=(last_ep[2] if last_ep else 0),
            holdover_gap_h=holdover_h,
            nearest_flash_to_node_km=(float(ng.dist_km.min()) if len(ng) else np.nan),
        )

        if cov is not None:
            # cov.day is a UTC midnight labelling the whole day [D, D+1), so it
            # cannot be compared against instants: doing so drops the first
            # partial day and swallows the whole discovery day. Use the calendar
            # days the flash window touches, and say so — archive counts are
            # day-granular and cannot be clipped any finer.
            d0 = pd.Timestamp(t0, unit="s", tz="UTC").floor("D")
            d1 = disc.floor("D")
            w = cov[(cov.vsn == p.vsn) & (cov.day >= d0) & (cov.day <= d1)
                    & (cov.n_uploads > 0)]
            cap = w[w.bucket.isin(("audio", "image", "ptz"))] if "bucket" in w else w
            rec["window_days"] = int((d1 - d0).days) + 1
            rec["uploads_in_window"] = int(w.n_uploads.sum())
            rec["media_uploads_in_window"] = int(w[w.is_media].n_uploads.sum()) if len(w) else 0
            rec["audio_clips_in_window"] = int(
                w[w.bucket == "audio"].n_uploads.sum()) if len(w) else 0
            rec["image_uploads_in_window"] = int(
                w[w.bucket == "image"].n_uploads.sum()) if len(w) else 0
            rec["ptz_frames_in_window"] = int(
                w[w.bucket == "ptz"].n_uploads.sum()) if len(w) else 0
            # days on which media was actually uploaded, not days with a row
            rec["recording_days_in_window"] = int(cap.day.nunique()) if len(cap) else 0
        rows.append(rec)

        if len(fg):
            d = fg[["epoch", "flash_lat", "flash_lon", "dist_km", "flash_energy_j", "sat"]].copy()
            d["fire_id"] = p.fire_id
            d["vsn"] = p.vsn
            d = d.rename(columns={"dist_km": "dist_fire_km"})
            detail.append(d)

    ev = pd.DataFrame(rows)
    ev["nearest_flash_time"] = pd.to_datetime(ev.nearest_flash_epoch, unit="s", utc=True)
    ev["last_flash_time"] = pd.to_datetime(ev.last_flash_epoch, unit="s", utc=True)
    ev["first_flash_time"] = pd.to_datetime(ev.first_flash_epoch, unit="s", utc=True)
    ev = ev.sort_values(["n_flash_fire_30km", "nearest_flash_to_fire_km"],
                        ascending=[False, True]).reset_index(drop=True)
    ev.to_parquet(C.CATALOG / "fire_events.parquet", index=False)
    C.log(f"wrote catalog/fire_events.parquet  rows={len(ev)}")

    if detail:
        det = pd.concat(detail, ignore_index=True)
        det["time"] = pd.to_datetime(det.epoch, unit="s", utc=True)
        det.to_parquet(C.CATALOG / "fire_flashes.parquet", index=False)
        C.log(f"wrote catalog/fire_flashes.parquet rows={len(det):,}")

    lit = ev[ev.n_flash_fire_30km > 0]
    C.log(f"fires with GLM lightning <=30 km in the 10 d before discovery: "
          f"{lit.fire_id.nunique()}/{ev.fire_id.nunique()}")
    if len(lit):
        C.log(f"  median nearest-flash-to-fire: {lit.nearest_flash_to_fire_km.median():.1f} km")
        C.log(f"  median holdover gap: {lit.holdover_gap_h.median():.1f} h")
    C.log("PHASE 1 DONE — safe to shelve")


if __name__ == "__main__":
    main()
