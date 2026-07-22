"""Sage data access for the dashboard.

Three layers, matching how the fleet actually exposes data (see ../CLAUDE.md):
- metadata (node manifest snapshot, case presets): baked JSON in assets/
- listings + numeric telemetry: sage_data_client queries — public, no auth
- media files (FLAC/JPG): HTTP Basic auth (portal user + access token),
  mirrored into flashpoint/data/cache/ so nothing is downloaded twice

Keep queries narrow (vsn + task + short window) — broad ones time out.
"""
import json
import os
import pathlib
import re

import pandas as pd
import requests

DASH = pathlib.Path(__file__).resolve().parent.parent
ROOT = DASH.parent
ASSETS = DASH / "assets"
DATA = ROOT / "data"
CACHE = DATA / "cache"

STORAGE_PREFIX = "https://storage.sagecontinuum.org/api/v1/data/"


class SageAuthError(RuntimeError):
    """Media download rejected — credentials missing or wrong."""


def load_nodes():
    raw = json.loads((ASSETS / "nodes.json").read_text())
    return pd.DataFrame(raw["nodes"])


def load_cases():
    return json.loads((ASSETS / "cases.json").read_text())["cases"]


def env_credentials():
    """(user, token) from the environment / flashpoint/.env — never committed."""
    user = os.environ.get("SAGE_USER", "")
    token = os.environ.get("SAGE_TOKEN", "")
    envfile = ROOT / ".env"
    if (not user or not token) and envfile.exists():
        for line in envfile.read_text().splitlines():
            m = re.match(r"^\s*(SAGE_USER|SAGE_TOKEN)\s*=\s*['\"]?([^'\"#]+)", line)
            if m:
                if m.group(1) == "SAGE_USER" and not user:
                    user = m.group(2).strip()
                if m.group(1) == "SAGE_TOKEN" and not token:
                    token = m.group(2).strip()
    return user, token


def list_uploads(vsn, task_regex, start_iso, end_iso):
    """Upload listing (public) -> DataFrame[timestamp, task, url, filename]."""
    import sage_data_client

    df = sage_data_client.query(
        start=start_iso, end=end_iso,
        filter={"name": "upload", "vsn": vsn, "task": task_regex},
    )
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "task", "url", "filename"])
    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df["timestamp"], utc=True),
        "task": df["meta.task"],
        "url": df["value"],
    })
    out["filename"] = out["url"].str.rsplit("/", n=1).str[-1]
    return out.sort_values("timestamp").reset_index(drop=True)


def met_series(vsn, name_regex, start_iso, end_iso):
    """Numeric telemetry (public) -> DataFrame[timestamp, name, value]."""
    import sage_data_client

    df = sage_data_client.query(
        start=start_iso, end=end_iso, filter={"name": name_regex, "vsn": vsn},
    )
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "name", "value"])
    out = df[["timestamp", "name", "value"]].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna(subset=["value"]).sort_values("timestamp").reset_index(drop=True)


def temperature_at(vsn, when, half_window_min=30):
    """Mean env temperature (°C) around `when`, or None. Used to set the speed
    of sound for flash-to-bang ranging."""
    t = pd.Timestamp(when)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    start = (t - pd.Timedelta(minutes=half_window_min)).isoformat()
    end = (t + pd.Timedelta(minutes=half_window_min)).isoformat()
    try:
        df = met_series(vsn, "env.temperature", start, end)
    except Exception:
        return None
    return float(df["value"].mean()) if len(df) else None


def cache_path_for(url):
    """Mirror a storage URL under flashpoint/data/cache/."""
    rel = url[len(STORAGE_PREFIX):] if url.startswith(STORAGE_PREFIX) else re.sub(r"^https?://", "", url)
    rel = rel.strip("/").replace("..", "_")
    return CACHE / rel


def fetch_media(url, user="", token="", timeout=90, session=None):
    """Download one protected file into the cache (or reuse it). Returns Path.

    Raises SageAuthError on 401/403 so the UI can prompt for credentials.
    """
    dest = cache_path_for(url)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https media url: {url}")
    auth = (user, token) if (user and token) else None
    http = session or requests
    r = http.get(url, auth=auth, timeout=timeout,
                 headers={"User-Agent": "flashpoint-dashboard"})
    if r.status_code in (401, 403):
        raise SageAuthError(
            f"HTTP {r.status_code} for {url.rsplit('/', 1)[-1]} — set portal "
            "credentials (username + access token from "
            "portal.sagecontinuum.org/account/access)."
        )
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.rename(dest)
    return dest


def local_media_index():
    """Index media already on disk: fetch_case_media.py downloads under
    data/<vsn>/<task>/, plus everything in data/cache/. Filenames start with a
    nanosecond epoch (Sage storage convention) -> timestamp."""
    rows = []
    if not DATA.exists():
        return pd.DataFrame(columns=["timestamp", "vsn", "task", "path", "filename"])
    for p in DATA.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in (
                ".flac", ".wav", ".jpg", ".jpeg", ".png"):
            continue
        m = re.match(r"^(\d{16,19})", p.name)
        if not m:
            continue
        ts = pd.Timestamp(int(m.group(1)), unit="ns", tz="UTC")
        parts = p.relative_to(DATA).parts
        if parts[0] == "cache":
            # cache/<job-dir>/<plugin>/<node-id>/<file>; job dir names the task
            task = re.sub(r"-\d+$", "", parts[1]) if len(parts) > 1 else "?"
            vsn = ""
        else:
            vsn = parts[0] if len(parts) > 1 else ""
            task = parts[1] if len(parts) > 2 else "?"
        rows.append({"timestamp": ts, "vsn": vsn, "task": task,
                     "path": str(p), "filename": p.name})
    df = pd.DataFrame(rows, columns=["timestamp", "vsn", "task", "path", "filename"])
    return df.sort_values("timestamp").reset_index(drop=True) if len(df) else df
