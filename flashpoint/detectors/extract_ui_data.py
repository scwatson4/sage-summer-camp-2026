#!/usr/bin/env python3
"""Extract the M1 ground truth embedded in ui/index.html into data/kitten_glm.json.

The replay UI carries the real GLM flashes (955, GOES dual-satellite, Jul 2-3
2025 around the Kitten Fire point) and the 22 satellite-anchored thunder
arrivals recovered from W06C's archived clips. Times in the UI are HH:MM:SS UT
on Jul 2 2025, rolling into Jul 3 after midnight; this script makes them
absolute ISO timestamps so the detector eval can use them directly.

Rerun after any ui/index.html update:  python detectors/extract_ui_data.py
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
UI = HERE.parent / "ui" / "index.html"
OUT = HERE / "data" / "kitten_glm.json"

BASE_DAY = "2025-07-02"
NEXT_DAY = "2025-07-03"
ROLLOVER_H = 12  # HH < 12 → after midnight → Jul 3


def absolute(hms):
    day = NEXT_DAY if int(hms[:2]) < ROLLOVER_H else BASE_DAY
    return f"{day}T{hms}Z"


def main():
    html = UI.read_text()
    m = re.search(r"const D\s*=\s*(\{.*?\});\s*\n", html, re.S)
    d = json.loads(m.group(1))
    out = {
        "source": "ui/index.html (M1 handoff 2026-07-23)",
        "node": {"vsn": "W06C", "lat": d["node"][0], "lon": d["node"][1]},
        "fire": {"name": "Kitten", "lat": d["fire"][0], "lon": d["fire"][1]},
        "glm_flashes": [
            {"time": absolute(f["t"]), "lat": f["lat"], "lon": f["lon"],
             "dist_node_km": f["d"]}
            for f in d["flashes"]
        ],
        "thunder_arrivals": [
            {"time": absolute(t["t"]), "range_km": t["d"], "snr": t["snr"]}
            for t in d["thunder"]
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"{OUT.name}: {len(out['glm_flashes'])} GLM flashes, "
          f"{len(out['thunder_arrivals'])} thunder arrivals")


if __name__ == "__main__":
    main()
