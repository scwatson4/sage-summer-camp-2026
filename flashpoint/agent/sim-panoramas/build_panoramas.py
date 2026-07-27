#!/usr/bin/env python3
"""Build sage-agent sim panoramas from the W097 forensics imagery.

Produces 360-degree strips the sim PTZ backend can pan across
(vendor sim: pan 0-360 maps to image width; 16:9 viewport; tilt range from
aspect). Layout: 6 sectors x 60 degrees, each 1920x2160 (real frame in the
middle band, sky/ground edge-extended so the default tilt centers on real
content and there is room to tilt).

Two test panoramas (the point is the CONTRAST):
- w097-pano-A-day-plume.jpg: quiet ohia-canopy sectors + ONE real smoke
  positive — the 2025-10-05 Halemaumau gas plume — at sector 2 (pan ~150).
- w097-pano-B-confusers.jpg: the false-positive reel — fog, rain-blurred
  lens, night IR, eruption glow lighting clouds — everything that fooled
  W097's fire detector for months. A good smoke watcher flags NOTHING here
  (or flags-and-retracts on the second look).

The fire-detection frames carry burned-in annotation boxes (red rects, green
labels) from the original YOLOv7 job; scrub_annotations() removes them so a
detector under test cannot cheat on painted-on hints.

Run:  python build_panoramas.py     (writes JPGs + sectors.json here)
"""
import json
import pathlib

import numpy as np
from PIL import Image, ImageFilter

HERE = pathlib.Path(__file__).resolve().parent
IMG = HERE.parents[1] / "docs" / "w097-imagery"

SECTOR_W, SECTOR_H = 1920, 2160
FRAME_H = 1080
N_SECTORS = 6


def scrub_annotations(arr):
    """Remove burned-in detector overlays: red box lines and green label text.

    JPEG compression bleeds the overlay colors into neighbors, so the mask is
    hue-based (dominance, not purity) and dilated before filling each masked
    pixel from its nearest clean left/right neighbors."""
    from scipy import ndimage

    r, g, b = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int)
    red = (r > 130) & (r - g > 35) & (r - b > 35)
    green = (g > 110) & (g - r > 35) & (g - b > 35)
    mask = ndimage.binary_dilation(red | green, iterations=4)
    if not mask.any():
        return arr
    # exact 2-D nearest-clean-pixel fill (no directional streaks), then blend
    # the filled region with a local blur so thin fill seams disappear
    _, (iy, ix) = ndimage.distance_transform_edt(mask, return_indices=True)
    out = arr[iy, ix]
    blurred = ndimage.uniform_filter(out.astype(float), size=(7, 7, 1))
    blend = ndimage.binary_dilation(mask, iterations=2)
    out = out.astype(float)
    out[blend] = blurred[blend]
    return np.clip(out, 0, 255).astype(arr.dtype)


def load_frame(name, scrub=False):
    im = Image.open(IMG / name).convert("RGB")
    if scrub:
        im = Image.fromarray(scrub_annotations(np.asarray(im)))
    # center-crop to 16:9 then resize to sector frame size
    w, h = im.size
    target = 16 / 9
    if w / h > target:
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
    else:
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h + nh) // 2))
    return im.resize((SECTOR_W, FRAME_H), Image.LANCZOS)


def sectorize(frame):
    """1920x1080 frame -> 1920x2160 sector: sky/ground edge-extension bands."""
    canvas = Image.new("RGB", (SECTOR_W, SECTOR_H))
    band = (SECTOR_H - FRAME_H) // 2
    top = frame.crop((0, 0, SECTOR_W, 4)).resize((SECTOR_W, band)) \
        .filter(ImageFilter.GaussianBlur(6))
    bottom = frame.crop((0, FRAME_H - 4, SECTOR_W, FRAME_H)) \
        .resize((SECTOR_W, band)).filter(ImageFilter.GaussianBlur(6))
    canvas.paste(top, (0, 0))
    canvas.paste(frame, (0, band))
    canvas.paste(bottom, (0, band + FRAME_H))
    return canvas


PANORAMAS = {
    "w097-pano-A-day-plume": [
        ("ptz-2025-07-24T1820Z.jpg", False, "ohia canopy, clear day (negative)"),
        ("ptz-2025-10-01T2020Z.jpg", False, "ohia canopy, clear day (negative)"),
        ("firedet-2025-10-05T1733Z-halemaumau-plume-day.jpg", True,
         "REAL Halemaumau gas plume, boxes scrubbed (THE positive)"),
        ("ptz-2025-09-02T1820Z.jpg", False, "ohia canopy, scattered cloud (negative)"),
        ("ptz-2025-12-01T2020Z.jpg", False, "ohia canopy, winter light (negative)"),
        ("ptz-2025-10-05T2020Z.jpg", False,
         "canopy same day as the plume, 3 h later (negative)"),
    ],
    "w097-pano-B-confusers": [
        ("ptz-2025-08-23T2220Z-fog.jpg", False, "full fog-out on a top smoke-day (confuser)"),
        ("ptz-2025-09-02T2220Z.jpg", False, "dusk haze (confuser)"),
        ("firedet-2025-09-02T1347Z-eruption-glow-clouds.jpg", True,
         "eruption glow lighting the cloud deck, boxes scrubbed (confuser)"),
        ("ptz-2025-11-01T2020Z-rain.jpg", False, "rain-blurred lens (confuser)"),
        ("firedet-2025-08-23T0954Z-eruption-glow-night.jpg", True,
         "night eruption glow + moonlit cloud, boxes scrubbed (confuser)"),
        ("ptz-2025-12-30T1620Z-final-frame-ir.jpg", False, "pre-dawn IR (confuser)"),
    ],
}


def main():
    meta = {}
    for name, sectors in PANORAMAS.items():
        strip = Image.new("RGB", (SECTOR_W * N_SECTORS, SECTOR_H))
        entries = []
        for i, (fname, scrub, note) in enumerate(sectors):
            strip.paste(sectorize(load_frame(fname, scrub)), (i * SECTOR_W, 0))
            entries.append({
                "sector": i,
                "pan_center_deg": (i + 0.5) * 360 / N_SECTORS,
                "source": fname,
                "annotation_scrubbed": scrub,
                "note": note,
            })
        out = HERE / f"{name}.jpg"
        strip.save(out, quality=88)
        meta[name] = {"width": strip.width, "height": strip.height,
                      "sector_deg": 360 / N_SECTORS, "sectors": entries}
        print(f"{out.name}: {strip.width}x{strip.height}")

        # small labeled overview for humans
        ov = strip.resize((N_SECTORS * 320, int(SECTOR_H * 320 / SECTOR_W)))
        from PIL import ImageDraw
        d = ImageDraw.Draw(ov)
        for i, e in enumerate(meta[name]["sectors"]):
            d.rectangle([i * 320, 0, (i + 1) * 320 - 1, ov.height - 1],
                        outline=(245, 183, 34), width=2)
            d.text((i * 320 + 8, 6), f"{i}: pan {e['pan_center_deg']:.0f}°",
                   fill=(245, 183, 34))
        ov.save(HERE / f"{name}-overview.jpg", quality=85)

    (HERE / "sectors.json").write_text(json.dumps(meta, indent=1))
    print("sectors.json written")


if __name__ == "__main__":
    main()
