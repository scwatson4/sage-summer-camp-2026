"""Shared plumbing for the FlashPoint storm-archive-fire catalog.

Everything here is credential-free: GOES GLM on AWS is anonymous, the Sage
manifest and query API are public, WFIGS is public. No Sage token is used or
required by any code in this package.

Design notes that matter:

* GLM L2 LCFA granules are **full-disk** 20-second files (180/hour, 4320/day).
  One granule download therefore serves *every* node simultaneously — the cost
  of a scan is driven by the set of DATES, not by the number of nodes. Scans
  are organised by (satellite, date, hour) and filtered against all targets at
  once.
* Granules are staged in tmpfs (/dev/shm) and deleted as soon as the hour is
  filtered, so raw data never accumulates beyond the in-flight batch.
* Every scan is checkpointed per work unit so a shelve/restart resumes.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import uuid

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]          # .../flashpoint
CATALOG = REPO / "catalog"
WORK = pathlib.Path(os.environ.get("FP_WORK", "/media/volume/Sage-Grande-Flashpoint/work"))
CKPT = WORK / "ckpt"
SHARDS = WORK / "shards"
CACHE = WORK / "cache"
S5CMD = os.environ.get("S5CMD", "/media/volume/Sage-Grande-Flashpoint/bin/s5cmd")
STAGE_ROOT = os.environ.get("FP_STAGE", "/dev/shm/fpglm")

for _d in (CKPT, SHARDS, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

MANIFEST_URL = "https://auth.sagecontinuum.org/manifests/?format=json"

# ---------------------------------------------------------------- geodesy ---

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Vectorised over any broadcastable inputs."""
    lat1 = np.radians(np.asarray(lat1, dtype="float64"))
    lon1 = np.radians(np.asarray(lon1, dtype="float64"))
    lat2 = np.radians(np.asarray(lat2, dtype="float64"))
    lon2 = np.radians(np.asarray(lon2, dtype="float64"))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def bbox_pad_deg(lat, radius_km):
    """Lat/lon half-widths that certainly contain a radius_km circle."""
    dlat = radius_km / 110.574
    dlon = radius_km / max(111.320 * np.cos(np.radians(lat)), 1e-6)
    return dlat, dlon


# ------------------------------------------------- GOES GLM satellite map ---
# Operational GLM windows, verified empirically against the S3 buckets
# (first/last day-of-year directories present) on 2026-07-27:
#   G16 GLM-L2-LCFA : 2018-001 .. 2025-097   (GOES-East, sub-satellite 75.2W)
#   G17 GLM-L2-LCFA : 2018-... .. 2023-010   (GOES-West, sub-satellite 137.2W)
#   G18 GLM-L2-LCFA : 2022-262 .. present    (GOES-West, sub-satellite 137.0W)
#   G19 GLM-L2-LCFA : 2025-015 .. present    (GOES-East, sub-satellite 75.2W)
GLM_WINDOWS = {
    16: (dt.date(2018, 1, 1), dt.date(2025, 4, 7)),
    17: (dt.date(2018, 8, 1), dt.date(2023, 1, 10)),
    18: (dt.date(2022, 9, 19), None),
    19: (dt.date(2025, 1, 15), None),
}
SAT_LON = {16: -75.2, 17: -137.2, 18: -137.0, 19: -75.2}
EAST_CHAIN = [16, 19]   # preference order resolved by date
WEST_CHAIN = [17, 18]


def _covers(sat: int, day: dt.date) -> bool:
    lo, hi = GLM_WINDOWS[sat]
    return lo <= day and (hi is None or day <= hi)


def sats_for_date(day: dt.date):
    """(east_sat, west_sat) operational on `day`; either may be None."""
    east = next((s for s in EAST_CHAIN if _covers(s, day)), None)
    west = next((s for s in WEST_CHAIN if _covers(s, day)), None)
    return east, west


def primary_sat(day: dt.date, lon: float):
    """The single best-viewing operational GLM for a longitude on a date.

    GLM sits on the ABI platform; detection efficiency falls off toward the
    limb, so pick the satellite whose sub-satellite longitude is nearest.
    """
    east, west = sats_for_date(day)
    cands = [s for s in (east, west) if s is not None]
    if not cands:
        return None
    return min(cands, key=lambda s: abs(lon - SAT_LON[s]))


def glm_prefix(sat: int, day: dt.date, hour: int) -> str:
    return (f"s3://noaa-goes{sat}/GLM-L2-LCFA/{day.year}/{day.timetuple().tm_yday:03d}/"
            f"{hour:02d}/")


