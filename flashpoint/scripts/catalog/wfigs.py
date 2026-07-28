"""WFIGS wildfire records for the catalog.

Layer gotchas (carried over from scripts/wfigs_crossref.py and re-verified
2026-07-27): use the `WFIGS_Incident_Locations` layer — the similarly named
variants 400 out; keep only the timestamp predicate in `where` and filter
FireCause client-side; and sanity-check coordinates, because some records
carry an InitialLatitude/Longitude far from the incident geometry.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

BASE = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
        "WFIGS_Incident_Locations/FeatureServer/0/query")

OUT_FIELDS = ",".join([
    "OBJECTID", "IncidentName", "FireDiscoveryDateTime", "ControlDateTime",
    "FireCause", "FireCauseGeneral", "FireCauseSpecific", "IncidentSize",
    "InitialLatitude", "InitialLongitude", "POOState", "POOCounty",
    "IrwinID", "UniqueFireIdentifier", "IncidentTypeCategory",
])


def _get(url, retries=4, timeout=120):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "flashpoint-catalog"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"WFIGS request failed after {retries} tries: {last}")


def fires_in_bbox(lat, lon, half_deg_lat, half_deg_lon, since="2021-01-01",
                  until=None, page=1000):
    """All incidents whose point falls in the bbox, paged. Cause filtered later."""
    where = f"FireDiscoveryDateTime >= timestamp '{since} 00:00:00'"
    if until:
        where += f" AND FireDiscoveryDateTime < timestamp '{until} 00:00:00'"
    rows, offset = [], 0
    while True:
        params = {
            "where": where,
            "geometry": f"{lon-half_deg_lon},{lat-half_deg_lat},"
                        f"{lon+half_deg_lon},{lat+half_deg_lat}",
            "geometryType": "esriGeometryEnvelope", "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": OUT_FIELDS, "returnGeometry": "true",
            "f": "json", "resultRecordCount": str(page), "resultOffset": str(offset),
        }
        res = _get(BASE + "?" + urllib.parse.urlencode(params))
        if "error" in res:
            raise RuntimeError(f"WFIGS error: {res['error'].get('message')}")
        feats = res.get("features", [])
        for f in feats:
            a = dict(f["attributes"])
            g = f.get("geometry") or {}
            a["_geom_lat"], a["_geom_lon"] = g.get("y"), g.get("x")
            rows.append(a)
        if len(feats) < page or not res.get("exceededTransferLimit", False):
            if len(feats) < page:
                break
        offset += page
        if offset > 20000:
            break
    return rows


def normalise(rows, max_coord_disagree_km=25.0):
    """One row per incident with a trusted (lat, lon) and a UTC discovery time.

    Prefers InitialLatitude/Longitude (the reported point of origin, which is
    what matched the documented Kitten distance) but falls back to the incident
    geometry when the initial point is missing or implausibly far from it.
    """
    from common import haversine_km

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["OBJECTID"])

    ini_lat = pd.to_numeric(df.get("InitialLatitude"), errors="coerce")
    ini_lon = pd.to_numeric(df.get("InitialLongitude"), errors="coerce")
    geo_lat = pd.to_numeric(df.get("_geom_lat"), errors="coerce")
    geo_lon = pd.to_numeric(df.get("_geom_lon"), errors="coerce")

    valid_ini = (ini_lat.between(-90, 90) & ini_lon.between(-180, 180)
                 & ini_lat.notna() & ini_lon.notna()
                 & ~((ini_lat == 0) & (ini_lon == 0)))
    valid_geo = (geo_lat.between(-90, 90) & geo_lon.between(-180, 180)
                 & geo_lat.notna() & geo_lon.notna())

    disagree = pd.Series(np.nan, index=df.index)
    both = valid_ini & valid_geo
    if both.any():
        disagree.loc[both] = haversine_km(ini_lat[both], ini_lon[both],
                                          geo_lat[both], geo_lon[both])

    use_ini = valid_ini & (~both | (disagree <= max_coord_disagree_km))
    df["lat"] = np.where(use_ini, ini_lat, np.where(valid_geo, geo_lat, np.nan))
    df["lon"] = np.where(use_ini, ini_lon, np.where(valid_geo, geo_lon, np.nan))
    df["coord_source"] = np.where(use_ini, "initial",
                                  np.where(valid_geo, "geometry", "none"))
    df["coord_disagree_km"] = disagree

    df["discovery"] = pd.to_datetime(df["FireDiscoveryDateTime"], unit="ms", utc=True)
    df["control"] = pd.to_datetime(df.get("ControlDateTime"), unit="ms", utc=True,
                                   errors="coerce")
    df["cause"] = df.get("FireCause").fillna("").astype(str)
    df["size_acres"] = pd.to_numeric(df.get("IncidentSize"), errors="coerce")
    df["name"] = df.get("IncidentName").fillna("").astype(str)
    df["fire_id"] = (df.get("IrwinID").fillna("").astype(str)
                     .where(lambda s: s.str.len() > 0,
                            df.get("UniqueFireIdentifier").fillna("").astype(str))
                     .where(lambda s: s.str.len() > 0,
                            "OBJ" + df["OBJECTID"].astype(str)))

    keep = ["fire_id", "name", "discovery", "control", "cause", "FireCauseGeneral",
            "FireCauseSpecific", "size_acres", "lat", "lon", "coord_source",
            "coord_disagree_km", "POOState", "POOCounty", "IncidentTypeCategory",
            "OBJECTID"]
    out = df[[c for c in keep if c in df.columns]].copy()
    return out[out.lat.notna() & out.discovery.notna()].reset_index(drop=True)
