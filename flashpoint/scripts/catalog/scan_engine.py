#!/usr/bin/env python3
"""The GLM scan engine shared by Phase 1 and Phase 2.

Why one engine and one plan
---------------------------
GLM L2 LCFA granules are FULL-DISK. Downloading the 4320 granules of a
satellite-day yields every flash the satellite saw that day, so filtering them
against 1 target or 400 targets costs the same. Two consequences drive this
design:

1. Scan cost is |unique (satellite, date)| x 4320 granules. It is NOT
   proportional to the number of nodes or fires. Trimming the target list to
   "the top N nodes" saves nothing unless it removes whole DATES or a whole
   SATELLITE track.
2. Phase 1 (fire windows) and Phase 2 (May-Sep node lifetimes) overlap heavily,
   so they are planned as one union and scanned once. Measured on this
   catalog that saves ~2.15M granules (~1.5 h) versus scanning them separately.

Each (satellite, date) is one checkpointed work unit: 24 hours downloaded into
tmpfs, filtered against every target assigned to that satellite, then deleted.
Raw granules never accumulate beyond the hour in flight per worker.
"""
from __future__ import annotations

import argparse
import datetime as dt
import multiprocessing as mp
import os
import pathlib
import shutil
import sys
import time

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C

_TARGETS: pd.DataFrame | None = None
_NUMWORKERS = 16
_KEEP_RADIUS = 30.0


def _init(targets: pd.DataFrame, numworkers: int):
    global _TARGETS, _NUMWORKERS
    _TARGETS = targets
    _NUMWORKERS = numworkers


def _targets_for(sat: int, day: dt.date) -> pd.DataFrame:
    """Targets whose best-viewing GLM on this date is `sat`."""
    t = _TARGETS
    keep = [C.primary_sat(day, lon) == sat for lon in t["lon"]]
    return t[pd.Series(keep, index=t.index)]


def scan_day(unit):
    """One (satellite, date): 24 hours, filtered, granules discarded."""
    sat, day_str = unit
    day = dt.date.fromisoformat(day_str)
    tg = _targets_for(sat, day)
    if not len(tg):
        return unit, pd.DataFrame(), 0, 0.0, None
    t0 = time.time()
    frames, ngran = [], 0
    try:
        for hour in range(24):
            df, n = C.scan_hour(sat, day, hour, tg, numworkers=_NUMWORKERS)
            ngran += n
            if len(df):
                frames.append(df)
    except Exception as exc:
        return unit, None, ngran, time.time() - t0, str(exc)[:200]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["key", "epoch", "flash_lat", "flash_lon", "flash_energy_j",
                 "dist_km", "sat"])
    if len(out):
        out["date"] = day_str
    return unit, out, ngran, time.time() - t0, None


def build_targets(fires: pd.DataFrame, nodes: pd.DataFrame,
                  radius_km: float = _KEEP_RADIUS) -> pd.DataFrame:
    """Fire points and node points, one row each, keyed for later attribution."""
    rows = []
    for r in nodes.itertuples():
        rows.append(dict(key=f"node:{r.vsn}", kind="node", ref=r.vsn,
                         lat=float(r.lat), lon=float(r.lon), radius_km=radius_km))
    for r in fires.itertuples():
        rows.append(dict(key=f"fire:{r.fire_id}", kind="fire", ref=r.fire_id,
                         lat=float(r.lat), lon=float(r.lon), radius_km=radius_km))
    return pd.DataFrame(rows)


def run(plan: list[tuple[int, str]], targets: pd.DataFrame, name: str,
        procs: int = 16, numworkers: int = 16):
    ck = C.Checkpoint(name)
    todo = [u for u in plan if f"{u[0]}|{u[1]}" not in ck]
    C.log(f"scan '{name}': {len(plan)} satellite-days planned, "
          f"{len(plan) - len(todo)} done, {len(todo)} to go "
          f"(~{len(todo) * 4320:,} granules)")
    if not todo:
        ck.close()
        return

    shutil.rmtree(C.STAGE_ROOT, ignore_errors=True)
    os.makedirs(C.STAGE_ROOT, exist_ok=True)

    t_start = time.time()
    n_gran = n_hits = 0
    done = 0
    with mp.Pool(procs, initializer=_init, initargs=(targets, numworkers)) as pool:
        for unit, df, ngran, secs, err in pool.imap_unordered(scan_day, todo, chunksize=1):
            done += 1
            sat, day_str = unit
            if err:
                C.log(f"  ERROR G{sat} {day_str}: {err}")
                continue
            n_gran += ngran
            n_hits += len(df)
            if len(df):
                C.write_shard(name, f"{sat}_{day_str}", df)
            ck.mark(f"{sat}|{day_str}", granules=ngran, flashes=len(df))
            if done % 20 == 0 or done == len(todo):
                el = time.time() - t_start
                rate = n_gran / max(el, 1e-9)
                eta = (len(todo) - done) * (el / done) / 3600
                C.log(f"  {done}/{len(todo)} sat-days | {n_gran:,} granules "
                      f"| {rate:.0f} gran/s | {n_hits:,} flash-hits | ETA {eta:.2f} h")
    ck.close()
    shutil.rmtree(C.STAGE_ROOT, ignore_errors=True)
    C.log(f"scan '{name}' complete: {n_gran:,} granules, {n_hits:,} flash-hits, "
          f"{(time.time()-t_start)/3600:.2f} h")


def plan_fire_windows(fires: pd.DataFrame, lookback_days: int = 10):
    units = set()
    for r in fires.itertuples():
        d = (r.discovery - pd.Timedelta(days=lookback_days)).date()
        end = r.discovery.date()
        while d <= end:
            s = C.primary_sat(d, r.lon)
            if s:
                units.add((s, d.isoformat()))
            d += dt.timedelta(days=1)
    return units


def plan_node_seasons(nodes: pd.DataFrame, months=(5, 9), until: dt.date | None = None):
    """May-Sep of every year from each node's deployment start."""
    until = until or dt.date.today()
    units = set()
    for r in nodes.itertuples():
        start = pd.Timestamp(r.first_data).date()
        for y in range(start.year, until.year + 1):
            d = max(dt.date(y, months[0], 1), start)
            end = min(dt.date(y, months[1], 30), until)
            while d <= end:
                s = C.primary_sat(d, float(r.lon))
                if s:
                    units.add((s, d.isoformat()))
                d += dt.timedelta(days=1)
    return units


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="glm")
    ap.add_argument("--procs", type=int, default=16)
    ap.add_argument("--numworkers", type=int, default=16)
    ap.add_argument("--plan", required=True, help="parquet with columns sat,date")
    ap.add_argument("--targets", required=True, help="parquet with key,kind,ref,lat,lon,radius_km")
    args = ap.parse_args()

    plan_df = pd.read_parquet(args.plan)
    targets = pd.read_parquet(args.targets)
    plan = [(int(r.sat), str(r.date)) for r in plan_df.itertuples()]
    C.log(f"targets: {len(targets)} ({(targets.kind=='node').sum()} nodes, "
          f"{(targets.kind=='fire').sum()} fires)")
    run(plan, targets, args.name, procs=args.procs, numworkers=args.numworkers)
    C.log(f"SCAN {args.name} DONE — safe to shelve")


if __name__ == "__main__":
    main()
