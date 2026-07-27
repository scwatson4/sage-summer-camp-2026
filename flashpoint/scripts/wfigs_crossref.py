#!/usr/bin/env python3
"""Cross-reference natural-cause wildfires (NIFC WFIGS) with fire-country Sage nodes.

Layer gotchas (learned 2026-07-21): use WFIGS_Incident_Locations (the similarly named
variants 400 out); put only the timestamp in `where` and filter FireCause client-side;
sanity-check distances (some records carry junk InitialLatitude/Longitude).
"""
import json, math, datetime, urllib.parse, urllib.request

BASE = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
        "WFIGS_Incident_Locations/FeatureServer/0/query")
MANIFEST = "https://auth.sagecontinuum.org/manifests/?format=json"
NODES = ["W084", "W06F", "W06C", "W070", "V023", "W067", "W019", "W045", "W02B", "W069", "W097"]
R_DEG = 0.35  # ~35 km box
SINCE = "2023-01-01"
OUT = ("IncidentName,FireDiscoveryDateTime,FireCause,FireCauseGeneral,"
       "IncidentSize,InitialLatitude,InitialLongitude,POOState")


def get(url):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "flashpoint"}), timeout=60))


def main():
    coord = {n["vsn"]: (float(n["gps_lat"]), float(n["gps_lon"]))
             for n in get(MANIFEST) if n.get("gps_lat") and n.get("gps_lon")}
    for vsn in NODES:
        if vsn not in coord:
            print(f"{vsn}: no GPS in manifest"); continue
        lat, lon = coord[vsn]
        params = {
            "where": f"FireDiscoveryDateTime >= timestamp '{SINCE} 00:00:00'",
            "geometry": f"{lon-R_DEG},{lat-R_DEG},{lon+R_DEG},{lat+R_DEG}",
            "geometryType": "esriGeometryEnvelope", "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects", "outFields": OUT,
            "returnGeometry": "false", "f": "json", "resultRecordCount": "2000"}
        res = get(BASE + "?" + urllib.parse.urlencode(params))
        if "error" in res:
            print(f"{vsn}: API error {res['error'].get('message')}"); continue
        nat = [f["attributes"] for f in res.get("features", [])
               if (f["attributes"].get("FireCause") or "") == "Natural"]
        nat.sort(key=lambda a: -(a.get("IncidentSize") or 0))
        print(f"\n{vsn} ({lat:.3f},{lon:.3f}) — natural-cause fires since {SINCE}: {len(nat)}")
        for a in nat[:6]:
            t = datetime.datetime.utcfromtimestamp((a["FireDiscoveryDateTime"] or 0) / 1000)
            d = ""
            if a.get("InitialLatitude"):
                dx = (a["InitialLongitude"] - lon) * 111.32 * math.cos(math.radians(lat))
                dy = (a["InitialLatitude"] - lat) * 110.54
                km = math.hypot(dx, dy)
                d = f"{km:5.0f} km" if km < 500 else "  bad-coord"
            print(f"   {t:%Y-%m-%d}  {(a.get('IncidentName') or '?')[:30]:<30}"
                  f" {(a.get('IncidentSize') or 0):9.1f} ac {d}")


if __name__ == "__main__":
    main()