# ------------------------------------------------------------ granule I/O ---

class GranuleFetchError(RuntimeError):
    pass


def fetch_hour(sat: int, day: dt.date, hour: int, stage_dir: str, numworkers: int = 8,
               retries: int = 3):
    """Download one satellite-hour of LCFA granules into `stage_dir`.

    Returns the list of local .nc paths. A missing prefix (satellite outage,
    hour not published) yields an empty list rather than an error — real gaps
    exist in the archive and must not abort a multi-thousand-hour scan.
    """
    os.makedirs(stage_dir, exist_ok=True)
    src = glm_prefix(sat, day, hour) + "*.nc"
    last = ""
    best: list[str] = []
    for attempt in range(retries):
        proc = subprocess.run(
            [S5CMD, "--no-sign-request", "--numworkers", str(numworkers),
             "cp", src, stage_dir + "/"],
            capture_output=True, text=True)
        files = sorted(str(p) for p in pathlib.Path(stage_dir).glob("*.nc"))
        if proc.returncode == 0 and files:
            return files
        last = (proc.stderr or "")[-300:]
        if "no object found" in last:
            return []          # genuine archive gap, not an error
        # Partial download: keep what landed but RETRY, because s5cmd skips
        # files already staged and will fill the holes. Returning here (as an
        # earlier version did) made `retries` unreachable for exactly the
        # transient failure it exists for, and silently checkpointed a
        # truncated hour as complete.
        if len(files) > len(best):
            best = files
    if best:
        return best
    raise GranuleFetchError(f"{src}: {last}")


