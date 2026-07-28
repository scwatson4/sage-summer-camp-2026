#!/usr/bin/env python3
"""Phase 1a — the fire inventory that anchors the GLM scans.

Every natural-cause WFIGS incident since 2021 within 35 km of a Phase-0 node
(deployed W/V node with a microphone or camera and a GPS fix), de-duplicated
across nodes, with the distance to every node that saw it.

Also prints the GLM work-unit estimate for Phase 1b, which is what actually
costs money: because LCFA granules are full-disk, the scan cost is the size of
the UNION of (satellite, date, hour) work units over all fire windows — not
the number of fires.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C
import wfigs

RADIUS_KM = 35.0
SINCE = "2021-01-01"
LOOKBACK_DAYS = 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius-km", type=float, default=RADIUS_KM)
    ap.add_argument("--since", default=SINCE)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    args = ap.parse_args()

    C.log("Phase 1a — WFIGS fire inventory")
    nodes = C.node_table()
    nodes = nodes[(nodes.phase == "Deployed") & (nodes.mic | nodes.cam)]
    geo = nodes[nodes.lat.notna() & nodes.lon.notna()].copy()
    C.log(f"nodes: {len(nodes)} deployed with mic/cam; {len(geo)} have GPS "
          f"({len(nodes) - len(geo)} without — cannot be fire-matched)")

    def fetch(row):
        dlat, dlon = C.bbox_pad_deg(row.lat, args.radius_km)
        return row.vsn, wfigs.fires_in_bbox(row.lat, row.lon, dlat, dlon,
                                            since=args.since)

    raw = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch, r): r.vsn for r in geo.itertuples()}
        for i, f in enumerate(as_completed(futs), 1):
            vsn = futs[f]
            try:
                v, rows = f.result()
                raw[v] = rows
            except Exception as exc:
                C.log(f"  WFIGS {vsn} failed: {exc}")
                raw[vsn] = []
            if i % 20 == 0:
                C.log(f"  WFIGS queried {i}/{len(futs)} nodes")

    allrows = [r for rows in raw.values() for r in rows]
    C.log(f"raw WFIGS records in all node boxes: {len(allrows)}")
    fires = wfigs.normalise(allrows)
    C.log(f"unique incidents with usable coords: {len(fires)}")
    if len(fires):
        bad = fires[fires.coord_source == "geometry"]
        C.log(f"  coords from geometry fallback (initial point missing/implausible): {len(bad)}")

    # exact distance from every fire to every node; keep pairs within radius
    nl = geo.lat.to_numpy(); no = geo.lon.to_numpy(); nv = geo.vsn.to_numpy()
    d = C.haversine_km(fires.lat.to_numpy()[:, None], fires.lon.to_numpy()[:, None],
                       nl[None, :], no[None, :])
    fi, ni = np.nonzero(d <= args.radius_km)
    pairs = pd.DataFrame({
        "fire_id": fires.fire_id.to_numpy()[fi],
        "vsn": nv[ni],
        "dist_node_km": d[fi, ni],
    })
    C.log(f"(fire, node) pairs within {args.radius_km:g} km: {len(pairs)}")

    fires = fires[fires.fire_id.isin(pairs.fire_id)].reset_index(drop=True)
    nearest = pairs.sort_values("dist_node_km").groupby("fire_id").first().reset_index()
    fires = fires.merge(nearest.rename(columns={"vsn": "nearest_vsn",
                                                "dist_node_km": "nearest_node_km"}),
                        on="fire_id", how="left")
    fires["n_nodes_within"] = fires.fire_id.map(pairs.groupby("fire_id").size())

    natural = fires[fires.cause.str.strip().str.lower() == "natural"].copy()
    C.log(f"ALL incidents near a node: {len(fires)}   NATURAL-cause: {len(natural)}")
    if len(fires):
        C.log("  cause breakdown: " +
              ", ".join(f"{k}={v}" for k, v in fires.cause.value_counts().items()))

    C.CATALOG.mkdir(parents=True, exist_ok=True)
    fires.to_parquet(C.CATALOG / "fires_all.parquet", index=False)
    natural.to_parquet(C.CATALOG / "fires_natural.parquet", index=False)
    pairs.to_parquet(C.CATALOG / "fire_node_pairs.parquet", index=False)
    C.log("wrote catalog/fires_all.parquet, fires_natural.parquet, fire_node_pairs.parquet")

    if not len(natural):
        C.log("no natural-cause fires — nothing to scan")
        return

    # -------- GLM work-unit estimate (the number that sets the budget) ------
    natural = natural.sort_values("discovery")
    C.log(f"natural-cause fire window: {natural.discovery.min():%Y-%m-%d} .. "
          f"{natural.discovery.max():%Y-%m-%d}")
    C.log(f"  by year: " + ", ".join(
        f"{y}={n}" for y, n in natural.discovery.dt.year.value_counts().sort_index().items()))
    C.log(f"  states: " + ", ".join(
        f"{k}={v}" for k, v in natural.POOState.value_counts().head(12).items()))

    units_primary, units_dual = set(), set()
    for r in natural.itertuples():
        d1 = (r.discovery - pd.Timedelta(days=args.lookback_days)).date()
        d2 = r.discovery.date()
        day = d1
        while day <= d2:
            east, west = C.sats_for_date(day)
            prim = C.primary_sat(day, r.lon)
            if prim:
                units_primary.add((prim, day))
            for s in (east, west):
                if s:
                    units_dual.add((s, day))
            day += dt.timedelta(days=1)

    for label, u in (("primary-satellite", units_primary), ("dual-satellite", units_dual)):
        gran = len(u) * 4320
        C.log(f"  {label}: {len(u)} satellite-days -> {len(u)*24} hour-units, "
              f"~{gran:,} granules, ~{gran/320/3600:.1f} h at 320 granules/s")

    est = pd.DataFrame(sorted(units_primary), columns=["sat", "date"])
    est.to_parquet(C.CATALOG / "phase1_scan_plan.parquet", index=False)
    C.log(f"wrote catalog/phase1_scan_plan.parquet ({len(est)} satellite-days)")
    C.log("PHASE 1a DONE — fire inventory complete")


if __name__ == "__main__":
    main()
