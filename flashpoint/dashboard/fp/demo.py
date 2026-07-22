"""Synthetic storm replay ("no-storm insurance", plan §F6).

Generates a physically consistent multi-node lightning storm over the REAL
Argonne-cluster node geometry so every dashboard feature works offline and
unauthenticated:

- truth strikes at known positions/times
- per node, per strike: a 60 s "storm-mode" audio clip (WAV) whose thunder
  arrives exactly flash-time + distance / c after the flash
- per node: night-sky frames on a 30 s cadence plus a flash-triggered frame
  at each strike (bolt + global brightening)
- per node: met series (temperature, falling pressure, rain accumulation)

Everything lands under flashpoint/data/demo/ (gitignored) with a manifest so
regeneration is skipped when present. Deterministic for a given seed.
"""
import datetime
import json
import math

import numpy as np
import pandas as pd
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter

from . import analysis, geo, sage

DEMO_ROOT = sage.DATA / "demo"
SR = 4000                       # thunder lives <150 Hz; 4 kHz keeps files small
CLIP_S = 60.0
PRE_ROLL_S = 5.0                # clip starts this long before the flash
FRAME_CADENCE_S = 30.0
IMG_SIZE = (256, 192)
T0 = datetime.datetime(2026, 7, 18, 3, 0, 0, tzinfo=datetime.timezone.utc)
WINDOW_MIN = 40
TEMP_C = 24.0

PREFERRED = ["W023", "W0AE", "W027", "W030", "W0A4", "V032"]  # best-spread six


def demo_nodes(nodes_df):
    """The Argonne six (real coordinates), falling back to any six mic nodes
    closest to Argonne if the manifest snapshot changed."""
    sel = nodes_df[nodes_df.vsn.isin(PREFERRED)]
    if len(sel) >= 4:
        return sel.reset_index(drop=True)
    lat0, lon0 = 41.70, -87.98
    cand = nodes_df[nodes_df.mic].copy()
    cand["d"] = [geo.dist_km(lat0, lon0, r.lat, r.lon) for r in cand.itertuples()]
    return cand.nsmallest(6, "d").drop(columns="d").reset_index(drop=True)


def _strike_truth(nodes, rng):
    lat0, lon0 = float(nodes.lat.mean()), float(nodes.lon.mean())
    strikes = []
    t = T0 + datetime.timedelta(minutes=4)
    for i in range(5):
        x = float(rng.uniform(-2500, 2500))
        y = float(rng.uniform(-2500, 2500))
        lat, lon = geo.to_latlon(x, y, lat0, lon0)
        strikes.append({
            "id": f"S{i + 1}",
            "time": t.isoformat(),
            "lat": lat, "lon": lon,
        })
        t += datetime.timedelta(minutes=float(rng.uniform(5, 9)))
    return strikes, (lat0, lon0)


def _thunder(y, sr, t_on, dist_m, rng):
    """Add a thunder arrival at t_on seconds: several low-band rumble bursts
    with a leading edge and a long decaying tail, amplitude falling with
    distance."""
    n = len(y)
    amp = 0.9 * min(1.0, 800.0 / max(dist_m, 100.0)) + 0.05
    n_bursts = int(rng.integers(2, 5))
    for b in range(n_bursts):
        start = t_on + (0.0 if b == 0 else float(rng.uniform(0.3, 2.5)) * b)
        dur = float(rng.uniform(1.5, 4.0))
        i0 = int(start * sr)
        if i0 >= n:
            continue
        m = min(int(dur * sr), n - i0)
        burst = np.cumsum(rng.standard_normal(m)).astype(np.float32)  # brown noise
        burst -= burst.mean()
        burst /= (np.abs(burst).max() + 1e-9)
        t = np.arange(m) / sr
        env = np.minimum(t / 0.15, 1.0) * np.exp(-t / (dur * 0.5))
        y[i0:i0 + m] += amp * (0.9 if b == 0 else 0.5) * burst * env
    return y


def _clip(dist_m, rng):
    """One 60 s storm clip: background + thunder at PRE_ROLL + dist/c."""
    n = int(CLIP_S * SR)
    bg = np.cumsum(rng.standard_normal(n)).astype(np.float32)
    bg -= bg.mean()
    bg /= (np.abs(bg).max() + 1e-9)
    y = 0.02 * bg + 0.005 * rng.standard_normal(n).astype(np.float32)  # wind + hiss
    t_arrival = PRE_ROLL_S + dist_m / analysis.speed_of_sound(TEMP_C)
    if t_arrival < CLIP_S - 2:
        y = _thunder(y, SR, t_arrival, dist_m, rng)
    y = analysis.bandpass(y, SR, 10.0, 1500.0)
    peak = np.abs(y).max()
    if peak > 0.99:
        y = 0.99 * y / peak
    return y.astype(np.float32), t_arrival


def _night_frame(rng, flash=False, bolt_x=None):
    """Dark cloudy night sky; flash frames get global brightening + a bolt."""
    w, h = IMG_SIZE
    small = rng.uniform(0, 1, (12, 16)).astype(np.float32)
    clouds = np.asarray(
        Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
        dtype=np.float32) / 255.0
    base = 8 + 14 * clouds
    if flash:
        base = base * 5.0 + 60 * clouds + 40
    img = np.clip(base, 0, 255).astype(np.uint8)
    rgb = np.stack([img * 0.92, img * 0.95, np.clip(img * 1.1, 0, 255)], axis=-1)
    im = Image.fromarray(rgb.astype(np.uint8), "RGB")
    if flash and bolt_x is not None:
        d = ImageDraw.Draw(im)
        x, ypos = int(bolt_x * w), 0
        pts = [(x, 0)]
        while ypos < h * 0.75:
            ypos += int(rng.integers(10, 26))
            x += int(rng.integers(-14, 15))
            pts.append((max(2, min(w - 2, x)), min(ypos, int(h * 0.75))))
        d.line(pts, fill=(255, 255, 245), width=2)
        im = im.filter(ImageFilter.GaussianBlur(0.6))
    return im


