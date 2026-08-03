"""Screen the 448 ranked (fire, node) study candidates against Census
American Indian / Alaska Native / Native Hawaiian (AIANNH) area boundaries.

WHY THIS EXISTS
---------------
The catalog ranks (fire, node) pairs for retrospective follow-up. Publishing a
place-identified ranking without knowing whether it touches tribal lands would
be careless: the nodes sit somewhere, the fires burned somewhere, and those
somewheres have governments. This script answers "where, exactly" so the
question can be raised with the right people before anything is released.

WHAT IT IS NOT
--------------
A screening tool, not a legal determination. Census AIANNH polygons cover
federally and state-recognized reservations, off-reservation trust land,
Hawaiian home lands, and statistical areas. They do NOT capture ceded
territory, off-reservation treaty rights (the 1837/1842 Lake Superior Chippewa
cessions are the live example here), ancestral lands, or cultural sites. A
node outside every polygon may still sit on land where a nation holds
usufructuary rights. Proximity is not jurisdiction, and neither is absence
from a shapefile.

Boundaries: US Census Bureau cartographic boundary file cb_2023_us_aiannh_500k
(EPSG:4269). Distances computed in EPSG:5070 (Albers equal-area, CONUS); all
448 candidate pairs fall in CONUS states, so no HI/AK reprojection is needed.

Usage:  python scripts/catalog/tribal_lands_screen.py [--aiannh DIR] [--json OUT]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

CATALOG = pathlib.Path(__file__).resolve().parents[2] / "catalog"
CANDIDATES = CATALOG / "study_candidates.parquet"
AIANNH_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_aiannh_500k.zip"
)
EQUAL_AREA = "EPSG:5070"

# LSAD codes that denote legally defined land rather than a statistical area.
# 86 reservation + off-reservation trust land, 85 state reservation,
# 79 Hawaiian home land, 81/84/87/88/89/90 other legal designations.
LEGAL_LSAD = {"79", "81", "84", "85", "86", "87", "88", "89", "90"}


def load_areas(aiannh_dir: pathlib.Path):
    import geopandas as gpd

    if not aiannh_dir.exists():
        sys.exit(
            f"AIANNH boundaries not found at {aiannh_dir}.\n"
            f"Download and unzip: {AIANNH_URL}"
        )
    g = gpd.read_file(aiannh_dir)
    g["kind"] = g["LSAD"].apply(lambda x: "legal" if x in LEGAL_LSAD else "statistical")
    return g.to_crs(EQUAL_AREA)


def to_points(df, lat_col, lon_col):
    import geopandas as gpd
    from shapely.geometry import Point

    geom = [Point(x, y) for x, y in zip(df[lon_col], df[lat_col])]
    return gpd.GeoDataFrame(df.copy(), geometry=geom, crs="EPSG:4269").to_crs(EQUAL_AREA)


def screen(aiannh_dir: pathlib.Path):
    import geopandas as gpd

    areas = load_areas(aiannh_dir)
    union = areas.geometry.union_all()
    pairs = pd.read_parquet(CANDIDATES)

    nodes = pairs[["vsn", "node_lat", "node_lon"]].drop_duplicates("vsn").reset_index(drop=True)
    node_pts = to_points(nodes, "node_lat", "node_lon")
    fire_pts = to_points(pairs, "fire_lat", "fire_lon")

    cols = ["NAMELSAD", "LSAD", "kind", "geometry"]
    node_in = gpd.sjoin(node_pts, areas[cols], how="left", predicate="within")
    fire_in = gpd.sjoin(fire_pts, areas[cols], how="left", predicate="within")

    node_pts["km_to_tribal"] = [p.distance(union) / 1000 for p in node_pts.geometry]
    fire_pts["km_to_tribal"] = [p.distance(union) / 1000 for p in fire_pts.geometry]
    node_pts["nearest_area"] = [
        areas.loc[areas.distance(p).idxmin(), "NAMELSAD"] for p in node_pts.geometry
    ]

    on_land = node_in[node_in["NAMELSAD"].notna()]
    fires_on = fire_in[fire_in["NAMELSAD"].notna()]

    return {
        "n_pairs": int(len(pairs)),
        "n_nodes": int(len(nodes)),
        "nodes_on_tribal_land": on_land[["vsn", "NAMELSAD", "LSAD"]].to_dict("records"),
        "fires_on_tribal_land": int(len(fires_on)),
        "fires_within_km": {
            str(t): int((fire_pts["km_to_tribal"] <= t).sum()) for t in (1, 5, 10, 35)
        },
        "fire_median_km": round(float(fire_pts["km_to_tribal"].median()), 1),
        "node_distances": node_pts[["vsn", "km_to_tribal", "nearest_area"]]
        .sort_values("km_to_tribal")
        .round({"km_to_tribal": 3})
        .to_dict("records"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aiannh", type=pathlib.Path, required=True,
                    help="directory holding the unzipped cb_2023_us_aiannh_500k shapefile")
    ap.add_argument("--json", type=pathlib.Path, help="write results as JSON")
    args = ap.parse_args()

    r = screen(args.aiannh)

    print(f"Ranked pairs screened: {r['n_pairs']}  ({r['n_nodes']} distinct nodes)\n")
    print(f"NODES ON TRIBAL LAND: {len(r['nodes_on_tribal_land'])} of {r['n_nodes']}")
    for n in r["nodes_on_tribal_land"]:
        print(f"  {n['vsn']}  {n['NAMELSAD']}")
    print(f"\nFIRES INSIDE TRIBAL AREAS: {r['fires_on_tribal_land']} of {r['n_pairs']} pairs")
    for t, n in r["fires_within_km"].items():
        print(f"  within {t:>2} km: {n}")
    print(f"  median distance: {r['fire_median_km']} km")
    print("\nReminder: screening only. Ceded territory, off-reservation treaty rights,")
    print("ancestral lands, and cultural sites are not in these boundaries.")

    if args.json:
        import json
        args.json.write_text(json.dumps(r, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
