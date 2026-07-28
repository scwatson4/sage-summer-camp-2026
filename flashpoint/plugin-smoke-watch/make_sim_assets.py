#!/usr/bin/env python3
"""Bake the offline-demo sim assets from the full-res W097 panorama.

Downscales agent/sim-panoramas/w097-pano-A-day-plume.jpg (11520x2160, ~5 MB)
to a 1280px-wide JPEG small enough to live in the plugin build context, and
copies sectors.json alongside. The SimGateway maps pan 0-360 to image width,
so the sector->pan geometry survives the downscale untouched (sectors.json
width/height fields describe the ORIGINAL; the gateway reads size from the
image itself).

Run from the plugin dir:  python3 make_sim_assets.py
Commit sim-assets/ — the container demo depends on it.
"""
import json
import pathlib

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "agent" / "sim-panoramas"
OUT = HERE / "sim-assets"
TARGET_W = 1280


def main():
    OUT.mkdir(exist_ok=True)
    im = Image.open(SRC / "w097-pano-A-day-plume.jpg")
    small = im.resize((TARGET_W, round(im.height * TARGET_W / im.width)),
                      Image.LANCZOS)
    pano = OUT / "panorama.jpg"
    small.save(pano, quality=85, optimize=True)
    sectors = json.loads((SRC / "sectors.json").read_text())
    (OUT / "sectors.json").write_text(json.dumps(sectors, indent=1))
    kb = pano.stat().st_size / 1024
    print(f"{pano.name}: {im.size} -> {small.size}, {kb:.0f} KB "
          f"(full-res original stays in agent/sim-panoramas/)")
    assert kb < 500, "panorama too big for the build context"


if __name__ == "__main__":
    main()