def generate(nodes_df, seed=7, force=False):
    """Build (or load) the demo dataset. Returns the manifest dict."""
    manifest_path = DEMO_ROOT / "manifest.json"
    if manifest_path.exists() and not force:
        return json.loads(manifest_path.read_text())

    rng = np.random.default_rng(seed)
    nodes = demo_nodes(nodes_df)
    strikes, (lat0, lon0) = _strike_truth(nodes, rng)
    media, met_rows = [], []

    for nrow in nodes.itertuples():
        vsn = nrow.vsn
        adir = DEMO_ROOT / vsn / "audio"
        idir = DEMO_ROOT / vsn / "img"
        adir.mkdir(parents=True, exist_ok=True)
        idir.mkdir(parents=True, exist_ok=True)

        # audio: one storm-mode clip per strike
        for s in strikes:
            t_strike = datetime.datetime.fromisoformat(s["time"])
            d_m = geo.dist_km(nrow.lat, nrow.lon, s["lat"], s["lon"]) * 1000
            y, _ = _clip(d_m, rng)
            t_clip = t_strike - datetime.timedelta(seconds=PRE_ROLL_S)
            ns = int(t_clip.timestamp() * 1e9)
            f = adir / f"{ns}-storm.wav"
            if not f.exists():
                sf.write(f, y, SR, subtype="PCM_16")
            media.append({"timestamp": t_clip.isoformat(), "vsn": vsn,
                          "task": "storm-audio", "path": str(f)})

        # a couple of quiet cadence clips for contrast
        for k in (2, int(WINDOW_MIN) - 3):
            t_clip = T0 + datetime.timedelta(minutes=k)
            n = int(10 * SR)
            y = 0.015 * np.cumsum(rng.standard_normal(n)).astype(np.float32)
            y -= y.mean()
            y = analysis.bandpass(y / (np.abs(y).max() + 1e-9) * 0.02, SR, 10, 1500)
            ns = int(t_clip.timestamp() * 1e9)
            f = adir / f"{ns}-ambient.wav"
            if not f.exists():
                sf.write(f, y.astype(np.float32), SR, subtype="PCM_16")
            media.append({"timestamp": t_clip.isoformat(), "vsn": vsn,
                          "task": "storm-audio", "path": str(f)})

        # images: 30 s cadence + flash-triggered frame per strike
        strike_times = [datetime.datetime.fromisoformat(s["time"]) for s in strikes]
        frame_times = [(T0 + datetime.timedelta(seconds=k * FRAME_CADENCE_S), False)
                       for k in range(int(WINDOW_MIN * 60 / FRAME_CADENCE_S))]
        frame_times += [(ts + datetime.timedelta(milliseconds=200), True)
                        for ts in strike_times]
        for t_img, is_flash in sorted(frame_times):
            ns = int(t_img.timestamp() * 1e9)
            f = idir / f"{ns}-{'flash' if is_flash else 'sky'}.jpg"
            if not f.exists():
                im = _night_frame(rng, flash=is_flash,
                                  bolt_x=float(rng.uniform(0.15, 0.85)))
                im.save(f, quality=85)
            media.append({"timestamp": t_img.isoformat(), "vsn": vsn,
                          "task": "storm-cam", "path": str(f)})

        # met: 1-min cadence; pressure falls into the storm, rain follows
        for k in range(WINDOW_MIN):
            t = T0 + datetime.timedelta(minutes=k)
            met_rows += [
                {"timestamp": t.isoformat(), "vsn": vsn, "name": "env.temperature",
                 "value": TEMP_C - 0.05 * k + float(rng.normal(0, 0.1))},
                {"timestamp": t.isoformat(), "vsn": vsn, "name": "env.pressure",
                 "value": 98600 - 8 * k + float(rng.normal(0, 5))},
                {"timestamp": t.isoformat(), "vsn": vsn, "name": "wxt.rain.accumulation",
                 "value": 0.0 if k < 18 else 0.08 * (k - 18)},
            ]

    manifest = {
        "seed": seed,
        "center": {"lat": lat0, "lon": lon0},
        "temp_c": TEMP_C,
        "nodes": nodes.to_dict("records"),
        "strikes": strikes,
        "media": media,
        "met": met_rows,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest))
    return manifest


def media_index(manifest):
    df = pd.DataFrame(manifest["media"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    df["filename"] = df["path"].str.rsplit("/", n=1).str[-1]
    return df.sort_values("timestamp").reset_index(drop=True)


def met_index(manifest):
    df = pd.DataFrame(manifest["met"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return df


def demo_case(manifest):
    """Case-preset dict in the same shape as assets/cases.json entries."""
    return {
        "id": "demo-storm",
        "title": "Demo storm — synthetic replay (Argonne array)",
        "vsn": manifest["nodes"][0]["vsn"],
        "nodes": [n["vsn"] for n in manifest["nodes"]],
        "start": T0.isoformat(),
        "end": (T0 + datetime.timedelta(minutes=WINDOW_MIN)).isoformat(),
        "audio_task": "storm-audio",
        "image_tasks": ["storm-cam"],
        "fires": [],
        "notes": ("Synthetic 5-strike storm over the real Argonne node geometry "
                  "(the plan's replay-harness insurance). Thunder arrivals are "
                  "physically consistent, so flash-to-bang rings from 3+ nodes "
                  "should land on the truth markers."),
    }
