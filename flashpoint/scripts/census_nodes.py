#!/usr/bin/env python3
"""Fleet census: which deployed nodes have mics/cameras/GPS, grouped by region,
plus co-location clusters (acoustic co-detection viability)."""
import json, math, urllib.request

MANIFEST = "https://auth.sagecontinuum.org/manifests/?format=json"

def main():
    req = urllib.request.Request(MANIFEST, headers={"User-Agent": "flashpoint"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    rows = []
    for n in data:
        if n.get("phase") != "Deployed" or not n.get("gps_lat"):
            continue
        sn = [(s.get("name") or "").lower() for s in n.get("sensors", [])]
        rows.append({
            "vsn": n["vsn"], "lat": float(n["gps_lat"]), "lon": float(n["gps_lon"]),
            "mic": any("microphone" in s for s in sn),
            "cam": any("camera" in s for s in sn),
            "addr": (n.get("address") or "").replace("\n", " ")[:50]})
    mic = [r for r in rows if r["mic"]]
    print(f"deployed w/ GPS: {len(rows)} | with mic: {len(mic)} | mic+cam: {sum(1 for r in rows if r['mic'] and r['cam'])}")

    # link clusters of mic nodes within 12 km (thunder co-detection)
    def dist(a, b):
        dx = (b["lon"] - a["lon"]) * 111.32 * math.cos(math.radians(a["lat"]))
        return math.hypot(dx, (b["lat"] - a["lat"]) * 110.54)
    parent = {r["vsn"]: r["vsn"] for r in mic}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i in range(len(mic)):
        for j in range(i + 1, len(mic)):
            if dist(mic[i], mic[j]) <= 12.0:
                parent[find(mic[i]["vsn"])] = find(mic[j]["vsn"])
    comps = {}
    for r in mic:
        comps.setdefault(find(r["vsn"]), []).append(r)
    print("\nmic clusters (>=3 nodes within 12 km links) — viable thunder-TDOA arrays:")
    for c in sorted(comps.values(), key=len, reverse=True):
        if len(c) < 3:
            continue
        print(f"  [{len(c)} nodes] " + ", ".join(sorted(r['vsn'] for r in c)))
        print(f"     e.g. {c[0]['addr']}")

if __name__ == "__main__":
    main()