_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def _units_base_epoch(units: str) -> float:
    """'seconds since 2025-07-02 22:00:00.000' -> unix epoch seconds."""
    stamp = units.split("since", 1)[1].strip().replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(stamp, fmt).replace(
                tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError(f"unparsable time units: {units!r}")


def read_flashes(path: str):
    """(epoch_s, lat, lon, energy_J, quality_flag) arrays from one LCFA granule.

    Times come from `flash_time_offset_of_first_event`, whose `units` attribute
    carries the granule epoch. Computing epochs by vector add is ~100x faster
    than cftime's num2date and gives identical values.
    """
    from netCDF4 import Dataset
    with Dataset(path) as ds:
        if "flash_lat" not in ds.variables:
            return (np.empty(0), np.empty(0), np.empty(0), np.empty(0), np.empty(0))
        lat = np.asarray(ds.variables["flash_lat"][:], dtype="float64")
        if lat.size == 0:
            return (np.empty(0), np.empty(0), np.empty(0), np.empty(0), np.empty(0))
        lon = np.asarray(ds.variables["flash_lon"][:], dtype="float64")
        tv = ds.variables["flash_time_offset_of_first_event"]
        off = np.asarray(tv[:], dtype="float64")
        epoch = _units_base_epoch(tv.units) + off
        eng = (np.asarray(ds.variables["flash_energy"][:], dtype="float64")
               if "flash_energy" in ds.variables else np.full(lat.size, np.nan))
        qf = (np.asarray(ds.variables["flash_quality_flag"][:], dtype="int16")
              if "flash_quality_flag" in ds.variables else np.zeros(lat.size, "int16"))
    return epoch, lat, lon, eng, qf


def scan_hour(sat: int, day: dt.date, hour: int, targets: pd.DataFrame,
              numworkers: int = 8, keep_quality_zero: bool = True):
    """Download one satellite-hour, keep flashes near any target, drop the rest.

    `targets` needs columns: key, lat, lon, radius_km.
    Returns a DataFrame with one row per (flash, matched target).
    Staged granules are removed before returning, on every path.
    """
    stage = os.path.join(STAGE_ROOT, f"{sat}_{day:%Y%m%d}_{hour:02d}_{uuid.uuid4().hex[:8]}")
    tlat = targets["lat"].to_numpy("float64")
    tlon = targets["lon"].to_numpy("float64")
    trad = targets["radius_km"].to_numpy("float64")
    tkey = targets["key"].to_numpy(object)

    # Cheap rectangular pre-gate around the whole target set.
    pads = [bbox_pad_deg(la, r) for la, r in zip(tlat, trad)]
    lat_lo = min(la - p[0] for la, p in zip(tlat, pads))
    lat_hi = max(la + p[0] for la, p in zip(tlat, pads))
    lon_lo = min(lo - p[1] for lo, p in zip(tlon, pads))
    lon_hi = max(lo + p[1] for lo, p in zip(tlon, pads))

    out = []
    n_gran = 0
    try:
        files = fetch_hour(sat, day, hour, stage, numworkers=numworkers)
        n_gran = len(files)
        for f in files:
            try:
                epoch, lat, lon, eng, qf = read_flashes(f)
            except Exception:
                continue                      # corrupt granule: skip, keep scanning
            if lat.size == 0:
                continue
            m = (lat >= lat_lo) & (lat <= lat_hi) & (lon >= lon_lo) & (lon <= lon_hi)
            if keep_quality_zero:
                m &= (qf == 0)
            if not m.any():
                continue
            epoch, lat, lon, eng = epoch[m], lat[m], lon[m], eng[m]
            # exact per-target radius test
            d = haversine_km(lat[:, None], lon[:, None], tlat[None, :], tlon[None, :])
            hit = d <= trad[None, :]
            if not hit.any():
                continue
            fi, ti = np.nonzero(hit)
            out.append(pd.DataFrame({
                "key": tkey[ti],
                "epoch": epoch[fi],
                "flash_lat": lat[fi],
                "flash_lon": lon[fi],
                "flash_energy_j": eng[fi],
                "dist_km": d[fi, ti],
                "sat": sat,
            }))
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    df = (pd.concat(out, ignore_index=True) if out else
          pd.DataFrame(columns=["key", "epoch", "flash_lat", "flash_lon",
                                "flash_energy_j", "dist_km", "sat"]))
    return df, n_gran


# ---------------------------------------------------------- checkpointing ---

class Checkpoint:
    """Append-only JSONL of completed work-unit ids; survives restart."""

    def __init__(self, name: str):
        self.path = CKPT / f"{name}.jsonl"
        self.done = set()
        if self.path.exists():
            with self.path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self.done.add(json.loads(line)["unit"])
                    except Exception:
                        continue
        self._fh = self.path.open("a")

    def __contains__(self, unit):
        return unit in self.done

    def mark(self, unit, **info):
        self.done.add(unit)
        self._fh.write(json.dumps({"unit": unit, **info}) + "\n")
        self._fh.flush()

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass


def write_shard(name: str, unit: str, df: pd.DataFrame):
    """Persist one work unit's filtered output; shards are concatenated later."""
    d = SHARDS / name
    d.mkdir(parents=True, exist_ok=True)
    safe = unit.replace("/", "_").replace(":", "_")
    if len(df):
        df.to_parquet(d / f"{safe}.parquet", index=False)


def read_shards(name: str) -> pd.DataFrame:
    d = SHARDS / name
    files = sorted(d.glob("*.parquet")) if d.exists() else []
    if not files:
        return pd.DataFrame()
    return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


# --------------------------------------------------------------- manifest ---

def load_manifest(refresh: bool = False):
    import urllib.request
    p = CACHE / "manifest.json"
    if refresh or not p.exists():
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "flashpoint-catalog"})
        with urllib.request.urlopen(req, timeout=120) as r:
            p.write_bytes(r.read())
    return json.loads(p.read_text())


def node_table(manifest=None) -> pd.DataFrame:
    """Deployed W/V nodes carrying a microphone and/or camera."""
    manifest = manifest or load_manifest()
    rows = []
    for n in manifest:
        vsn = n.get("vsn") or ""
        if not vsn or vsn[0] not in "WV":
            continue
        caps, models = set(), set()
        for s in (n.get("sensors") or []):
            hw = s.get("hardware") or {}
            caps.update(hw.get("capabilities") or [])
            if hw.get("hw_model"):
                models.add(hw["hw_model"])
        mic = "Microphone" in caps
        cam = "Camera" in caps
        thermal = "Thermal Camera" in caps
        if not (mic or cam or thermal):
            continue
        lat, lon = n.get("gps_lat"), n.get("gps_lon")
        rows.append(dict(
            vsn=vsn, phase=n.get("phase"), project=n.get("project"),
            address=n.get("address"), name=n.get("name"),
            mic=mic, cam=cam, thermal=thermal,
            lat=float(lat) if lat not in (None, "") else np.nan,
            lon=float(lon) if lon not in (None, "") else np.nan,
            rain_gauge=("Precipitation" in caps),
            sensor_models=",".join(sorted(models)),
        ))
    return pd.DataFrame(rows).sort_values("vsn").reset_index(drop=True)


def log(msg: str):
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)
