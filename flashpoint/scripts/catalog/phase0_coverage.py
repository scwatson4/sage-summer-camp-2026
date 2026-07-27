#!/usr/bin/env python3
"""Phase 0 — node inventory and archive coverage.

For every DEPLOYED W/V node carrying a microphone or camera, establish:
  * deployment start  = first datapoint the node ever published
  * archive coverage  = upload counts per task per day (rolled up per month)

Why it is built this way (measured on the live API, 2026-07-27):
  * A narrow query (one node, one month, one task) returns in ~0.1-4 s. A
    fleet-wide or multi-year query times out — see CLAUDE.md gotchas.
  * The server-side aggregation (`experimental_func=count`, window=1d) groups
    by every meta field, so it is ~0.1 s for tasks with a constant
    `meta.filename` (audio-sampler: 'sample.flac') but explodes to ~850k rows
    for tasks with a unique filename per record (ptz-yolo). Those tasks are
    counted from the raw rows instead, which is ~30x faster for them.

Outputs
  catalog/node_coverage.parquet   one row per (vsn, task, day) with n_uploads
  catalog/node_inventory.parquet  one row per node: capabilities, GPS, start
Both are checkpointed per (vsn, task, month) so a restart resumes.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import re
import itertools
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import sage_data_client

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import common as C

# Tasks whose meta.filename is unique per record: aggregation explodes, so the
# raw rows are counted instead. Detected automatically as well (see count_month).
RAW_COUNT_TASKS = {"ptz-yolo"}

# Media-capture tasks — the ones that answer "was this node recording?".
#
# Prefix matching was not enough: the live archive spells the same plugins many
# ways. `audiosampler` (259 shards) is MORE common than `audio-sampler` (151),
# and the image sampler appears as imagesampler-top, image-sampler-bottom and
# fast-imagesampler. Classify with patterns, and keep raw capture separate from
# camera-derived inference — both prove the sensor was live, but only raw
# capture can be re-listened to or re-examined in a retrospective study.
CAPTURE_PATTERNS = {
    "audio": re.compile(r"audio-?sampler", re.I),
    "image": re.compile(r"(fast-)?image-?sampler|get-images|mobotix.*scan|car-sampler"
                        r"|panda-rosbag-cam", re.I),
    "ptz": re.compile(r"ptz-yolo", re.I),
}
DERIVED_PATTERN = re.compile(
    r"cloud-motion|motion-analysis|motion-detection|object-counter|smoke-detector"
    r"|image-captioner|weather-classification|fire-detection|bioclip|yolo|birdnet"
    r"|surface-water|moondream", re.I)


def media_bucket(task: str) -> str:
    """audio | image | ptz | derived | non_media."""
    t = task or ""
    for name, pat in CAPTURE_PATTERNS.items():
        if pat.search(t):
            return name
    return "derived" if DERIVED_PATTERN.search(t) else "non_media"


def is_media_task(task: str) -> bool:
    return media_bucket(task) != "non_media"

_print_lock = threading.Lock()


def tlog(msg):
    with _print_lock:
        C.log(msg)


def month_bounds(y, m):
    start = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return start, dt.datetime(ny, nm, 1, tzinfo=dt.timezone.utc)


def months_between(start_date: dt.date, end_date: dt.date):
    y, m = start_date.year, start_date.month
    while (y, m) <= (end_date.year, end_date.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


# --------------------------------------------------------------- step A ----

def first_datapoint(vsn: str) -> dt.datetime | None:
    """Earliest record the node ever published (deployment start proxy)."""
    for filt in ({"vsn": vsn, "name": "sys.uptime"},
                 {"vsn": vsn, "name": "env.temperature"},
                 {"vsn": vsn}):
        try:
            df = sage_data_client.query(
                start="2018-01-01T00:00:00Z",
                end=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                filter=filt, head=1)
            if len(df):
                return df["timestamp"].iloc[0].to_pydatetime()
        except Exception:
            continue
    return None


# --------------------------------------------------------------- step B ----

def fleet_task_universe(samples=24) -> set[str]:
    """Task names seen anywhere on the fleet, sampled across the archive.

    One fleet-wide `name=upload` hour is ~7-11 s and lists every task actively
    uploading in that hour; sampling across seasons and years captures the
    stable task families (audio-sampler, imagesampler-*, ptz-yolo, ...).
    """
    tasks = set()
    windows = []
    for year in range(2021, 2027):
        for month in (2, 6, 7, 11):
            if (year, month) > (2026, 7):
                continue
            windows.append(dt.datetime(year, month, 15, 20, tzinfo=dt.timezone.utc))
    windows = windows[:samples]

    def probe(t0):
        try:
            df = sage_data_client.query(
                start=t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end=(t0 + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                filter={"name": "upload"})
            return set(df["meta.task"].dropna().unique()) if len(df) else set()
        except Exception:
            return set()

    with ThreadPoolExecutor(max_workers=8) as ex:
        for s in ex.map(probe, windows):
            tasks |= s
    return tasks


def node_tasks(vsn: str, start: dt.date, end: dt.date) -> set[str]:
    """Tasks this node ever uploaded, probed on a week per year (catches
    node-specific tasks the fleet sampler would miss)."""
    tasks = set()
    for year in range(start.year, end.year + 1):
        w0 = max(dt.datetime(year, 7, 10, tzinfo=dt.timezone.utc),
                 dt.datetime.combine(start, dt.time(), dt.timezone.utc))
        w1 = min(w0 + dt.timedelta(days=7),
                 dt.datetime.combine(end, dt.time(), dt.timezone.utc))
        if w1 <= w0:
            continue
        try:
            df = sage_data_client.query(
                start=w0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end=w1.strftime("%Y-%m-%dT%H:%M:%SZ"),
                filter={"name": "upload", "vsn": vsn})
            if len(df):
                tasks |= set(df["meta.task"].dropna().unique())
        except Exception:
            continue
    return tasks


# --------------------------------------------------------------- step C ----

def count_month(vsn: str, task: str, y: int, m: int) -> pd.DataFrame:
    """Daily upload counts for one (node, task, month). Returns vsn/task/day/n."""
    s, e = month_bounds(y, m)
    ss, es = s.strftime("%Y-%m-%dT%H:%M:%SZ"), e.strftime("%Y-%m-%dT%H:%M:%SZ")
    filt = {"name": "upload", "vsn": vsn, "task": task}
    ndays = calendar.monthrange(y, m)[1]

    if task not in RAW_COUNT_TASKS:
        try:
            df = sage_data_client.query(start=ss, end=es, filter=filt,
                                        experimental_func="count",
                                        experimental_window="1d")
            # Guard: if the group-by exploded, fall through to the raw path.
            if len(df) <= ndays * 40:
                if not len(df):
                    return pd.DataFrame(columns=["vsn", "task", "day", "n_uploads"])
                # The aggregation labels each bucket with the window END, so a
                # row stamped D covers [D-1d, D). Verified against raw rows on
                # 2026-07-27 (W06C audio-sampler: raw 2025-07-01 = 261 uploads
                # appears as the bucket labelled 2025-07-02). Shift back by one
                # day, or every storm-day/recording-day join is off by one.
                g = (df.assign(day=(df["timestamp"] - pd.Timedelta(days=1)).dt.date)
                       .groupby("day")["value"].sum().reset_index())
                g["vsn"], g["task"] = vsn, task
                return g.rename(columns={"value": "n_uploads"})[
                    ["vsn", "task", "day", "n_uploads"]]
        except Exception:
            pass

    df = sage_data_client.query(start=ss, end=es, filter=filt)
    if not len(df):
        return pd.DataFrame(columns=["vsn", "task", "day", "n_uploads"])
    g = (df.assign(day=df["timestamp"].dt.date)
           .groupby("day").size().reset_index(name="n_uploads"))
    g["vsn"], g["task"] = vsn, task
    return g[["vsn", "task", "day", "n_uploads"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit-nodes", type=int, default=0)
    args = ap.parse_args()

    today = dt.date.today()
    ck = C.Checkpoint("phase0")

    C.log("Phase 0 — node inventory & archive coverage")
    nodes = C.node_table()
    deployed = nodes[(nodes.phase == "Deployed") & (nodes.mic | nodes.cam)].copy()
    if args.limit_nodes:
        deployed = deployed.head(args.limit_nodes)
    C.log(f"deployed W/V nodes with mic or camera: {len(deployed)} "
          f"(mic={int(deployed.mic.sum())}, cam={int(deployed.cam.sum())}, "
          f"no-GPS={int(deployed.lat.isna().sum())})")

    # --- Step A: deployment starts -----------------------------------------
    starts = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(first_datapoint, v): v for v in deployed.vsn}
        for i, f in enumerate(as_completed(futs), 1):
            v = futs[f]
            try:
                starts[v] = f.result()
            except Exception as exc:
                starts[v] = None
                tlog(f"  start-probe {v} failed: {exc}")
            if i % 25 == 0:
                tlog(f"  deployment starts: {i}/{len(futs)}")
    deployed["first_data"] = deployed.vsn.map(starts)
    live = deployed[deployed.first_data.notna()].copy()
    C.log(f"nodes with any published data: {len(live)}/{len(deployed)}")
    C.log(f"earliest deployment: {live.first_data.min()}  latest: {live.first_data.max()}")

    # --- Step B: task discovery --------------------------------------------
    C.log("discovering task universe (fleet sample + per-node probes)...")
    universe = fleet_task_universe()
    C.log(f"  fleet task universe: {len(universe)} tasks")

    per_node = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(node_tasks, r.vsn, r.first_data.date(), today): r.vsn
                for r in live.itertuples()}
        for i, f in enumerate(as_completed(futs), 1):
            v = futs[f]
            try:
                per_node[v] = f.result()
            except Exception:
                per_node[v] = set()
            if i % 25 == 0:
                tlog(f"  node task probes: {i}/{len(futs)}")
    extra = set().union(*per_node.values()) - universe if per_node else set()
    if extra:
        C.log(f"  node-specific tasks not in fleet sample: {sorted(extra)}")
    universe |= extra

    # Only chase tasks that plausibly exist on that node: its own probe hits,
    # plus the media families (a node may capture media outside probe weeks).
    media_universe = {t for t in universe if is_media_task(t)}
    C.log(f"  media-capture tasks tracked: {len(media_universe)} of {len(universe)}")

    # --- Step C: per (node, task, month) daily counts ----------------------
    units = []
    for r in live.itertuples():
        cand = (per_node.get(r.vsn, set()) | media_universe)
        for task in sorted(cand):
            for y, m in months_between(r.first_data.date(), today):
                units.append((r.vsn, task, y, m))
    todo = [u for u in units if f"{u[0]}|{u[1]}|{u[2]}-{u[3]:02d}" not in ck]
    C.log(f"work units (vsn,task,month): {len(units)}  "
          f"done={len(units) - len(todo)}  remaining={len(todo)}")

    done = 0
    lock = threading.Lock()

    def work(u):
        vsn, task, y, m = u
        uid = f"{vsn}|{task}|{y}-{m:02d}"
        try:
            df = count_month(vsn, task, y, m)
        except Exception as exc:
            return uid, None, str(exc)[:120]
        return uid, df, None

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, u): u for u in todo}
        for f in as_completed(futs):
            uid, df, err = f.result()
            with lock:
                done += 1
                if err:
                    tlog(f"  ERR {uid}: {err}")
                else:
                    if df is not None and len(df):
                        C.write_shard("phase0", uid, df)
                    ck.mark(uid, rows=0 if df is None else len(df))
                if done % 500 == 0:
                    tlog(f"  counted {done}/{len(todo)} node-task-months")

    ck.close()

    # --- assemble ----------------------------------------------------------
    cov = C.read_shards("phase0")
    C.CATALOG.mkdir(parents=True, exist_ok=True)
    if len(cov):
        cov["day"] = pd.to_datetime(cov["day"])
        cov = cov.sort_values(["vsn", "task", "day"]).reset_index(drop=True)
        # Drop zero-upload days. The aggregation returns a bucket for EVERY
        # day of the queried month, active or not, so a bare row-count (e.g.
        # nunique of day) would read empty months as full coverage — and would
        # emit future-dated rows for the current month.
        cov = cov[cov["n_uploads"] > 0].copy()
        cov["bucket"] = cov["task"].map(media_bucket)
        cov["is_media"] = cov["bucket"] != "non_media"
        cov["is_capture"] = cov["bucket"].isin(("audio", "image", "ptz"))
        cov.to_parquet(C.CATALOG / "node_coverage.parquet", index=False)
        C.log(f"wrote catalog/node_coverage.parquet  rows={len(cov)} "
              f"nodes={cov.vsn.nunique()} tasks={cov.task.nunique()}")

        monthly = (cov.assign(month=cov.day.dt.to_period("M").astype(str))
                      .groupby(["vsn", "task", "month"], as_index=False)
                      .agg(n_uploads=("n_uploads", "sum"),
                           active_days=("day", "nunique")))
        monthly.to_parquet(C.CATALOG / "node_coverage_monthly.parquet", index=False)
        C.log(f"wrote catalog/node_coverage_monthly.parquet rows={len(monthly)}")

    inv = live.copy()
    inv["first_data"] = pd.to_datetime(inv["first_data"], utc=True)
    if len(cov):
        last = cov.groupby("vsn").day.max()
        med = cov[cov.is_media].groupby("vsn").n_uploads.sum()
        inv["last_upload"] = inv.vsn.map(last)
        inv["media_uploads_total"] = inv.vsn.map(med).fillna(0).astype("int64")
    inv.to_parquet(C.CATALOG / "node_inventory.parquet", index=False)
    C.log(f"wrote catalog/node_inventory.parquet rows={len(inv)}")
    C.log("PHASE 0 DONE — safe to shelve")


if __name__ == "__main__":
    main()
