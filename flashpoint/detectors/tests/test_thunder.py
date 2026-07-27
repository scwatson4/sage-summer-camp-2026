"""Synthetic separation tests for the noise-adaptive thunder detector.

Run:  python -m pytest detectors/tests/ -q   (or python detectors/tests/test_thunder.py)

The scenarios mirror the M1 failure modes: thunder alone, thunder UNDER heavy
rain (v0's false negative), rain alone (v0's false positive), wind buffeting,
and raindrop impulses. Pass criteria are detector-level, not exact numbers.
"""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from detectors import thunder  # noqa: E402

SR = 8000
RNG = np.random.default_rng(42)


def _norm(y, level):
    y = y - y.mean()
    return level * y / (np.abs(y).max() + 1e-9)


def make_thunder(dur_s=30.0, t_on=12.0, strength=0.5):
    n = int(dur_s * SR)
    y = np.zeros(n, dtype=np.float32)
    for k, (dt, amp, tail) in enumerate([(0.0, 1.0, 3.0), (1.2, 0.6, 2.0), (2.8, 0.4, 2.5)]):
        i0 = int((t_on + dt) * SR)
        m = int(tail * 2 * SR)
        burst = np.cumsum(RNG.standard_normal(m)).astype(np.float32)
        burst = _norm(burst, 1.0)
        tt = np.arange(m) / SR
        env = np.minimum(tt / 0.12, 1.0) * np.exp(-tt / tail)
        y[i0:i0 + m] += strength * amp * (burst * env)[:max(0, n - i0)]
    return y


def make_rain(dur_s=30.0, rate_hz=80, level=0.3):
    """Dense raindrop impulses + broadband patter — quasi-stationary."""
    n = int(dur_s * SR)
    y = 0.4 * RNG.standard_normal(n).astype(np.float32)
    hits = RNG.uniform(0, dur_s, int(rate_hz * dur_s))
    for h in hits:
        i = int(h * SR)
        m = min(int(0.004 * SR), n - i)
        y[i:i + m] += RNG.uniform(0.5, 2.0) * np.exp(-np.arange(m) / (0.001 * SR))
    return _norm(y, level)


def make_wind(dur_s=30.0, level=0.4):
    """Sub-20 Hz dominated buffeting with gusty envelope."""
    n = int(dur_s * SR)
    slow = np.cumsum(np.cumsum(RNG.standard_normal(n))).astype(np.float32)
    slow = _norm(slow, 1.0)
    gust = 0.5 + 0.5 * np.clip(np.sin(np.arange(n) / SR * 0.7) +
                               0.3 * RNG.standard_normal(n // 4000 + 1).repeat(4000)[:n], 0, 2)
    return _norm(slow * gust, level)


def scenario(name, y, expect_pass, anchors=None, wind_ms=None):
    events = thunder.detect(y, SR, anchor_times_s=anchors, wind_ms=wind_ms)
    passed = [e for e in events if e.passed]
    ok = (len(passed) > 0) == expect_pass
    detail = "; ".join(f"on={e.onset_s:.1f}s dur={e.duration_s:.1f}s "
                       f"score={e.score:.2f} {'PASS' if e.passed else e.reject_reason}"
                       for e in events) or "no events"
    print(f"{'OK ' if ok else 'FAIL'} {name}: {detail}")
    return ok, events


def main():
    results = []

    # 1. clean thunder -> detected standalone
    y = make_thunder() + 0.02 * RNG.standard_normal(int(30 * SR)).astype(np.float32)
    ok, ev = scenario("thunder/quiet", y, True)
    results.append(ok)
    if ev:
        best = max(ev, key=lambda e: e.score)
        results.append(abs(best.onset_s - 12.0) < 1.0)
        print(f"     onset err {abs(best.onset_s - 12.0):.2f}s")

    # 2. thunder buried in heavy rain -> still found in ANCHORED mode
    #    (flash 8 s before the first burst; expected range from "GLM" ~3 km)
    y = make_thunder(strength=0.35) + make_rain(level=0.5)
    ok_anch, ev = scenario("thunder-under-rain/anchored", y, True,
                           anchors=[(12.0 - 8.0, 3.0)])
    results.append(ok_anch)

    # 3. rain alone -> NO pass (v0's false-positive mode), even anchored:
    #    random rain transients land at delays inconsistent with the anchors'
    #    known ranges (the gate that formalizes M1's falsification logic)
    ok, _ = scenario("rain-only/standalone", make_rain(level=0.6), False)
    results.append(ok)
    ok, _ = scenario("rain-only/anchored", make_rain(level=0.6), False,
                     anchors=[(5.0, 20.0), (15.0, 25.0)])
    results.append(ok)

    # 4. wind buffeting -> rejected (band-shape gate)
    ok, _ = scenario("wind-only", make_wind(level=0.6), False)
    results.append(ok)

    # 5. anchored event carries an implied range
    y = make_thunder(strength=0.5)
    ev = thunder.detect(y, SR, anchor_times_s=[12.0 - 8.75])  # 8.75 s ≈ 3.0 km
    hit = [e for e in ev if e.passed and e.anchored]
    rng_ok = bool(hit) and abs(hit[0].implied_range_km - 3.0) < 0.6
    print(f"{'OK ' if rng_ok else 'FAIL'} implied-range: "
          + (f"{hit[0].implied_range_km:.2f} km (expect ~3.0)" if hit else "no anchored event"))
    results.append(rng_ok)

    assert all(results), f"{results.count(False)} scenario(s) failed"
    print(f"\nALL {len(results)} THUNDER SCENARIOS PASS")


if __name__ == "__main__":
    main()
