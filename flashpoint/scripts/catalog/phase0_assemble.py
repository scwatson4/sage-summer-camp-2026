#!/usr/bin/env python3
"""Phase 0 mop-up + assembly.

Two jobs, both cheap, neither re-querying anything already checkpointed:

1. Retry exactly the (vsn, task, month) units that errored in a previous run.
   `sage_data_client` calls `urlopen` with no timeout, so a dropped connection
   hangs forever — a full re-run of Phase 0 stalled on 8 such sockets. A global
   socket timeout makes those fail fast and get retried instead.

2. Rebuild catalog/node_coverage.parquet from the shards with the corrected
   classification: drop zero-upload days (the aggregation emits a bucket for
   every day of a queried month, active or not) and tag each task with its
   media bucket.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C
from phase0_coverage import count_month, media_bucket

UNIT_RE = re.compile(r"ERR ([A-Za-z0-9]+)\|([^|]+)\|(\d{4})-(\d{2})")


def failed_units(log_paths):
    seen = set()
    for p in log_paths:
        fp = pathlib.Path(p)
        if not fp.exists():
            continue
        for line in fp.read_text(errors="ignore").splitlines():
            m = UNIT_RE.search(line)
            if m:
                seen.add((m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))
    return sorted(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", nargs="*", default=[
        "/media/volume/Sage-Grande-Flashpoint/work/phase0.log"])
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--skip-retry", action="store_true")
    args = ap.parse_args()

    socket.setdefaulttimeout(args.timeout)
    ck = C.Checkpoint("phase0")

    if not args.skip_retry:
        units = [u for u in failed_units(args.logs)
                 if f"{u[0]}|{u[1]}|{u[2]}-{u[3]:02d}" not in ck]
        C.log(f"retrying {len(units)} previously-failed units "
              f"(socket timeout {args.timeout:g}s)")
        ok = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(count_month, *u): u for u in units}
            for f in as_completed(futs):
                vsn, task, y, m = futs[f]
                uid = f"{vsn}|{task}|{y}-{m:02d}"
                try:
                    df = f.result()
                except Exception as exc:
                    C.log(f"  still failing {uid}: {str(exc)[:90]}")
                    continue
                if len(df):
                    C.write_shard("phase0", uid, df)
                ck.mark(uid, rows=len(df))
                ok += 1
        C.log(f"recovered {ok}/{len(units)}")
    ck.close()

    cov = C.read_shards("phase0")
    C.log(f"shard rows: {len(cov):,}")
    before = len(cov)
    cov = cov[cov["n_uploads"] > 0].copy()
    C.log(f"dropped {before - len(cov):,} zero-upload day rows")

    cov["day"] = pd.to_datetime(cov["day"])
    today = pd.Timestamp.utcnow().normalize().tz_localize(None)
    fut = int((cov.day > today).sum())
    if fut:
        cov = cov[cov.day <= today]
        C.log(f"dropped {fut:,} future-dated rows")

    cov["bucket"] = cov["task"].map(media_bucket)
    cov["is_media"] = cov["bucket"] != "non_media"
    cov["is_capture"] = cov["bucket"].isin(("audio", "image", "ptz"))
    cov = cov.sort_values(["vsn", "task", "day"]).reset_index(drop=True)

    C.CATALOG.mkdir(parents=True, exist_ok=True)
    cov.to_parquet(C.CATALOG / "node_coverage.parquet", index=False)
    C.log(f"wrote catalog/node_coverage.parquet rows={len(cov):,} "
          f"nodes={cov.vsn.nunique()} tasks={cov.task.nunique()}")
    C.log("  buckets: " + ", ".join(
        f"{k}={v:,}" for k, v in cov.groupby('bucket').n_uploads.sum().items()))

    monthly = (cov.assign(month=cov.day.dt.to_period("M").astype(str))
                  .groupby(["vsn", "task", "bucket", "month"], as_index=False)
                  .agg(n_uploads=("n_uploads", "sum"), active_days=("day", "nunique")))
    monthly.to_parquet(C.CATALOG / "node_coverage_monthly.parquet", index=False)
    C.log(f"wrote catalog/node_coverage_monthly.parquet rows={len(monthly):,}")

    inv_path = C.CATALOG / "node_inventory.parquet"
    if inv_path.exists():
        inv = pd.read_parquet(inv_path)
        last = cov.groupby("vsn").day.max()
        capt = cov[cov.is_capture].groupby("vsn").n_uploads.sum()
        inv["last_upload"] = inv.vsn.map(last)
        inv["capture_uploads_total"] = inv.vsn.map(capt).fillna(0).astype("int64")
        inv.to_parquet(inv_path, index=False)
        C.log(f"refreshed catalog/node_inventory.parquet rows={len(inv)}")
    C.log("PHASE 0 DONE — safe to shelve")


if __name__ == "__main__":
    main()
