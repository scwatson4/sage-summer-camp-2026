#!/usr/bin/env python3
"""Bake the dashboard's offline assets from live sources.

Produces:
  assets/nodes.json  — slim snapshot of deployed Sage nodes (GPS, mic/cam flags)
  assets/cases.json  — case-study presets with WFIGS fire records near each node

Rerun whenever the fleet or the case list changes:
    python bake_assets.py
Both files are committed so the dashboard works with no network access.
"""
import datetime
import json
import math
import pathlib
import urllib.parse
import urllib.request

ASSETS = pathlib.Path(__file__).resolve().parent / "assets"
MANIFEST = "https://auth.sagecontinuum.org/manifests/?format=json"
WFIGS = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
         "WFIGS_Incident_Locations/FeatureServer/0/query")

# Case presets: node under study, analysis window (UTC), fire-search window,
# and which incidents the handoff plan calls out by name.
CASES = [
    {
        "id": "kitten-fire",
        "title": "Kitten Fire — Moran, WY (flagship)",
        "vsn": "W06C",
        "start": "2025-07-01T00:00:00Z",
        "end": "2025-07-04T00:00:00Z",
        "fire_window": ("2025-07-01", "2025-07-05"),
        "featured_fires": ["Kitten"],
        "audio_task": "audio-sampler",
        "image_tasks": ["imagesampler-top", "imagesampler-bottom",
                        "imagesampler-mobotix", "imagesampler-hanwhaptz"],
        "notes": ("0.32-acre natural-cause fire discovered 2025-07-03 ~6 km from "
                  "W06C (Grand Teton / AMK Ranch). The node captured 779 audio "
                  "clips plus thermal/sky imagery across the storm window — the "
                  "post-hoc thunder-detection flagship."),
    },
    {
        "id": "signal-flat",
        "title": "Signal Flat — Moran, WY",
        "vsn": "W06C",
        "start": "2025-07-24T00:00:00Z",
        "end": "2025-07-27T00:00:00Z",
        "fire_window": ("2025-07-24", "2025-07-28"),
        "featured_fires": ["Signal Flat"],
        "audio_task": "audio-sampler",
        "image_tasks": ["imagesampler-top", "imagesampler-bottom",
                        "imagesampler-mobotix", "imagesampler-hanwhaptz"],
        "notes": ("7.7-acre natural-cause fire discovered 2025-07-26, ~12 km from "
                  "W06C — second event for the same node."),
    },
    {
        "id": "selma-bust",
        "title": "Selma lightning bust — Siskiyou, OR",
        "vsn": "W067",
        "start": "2025-07-06T00:00:00Z",
        "end": "2025-07-09T00:00:00Z",
        "fire_window": ("2025-07-06", "2025-07-10"),
        "featured_fires": ["N Fork Deer Creek", "Holcomb Peak", "Cedar Flat",
                           "Esterly Mine"],
        "audio_task": None,  # audio-sampler was not running on W067 that week
        "image_tasks": ["imagesampler-top", "imagesampler-left",
                        "imagesampler-bottom"],
        "notes": ("Classic lightning-bust: many natural-cause fires discovered "
                  "2025-07-08 within ~35 km of W067. Hourly sky imagery + met "
                  "records (incl. rain accumulation) — a camera+met study; no "
                  "audio that week."),
    },
]

R_DEG = 0.35  # ~35 km search box around the node


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "flashpoint-dashboard"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def bake_nodes():
    rows = []
    for n in get(MANIFEST):
        if n.get("phase") != "Deployed" or not n.get("gps_lat") or not n.get("gps_lon"):
            continue
        sensors = [(s.get("name") or "").lower() for s in n.get("sensors", [])]
        rows.append({
            "vsn": n["vsn"],
            "lat": float(n["gps_lat"]),
            "lon": float(n["gps_lon"]),
            "address": " ".join((n.get("address") or "").split()),
            "mic": any("microphone" in s for s in sensors),
            "cam": any("camera" in s for s in sensors),
        })
    rows.sort(key=lambda r: r["vsn"])
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "source": MANIFEST, "nodes": rows}
    (ASSETS / "nodes.json").write_text(json.dumps(out, indent=1))
    print(f"nodes.json: {len(rows)} deployed nodes with GPS")
    return {r["vsn"]: r for r in rows}


def fires_near(lat, lon, day_from, day_to):
    fields = ("IncidentName,FireDiscoveryDateTime,FireCause,IncidentSize,"
              "InitialLatitude,InitialLongitude,POOState")
    params = {
        "where": (f"FireDiscoveryDateTime >= timestamp '{day_from} 00:00:00' AND "
                  f"FireDiscoveryDateTime <= timestamp '{day_to} 00:00:00'"),
        "geometry": f"{lon - R_DEG},{lat - R_DEG},{lon + R_DEG},{lat + R_DEG}",
        "geometryType": "esriGeometryEnvelope", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
        "returnGeometry": "false", "f": "json", "resultRecordCount": "2000",
    }
    res = get(WFIGS + "?" + urllib.parse.urlencode(params))
    fires = []
    for f in res.get("features", []):
        a = f["attributes"]
        if (a.get("FireCause") or "") != "Natural":
            continue
        flat, flon = a.get("InitialLatitude"), a.get("InitialLongitude")
        if flat is None or flon is None:
            continue
        dx = (flon - lon) * 111.32 * math.cos(math.radians(lat))
        dy = (flat - lat) * 110.54
        km = math.hypot(dx, dy)
        if km > 60:  # junk coordinates guard (see wfigs_crossref.py)
            continue
        t = datetime.datetime.fromtimestamp((a["FireDiscoveryDateTime"] or 0) / 1000,
                                            datetime.timezone.utc)
        fires.append({
            "name": a.get("IncidentName") or "?",
            "discovered": t.isoformat(timespec="seconds"),
            "size_ac": a.get("IncidentSize") or 0,
            "lat": flat, "lon": flon,
            "state": a.get("POOState") or "",
            "dist_km": round(km, 1),
        })
    fires.sort(key=lambda x: x["dist_km"])
    return fires


def bake_cases(nodes):
    cases = []
    for c in CASES:
        node = nodes.get(c["vsn"])
        if node is None:
            print(f"WARNING: {c['vsn']} not in manifest, skipping fire lookup")
            fires = []
        else:
            day_from, day_to = c["fire_window"]
            fires = fires_near(node["lat"], node["lon"], day_from, day_to)
            for f in fires:
                f["featured"] = f["name"] in c["featured_fires"]
        entry = {k: v for k, v in c.items() if k not in ("fire_window", "featured_fires")}
        entry["fires"] = fires
        cases.append(entry)
        print(f"{c['id']}: {len(fires)} natural-cause fires near {c['vsn']}")
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "cases": cases}
    (ASSETS / "cases.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    bake_cases(bake_nodes())
