#!/usr/bin/env python3
"""Build the unified GLM scan plan (Phase 1 fire windows + Phase 2 node seasons).

Phase-2 node selection is data-driven rather than hand-listed: a node qualifies
if it is deployed, microphone-equipped, has a GPS fix, and has at least one
natural-cause WFIGS fire within 35 km since 2021 (i.e. it is genuinely in fire
country). See catalog/REPORT.md for why the set is then restricted to the
GOES-West track.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C
import scan_engine as E

WEST_LON_CUT = -101.0     # nodes west of this are best viewed by GOES-West


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-days", type=int, default=10)
    ap.add_argument("--radius-km", type=float, default=30.0)
    ap.add_argument("--fire-radius-km", type=float, default=35.0)
    ap.add_argument("--include-east", action="store_true",
                    help="also scan the GOES-East track for eastern mic nodes")
    ap.add_argument("--until", default=None)
    ap.add_argument("--census-only", action="store_true",
                    help="refresh the Phase-2 node set without rewriting scan_plan")
    args = ap.parse_args()

    until = dt.date.fromisoformat(args.until) if args.until else dt.date.today()

    fires = pd.read_parquet(C.CATALOG / "fires_natural.parquet")
    pairs = pd.read_parquet(C.CATALOG / "fire_node_pairs.parquet")
    inv = pd.read_parquet(C.CATALOG / "node_inventory.parquet")

    geo = inv[inv.lat.notna() & inv.lon.notna()].copy()
    C.log(f"nodes with GPS: {len(geo)}   natural-cause fires: {len(fires)}")

    # ---- Phase-2 node set --------------------------------------------------
    # "Microphone-equipped" is taken from the ARCHIVE, not the manifest. The
    # manifest's Microphone capability is a poor proxy for what is actually
    # recorded: fleet-wide, 97 nodes claim a mic but only 64 ever publish
    # audio, while V040, V041, W021 and W068 publish audio with no mic listed.
    # Selecting on the manifest alone both misses real recorders and admits
    # nodes that have never captured a second of sound.
    records_audio = pd.Series(dtype=bool)
    cov_path = C.CATALOG / "node_coverage.parquet"
    if cov_path.exists():
        cov = pd.read_parquet(cov_path)
        if "bucket" in cov.columns:
            records_audio = cov[cov.bucket == "audio"].groupby("vsn").n_uploads.sum() > 0

    near = pairs[pairs.fire_id.isin(fires.fire_id)]
    fire_counts = near.groupby("vsn").fire_id.nunique()
    nearest = near.groupby("vsn").dist_node_km.min()

    geo = geo.copy()
    geo["records_audio"] = geo.vsn.map(records_audio).fillna(False).astype(bool)
    p2 = geo[(geo.mic | geo.records_audio) & geo.vsn.isin(fire_counts.index)].copy()
    p2["n_natural_fires"] = p2.vsn.map(fire_counts)
    p2["nearest_fire_km"] = p2.vsn.map(nearest)
    p2 = p2.sort_values(["n_natural_fires", "nearest_fire_km"],
                        ascending=[False, True]).reset_index(drop=True)
    # Track by the actual viewing rule, not a longitude guess: the GOES
    # East/West crossover sits at the midpoint of the sub-satellite longitudes
    # (-106.2), so a node at -105 is EAST-viewed and pulls in a whole extra
    # satellite's worth of dates.
    ref = dt.date(2024, 7, 1)
    p2["track"] = ["WEST" if C.primary_sat(ref, lo) in (17, 18) else "EAST"
                   for lo in p2.lon]
    C.log(f"mic nodes in fire country: {len(p2)} "
          f"(WEST={int((p2.track=='WEST').sum())}, EAST={int((p2.track=='EAST').sum())})")

    sel = p2 if args.include_east else p2[p2.track == "WEST"]
    C.log(f"Phase-2 census nodes ({len(sel)}): {', '.join(sel.vsn)}")

    # ---- plans -------------------------------------------------------------
    u1 = E.plan_fire_windows(fires, lookback_days=args.lookback_days)
    u2 = E.plan_node_seasons(sel, until=until)
    union = u1 | u2
    for label, u in (("phase1 fire windows", u1), ("phase2 node seasons", u2),
                     ("UNION (scanned once)", union)):
        C.log(f"  {label:22s}: {len(u):5d} satellite-days  {len(u)*4320:>11,} granules "
              f" ~{len(u)*4320/414/3600:.2f} h at 414 granules/s")
    C.log(f"  union saves {len(u1)+len(u2)-len(union)} satellite-days "
          f"({(len(u1)+len(u2)-len(union))*4320:,} granules) vs scanning separately")

    targets = E.build_targets(fires, geo, radius_km=args.radius_km)
    plan = pd.DataFrame(sorted(union), columns=["sat", "date"])

    if not args.census_only:
        plan.to_parquet(C.CATALOG / "scan_plan.parquet", index=False)
        targets.to_parquet(C.CATALOG / "scan_targets.parquet", index=False)
    else:
        C.log("--census-only: scan_plan.parquet / scan_targets.parquet left untouched")
    sel.to_parquet(C.CATALOG / "phase2_nodes.parquet", index=False)
    p2.to_parquet(C.CATALOG / "fire_country_mic_nodes.parquet", index=False)
    C.log(f"wrote phase2_nodes.parquet ({len(sel)} nodes)"
          + ("" if args.census_only else
             f", scan_plan.parquet ({len(plan)} units), "
             f"scan_targets.parquet ({len(targets)})"))


if __name__ == "__main__":
    main()
