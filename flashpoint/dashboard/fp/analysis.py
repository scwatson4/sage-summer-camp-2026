"""Signal analysis: image luminance series + flash candidates, audio clip
features + thunder-onset picking, and the flash-to-bang range engine.

Physics notes:
- speed of sound c ≈ 343 m/s at 20 °C, +0.6 m/s per °C (correct with the
  node's own met temperature when available — see plan §7).
- thunder onset is a smeared rumble: pick the LEADING EDGE of the envelope,
  never the loudest peak (reflections/rumble tail are often louder).
"""
import io

import numpy as np
import soundfile as sf
from PIL import Image
from scipy import ndimage, signal

THUNDER_BAND = (20.0, 150.0)  # Hz — thunder's dominant energy
EPS = 1e-12
_trapz = getattr(np, "trapezoid", None) or np.trapz  # numpy 2.x renamed trapz


def speed_of_sound(temp_c):
    """m/s; linear approximation around 20 °C."""
    return 343.0 + 0.6 * (float(temp_c) - 20.0)


def flash_to_bang_range(dt_s, temp_c=20.0, onset_sigma_s=0.1):
    """Range and 1-sigma uncertainty from a flash→thunder delay."""
    c = speed_of_sound(temp_c)
    return c * float(dt_s), c * float(onset_sigma_s)


# ---------------------------------------------------------------- images

def mean_luminance(path, thumb=96):
    """Mean luma (0-255) of an image file; downsampled first for speed."""
    with Image.open(path) as im:
        im = im.convert("L")
        im.thumbnail((thumb, thumb))
        return float(np.asarray(im, dtype=np.float32).mean())


def flash_candidates(times, lumas, z_thresh=4.0, min_jump=8.0):
    """Robust-z spikes in a luminance series -> indices of flash candidates.

    Uses median/MAD of the *differences* from a rolling baseline so slow
    dawn/dusk trends don't trigger. Snapshot cadences are minutes, so a
    'candidate' means 'this frame caught the sky lit up', not a strike time.
    """
    x = np.asarray(lumas, float)
    if len(x) < 5:
        return []
    k = min(7, len(x) if len(x) % 2 else len(x) - 1)
    # edge-replicated (not zero-padded) median, else a rising dawn/clearing ramp
    # collapses its own trailing baseline and the newest frames look like flashes
    baseline = ndimage.median_filter(x, size=k, mode="nearest")
    d = x - baseline
    mad = np.median(np.abs(d - np.median(d))) + EPS
    z = 0.6745 * (d - np.median(d)) / mad
    return [int(i) for i in np.where((z > z_thresh) & (d > min_jump))[0]]


# ---------------------------------------------------------------- audio

def load_audio(path):
    """Read any soundfile-supported format (FLAC/WAV/OGG) as mono float32."""
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    return y.mean(axis=1), sr


def to_wav_bytes(y, sr):
    """WAV bytes for st.audio (browser-safe regardless of source format)."""
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def envelope_db(y, sr, hop_s=0.02):
    """RMS envelope in dBFS on hop_s hops -> (t, db)."""
    hop = max(int(sr * hop_s), 1)
    n = len(y) // hop
    if n == 0:
        return np.array([0.0]), np.array([-120.0])
    seg = y[: n * hop].reshape(n, hop)
    rms = np.sqrt((seg ** 2).mean(axis=1)) + EPS
    return np.arange(n) * hop_s + hop_s / 2, 20 * np.log10(rms)


def band_energy_ratio(y, sr, band=THUNDER_BAND):
    """Fraction of spectral power inside `band` (Welch PSD). Thunder-ish clips
    put most of their energy below ~150 Hz."""
    if len(y) < sr // 4:
        return 0.0
    f, p = signal.welch(y, sr, nperseg=min(4096, len(y)))
    total = float(_trapz(p, f)) + EPS
    m = (f >= band[0]) & (f <= band[1])
    return float(_trapz(p[m], f[m])) / total


def clip_features(y, sr):
    """Summary features for the clip timeline."""
    t, db = envelope_db(y, sr)
    lowband = bandpass(y, sr, *THUNDER_BAND)
    _, low_db = envelope_db(lowband, sr)
    return {
        "rms_db": float(20 * np.log10(np.sqrt((y ** 2).mean()) + EPS)),
        "peak_db": float(db.max()),
        "low_peak_db": float(low_db.max()) if len(low_db) else -120.0,
        "low_ratio": band_energy_ratio(y, sr),
        "duration_s": len(y) / sr,
    }


def bandpass(y, sr, lo, hi, order=4):
    y = np.asarray(y)
    nyq = sr / 2
    hi = min(hi, nyq * 0.95)
    if lo >= hi:
        return y
    sos = signal.butter(order, [lo / nyq, hi / nyq], btype="band", output="sos")
    # sosfiltfilt raises if the clip is shorter than its edge padding; a
    # truncated/corrupt FLAC should degrade to "no onset", not crash the tab.
    if len(y) <= 3 * (2 * len(sos) + 1):
        return y
    return signal.sosfiltfilt(sos, y)


def onset_time(y, sr, band=THUNDER_BAND, hop_s=0.02, k_db=8.0, sustain_hops=4):
    """Leading-edge onset within a clip (seconds from clip start), or None.

    Envelope of the band-passed signal; noise floor = 20th percentile;
    onset = first hop that exceeds floor + k_db and stays there for
    `sustain_hops` hops. Refined to the earliest adjacent hop still 3 dB up.
    """
    yb = bandpass(y, sr, *band)
    t, db = envelope_db(yb, sr, hop_s)
    if len(db) < sustain_hops + 2:
        return None
    floor = np.percentile(db, 20)
    above = db > floor + k_db
    for i in range(len(above) - sustain_hops):
        if above[i : i + sustain_hops].all():
            j = i
            while j > 0 and db[j - 1] > floor + 3.0:
                j -= 1
            return float(t[j])
    return None


def spectrogram(y, sr, fmax=1200.0):
    """(t, f, dB) spectrogram capped at fmax — thunder lives at the bottom."""
    nperseg = min(2048, max(256, len(y) // 64))
    f, t, sxx = signal.spectrogram(y, sr, nperseg=nperseg, noverlap=nperseg // 2)
    m = f <= fmax
    return t, f[m], 10 * np.log10(sxx[m] + EPS)
