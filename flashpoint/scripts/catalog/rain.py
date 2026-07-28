"""Node rain-gauge accumulation, at hourly resolution, from the public API.

Gotcha that shaped this module: the raw rain streams are enormous — a single
day of `env.raingauge.*` on W06C is ~1.1M records and a 5-day raw pull times
out. The server-side aggregation is the only workable path, and it is cheap
(~0.1-5 s for a whole month at 1-hour buckets).

Second gotcha: an aggregation bucket is labelled with the window END, so a row
stamped T covers [T-1h, T). Everything here shifts back by one bucket.

Accumulation semantics
  env.raingauge.total_acc   RG-15, monotonically cumulative (mm)
  wxt.rain.accumulation     WXT536, cumulative within a reset cycle (mm)
Rain over any interval is max-min of the cumulative trace, clipped at zero so a
gauge reset reads as "no rain" rather than a large negative.
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd
import sage_data_client

GAUGE_NAMES = ["env.raingauge.total_acc", "wxt.rain.accumulation"]


def _agg(vsn, name, start, end, func, window="1h"):
    df = sage_data_client.query(
        start=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        filter={"vsn": vsn, "name": name},
        experimental_func=func, experimental_window=window)
    if not len(df):
        return pd.Series(dtype="float64")
    v = pd.to_numeric(df["value"], errors="coerce")
    t = df["timestamp"] - pd.Timedelta(window)      # label is the window END
    return pd.Series(v.to_numpy(), index=t).groupby(level=0).agg(func)


class RainFetchError(RuntimeError):
    """Transport failure — distinct from 'this node has no gauge'."""


def hourly_accum(vsn: str, start: dt.datetime, end: dt.datetime, retries: int = 3):
    """Hourly (min, max) of the cumulative rain trace. Returns (df, gauge_name).

    df is indexed by the hour the data belongs to, with columns lo/hi in mm.
    Returns (None, None) only when the node genuinely published no gauge data in
    the window. A transport failure raises RainFetchError instead: swallowing it
    here would silently record a working gauge as absent, and the caller would
    checkpoint that as a completed unit.
    """
    errors = []
    for name in GAUGE_NAMES:
        for attempt in range(retries):
            try:
                hi = _agg(vsn, name, start, end, "max")
                if not len(hi):
                    break                      # no data for this gauge: try next
                lo = _agg(vsn, name, start, end, "min")
                df = pd.DataFrame({"hi": hi, "lo": lo}).dropna(how="all").sort_index()
                if len(df):
                    df.index.name = "hour"   # else the index inherits "timestamp"
                    return df, name
                break
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                time.sleep(1.5 * (attempt + 1))
    if errors:
        raise RainFetchError(f"{vsn} {start:%Y-%m}: " + "; ".join(errors[-2:]))
    return None, None


def rain_mm(acc: pd.DataFrame, t0, t1) -> float:
    """Rain accumulated in [t0, t1) from an hourly cumulative trace."""
    if acc is None or not len(acc):
        return float("nan")
    w = acc[(acc.index >= t0) & (acc.index < t1)]
    if not len(w):
        return float("nan")
    return float(max(0.0, w.hi.max() - w.lo.min()))


def month_windows(start: dt.date, end: dt.date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        s = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield s, dt.datetime(ny, nm, 1, tzinfo=dt.timezone.utc)
        y, m = ny, nm
