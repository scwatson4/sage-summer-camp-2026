"""Evidence rendering for smoke-watch notifications.

THE RULE (learned from W097): annotations NEVER touch the source frame.
The archive's fire-detection job burned `smoke:53%` boxes into the only
stored copy, contaminating every downstream reuse — we had to inpaint them
back out to build the sim panoramas. So every capture ships as a PAIR:
  raw       — pristine, exactly what the sensor saw
  annotated — a derived copy with detector overlays

Renders:
- annotate_boxes()  : YOLO/Florence-style bounding boxes
- annotate_tiles()  : SmokeyNet-style horizon-band tile-grid probabilities
- before_after()    : side-by-side dwell pair with timestamps + delta hint

Pure PIL — no detector dependency, so it runs anywhere the frames do.
"""
from __future__ import annotations

import datetime
import pathlib

from PIL import Image, ImageDraw, ImageFilter

# palette shared with the maps/UI
GOLD = (245, 183, 34)
FIRE = (224, 89, 42)
CYAN = (127, 219, 255)
INK = (21, 28, 44)
PAPER = (245, 247, 250)


def _stamp(draw, xy, text, fill=PAPER, bg=INK):
    """Legible text on any background: dark plate + light glyphs."""
    x, y = xy
    pad = 4
    try:
        box = draw.textbbox((x, y), text)
    except Exception:  # very old PIL
        box = (x, y, x + 8 * len(text), y + 12)
    draw.rectangle([box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad],
                   fill=bg)
    draw.text((x, y), text, fill=fill)


def _out_path(raw_path, suffix):
    p = pathlib.Path(raw_path)
    return p.with_name(f"{p.stem}-{suffix}{p.suffix}")


def annotate_boxes(raw_path, detections, out_path=None, title=None):
    """detections: [{label, confidence, box:[x0,y0,x1,y1]}] in pixel coords.
    Writes a NEW annotated file; raw is never modified."""
    im = Image.open(raw_path).convert("RGB")
    d = ImageDraw.Draw(im)
    for det in detections:
        x0, y0, x1, y1 = det["box"]
        col = FIRE if "fire" in str(det.get("label", "")).lower() else GOLD
        d.rectangle([x0, y0, x1, y1], outline=col, width=3)
        _stamp(d, (x0 + 4, max(y0 - 16, 2)),
               f"{det.get('label','?')} {det.get('confidence',0):.0%}", bg=col,
               fill=INK)
    if title:
        _stamp(d, (8, 8), title)
    out = out_path or _out_path(raw_path, "annotated")
    im.save(out, quality=90)
    return str(out)


def annotate_tiles(raw_path, tile_probs, grid=(5, 9), band=(0.25, 0.65),
                   threshold=0.5, out_path=None, title=None):
    """SmokeyNet-style overlay: probabilities on a rows x cols grid over the
    horizon band (fraction of image height). Highlights tiles >= threshold,
    dims the rest — coarse but truthful about what the model actually scores.

    tile_probs: flat list or rows x cols nested, len == rows*cols.
    """
    im = Image.open(raw_path).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    W, H = im.size
    rows, cols = grid
    y0b, y1b = int(H * band[0]), int(H * band[1])
    flat = ([p for row in tile_probs for p in row]
            if tile_probs and isinstance(tile_probs[0], (list, tuple))
            else list(tile_probs))
    tw, th = W / cols, (y1b - y0b) / rows
    for i, p in enumerate(flat[:rows * cols]):
        r, c = divmod(i, cols)
        x0, y0 = c * tw, y0b + r * th
        rect = [x0, y0, x0 + tw, y0 + th]
        if p >= threshold:
            d.rectangle(rect, fill=(*GOLD, int(70 + 120 * min(p, 1.0))),
                        outline=GOLD, width=2)
            _stamp(d, (x0 + 3, y0 + 3), f"{p:.2f}", bg=GOLD, fill=INK)
        else:
            d.rectangle(rect, outline=(*CYAN, 60), width=1)
    d.rectangle([0, y0b, W - 1, y1b], outline=CYAN, width=2)
    _stamp(d, (8, y0b - 20), "horizon band (analysis region)", fill=CYAN)
    if title:
        _stamp(d, (8, 8), title)
    out = out_path or _out_path(raw_path, "tiles")
    im.save(out, quality=90)
    return str(out)


def before_after(before_path, after_path, out_path, labels=("before", "after"),
                 gap_s=None, show_delta=True):
    """Side-by-side dwell pair — often more convincing to a human than any
    box: a plume grows and drifts between frames; vog and cloud shadow don't.
    Optional third panel shows the amplified difference."""
    a = Image.open(before_path).convert("RGB")
    b = Image.open(after_path).convert("RGB").resize(a.size)
    panels = [a, b]
    if show_delta:
        from PIL import ImageChops
        diff = ImageChops.difference(a, b).filter(ImageFilter.GaussianBlur(1))
        diff = diff.point(lambda v: min(255, int(v * 3.5)))  # amplify
        panels.append(diff)
    w, h = a.size
    pad, label_h = 8, 24
    canvas = Image.new("RGB", (w * len(panels) + pad * (len(panels) + 1),
                               h + label_h + pad * 2), INK)
    d = ImageDraw.Draw(canvas)
    names = list(labels) + ["difference (x3.5)"]
    for i, panel in enumerate(panels):
        x = pad + i * (w + pad)
        canvas.paste(panel, (x, label_h + pad))
        cap = names[i]
        if i == 1 and gap_s:
            cap += f"  (+{gap_s:.0f} s)"
        d.text((x + 4, 8), cap, fill=PAPER)
    canvas.save(out_path, quality=90)
    return str(out_path)


def evidence_pack(sector, raw_frames, detections=None, tile_probs=None,
                  gap_s=None, outdir=None):
    """Build the full evidence set for one watched sector.

    Returns {sector, raw:[...], annotated:[...], composite, note} — the shape
    risk.card.build_card()'s `evidence` argument expects.
    """
    outdir = pathlib.Path(outdir or pathlib.Path(raw_frames[0]).parent)
    outdir.mkdir(parents=True, exist_ok=True)
    annotated = []
    for i, raw in enumerate(raw_frames):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%SZ")
        title = f"sector {sector}° · frame {i + 1}/{len(raw_frames)} · {stamp}"
        if tile_probs is not None:
            annotated.append(annotate_tiles(raw, tile_probs, title=title))
        elif detections:
            annotated.append(annotate_boxes(raw, detections, title=title))
    composite = None
    if len(raw_frames) >= 2:
        composite = before_after(
            raw_frames[0], raw_frames[1],
            outdir / f"sector{int(sector)}-before-after.jpg", gap_s=gap_s)
    return {"sector": sector, "raw": [str(p) for p in raw_frames],
            "annotated": annotated, "composite": composite,
            "note": "raw frames unmodified; overlays on derived copies only"}
