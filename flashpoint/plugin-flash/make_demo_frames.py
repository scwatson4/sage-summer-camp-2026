#!/usr/bin/env python3
"""Synthetic demo batch for the offline smoke test — NOT real lightning.

Writes demo-frames/: 40 grayscale 64x64 JPEGs at 1.0 s synthetic cadence
(filename stem = epoch seconds, e.g. 0001.00.jpg, so sparse_cadence stays
False), night-sky base luma ~30 with mild noise, and exactly two flash
frames (mean luma ~120) at epochs 13.00 s and 29.00 s. The flash light is
scene-wide plus a hot wedge at 50-85 deg (detector angle convention), so
the fisheye azimuth sectoring has a deterministic answer: sector 1 of 8,
center 67.5 deg. Seeded RNG — rerun to regenerate identical statistics.
"""
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent / "demo-frames"
N, SIZE = 40, 64
FLASH_IDX = (12, 28)          # 0-based -> epochs 13.00 s and 29.00 s
BASE = 30.0                   # night baseline (DAY_LUMA=90 stays False)
FLASH_FLOOR = 110.0           # scene-wide lift; +100 over 35/360 deg -> mean ~120
WEDGE = (50.0, 85.0)          # inside sector 1 (45-90 deg) of 8


def main():
    rng = np.random.default_rng(2026)
    OUT.mkdir(exist_ok=True)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    # same angle convention as detectors.flash.fisheye_azimuth_sector
    ang = np.degrees(np.arctan2(xx - SIZE / 2, -(yy - SIZE / 2))) % 360.0
    wedge = (ang >= WEDGE[0]) & (ang < WEDGE[1])
    for i in range(N):
        img = BASE + rng.normal(0, 1.0) + rng.normal(0, 3.0, (SIZE, SIZE))
        if i in FLASH_IDX:
            img = FLASH_FLOOR + rng.normal(0, 3.0, (SIZE, SIZE))
            img[wedge] += 100.0
        Image.fromarray(np.clip(img, 0, 255).astype("uint8"), mode="L").save(
            OUT / f"{i + 1.0:07.2f}.jpg", quality=90)
    print(f"wrote {N} frames -> {OUT}")


if __name__ == "__main__":
    main()
