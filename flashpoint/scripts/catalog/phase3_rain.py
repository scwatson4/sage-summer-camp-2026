#!/usr/bin/env python3
"""Phase 3a — hourly rain-gauge traces for the census nodes.

Fetched once per (node, month) at 1-hour buckets so that both UTC-day rain and
storm-window rain can be computed later without re-querying. Checkpointed.

Output: catalog/node_rain_hourly.parquet  (vsn, hour, lo, hi, gauge)
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C
import rain as R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--months", default="4-10",
                    help="inclusive month range; wider than May-Sep so that "
                         "storm windows crossing a season edge are covered")
    args = ap.parse_args()

    mlo, mhi = (int(x) for x in args.months.split("-"))
    C.log(f"Phase 3a — node rain traces (months {mlo}-{mhi})")
    nodes = pd.read_parquet(C.CATALOG / "phase2_nodes.parquet")
    ck = C.Checkpoint("phase3_rain")

    units = []
    today = pd.Timestamp.utcnow().date()
    for r in nodes.itertuples():
        start = pd.Timestamp(r.first_data).date()
        for s, e in R.month_windows(start, today):
            if not (mlo <= s.month <= mhi):
                continue
            if s.date() < start.replace(day=1):
                continue
            units.append((r.vsn, s, e))
    todo = [u for u in units if f"{u[0]}|{u[1]:%Y-%m}" not in ck]
    C.log(f"rain units (node, month): {len(units)}  remaining {len(todo)}")

    def work(u):
        vsn, s, e = u
        acc, name = R.hourly_accum(vsn, s, e)
        if acc is None or not len(acc):
            return u, None
        d = acc.reset_index().rename(columns={"index": "hour"})
        d["vsn"], d["gauge"] = vsn, name
        return u, d

    got = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, u): u for u in todo}
        for i, f in enumerate(as_completed(futs), 1):
            u = futs[f]
            try:
                _, d = f.result()
            except Exception as exc:
                C.log(f"  ERR {u[0]} {u[1]:%Y-%m}: {str(exc)[:100]}")
                continue
            if d is not None and len(d):
                C.write_shard("phase3_rain", f"{u[0]}_{u[1]:%Y-%m}", d)
                got += 1
            ck.mark(f"{u[0]}|{u[1]:%Y-%m}", rows=0 if d is None else len(d))
            if i % 100 == 0:
                C.log(f"  {i}/{len(todo)} node-months ({got} with data)")
    ck.close()

    df = C.read_shards("phase3_rain")
    if len(df):
        # Shards written before rain.py named its index carry "timestamp".
        # pd.concat unions columns, so a mixed set has BOTH and an all-or-
        # nothing rename would leave half the rows with a null hour.
        if "timestamp" in df.columns:
            df["hour"] = (df["hour"].fillna(df["timestamp"])
                          if "hour" in df.columns else df["timestamp"])
            df = df.drop(columns=["timestamp"])
        df = df[df["hour"].notna()]
        df = df.sort_values(["vsn", "hour"]).reset_index(drop=True)
        df.to_parquet(C.CATALOG / "node_rain_hourly.parquet", index=False)
        C.log(f"wrote catalog/node_rain_hourly.parquet rows={len(df):,} "
              f"nodes={df.vsn.nunique()} gauges={sorted(df.gauge.unique())}")
    else:
        C.log("no rain data retrieved")
    C.log("PHASE 3a DONE — rain traces cached")


if __name__ == "__main__":
    main()
